package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"reflect"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/tracing"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/offchainlabs/nitro/arbos/arbosState"
)

const targetHash = "0x5f82e30b8ad8ae0bd4e5b60cbde55a47702d2d4b90234ad0db58bd9b89a458db"
const commitmentDomain = "rhook/local-phase4/intervention/1\n"

type caseManifest struct {
	X struct {
		Block uint64
		Index int
		Hash  common.Hash
		Input hexutil.Bytes
	}
	ProposedXPrime struct {
		Kind     string
		Calldata hexutil.Bytes
	}
}
type branchSession struct {
	pool            common.Address
	slots           []common.Hash
	branch          string
	manifest        caseManifest
	interventions   int
	records         []map[string]any
	hashQueries     []map[string]any
	current         map[string]any
	enters, opcodes int
	calls           []map[string]any
	pendingHash     map[string]any
	pendingDepth    int
}

func rootOf(s *state.StateDB) common.Hash {
	c := s.Copy()
	r := c.IntermediateRoot(true)
	must(c.Error())
	must(s.Error())
	return r
}
func digestBytes(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func jsonObject(v any) map[string]any {
	b, e := json.Marshal(v)
	must(e)
	var out map[string]any
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber()
	must(d.Decode(&out))
	return out
}
func messageRecord(msg *core.Message) map[string]any {
	// Marshal every exported Message field; include explicit identities for the
	// opaque native replay context and original signed transaction bytes.
	out := jsonObject(msg)
	raw, e := msg.Tx.MarshalBinary()
	must(e)
	out["TxRunContextPolicy"] = "core.NewMessageReplayContext()"
	out["originalSignedEnvelopeSha256"] = digestBytes(raw)
	out["originalSignedEnvelopeKeccak256"] = crypto.Keccak256Hash(raw)
	out["Data"] = hexutil.Bytes(msg.Data)
	return out
}
func (p *branchSession) prepare(msg *core.Message, block uint64, index int) {
	p.enters = 0
	p.opcodes = 0
	p.calls = []map[string]any{}
	p.pendingHash = nil
	p.current = map[string]any{"block": block, "index": index, "canonicalTransactionHash": msg.Tx.Hash(), "inputCalldataSha256": digestBytes(msg.Data)}
	if block != 70397227 || index != 3 {
		return
	}
	require(msg.Tx.Hash() == common.HexToHash(targetHash), "frozen target mismatch")
	require(reflect.DeepEqual(msg.Data, []byte(p.manifest.X.Input)), "original calldata changed")
	before := messageRecord(msg)
	if p.branch == "COUNTERFACTUAL" {
		msg.Data = append([]byte(nil), p.manifest.ProposedXPrime.Calldata...)
		p.interventions++
	}
	after := messageRecord(msg)
	p.current["targetMessageBefore"] = before
	p.current["targetMessageAfter"] = after
	if p.branch == "COUNTERFACTUAL" {
		beforePreserved := messageRecord(msg)
		beforePreserved["Data"] = before["Data"]
		require(reflect.DeepEqual(beforePreserved, before), "intervention changed a non-calldata Message field")
		body := map[string]any{"kind": p.manifest.ProposedXPrime.Kind, "canonicalEnvelopeIdentity": map[string]any{"blockNumber": block, "transactionIndex": index, "transactionHash": msg.Tx.Hash()}, "originalCalldataSha256": digestBytes(p.manifest.X.Input), "replacementCalldataSha256": digestBytes(msg.Data), "messageBefore": before, "messageAfter": after, "senderPolicy": "Native TransactionToMessage/types.Sender from original signed envelope; only Message.Data replaced; not an alternatively signed transaction", "posterCostPolicy": "Native PosterDataCost retains original Message.Tx bytes; intrinsic gas and EVM use replaced Message.Data; all accounting runs natively"}
		raw, e := json.Marshal(body)
		must(e)
		p.current["intervention"] = map[string]any{"body": body, "bodyJson": string(raw), "domain": commitmentDomain, "commitmentSha256": digestBytes(append([]byte(commitmentDomain), raw...))}
	}
	p.current["inputCalldataSha256"] = digestBytes(msg.Data)
}
func (p *branchSession) hooks() *tracing.Hooks {
	return &tracing.Hooks{
		OnEnter: func(depth int, typ byte, from, to common.Address, input []byte, gas uint64, value *big.Int) {
			p.enters++
			p.calls = append(p.calls, map[string]any{"depth": depth, "type": typ, "from": from, "to": to, "inputSha256": digestBytes(input), "gas": gas, "value": value.String()})
		},
		OnOpcode: func(pc uint64, op byte, gas, cost uint64, scope tracing.OpContext, data []byte, depth int, err error) {
			p.opcodes++
			stack := scope.StackData()
			if p.pendingHash != nil {
				require(depth == p.pendingDepth && len(stack) > 0, "cannot observe BLOCKHASH result")
				p.pendingHash["value"] = common.Hash(stack[len(stack)-1].Bytes32())
				p.pendingHash["completion"] = "native opcode stack result"
				p.hashQueries = append(p.hashQueries, p.pendingHash)
				p.pendingHash = nil
			}
			if op == 0x40 {
				require(len(stack) > 0, "BLOCKHASH stack unavailable")
				p.pendingDepth = depth
				p.pendingHash = map[string]any{"kind": "EVM_BLOCKHASH_ARBITRUM_L1", "block": p.current["block"], "index": p.current["index"], "query256": stack[len(stack)-1].String(), "pc": pc}
			}
		},
		OnBlockHashRead: func(number uint64, hash common.Hash) {
			p.hashQueries = append(p.hashQueries, map[string]any{"kind": "NATIVE_L1_BLOCKHASH_READ", "block": p.current["block"], "index": p.current["index"], "query": number, "value": hash})
		},
	}
}
func (p *branchSession) finish(pre, post common.Hash, gasBefore, gasAfter uint64, status string) {
	require(p.pendingHash == nil, "unresolved BLOCKHASH observation")
	p.current["preStateRoot"] = pre
	p.current["postStateRoot"] = post
	p.current["gasPoolBefore"] = gasBefore
	p.current["gasPoolAfter"] = gasAfter
	p.current["lifecycle"] = status
	p.current["callEntries"] = p.enters
	p.current["opcodeCount"] = p.opcodes
	p.current["calls"] = p.calls
	p.records = append(p.records, p.current)
}
func validationClass(err error) string {
	// Only native preCheck errors before buyGas has debited balance/gas pool.
	for _, v := range []struct {
		e    error
		name string
	}{{core.ErrNonceTooLow, "NATIVE_NONCE_TOO_LOW"}, {core.ErrNonceTooHigh, "NATIVE_NONCE_TOO_HIGH"}, {core.ErrNonceMax, "NATIVE_NONCE_MAX"}, {core.ErrSenderNoEOA, "NATIVE_SENDER_NOT_EOA"}, {core.ErrFeeCapVeryHigh, "NATIVE_FEE_CAP_OVERFLOW"}, {core.ErrTipVeryHigh, "NATIVE_TIP_OVERFLOW"}, {core.ErrTipAboveFeeCap, "NATIVE_TIP_ABOVE_FEE_CAP"}, {core.ErrFeeCapTooLow, "NATIVE_FEE_CAP_BELOW_BASE_FEE"}, {core.ErrInsufficientFunds, "NATIVE_INSUFFICIENT_GAS_FUNDS"}, {core.ErrGasLimitReached, "NATIVE_BLOCK_GAS_EXHAUSTED"}} {
		if errors.Is(err, v.e) {
			return v.name
		}
	}
	return ""
}
func qualifyInvalidation(err error, tx *types.Transaction, pre, post common.Hash, gasBefore, gasAfter, usedBefore, usedAfter uint64, enters, opcodes int) string {
	label := validationClass(err)
	require(tx.Type() == 0 || tx.Type() == 1 || tx.Type() == 2 || tx.Type() == 4, "invalidation unsupported for native/system tx")
	require(label != "", fmt.Sprintf("unclassified native error: %v", err))
	require(pre == post && gasBefore == gasAfter && usedBefore == usedAfter && enters == 0 && opcodes == 0, "native failure did not preserve pre-execution state/accounting")
	return label
}
func l1History(s *state.StateDB) map[string]any {
	a, e := arbosState.OpenSystemArbosState(s, nil, true)
	must(e)
	n, e := a.Blockhashes().L1BlockNumber()
	must(e)
	hashes := map[string]common.Hash{}
	var start uint64
	if n > 256 {
		start = n - 256
	}
	for k := start; k < n; k++ {
		h, e := a.Blockhashes().BlockHash(k)
		must(e)
		hashes[fmt.Sprint(k)] = h
	}
	must(s.Error())
	return map[string]any{"number": n, "hashes": hashes}
}
