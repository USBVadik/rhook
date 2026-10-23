package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"math/big"
	"time"
)

type EventCapture struct {
	Package      json.RawMessage          `json:"-"`
	Inventory    *Inventory               `json:"inventory,omitempty"`
	Intervention *LPIntervention          `json:"intervention,omitempty"`
	Plan         *EconomicObservationPlan `json:"plan,omitempty"`
	Error        string                   `json:"error,omitempty"`
}

// State-first acquisition, independent of scientific eligibility. The original
// package is durable even if a later proof/admission/precondition fails.
func CaptureEventPackage(ctx context.Context, rpc *RPCSource, l *types.Log, write WriteEvidence) (out *EventCapture, err error) {
	out = &EventCapture{}
	var p BlockPackage
	defer func() {
		raw, e := json.Marshal(p)
		if e == nil {
			out.Package = raw
			if e = write("BLOCK_PACKAGE.json", raw); e != nil && err == nil {
				err = e
			}
		}
		if err != nil {
			out.Error = err.Error()
		}
		if e = EmitJSON(write, "CAPTURE_META.json", out); e != nil && err == nil {
			err = e
		}
	}()
	if !eventTarget(l) || l.Removed {
		return out, errors.New("PROVISIONAL_EVENT_IDENTITY")
	}
	var block, parent json.RawMessage
	if err = rpc.call(ctx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(l.BlockNumber), true}, &block); err != nil {
		return
	}
	p.Block = block
	h, e := decodeHeader(block)
	if e != nil || h.Hash() != l.BlockHash || h.Number.Uint64() != l.BlockNumber || l.BlockNumber == 0 {
		return out, errors.New("PROVISIONAL_BLOCK_HASH")
	}
	if err = rpc.call(ctx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(l.BlockNumber - 1), false}, &parent); err != nil {
		return
	}
	p.Parent = parent
	ph, e := decodeHeader(parent)
	if e != nil || ph.Hash() != h.ParentHash || ph.Number.Uint64()+1 != h.Number.Uint64() {
		return out, errors.New("PROVISIONAL_PARENT_LINK")
	}
	p.Checkpoint = Checkpoint{4663, ph.Number.Uint64(), ph.Hash(), ph.Root}
	if err = EmitJSON(write, "CHECKPOINT_PIN.json", p.Checkpoint); err != nil {
		return
	}
	initial := func(a common.Address, slots []common.Hash) (*RPCProof, error) {
		v, e := rpc.GetProof(ctx, p.Checkpoint, a, slots)
		if e != nil {
			return nil, e
		}
		if _, e = verifyProof(ph.Root, a, slots, v); e != nil {
			return nil, e
		}
		p.Proofs = append(p.Proofs, CapturedProof{a, slots, v})
		return v, nil
	}
	if _, err = initial(hookrRules, []common.Hash{plus(hookrConfigSlot, -1), hookrConfigSlot}); err != nil {
		return
	}
	var proof *RPCProof
	if proof, err = initial(ArbOSAccount, []common.Hash{ArbOSVersionSlot, ArbOSConfigLengthSlot, ArbOSPerBlockGasLimitSlot}); err != nil {
		return
	}
	values := map[common.Hash]*big.Int{}
	for _, x := range proof.StorageProof {
		values[x.Key] = x.Value.ToInt()
	}
	if values[ArbOSVersionSlot].Cmp(big.NewInt(61)) != 0 || !values[ArbOSConfigLengthSlot].IsUint64() {
		return out, errors.New("ARBOS_CONTEXT_DOMAIN")
	}
	length := values[ArbOSConfigLengthSlot].Uint64()
	if length == 0 || length > 1536 {
		return out, errors.New("CONFIG_LENGTH_DOMAIN")
	}
	var witness struct {
		State, Codes []hexutil.Bytes
		Headers      []json.RawMessage
	}
	if err = rpc.call(ctx, "debug_executionWitness", []any{hexutil.EncodeUint64(l.BlockNumber)}, &witness); err != nil {
		return
	}
	if len(witness.Headers) == 0 || len(witness.Headers) > 256 || len(witness.State) > 100000 || len(witness.Codes) > 10000 {
		return out, errors.New("WITNESS_PARENT_HEADER_MISSING")
	}
	for i, raw := range witness.Headers {
		wh, e := decodeHeader(raw)
		if e != nil {
			return out, e
		}
		if i == 0 && wh.Hash() != ph.Hash() {
			return out, errors.New("WITNESS_ORIGINAL_PARENT")
		}
		if i > 0 {
			prev, _ := decodeHeader(witness.Headers[i-1])
			if prev.ParentHash != wh.Hash() || prev.Number.Uint64() != wh.Number.Uint64()+1 {
				return out, errors.New("WITNESS_HISTORY_LINK")
			}
		}
	}
	p.State, p.Codes = witness.State, witness.Codes
	if err = EmitJSON(write, "ORIGINAL_WITNESS.json", witness); err != nil {
		return
	}
	slots := []common.Hash{}
	for i := uint64(1); i <= (length+31)/32; i++ {
		s := ArbOSConfigLengthSlot
		s[31] = byte(i)
		slots = append(slots, s)
	}
	if _, err = initial(ArbOSAccount, slots); err != nil {
		return
	}
	// Existing narrowly scoped Hookr dependencies and immutable LP semantics.
	dummy := &SelectedHookrTrade{Hash: l.TxHash, Ordinal: int(l.TxIndex)}
	if out.Intervention, out.Plan, err = captureHookrDependencies(ctx, rpc, &p, dummy); err != nil {
		return
	}
	var body struct {
		Transactions []struct {
			Hash common.Hash `json:"hash"`
		}
	}
	if json.Unmarshal(block, &body) != nil || len(body.Transactions) > 8 {
		return out, errors.New("RAW_INPUT_CAPTURE_DOMAIN")
	}
	for _, tx := range body.Transactions {
		var raw hexutil.Bytes
		if err = rpc.call(ctx, "eth_getRawTransactionByHash", []any{tx.Hash}, &raw); err != nil {
			return
		}
		p.Raw = append(p.Raw, raw)
	}
	var again json.RawMessage
	if err = rpc.call(ctx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(l.BlockNumber), false}, &again); err != nil {
		return
	}
	ah, e := decodeHeader(again)
	if e != nil || ah.Hash() != h.Hash() {
		return out, errors.New("PROVISIONAL_REORG")
	}
	raw, e := json.Marshal(p)
	if e != nil {
		return out, e
	}
	admitted, e := NewLiveCalibration(raw, nil, time.Now().Add(time.Minute))
	if e != nil {
		return out, e
	}
	defer admitted.Bridge.Close()
	out.Inventory = admitted.Inventory
	return out, nil
}

// Ready-to-run native pair, never called by an offline package compatibility
// test. Both worlds start at the same saved package; no ACTUAL state injection.
func RunPreparedEventPair(ctx context.Context, rpc *RPCSource, write WriteEvidence, emit EmitEvent, cap *EventCapture, subject *SelectedHookrTrade) (out *ProspectiveResult) {
	return runPreparedEventPairWith(ctx, rpc, write, emit, cap, subject, RunHookrObserved, completeHookrPair)
}
func runPreparedEventPairWith(ctx context.Context, rpc *RPCSource, write WriteEvidence, emit EmitEvent, cap *EventCapture, subject *SelectedHookrTrade, actual func(*Candidate, *Bridge, *LPIntervention, EconomicObservationPlan) (*CalibrationResult, error), complete func(context.Context, *RPCSource, WriteEvidence, EmitEvent, []byte, *ProspectiveResult) (string, error)) (out *ProspectiveResult) {
	out = &ProspectiveResult{Terminal: "RUNTIME_OR_RESOURCE_STOP", Hookr: &HookrPair{Subject: subject, Intervention: cap.Intervention, HeterogeneousAgreement: "NOT_EVALUATED", EconomicAssurance: "UNRESOLVED"}}
	fail := func(e error) { out.Cause = e.Error() }
	plan := *cap.Plan
	plan.Subject = subject.Hash
	plan.NativeOrdinal = subject.Ordinal
	plan.Accounts = []common.Address{hookrRules, hookrRoot, hookrManager, hookrRouter, subject.Payer, subject.Recipient}
	out.Hookr.Plan = &plan
	live, e := NewLiveCalibration(cap.Package, rpc, minTime(time.Now().Add(120*time.Second), rpc.deadline))
	if e != nil {
		fail(e)
		return
	}
	defer live.Bridge.Close()
	out.Inventory = live.Inventory
	out.InputPackageSHA = ByteDigest(cap.Package)
	out.InitialWitnessCommitment, _ = live.Bridge.WitnessSnapshot()
	defer func() {
		pin, w := live.Bridge.WitnessSnapshot()
		out.FinalWitnessCommitment = pin
		out.MissingStateAttempts = live.Attempts()
		if e := write("ACTUAL_FINAL_WITNESS.json", w); e != nil {
			out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
			out.Cause = e.Error()
		}
	}()
	if cap.Inventory == nil || live.Inventory.InputCommitment != cap.Inventory.InputCommitment || out.InitialWitnessCommitment != cap.Inventory.WitnessCommitment {
		fail(errors.New("SAVED_PACKAGE_IDENTITY"))
		return
	}
	if e = EmitJSON(write, "INPUT_PRECOMMIT.json", map[string]any{"inventory": out.Inventory, "packageSha256": out.InputPackageSHA, "intervention": cap.Intervention, "observationPlan": plan}); e != nil {
		fail(e)
		return
	}
	if e = emit("NATIVE_REPLAY_ENTERED", out.Inventory); e != nil {
		fail(e)
		return
	}
	out.NativeAttempts = 1
	out.Native, e = actual(live.Candidate, live.Bridge, nil, plan)
	out.Terminal, _ = ClassifyCalibrationError(e)
	if live.Bridge.observation != nil {
		if save := EmitJSON(write, "ACTUAL_OBSERVATION.json", live.Bridge.observation); save != nil {
			out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
			fail(save)
			return
		}
	}
	if e != nil {
		fail(e)
		return
	}
	if out.Native == nil || !out.Native.Matched {
		out.Terminal = "CANONICAL_EXECUTION_MISMATCH"
		fail(errors.New("ACTUAL_MATCH_REQUIRED"))
		return
	}
	if e = EmitJSON(write, "ACTUAL_RESULT.json", out.Native); e != nil {
		out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
		fail(e)
		return
	}
	out.Terminal, e = complete(ctx, rpc, write, emit, cap.Package, out)
	if e != nil {
		fail(e)
	}
	return
}
func eventCaptureDir(hash common.Hash) string { return fmt.Sprintf("case-%s", hash.Hex()[2:]) }
