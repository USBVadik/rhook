// Copyright 2015 The go-ethereum Authors
// This file is part of the go-ethereum library.
//
// The go-ethereum library is free software: you can redistribute it and/or modify
// it under the terms of the GNU Lesser General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// The go-ethereum library is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU Lesser General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public License
// along with the go-ethereum library. If not, see <http://www.gnu.org/licenses/>.

// Bounded block orchestration follows geth core/state_processor.go at
// dff2aadcd2e75e33923b13acce6468d847477e79 (LGPL-3.0-or-later).
// Execution, receipts, ArbOS accounting and finalization remain upstream calls.
package main

import (
	"encoding/json"
	"fmt"
	"math/big"
	"os"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/core/vm"
)

type bridge struct {
	mode       string
	s          *state.StateDB
	input      *json.Decoder
	output     *json.Encoder
	boundaries []map[string]any
	sequence   int
	phase      *branchSession
}

func newBridge(mode string, s *state.StateDB) *bridge {
	require(mode == "control" || mode == "off" || mode == "on", "invalid bridge mode")
	return &bridge{mode: mode, s: s, input: json.NewDecoder(os.Stdin), output: json.NewEncoder(os.Stdout), boundaries: []map[string]any{}}
}

func (b *bridge) initialize(block *types.Block) {
	if b.mode == "control" {
		return
	}
	transactions := make([]map[string]any, len(block.Transactions()))
	for i, tx := range block.Transactions() {
		transactions[i] = map[string]any{"hash": tx.Hash(), "gasLimit": hexutil.Uint64(tx.Gas()), "type": hexutil.Uint64(tx.Type())}
	}
	must(b.output.Encode(map[string]any{"event": "ready", "mode": b.mode, "blockNumber": block.Number().String(), "transactions": transactions}))
	var command struct{ Command string }
	must(b.input.Decode(&command))
	require(command.Command == "start", "host must explicitly start execution")
}

// The execution StateDB is paused until the host listener acknowledges this
// boundary. Root requests finalize ONLY a copy, never the execution StateDB.
func (b *bridge) boundary(kind string, index int, payload any) {
	if b.mode != "on" {
		return
	}
	b.sequence++
	record := map[string]any{"kind": kind, "index": index, "sequence": b.sequence, "rootRequests": 0}
	must(b.output.Encode(map[string]any{"event": kind, "index": index, "sequence": b.sequence, "payload": payload}))
	for {
		var command struct {
			Command  string
			Sequence int
		}
		must(b.input.Decode(&command))
		require(command.Sequence == b.sequence, "stale boundary acknowledgement")
		switch command.Command {
		case "root":
			copy := b.s.Copy()
			root := copy.IntermediateRoot(true)
			must(copy.Error())
			must(b.s.Error())
			record["rootRequests"] = record["rootRequests"].(int) + 1
			record["stateRoot"] = root
			must(b.output.Encode(map[string]any{"event": "root", "sequence": b.sequence, "stateRoot": root}))
		case "continue":
			b.boundaries = append(b.boundaries, record)
			return
		default:
			panic("unknown bridge command")
		}
	}
}

func errorText(err error) any {
	if err == nil {
		return nil
	}
	return err.Error()
}

func processNativeBlock(chain *context, block *types.Block, s *state.StateDB, bridge *bridge) (*core.ProcessResult, []map[string]any, error) {
	header, config := block.Header(), chain.Config()
	// This is a case adapter, not a replacement generic StateProcessor. Refuse
	// environments whose pre/post system calls are not included in this loop.
	require(config.IsArbitrum() && header.Number.Uint64() >= 70397227 && header.Number.Uint64() <= 70397276, "adapter only qualifies the pinned Nitro interval")
	require(block.BeaconRoot() == nil && len(block.Uncles()) == 0 && len(block.Withdrawals()) == 0, "unsupported block system inputs")
	require(!(config.DAOForkSupport && config.DAOForkBlock != nil && config.DAOForkBlock.Cmp(header.Number) == 0), "unsupported DAO transition")
	context := core.NewEVMBlockContext(header, chain, nil)
	phase := bridge.phase
	nativeHash := context.GetHash
	context.GetHash = func(n uint64) common.Hash {
		h := nativeHash(n)
		phase.hashQueries = append(phase.hashQueries, map[string]any{"kind": "NATIVE_L2_CONTEXT_GETHASH", "block": header.Number.Uint64(), "query": n, "value": h})
		return h
	}
	evm := vm.NewEVM(context, s, config, vm.Config{Tracer: phase.hooks()})
	signer := types.MakeSigner(config, header.Number, header.Time, context.ArbOSVersion)
	runCtx := core.NewMessageReplayContext()
	gp := new(core.GasPool).AddGas(block.GasLimit())
	var usedGas uint64
	var receipts types.Receipts
	var allLogs []*types.Log
	executions := make([]map[string]any, 0, len(block.Transactions()))
	for i, tx := range block.Transactions() {
		msg, err := core.TransactionToMessage(tx, signer, header.BaseFee, runCtx)
		if err != nil {
			return nil, nil, fmt.Errorf("message %d: %w", i, err)
		}
		phase.prepare(msg, header.Number.Uint64(), i)
		if header.Number.Uint64() == 70397227 && i == 3 {
			values := []common.Hash{}
			for _, slot := range phase.slots {
				values = append(values, s.GetState(phase.pool, slot))
			}
			phase.current["semanticBefore"] = values
			phase.current["senderNonceBefore"] = s.GetNonce(msg.From)
		}
		pre := rootOf(s)
		gasBefore := gp.Gas()
		usedBefore := usedGas
		s.SetTxContext(tx.Hash(), i)
		bridge.boundary("beforeTx", i, map[string]any{"hash": tx.Hash(), "gasLimit": hexutil.Uint64(tx.Gas()), "type": hexutil.Uint64(tx.Type())})
		receipt, result, err := core.ApplyTransactionWithEVM(msg, gp, s, header.Number, block.Hash(), context.Time, tx, &usedGas, evm, nil)
		if err != nil {
			if phase.branch != "COUNTERFACTUAL" {
				return nil, nil, fmt.Errorf("transaction %d: %w", i, err)
			}
			post := rootOf(s)
			classification := qualifyInvalidation(err, tx, pre, post, gasBefore, gp.Gas(), usedBefore, usedGas, phase.enters, phase.opcodes)
			phase.current["invalidation"] = map[string]any{"classification": classification, "nativeError": err.Error(), "allowedNativeClass": true, "beforeEVM": true, "stateUnchanged": true, "gasPoolUnchanged": true}
			phase.finish(pre, post, gasBefore, gp.Gas(), "PRE_EXECUTION_INVALIDATED")
			bridge.boundary("invalidatedTx", i, phase.current)
			continue
		}
		must(s.Error())
		// Derive receipt metadata on a copy using the engine's active fee policy.
		// The provisional block hash is replaced after finalization by the
		// original D1 DeriveFields path; it is never supplied as expected output.
		liveReceipt := *receipt
		liveReceipt.Logs = make([]*types.Log, len(receipt.Logs))
		for j, entry := range receipt.Logs {
			copy := *entry
			liveReceipt.Logs[j] = &copy
		}
		liveReceipt.DeriveFields(signer, types.DeriveReceiptContext{BlockHash: block.Hash(), BlockNumber: header.Number.Uint64(), BlockTime: header.Time, BaseFee: header.BaseFee, GasUsed: receipt.GasUsed, LogIndex: uint(len(allLogs)), Tx: tx, TxIndex: uint(i), CollectTips: evm.ProcessingHook.CollectTips()})
		fee := new(big.Int).Mul(new(big.Int).SetUint64(receipt.GasUsed), liveReceipt.EffectiveGasPrice)
		scheduled := make([]string, len(result.ScheduledTxes))
		for j, scheduledTx := range result.ScheduledTxes {
			scheduled[j] = scheduledTx.Hash().Hex()
		}
		execution := map[string]any{
			"index": i, "transactionHash": tx.Hash(), "type": hexutil.Uint64(tx.Type()), "gasLimit": hexutil.Uint64(tx.Gas()),
			"usedGas": hexutil.Uint64(result.UsedGas), "maxUsedGas": hexutil.Uint64(result.MaxUsedGas),
			"executionError": errorText(result.Err), "returnData": hexutil.Bytes(result.ReturnData),
			"returnBytes": hexutil.Bytes(result.Return()), "revertBytes": hexutil.Bytes(result.Revert()),
			"returnDataWasNil": result.ReturnData == nil, "returnWasNil": result.Return() == nil, "revertWasNil": result.Revert() == nil,
			"scheduledTransactionHashes": scheduled, "topLevelDeployed": result.TopLevelDeployed,
			"usedMultiGas": result.UsedMultiGas, "feePaid": fee.String(), "collectTips": evm.ProcessingHook.CollectTips(),
		}
		status := "SUCCESS"
		if result.Err != nil {
			status = "REVERT"
		}
		phase.finish(pre, rootOf(s), gasBefore, gp.Gas(), status)
		phase.current["execution"] = execution
		if header.Number.Uint64() == 70397227 && i == 3 {
			values := []common.Hash{}
			for _, slot := range phase.slots {
				values = append(values, s.GetState(phase.pool, slot))
			}
			phase.current["semanticAfter"] = values
			phase.current["senderNonceAfter"] = s.GetNonce(msg.From)
		}
		executions = append(executions, execution)
		bridge.boundary("afterTx", i, map[string]any{"execution": execution, "receipt": &liveReceipt})
		receipts = append(receipts, receipt)
		allLogs = append(allLogs, receipt.Logs...)
	}
	bridge.boundary("beforeBlockFinalization", len(block.Transactions()), nil)
	chain.Engine().Finalize(chain, header, s, block.Body())
	bridge.boundary("afterBlockFinalization", len(block.Transactions()), nil)
	return &core.ProcessResult{Receipts: receipts, Logs: allLogs, GasUsed: usedGas}, executions, nil
}
