package prestate

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
)

var ArbOSAccount = common.HexToAddress("0xa4b05fffffffffffffffffffffffffffffffffff")
var ArbOSVersionSlot = common.HexToHash("0x15fed0451499512d95f3ec5a41c878b9de55f21878b5b4e190d4667ec709b400")
var ArbOSConfigLengthSlot = common.HexToHash("0x696e3678057072f0c8dba2395c9474f6a52565714cff46262e4548533b097700")
var ArbOSPerBlockGasLimitSlot = common.HexToHash("0xe54de2a4cdacc0a0059d2b6e16348103df8c4aff409c31e40ec73d11926c8201")

func Digest(domain string, raw []byte) string {
	h := sha256.Sum256(append([]byte(domain+"\n"), raw...))
	return hex.EncodeToString(h[:])
}
func ByteDigest(raw []byte) string { h := sha256.Sum256(raw); return hex.EncodeToString(h[:]) }

type SelectionRecord struct {
	Number   uint64      `json:"number"`
	Hash     common.Hash `json:"hash"`
	Eligible bool        `json:"eligible"`
	Reason   string      `json:"reason"`
}
type ProspectiveResult struct {
	Terminal                 string             `json:"terminal"`
	Cause                    string             `json:"cause,omitempty"`
	AnchorNumber             uint64             `json:"anchorNumber"`
	Observations             []SelectionRecord  `json:"observations"`
	Inventory                *Inventory         `json:"inventory,omitempty"`
	InputPackageSHA          string             `json:"inputPackageSha256,omitempty"`
	NativeAttempts           int                `json:"nativeAttempts"`
	Native                   *CalibrationResult `json:"nativeResult,omitempty"`
	InitialWitnessCommitment string             `json:"initialWitnessCommitment,omitempty"`
	FinalWitnessCommitment   string             `json:"finalWitnessCommitment,omitempty"`
	FinalWitnessComplete     bool               `json:"finalWitnessComplete"`
	RpcTranscriptCommitment  string             `json:"rpcTranscriptCommitment"`
	RpcRequests              uint64             `json:"rpcRequests"`
	ResponseBytes            int64              `json:"responseBytesRead"`
	Hookr                    *HookrPair         `json:"hookr,omitempty"`
	MissingStateAttempts     []Attempt          `json:"hydrationAttempts"`
}

type WriteEvidence func(string, []byte) error
type EmitEvent func(string, any) error

func EmitJSON(write WriteEvidence, name string, value any) error {
	raw, e := json.MarshalIndent(value, "", "  ")
	if e != nil {
		return e
	}
	return write(name, append(raw, '\n'))
}

func eligibleHeader(raw []byte) (*types.Header, string, error) {
	h, e := decodeHeader(raw)
	if e != nil {
		return nil, "", e
	}
	if types.DeserializeHeaderExtraInformation(h).ArbOSFormatVersion != 61 {
		return h, "UNSUPPORTED_ARBOS", nil
	}
	var body struct {
		Transactions []struct {
			Type *hexutil.Uint64 `json:"type"`
		} `json:"transactions"`
	}
	if json.Unmarshal(raw, &body) != nil {
		return nil, "", errors.New("BLOCK_BODY_ENCODING")
	}
	if len(body.Transactions) < 2 || len(body.Transactions) > 8 {
		return h, "TRANSACTION_COUNT", nil
	}
	for _, tx := range body.Transactions {
		if tx.Type == nil {
			return nil, "", errors.New("MISSING_TRANSACTION_TYPE")
		}
	}
	if *body.Transactions[0].Type != hexutil.Uint64(types.ArbitrumInternalTxType) {
		return h, "NO_INITIAL_SYSTEM_ENVELOPE", nil
	}
	ordinary := false
	for _, tx := range body.Transactions[1:] {
		if *tx.Type <= 2 {
			ordinary = true
		}
	}
	if !ordinary {
		return h, "NO_ORDINARY_USER_TRANSACTION", nil
	}
	if h.GasUsed > 20000000 {
		return h, "GAS_USED_CAP", nil
	}
	return h, "ELIGIBLE", nil
}

// NewLiveCalibration reuses the exact generic importer and strict proof bridge.
// The initial package must independently admit offline before any EVM processing.
func NewLiveCalibration(raw []byte, source Source, expires time.Time) (*OfflineCalibration, error) {
	c, inv, e := AdmitPackage(raw)
	if e != nil {
		return nil, e
	}
	var p BlockPackage
	if e = json.Unmarshal(raw, &p); e != nil {
		return nil, e
	}
	nodes, codes := map[common.Hash]hexutil.Bytes{}, map[common.Hash]hexutil.Bytes{}
	for _, n := range p.State {
		nodes[crypto.Keccak256Hash(n)] = n
	}
	for _, n := range p.Codes {
		codes[crypto.Keccak256Hash(n)] = n
	}
	for _, proof := range p.Proofs {
		used, e := verifyProof(p.Checkpoint.StateRoot, proof.Address, proof.Slots, proof.Proof)
		if e != nil {
			return nil, e
		}
		for h, n := range used {
			nodes[h] = n
		}
	}
	b, e := NewBridge(p.Checkpoint, Budget{MaxRequests: 64, MaxBytes: 32 << 20, MaxResponseBytes: 8 << 20, ExpiresAt: expires, PerRequest: 15 * time.Second}, source)
	if e != nil {
		return nil, e
	}
	if e = b.LoadWitness(p.Checkpoint, nodes, codes); e != nil {
		b.Close()
		return nil, e
	}
	// Known block-prelude slot is checked before RunCanonical. It must be proved,
	// including a legitimately proved zero, rather than inferred from a header.
	before := b.requests
	e = b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		s.GetState(ArbOSAccount, ArbOSPerBlockGasLimitSlot)
		return s.Error()
	})
	if e != nil || b.requests != before {
		b.Close()
		if e != nil {
			return nil, e
		}
		return nil, errors.New("KNOWN_PRELUDE_SLOT_NOT_IN_INITIAL_PACKAGE")
	}
	x := &OfflineCalibration{Candidate: c, Bridge: b, Inventory: inv, ConfigSHA: ByteDigest(c.configRaw)}
	for _, tx := range c.block.Transactions() {
		x.TxHashes = append(x.TxHashes, tx.Hash())
	}
	return x, nil
}

func (b *Bridge) WitnessSnapshot() (string, []byte) {
	b.fetchMu.Lock()
	defer b.fetchMu.Unlock()
	raw, _ := json.Marshal(struct {
		Checkpoint Checkpoint             `json:"checkpoint"`
		Nodes      map[common.Hash][]byte `json:"nodes"`
		Codes      map[common.Hash][]byte `json:"codes"`
		Attempts   []Attempt              `json:"attempts"`
	}{b.checkpoint, b.nodes, b.codes, b.attempts})
	return Digest("rhook/native-prestate-witness/0.1", raw), raw
}

// RunProspective has one selection and one RunCanonical call. Tests may supply
// a simulated RPC transport and no-op wait; the executable always uses time.Sleep.
func RunProspective(ctx context.Context, rpc *RPCSource, write WriteEvidence, emit EmitEvent, wait func(time.Duration), captureDeadline time.Time, minimumAnchor ...uint64) (out *ProspectiveResult) {
	return runProspective(ctx, rpc, write, emit, wait, captureDeadline, false, minimumAnchor...)
}

func RunHookrProspective(ctx context.Context, rpc *RPCSource, write WriteEvidence, emit EmitEvent, wait func(time.Duration), captureDeadline time.Time) *ProspectiveResult {
	return runProspective(ctx, rpc, write, emit, wait, captureDeadline, true, 92076104)
}

func runProspective(ctx context.Context, rpc *RPCSource, write WriteEvidence, emit EmitEvent, wait func(time.Duration), captureDeadline time.Time, hookr bool, minimumAnchor ...uint64) (out *ProspectiveResult) {
	return runProspectiveLocked(ctx, rpc, write, emit, wait, captureDeadline, hookr, nil, minimumAnchor...)
}

func RunLockedHookrProspective(ctx context.Context, rpc *RPCSource, write WriteEvidence, emit EmitEvent, captureDeadline time.Time, locked *LockedHookrSelection) *ProspectiveResult {
	if locked == nil {
		return &ProspectiveResult{Terminal: "RUNTIME_OR_RESOURCE_STOP", Cause: "LOCKED_SELECTION_REQUIRED_NO_LEGACY_FALLBACK"}
	}
	return runProspectiveLocked(ctx, rpc, write, emit, time.Sleep, captureDeadline, true, locked, 92076104)
}

func runProspectiveLocked(ctx context.Context, rpc *RPCSource, write WriteEvidence, emit EmitEvent, wait func(time.Duration), captureDeadline time.Time, hookr bool, locked *LockedHookrSelection, minimumAnchor ...uint64) (out *ProspectiveResult) {
	out = &ProspectiveResult{Terminal: "RUNTIME_OR_RESOURCE_STOP"}
	if hookr {
		out.Hookr = &HookrPair{HeterogeneousAgreement: "NOT_EVALUATED", EconomicAssurance: "UNRESOLVED"}
	}
	var live *OfflineCalibration
	defer func() {
		if v := recover(); v != nil {
			out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
			out.Cause = "UNEXPECTED_NATIVE_PANIC"
		}
		if live != nil {
			if live.Bridge.observation != nil {
				if e := EmitJSON(write, "ACTUAL_OBSERVATION.json", live.Bridge.observation); e != nil {
					out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
					out.Cause = "ACTUAL_OBSERVATION_RECORD_FAILURE"
				}
			}
			commitment, raw := live.Bridge.WitnessSnapshot()
			out.FinalWitnessCommitment = commitment
			out.MissingStateAttempts = live.Attempts()
			if e := write("FINAL_WITNESS.json", raw); e != nil {
				out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
				out.Cause = "FINAL_WITNESS_RECORD_FAILURE"
			}
			if out.Native != nil && out.Native.World == "ACTUAL" && out.Native.Matched {
				out.FinalWitnessComplete = out.Native != nil && out.FinalWitnessCommitment == out.Native.WitnessCommitment
				if !out.FinalWitnessComplete {
					out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
					out.Cause = "FINAL_WITNESS_COMMITMENT_MISMATCH"
				}
			}
			live.Bridge.Close()
		}
		var transcript []byte
		out.RpcTranscriptCommitment, transcript, out.RpcRequests, out.ResponseBytes = rpc.Transcript()
		if e := write("RPC_TRANSCRIPT.json", transcript); e != nil {
			out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
			out.Cause = "TRANSCRIPT_RECORD_FAILURE"
		}
	}()
	captureCtx, cancel := context.WithDeadline(ctx, captureDeadline)
	defer cancel()
	fail := func(e error) {
		if e != nil {
			out.Cause = e.Error()
			if len(out.Cause) > 4096 {
				out.Cause = out.Cause[:4096]
			}
		}
	}
	if e := emit("CAPTURE_STARTED", map[string]any{"maximumRpcRequests": 64, "legacyWindowBlocks": 10, "selectionAlreadyLocked": locked != nil}); e != nil {
		fail(e)
		return
	}
	var block json.RawMessage
	var chosen *types.Header
	if locked == nil {
		var chain string
		if e := rpc.call(captureCtx, "eth_chainId", []any{}, &chain); e != nil {
			fail(e)
			return
		}
		if chain != "0x1237" {
			fail(errors.New("CHAIN_ID_MISMATCH"))
			return
		}
		var anchor json.RawMessage
		if e := rpc.call(captureCtx, "eth_getBlockByNumber", []any{"latest", false}, &anchor); e != nil {
			fail(e)
			return
		}
		ah, e := decodeHeader(anchor)
		if e != nil {
			fail(e)
			return
		}
		out.AnchorNumber = ah.Number.Uint64()
		if len(minimumAnchor) > 0 && out.AnchorNumber <= minimumAnchor[0] {
			fail(errors.New("STALE_ACTIVATION_ANCHOR"))
			return
		}
		if out.AnchorNumber > ^uint64(0)-10 {
			fail(errors.New("ANCHOR_OVERFLOW"))
			return
		}
		previousHash := ah.Hash()
		for i := uint64(1); i <= 10; i++ {
			if time.Now().Add(time.Second).After(captureDeadline) {
				fail(errors.New("CAPTURE_DEADLINE"))
				return
			}
			wait(time.Second)
			raw, e := rpc.callRaw(captureCtx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(out.AnchorNumber + i), true}, true)
			if e != nil {
				fail(e)
				return
			}
			if bytes.Equal(raw, []byte("null")) {
				out.Terminal = "PROSPECTIVE_TARGET_NOT_FOUND"
				out.Cause = "SCHEDULED_BLOCK_NOT_AVAILABLE_NO_REQUERY"
				return
			}
			h, reason, e := eligibleHeader(raw)
			if e != nil {
				fail(e)
				return
			}
			if h.Number.Uint64() != out.AnchorNumber+i {
				fail(errors.New("OBSERVATION_HEIGHT_MISMATCH"))
				return
			}
			if h.ParentHash != previousHash {
				fail(errors.New("OBSERVATION_CHAIN_REORG"))
				return
			}
			previousHash = h.Hash()
			if hookr && reason == "ELIGIBLE" {
				subject, selectionReason, selectionError := selectHookrTrade(captureCtx, rpc, raw, h)
				if selectionError != nil {
					fail(selectionError)
					return
				}
				reason = selectionReason
				if subject != nil {
					out.Hookr.Subject = subject
				}
			}
			out.Observations = append(out.Observations, SelectionRecord{h.Number.Uint64(), h.Hash(), reason == "ELIGIBLE", reason})
			if e = EmitJSON(write, fmt.Sprintf("OBSERVATION_%02d.json", i), out.Observations[len(out.Observations)-1]); e != nil {
				fail(e)
				return
			}
			if reason == "ELIGIBLE" {
				block = raw
				chosen = h
				break
			}
		}

	} else {
		if e := ValidateLockedHookrSelection(locked); e != nil {
			fail(e)
			return
		}
		out.AnchorNumber = locked.ActivationNumber
		var chain string
		if e := rpc.call(captureCtx, "eth_chainId", []any{}, &chain); e != nil {
			fail(e)
			return
		}
		if chain != "0x1237" {
			fail(errors.New("CHAIN_ID_MISMATCH"))
			return
		}
		if e := rpc.call(captureCtx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(locked.BlockNumber), true}, &block); e != nil {
			fail(e)
			return
		}
		h, reason, e := eligibleHeader(block)
		if e != nil || reason != "ELIGIBLE" || h.Hash() != locked.BlockHash {
			fail(errors.New("LOCKED_BLOCK_CHANGED_OR_UNAVAILABLE"))
			return
		}
		var logs []*types.Log
		filter := map[string]any{"blockHash": h.Hash(), "address": []common.Address{hookrManager, hookrRouter}, "topics": []any{[]common.Hash{swapTopic, routerTopic}, hookrPoolID}}
		if e = rpc.call(captureCtx, "eth_getLogs", []any{filter}, &logs); e != nil {
			fail(e)
			return
		}
		subject, _, e := selectHookrTradeLogs(block, h, logs, true)
		if e != nil || subject == nil || *subject != *locked.Subject {
			fail(errors.New("LOCKED_SUBJECT_CHANGED_OR_UNAVAILABLE"))
			return
		}
		chosen = h
		out.Hookr.Subject = subject
		out.Observations = append(out.Observations, SelectionRecord{h.Number.Uint64(), h.Hash(), true, "LOCKED_MONITOR_TARGET_REVALIDATED"})
	}
	var e error
	if chosen == nil {
		out.Terminal = "PROSPECTIVE_TARGET_NOT_FOUND"
		out.Cause = "TEN_CONSECUTIVE_BLOCKS_NO_ELIGIBLE_TARGET"
		return
	}
	var parent json.RawMessage
	if e = rpc.call(captureCtx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(chosen.Number.Uint64() - 1), false}, &parent); e != nil {
		fail(e)
		return
	}
	ph, e := decodeHeader(parent)
	if e != nil {
		fail(e)
		return
	}
	if ph.Hash() != chosen.ParentHash {
		fail(errors.New("PARENT_REORG"))
		return
	}
	checkpoint := Checkpoint{4663, ph.Number.Uint64(), ph.Hash(), ph.Root}
	var body struct {
		Transactions []struct {
			Hash common.Hash     `json:"hash"`
			Type *hexutil.Uint64 `json:"type"`
		} `json:"transactions"`
	}
	if e = json.Unmarshal(block, &body); e != nil {
		fail(e)
		return
	}
	p := BlockPackage{Checkpoint: checkpoint, Parent: parent, Block: block}
	for _, tx := range body.Transactions {
		var raw hexutil.Bytes
		if e = rpc.call(captureCtx, "eth_getRawTransactionByHash", []any{tx.Hash}, &raw); e != nil {
			fail(e)
			return
		}
		p.Raw = append(p.Raw, raw)
	}
	var witness struct {
		State []hexutil.Bytes `json:"state"`
		Codes []hexutil.Bytes `json:"codes"`
	}
	if e = rpc.call(captureCtx, "debug_executionWitness", []any{hexutil.EncodeUint64(chosen.Number.Uint64())}, &witness); e != nil {
		fail(e)
		return
	}
	p.State = witness.State
	p.Codes = witness.Codes
	initialSlots := []common.Hash{ArbOSVersionSlot, ArbOSConfigLengthSlot, ArbOSPerBlockGasLimitSlot}
	proof, e := rpc.GetProof(captureCtx, checkpoint, ArbOSAccount, initialSlots)
	if e != nil {
		fail(e)
		return
	}
	if _, e = verifyProof(ph.Root, ArbOSAccount, initialSlots, proof); e != nil {
		fail(e)
		return
	}
	values := map[common.Hash]*big.Int{}
	for _, v := range proof.StorageProof {
		values[v.Key] = v.Value.ToInt()
	}
	if values[ArbOSVersionSlot].Cmp(big.NewInt(61)) != 0 || !values[ArbOSConfigLengthSlot].IsUint64() {
		fail(errors.New("ARBOS_CONFIGURATION_LENGTH_OR_VERSION"))
		return
	}
	length := values[ArbOSConfigLengthSlot].Uint64()
	if length == 0 || length > 1536 {
		fail(errors.New("CHAIN_CONFIG_SIZE_CAP"))
		return
	}
	p.Proofs = append(p.Proofs, CapturedProof{ArbOSAccount, initialSlots, proof})
	var slots []common.Hash
	for i := uint64(1); i <= (length+31)/32; i++ {
		s := ArbOSConfigLengthSlot
		s[31] = byte(i)
		slots = append(slots, s)
	}
	configProof, e := rpc.GetProof(captureCtx, checkpoint, ArbOSAccount, slots)
	if e != nil {
		fail(e)
		return
	}
	p.Proofs = append(p.Proofs, CapturedProof{ArbOSAccount, slots, configProof})
	if hookr {
		request, plan, err := captureHookrDependencies(captureCtx, rpc, &p, out.Hookr.Subject)
		if err != nil {
			fail(err)
			return
		}
		out.Hookr.Intervention = request
		out.Hookr.Plan = plan
	}
	raw, e := json.Marshal(p)
	if e != nil {
		fail(e)
		return
	}
	out.InputPackageSHA = ByteDigest(raw)
	live, e = NewLiveCalibration(raw, rpc, minTime(time.Now().Add(120*time.Second), rpc.deadline))
	if e != nil {
		fail(e)
		return
	}
	out.Inventory = live.Inventory
	for i, tx := range live.Candidate.block.Transactions() {
		if body.Transactions[i].Type == nil || uint64(tx.Type()) != uint64(*body.Transactions[i].Type) {
			fail(errors.New("RAW_TYPE_SELECTION_MISMATCH"))
			return
		}
	}
	out.InitialWitnessCommitment, _ = live.Bridge.WitnessSnapshot()
	if out.InitialWitnessCommitment != out.Inventory.WitnessCommitment {
		fail(errors.New("INITIAL_WITNESS_BINDING_MISMATCH"))
		return
	}
	if e = write("BLOCK_PACKAGE.json", raw); e != nil {
		fail(e)
		return
	}
	precommit := map[string]any{"inventory": out.Inventory, "packageSha256": out.InputPackageSHA, "initialWitnessCommitment": out.InitialWitnessCommitment, "chainConfigSha256": live.ConfigSHA, "orderedTransactionHashes": live.TxHashes, "knownPreludeSlot": ArbOSPerBlockGasLimitSlot, "finalWitnessFrozenBeforeExecution": false}
	if hookr {
		precommit["hookrSubject"] = out.Hookr.Subject
		precommit["intervention"] = out.Hookr.Intervention
		precommit["observationPlan"] = out.Hookr.Plan
	}
	if e = EmitJSON(write, "INPUT_PRECOMMIT.json", precommit); e != nil {
		fail(e)
		return
	}
	if e = captureCtx.Err(); e != nil {
		fail(errors.New("CAPTURE_DEADLINE"))
		return
	}
	// No manual interaction or second capture after this durable precommit.
	if e = emit("NATIVE_REPLAY_ENTERED", precommit); e != nil {
		fail(e)
		return
	}
	out.NativeAttempts = 1
	if hookr {
		out.Native, e = RunHookrObserved(live.Candidate, live.Bridge, nil, *out.Hookr.Plan)
	} else {
		out.Native, e = RunCanonical(live.Candidate, live.Bridge)
	}
	out.Terminal, out.Cause = ClassifyCalibrationError(e)
	if hookr && e == nil {
		if e = EmitJSON(write, "ACTUAL_RESULT.json", out.Native); e != nil {
			fail(e)
			return
		}
		branchTerminal, branchError := completeHookrPair(ctx, rpc, write, emit, raw, out)
		out.Terminal = branchTerminal
		if branchError != nil {
			out.Cause = branchError.Error()
		}
	}
	if e != nil {
		out.Cause = e.Error()
		rpc.mu.Lock()
		f := rpc.fatal
		rpc.mu.Unlock()
		if f != nil && (stringsResource(f.Error())) {
			out.Terminal = "RUNTIME_OR_RESOURCE_STOP"
		}
	}
	return
}
func minTime(a, b time.Time) time.Time {
	if !b.IsZero() && b.Before(a) {
		return b
	}
	return a
}
func stringsResource(s string) bool {
	for _, x := range []string{"BUDGET", "DEADLINE", "BODY_LIMIT"} {
		if bytes.Contains([]byte(s), []byte(x)) {
			return true
		}
	}
	return false
}
