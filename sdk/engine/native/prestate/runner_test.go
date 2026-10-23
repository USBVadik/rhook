package prestate

import (
	"encoding/json"
	"math/big"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/rawdb"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/tracing"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/ethereum/go-ethereum/triedb"
	"github.com/holiman/uint256"
	"github.com/offchainlabs/nitro/arbos"
	"github.com/offchainlabs/nitro/arbos/arbosState"
	"github.com/offchainlabs/nitro/arbos/arbostypes"
	"github.com/offchainlabs/nitro/arbos/burn"
)

func completeNativeSystemBlockFixture(t *testing.T, activeMultiGas bool, prospectiveMode ...string) {
	cfg, e := ValidateConfig(configBytes(t), 61)
	if e != nil {
		t.Fatal(e)
	}
	disk := rawdb.NewMemoryDatabase()
	defer disk.Close()
	tdb := triedb.NewDatabase(disk, triedb.HashDefaults)
	defer tdb.Close()
	database := state.NewDatabase(tdb, nil)
	s, e := state.New(types.EmptyRootHash, database)
	if e != nil {
		t.Fatal(e)
	}
	initCfg := *cfg
	initCfg.ArbitrumChainParams.InitialArbOSVersion = 61
	msg := &arbostypes.ParsedInitMessage{ChainId: big.NewInt(4663), InitialL1BaseFee: big.NewInt(100), SerializedChainConfig: configBytes(t)}
	if _, e = arbosState.InitializeArbosState(s, burn.NewSystemBurner(nil, false), &initCfg, nil, msg); e != nil {
		t.Fatal(e)
	}
	if activeMultiGas {
		arb, e := arbosState.OpenSystemArbosState(s, nil, false)
		if e != nil {
			t.Fatal(e)
		}
		if e = arb.L2PricingState().AddMultiGasConstraint(100000, 10, 20000, map[uint8]uint64{1: 1}); e != nil {
			t.Fatal(e)
		}
		arb.L2PricingState().UpdatePricingModel(1)
	}

	// Deterministic synthetic signed user transaction with a storage-clear refund.
	lpMode := len(prospectiveMode) > 0 && (prospectiveMode[0] == "lp-changed" || prospectiveMode[0] == "lp-unchanged")
	nestedObservation := lpMode && len(prospectiveMode) > 1 && prospectiveMode[1] == "nested-revert"
	var lpBefore common.Hash
	var lpCodeHash common.Hash
	destination := addrA
	key, e := crypto.HexToECDSA("1111111111111111111111111111111111111111111111111111111111111111")
	if e != nil {
		t.Fatal(e)
	}
	owner := crypto.PubkeyToAddress(key.PublicKey)
	s.SetBalance(owner, uint256.MustFromBig(new(big.Int).Exp(big.NewInt(10), big.NewInt(22), nil)), tracing.BalanceChangeUnspecified)
	s.SetCode(addrA, common.FromHex("0x6001600055600060005500"), tracing.CodeChangeUnspecified)
	if lpMode {
		destination = hookrRules
		lpBefore = syntheticLPWord()
		s.SetState(destination, hookrConfigSlot, lpBefore)
		// A toy program reading the guarded storage word; never real Hookr bytecode.
		code := append([]byte{0x7f}, hookrConfigSlot[:]...)
		code = append(code, 0x54, 0x60, 0xa0, 0x1c, 0x61, 0xff, 0xff, 0x16, 0x15, 0x15, 0x60, 0x00, 0x55, 0x00)
		if prospectiveMode[0] == "lp-unchanged" {
			code = []byte{0x00}
		}
		if nestedObservation {
			// Root catches a failed middle frame whose child succeeded, then
			// makes a separate successful call. The first child's effects are
			// rolled back; the later sibling must remain eligible for observation.
			call := func(to common.Address) []byte {
				v := append([]byte{0x5f, 0x5f, 0x5f, 0x5f, 0x5f, 0x73}, to[:]...)
				return append(v, 0x5a, 0xf1, 0x50)
			}
			s.SetCode(addrB, []byte{0x00}, tracing.CodeChangeUnspecified)
			s.SetCode(addrA, append(call(addrB), 0x5f, 0x5f, 0xfd), tracing.CodeChangeUnspecified)
			code = append(append(call(addrA), call(addrB)...), code...)
		}
		s.SetCode(destination, code, tracing.CodeChangeUnspecified)
		lpCodeHash = crypto.Keccak256Hash(code)
	}
	user, e := types.SignTx(types.NewTx(&types.LegacyTx{Nonce: 0, To: &destination, Gas: 200000, GasPrice: big.NewInt(1000000000), Value: big.NewInt(0)}), types.LatestSigner(cfg), key)
	if e != nil {
		t.Fatal(e)
	}

	root, e := s.Commit(123, true, false)
	if e != nil {
		t.Fatal(e)
	}
	if e = tdb.Commit(root, false); e != nil {
		t.Fatal(e)
	}
	nodes := map[common.Hash]hexutil.Bytes{}
	codes := map[common.Hash]hexutil.Bytes{}
	it := disk.NewIterator(nil, nil)
	for it.Next() {
		key, value := it.Key(), it.Value()
		if len(key) == 32 {
			nodes[common.BytesToHash(key)] = common.CopyBytes(value)
		} else if len(key) == 33 && key[0] == 'c' {
			codes[common.BytesToHash(key[1:])] = common.CopyBytes(value)
		}
	}
	it.Release()
	c, parentRaw, blockRaw, rawTxs := inputFixture(t)
	var parent, header types.Header
	json.Unmarshal(parentRaw, &parent)
	json.Unmarshal(blockRaw, &header)
	parent.Root = root
	header.ParentHash = parent.Hash()
	c.StateRoot = root
	c.BlockHash = parent.Hash()
	system := types.NewTx(arbos.InternalTxStartBlock(big.NewInt(4663), big.NewInt(100), 44, &header, &parent))
	raw, _ := system.MarshalBinary()
	rawTxs = []hexutil.Bytes{raw}
	txs := types.Transactions{system}
	header.TxHash = types.DeriveSha(txs, trie.NewStackTrie(nil))
	baseline, e := state.New(root, database)
	if e != nil {
		t.Fatal(e)
	}
	engine := &capturingEngine{}
	chain := &nativeChain{cfg, &parent, engine, nil}
	generated, _, receipts, e := arbos.ProduceBlockAdvanced(&arbostypes.L1IncomingMessageHeader{Poster: header.Coinbase, BlockNumber: 44, Timestamp: header.Time, L1BaseFee: big.NewInt(100)}, 0, &parent, baseline, chain, arbos.NewNoopSequencingHooks(types.Transactions{user}), false, core.NewMessageReplayContext(), false, nil)
	if e != nil {
		t.Fatal(e)
	}
	expectedRoot, e := baseline.Commit(124, true, false)
	if e != nil {
		t.Fatal(e)
	}
	if expectedRoot != generated.Root() || len(receipts) != 2 {
		t.Fatal("native producer baseline incomplete")
	}
	// Full-resident stock Nitro producer vs fresh witness-only adapter.
	header = *generated.Header()
	rawTxs = nil
	hashes := []common.Hash{}
	for _, tx := range generated.Transactions() {
		raw, e := tx.MarshalBinary()
		if e != nil {
			t.Fatal(e)
		}
		rawTxs = append(rawTxs, raw)
		hashes = append(hashes, tx.Hash())
	}

	marshal := func(h *types.Header, tx []common.Hash) []byte {
		r, _ := json.Marshal(h)
		var m map[string]any
		json.Unmarshal(r, &m)
		m["hash"] = h.Hash()
		m["transactions"] = tx
		r, _ = json.Marshal(m)
		return r
	}
	candidate, e := ImportBlock(c, marshal(&parent, nil), marshal(&header, hashes), rawTxs, configBytes(t))
	if e != nil {
		t.Fatal(e)
	}
	bundle := BlockPackage{Checkpoint: c, Parent: marshal(&parent, nil), Block: marshal(&header, hashes), Raw: rawTxs}
	for _, n := range nodes {
		bundle.State = append(bundle.State, n)
	}
	for _, code := range codes {
		bundle.Codes = append(bundle.Codes, code)
	}
	packed, _ := json.Marshal(bundle)
	admitted, inventory, e := AdmitPackage(packed)
	if e != nil {
		t.Fatal(e)
	}
	if admitted.InputCommitment() != candidate.InputCommitment() || inventory.ChainConfigBytes != 624 || inventory.ArbOSVersion != 61 || inventory.HistoricalNativeExecutions != 0 {
		t.Fatal("whole package native admission lost input/config context")
	}
	if len(prospectiveMode) > 0 && !lpMode {
		exerciseProspectiveFixture(t, c, bundle, tdb, disk, prospectiveMode[0])
		return
	}
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	b.checkpoint = c
	if e = b.LoadWitness(c, nodes, codes); e != nil {
		t.Fatal(e)
	}
	var out *CalibrationResult
	if lpMode {
		out, e = RunHookrObserved(candidate, b, nil, EconomicObservationPlan{Subject: user.Hash(), NativeOrdinal: 1, Accounts: []common.Address{hookrRules, owner}, Storage: []WatchedStorage{{hookrRules, hookrConfigSlot}}})
	} else {
		out, e = RunCanonical(candidate, b)
	}
	if e != nil {
		t.Fatal(e)
	}
	if !out.Matched || out.Transactions != 2 || out.StateRoot != expectedRoot || f.calls != 0 {
		t.Fatal("native system block did not match resident baseline without fallback")
	}
	if lpMode {
		// A separate witness-only StateDB; ACTUAL's mutable state is never reused.
		branch, err := NewBridge(c, Budget{MaxRequests: 1, MaxBytes: 32 << 20, MaxResponseBytes: 8 << 20, ExpiresAt: time.Now().Add(time.Minute)}, nil)
		if err != nil {
			t.Fatal(err)
		}
		defer branch.Close()
		if err = branch.LoadWitness(c, nodes, codes); err != nil {
			t.Fatal(err)
		}
		after, err := CheckedLPReplacement(lpBefore, lpBefore)
		if err != nil {
			t.Fatal(err)
		}
		request := LPIntervention{c, hookrPoolID, hookrRules, hookrConfigSlot, hookrLPMask, lpBefore, after}
		hypothetical, err := runObservedBlock(candidate, branch, EconomicObservationPlan{Subject: user.Hash(), NativeOrdinal: 1, Accounts: []common.Address{hookrRules, owner}, Storage: []WatchedStorage{{hookrRules, hookrConfigSlot}}}, func() (*CalibrationResult, error) {
			return runNativeBlock(candidate, branch, func(b *Bridge) (*LPWriteRecord, error) {
				record, e := applyLPOverlay(b, request, lpCodeHash)
				if e == nil && b.live.GetCommittedState(hookrRules, hookrConfigSlot) != after {
					t.Fatal("hypothetical word is not EIP-2200 original state before first arrival")
				}
				return record, e
			})
		})
		if err != nil {
			t.Fatal(err)
		}
		if hypothetical.Observation == nil || !hypothetical.Observation.Complete || len(hypothetical.Observation.Calls) == 0 || hypothetical.Observation.Before.Storage[0].Value != after || hypothetical.Observation.After.Storage[0].Value != after {
			t.Fatal("native observation not bound to patched initial/final state")
		}
		if out.Observation == nil || !out.Observation.Complete || out.Observation.Before.Storage[0].Value != lpBefore {
			t.Fatal("ACTUAL observation missing original word")
		}
		if nestedObservation {
			for _, observation := range []*NativeEconomicObservation{out.Observation, hypothetical.Observation} {
				calls := observation.Calls
				if len(calls) != 4 || calls[0].Reverted || !calls[1].Reverted || calls[2].Reverted || !calls[2].AncestorReverted || calls[2].Parent != 1 || calls[3].Parent != 0 || calls[3].Reverted || calls[3].AncestorReverted {
					t.Fatalf("native caught-revert ancestry is incomplete: %+v", calls)
				}
			}
		}
		if hypothetical.World != "BRANCH" || hypothetical.Patch == nil || hypothetical.Patch.SemanticInitialWrites != 1 || hypothetical.Transactions != 2 {
			t.Fatal("branch output incomplete")
		}
		if hypothetical.StateRoot == expectedRoot {
			t.Fatal("initial patch must affect final state root even if lifecycle is unchanged")
		}
		residentBranch, err := state.New(root, database)
		if err != nil {
			t.Fatal(err)
		}
		residentBranch.SetState(hookrRules, hookrConfigSlot, after)
		residentBranch.Finalise(true)
		residentChain := &nativeChain{cfg, &parent, &capturingEngine{}, nil}
		independentlyProduced, _, independentlyReceipts, err := arbos.ProduceBlockAdvanced(&arbostypes.L1IncomingMessageHeader{Poster: header.Coinbase, BlockNumber: 44, Timestamp: header.Time, L1BaseFee: big.NewInt(100)}, 0, &parent, residentBranch, residentChain, arbos.NewNoopSequencingHooks(types.Transactions{user}), false, core.NewMessageReplayContext(), false, nil)
		if err != nil {
			t.Fatal(err)
		}
		independentRoot, err := residentBranch.Commit(124, true, false)
		if err != nil {
			t.Fatal(err)
		}
		if hypothetical.StateRoot != independentRoot || hypothetical.BlockHash != independentlyProduced.Hash() || hypothetical.ReceiptsRoot != types.DeriveSha(independentlyReceipts, trie.NewStackTrie(nil)) {
			t.Fatal("partial witness branch disagrees with full-resident patched baseline")
		}

		if prospectiveMode[0] == "lp-unchanged" && (hypothetical.ReceiptsRoot != out.ReceiptsRoot || hypothetical.GasUsed != out.GasUsed) {
			t.Fatal("unchanged toy execution changed receipts")
		}
		if prospectiveMode[0] == "lp-changed" && (hypothetical.ReceiptsRoot == out.ReceiptsRoot) {
			t.Fatal("changed toy SSTORE cost did not affect native receipts")
		}
		if candidate.checkpoint != c {
			t.Fatal("original checkpoint mutated")
		}
		if _, err = RunCanonical(candidate, branch); !IsHostStop(err) {
			t.Fatal("reused mutable branch instance")
		}
	}

}
func TestMissingArbOSContextFailsBeforeProcessor(t *testing.T) {
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	candidate := &Candidate{checkpoint: f.checkpoint}
	out, e := RunCanonical(candidate, b)
	if !IsHostStop(e) || out != nil {
		t.Fatalf("missing system context produced result: %v %v", out, e)
	}
}

func TestCompleteNativeSystemBlockWithSyntheticPrestate(t *testing.T) {
	completeNativeSystemBlockFixture(t, false)
}
func TestActiveMultiGasFeesMatchStockNitroProducer(t *testing.T) {
	completeNativeSystemBlockFixture(t, true)
}

func TestProspectiveFullNativeBlockHydratesLiveProofAndCode(t *testing.T) {
	completeNativeSystemBlockFixture(t, true, "success")
}
func TestProspectiveWrongRootRemainsHostFailure(t *testing.T) {
	completeNativeSystemBlockFixture(t, true, "wrong-root")
}
func TestProspectiveUnavailableSourceStopsWithoutRetry(t *testing.T) {
	completeNativeSystemBlockFixture(t, true, "unavailable")
}

func TestProspectiveUnprovedCodePreimageRejected(t *testing.T) {
	completeNativeSystemBlockFixture(t, true, "bad-code")
}

func TestFullNativeLPBranchChangesExecution(t *testing.T) {
	completeNativeSystemBlockFixture(t, false, "lp-changed")
}
func TestFullNativeLPBranchUnchangedReceiptIsValid(t *testing.T) {
	completeNativeSystemBlockFixture(t, false, "lp-unchanged")
}
