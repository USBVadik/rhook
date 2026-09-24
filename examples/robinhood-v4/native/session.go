package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"math/big"
	"os"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/rawdb"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/core/vm"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/params"
	"github.com/ethereum/go-ethereum/rlp"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/ethereum/go-ethereum/triedb"
	"github.com/offchainlabs/nitro/arbos/arbosState"
)

type sessionInput struct {
	Parent *types.Header
	Blocks []struct {
		Header       *types.Header
		Transactions []hexutil.Bytes
	}
	PoolManager   common.Address
	SemanticSlots []common.Hash
}

func main() {
	inputPath := flag.String("input", "inputs/session.json", "sanitized ordered block inputs")
	witnessPath := flag.String("witness", "inputs/witness.json", "initial authenticated state only")
	branchName := flag.String("branch", "ACTUAL", "ACTUAL or COUNTERFACTUAL")
	mode := flag.String("bridge", "control", "original, control, off or on")
	count := flag.Int("count", 2, "bounded prefix length: 1, 2, 10 or 50")
	flag.Parse()
	a := &audit{reads: map[string]bool{}, nodes: map[string]bool{}}
	current := uint64(0)
	completed := 0
	encoder := json.NewEncoder(os.Stdout)
	defer func() {
		if p := recover(); p != nil {
			var detail any = fmt.Sprint(p)
			if f, ok := p.(failure); ok {
				detail = f
			}
			_ = encoder.Encode(map[string]any{"status": "EXECUTION_ERROR", "blockNumber": current, "completedBlocks": completed, "failure": detail, "reads": keys(a.reads), "nodeReads": keys(a.nodes)})
			os.Exit(2)
		}
	}()
	require(*count == 1 || *count == 2 || *count == 10 || *count == 50, "only declared incremental gates are supported")
	require(*mode == "original" || *mode == "control" || *mode == "off" || *mode == "on", "invalid execution mode")
	require(*branchName == "ACTUAL" || *branchName == "COUNTERFACTUAL", "unknown branch")
	require(*branchName == "ACTUAL" || *mode != "original", "counterfactual requires Message adapter")
	phase := &branchSession{branch: *branchName, records: []map[string]any{}, hashQueries: []map[string]any{}}
	manifestDigest := load("target-case-manifest.json", &phase.manifest)
	require(manifestDigest == "ccf28bf5b10e61b883339a698910863efb0ec7f0d8341dfbe410d5cb8942f7f0", "frozen Phase-3 case changed")
	var historical []*types.Header
	load("inputs/canonical-headers.json", &historical)
	historicalByNumber := map[uint64]*types.Header{}
	for _, h := range historical {
		historicalByNumber[h.Number.Uint64()] = h
	}
	var in sessionInput
	var w witness
	inputDigest := load(*inputPath, &in)
	phase.pool = in.PoolManager
	phase.slots = in.SemanticSlots
	witnessDigest := load(*witnessPath, &w)
	require(in.Parent != nil && len(in.Blocks) == 50, "complete pinned session inputs required")
	require(in.Parent.Number.Uint64() == 70397226 && in.Blocks[49].Header.Number.Uint64() == 70397276, "wrong case interval")
	require(w.ParentStateRoot == in.Parent.Root, "initial witness root binding failed")
	raw := &disk{rawdb.NewMemoryDatabase(), a}
	defer raw.Close()
	for h, node := range w.NodesByKeccak {
		require(crypto.Keccak256Hash(node) == h, "bad trie preimage hash")
		rawdb.WriteLegacyTrieNode(raw, h, node)
	}
	for h, code := range w.CodeByKeccak {
		require(crypto.Keccak256Hash(code) == h, "bad code preimage hash")
		rawdb.WriteCode(raw, h, code)
	}
	tdb := triedb.NewDatabase(raw, triedb.HashDefaults)
	defer tdb.Close()
	db := &strictDB{state.NewDatabase(tdb, nil), a}
	s, err := state.New(w.ParentStateRoot, db)
	must(err)
	arb, err := arbosState.OpenSystemArbosState(s, nil, true)
	must(err)
	cfgBytes, err := arb.ChainConfig()
	must(err)
	require(len(cfgBytes) > 0, "missing authenticated configuration")
	var cfg params.ChainConfig
	must(json.Unmarshal(cfgBytes, &cfg))
	require(cfg.ChainID.Cmp(big.NewInt(4663)) == 0, "wrong chain")
	version := arb.ArbOSVersion()
	engine := &captureEngine{}
	chain := &context{config: &cfg, parent: in.Parent, engine: engine, headers: map[common.Hash]*types.Header{in.Parent.Hash(): in.Parent}}
	if *branchName == "COUNTERFACTUAL" {
		for _, h := range historical {
			chain.headers[h.Hash()] = h
		}
	}
	currentRoot := w.ParentStateRoot
	nativeMode := *mode
	if nativeMode == "original" {
		nativeMode = "control"
	}
	bridge := newBridge(nativeMode, s)
	bridge.phase = phase
	initialHistory := l1History(s)
	initialSemantic := make([]common.Hash, len(in.SemanticSlots))
	for i, k := range in.SemanticSlots {
		initialSemantic[i] = s.GetState(in.PoolManager, k)
	}
	must(s.Error())
	for i := 0; i < *count; i++ {
		item := in.Blocks[i]
		h := item.Header
		current = h.Number.Uint64()
		require(h.Root == (common.Hash{}) && h.ReceiptHash == (common.Hash{}) && h.TxHash == (common.Hash{}) && h.GasUsed == 0 && h.Bloom == (types.Bloom{}), "expected output fields reached execution")
		require(h.Number.Uint64() == chain.parent.Number.Uint64()+1, "noncontiguous block number")
		require(h.ParentHash == chain.parent.Hash(), "computed previous block hash differs from fixed next parent identity")
		if *branchName == "ACTUAL" {
			require(currentRoot == chain.parent.Root, "computed state continuity broken")
		}
		require(rootOf(s) == currentRoot, "starting state does not equal preceding local root")
		phase.records = []map[string]any{}
		phase.hashQueries = []map[string]any{}
		txs := make([]*types.Transaction, len(item.Transactions))
		hashes := make([]common.Hash, len(txs))
		for j, b := range item.Transactions {
			txs[j] = new(types.Transaction)
			encoded := []byte(b)
			if len(b) > 0 && b[0] <= 0x7f {
				encoded, err = rlp.EncodeToBytes([]byte(b))
				must(err)
			}
			must(rlp.DecodeBytes(encoded, txs[j]))
			hashes[j] = txs[j].Hash()
		}
		block := types.NewBlockWithHeader(h).WithBody(types.Body{Transactions: txs})
		engine.finalized = nil
		bridge.s = s
		bridge.boundaries = []map[string]any{}
		bridge.initialize(block)
		var result *core.ProcessResult
		var executions []map[string]any
		if *mode == "original" {
			result, err = core.NewStateProcessor(chain).Process(block, s, vm.Config{})
		} else {
			result, executions, err = processNativeBlock(chain, block, s, bridge)
		}
		must(err)
		must(s.Error())
		require(engine.finalized != nil, "native finalization missing")
		semantic := make([]common.Hash, len(in.SemanticSlots))
		for j, k := range in.SemanticSlots {
			semantic[j] = s.GetState(in.PoolManager, k)
		}
		must(s.Error())
		finalHistory := l1History(s)
		computedRoot, err := s.Commit(current, true, false)
		must(err)
		require(computedRoot == engine.finalized.Root, "finalize/commit mismatch")
		finalHeader := types.CopyHeader(engine.finalized)
		finalHeader.GasUsed = result.GasUsed
		produced := types.NewBlock(finalHeader, &types.Body{Transactions: txs}, result.Receipts, trie.NewStackTrie(nil))
		info := types.DeserializeHeaderExtraInformation(produced.Header())
		receiptHashContext := produced.Hash()
		receiptTxs := txs
		if *branchName == "COUNTERFACTUAL" {
			receiptHashContext = historicalByNumber[current].Hash()
			receiptTxs = nil
			for _, e := range executions {
				receiptTxs = append(receiptTxs, txs[e["index"].(int)])
			}
		}
		must(result.Receipts.DeriveFields(&cfg, receiptHashContext, current, produced.Time(), produced.BaseFee(), nil, receiptTxs, info.CollectTips))
		if *branchName == "COUNTERFACTUAL" {
			for j, r := range result.Receipts {
				idx := executions[j]["index"].(int)
				r.TransactionIndex = uint(idx)
				for _, l := range r.Logs {
					l.TxIndex = uint(idx)
				}
			}
		}
		fees := make([]map[string]any, len(result.Receipts))
		for j, r := range result.Receipts {
			fees[j] = map[string]any{"index": j, "gasUsedForL1": hexutil.Uint64(r.GasUsedForL1), "effectiveGasPrice": (*hexutil.Big)(r.EffectiveGasPrice), "executionFee": new(big.Int).Mul(new(big.Int).SetUint64(r.GasUsed), r.EffectiveGasPrice).String()}
		}
		var outputHash any = produced.Hash()
		var outputHeader any = produced.Header()
		if *branchName == "COUNTERFACTUAL" {
			outputHash = nil
			outputHeader = nil
		}
		must(encoder.Encode(map[string]any{"phase4": map[string]any{"branch": *branchName, "records": phase.records, "hashQueries": phase.hashQueries, "historicalL1Context": finalHistory, "canonicalContextBlockHash": historicalByNumber[current].Hash(), "interventionCount": phase.interventions, "outputIsConsensusBlock": *branchName == "ACTUAL"}, "status": "BLOCK_EXECUTED_UNCOMPARED", "blockNumber": current, "sessionIndex": i, "startStateRoot": currentRoot, "finalStateRoot": computedRoot, "computedBlockHash": outputHash, "computedHeader": outputHeader, "receiptsRoot": produced.ReceiptHash(), "gasUsed": hexutil.Uint64(result.GasUsed), "transactionHashes": hashes, "receipts": result.Receipts, "fees": fees, "executions": executions, "lifecycle": bridge.boundaries, "semanticValues": semantic}))
		// StateDB.Commit invalidates its trie handles. The replacement StateDB opens
		// ONLY our just-computed root on the SAME updated local database. No canonical
		// post-state, RPC response, witness reload or external reset occurs here.
		currentRoot = computedRoot
		chain.parent = produced.Header()
		if *branchName == "ACTUAL" {
			chain.headers[produced.Hash()] = produced.Header()
		} else {
			chain.parent = historicalByNumber[current]
		}
		completed++
		if i+1 < *count {
			s, err = state.New(currentRoot, db)
			must(err)
		}
	}
	if *branchName == "COUNTERFACTUAL" {
		require(phase.interventions == 1, "intervention count must equal one")
	}
	must(encoder.Encode(map[string]any{"phase4": map[string]any{"branch": *branchName, "interventionCount": phase.interventions, "initialHistoricalL1Context": initialHistory}, "status": "SESSION_EXECUTED_UNCOMPARED", "count": completed, "inputSha256": inputDigest, "witnessSha256": witnessDigest, "initialRoot": w.ParentStateRoot, "finalRoot": currentRoot, "initialSemanticValues": initialSemantic, "arbosVersion": version, "effectiveChainConfig": json.RawMessage(cfgBytes), "initialStateLoads": 1, "computedStateReopens": completed - 1, "canonicalStateResets": 0, "reads": keys(a.reads), "nodeReads": keys(a.nodes)}))
}
