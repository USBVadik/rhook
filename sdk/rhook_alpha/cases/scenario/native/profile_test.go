package scenario

// G4A integration tests of the descriptor-driven linked profile. Offline only: admission, witness-backed
// StateDB initialization and evidence checks; Nitro's producer is never entered. Tests that need the accepted
// checkpoint witness read RHOOK_ACCEPTED_RECORDS (read-only) and are skipped without it. RHOOK_PARITY_OUT, when
// set, receives the admission parity table as JSON.
import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"math/big"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/params"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/offchainlabs/nitro/arbos"
	prestate "local/rhook-robinhood"
)

// testLoader returns a loader over the given descriptor bytes with a catalogue entry admitting the purposes. The
// per-kind statuses are those of the shipped catalogue (testKinds), so an offline-only kind stays offline-only.
func testLoader(t *testing.T, raw []byte, admits ...string) descriptorLoader {
	t.Helper()
	return testLoaderKinds(t, raw, testKinds(t), admits...)
}

func testKinds(t *testing.T) map[string]string {
	t.Helper()
	var c descriptorCatalogue
	if e := strictDecode(descriptorCatalogueRaw, &c); e != nil || len(c.Entries) != 1 {
		t.Fatal("shipped catalogue", e)
	}
	return c.Entries[0].Kinds
}

func testLoaderKinds(t *testing.T, raw []byte, kinds map[string]string, admits ...string) descriptorLoader {
	t.Helper()
	d, e := ParseDescriptor(raw)
	if e != nil {
		t.Fatal(e)
	}
	cat := descriptorCatalogue{Schema: DescriptorCatalogueSchema, Entries: []descriptorEntry{{DescriptorFile: "test.json", DescriptorSha256: d.Sha256(), Kinds: kinds,
		ProfileID: d.ProfileID, Review: descriptorReview{Admits: admits, Author: "test", IndependentReview: "TEST_ONLY", NativeExecution: "TEST_ONLY", Status: "TEST_ONLY"}, Revision: d.Revision}}}
	craw, _ := Canonical(cat)
	return func(id, purpose string) (*Descriptor, error) {
		return loadAcceptedFrom(craw, map[string][]byte{"test.json": raw}, id, purpose)
	}
}

// buildProfileInput is the Go mirror of profile_descriptor.build_spec over a source body.
func buildProfileInput(t *testing.T, src Body, d *Descriptor, items []ProfileIntervention) ([]byte, Spec) {
	t.Helper()
	b := src
	b.Schema, b.Intervention, b.Overlay, b.ProfileOverlay = ProfileDomain, nil, nil, nil
	canon, _, e := d.canonicalProfileInterventions(items)
	if e != nil {
		t.Fatal(e)
	}
	c, e := d.ComposeProfile(canon, d.OriginalsFromDescriptor())
	if e != nil {
		t.Fatal(e)
	}
	var baseline []common.Hash
	for _, w := range d.OriginalState.Words {
		if w.Target == d.ConfigurationTarget {
			baseline = append(baseline, w.Value)
		}
	}
	b.Configs = Configurations{Baseline: baseline, Variant: c.Words[d.ConfigurationTarget]}
	o := d.profileTransform(b, canon, c)
	b.Origin = Origin{Kind: ProfileKind, Capsule: d.profileCapsule(b, canon)}
	b.ProfileOverlay = &o
	s := Commit(b)
	raw, e := Canonical(s)
	if e != nil {
		t.Fatal(e)
	}
	return append(raw, '\n'), s
}

func syntheticBody() Body {
	p := overlayProfile()
	b := Body{Schema: Domain, Pool: p.Pool, Release: hashValue(Domain+"/release", json.RawMessage(p.Manifest)),
		Configs: Configurations{Baseline: append([]common.Hash{}, p.BaselineWords...), Variant: append([]common.Hash{}, p.BaselineWords...)}}
	b.Checkpoint.ChainID, b.Checkpoint.StateRoot = 4663, common.HexToHash("0x1234")
	b.Parent = json.RawMessage(`{}`)
	return b
}

func acceptedSource(t *testing.T) (string, Spec) {
	t.Helper()
	dir := os.Getenv("RHOOK_ACCEPTED_RECORDS")
	if dir == "" {
		t.Skip("accepted run inputs not supplied")
	}
	raw, e := os.ReadFile(filepath.Join(dir, "lp23/inputs/SCENARIO.json"))
	if e != nil {
		t.Fatal(e)
	}
	s, e := Parse(raw)
	if e != nil || s.Schema != Domain {
		t.Fatal("LP-domain source required", e)
	}
	return dir, s
}

func TestProfileWorkerBoundsAndReviewGate(t *testing.T) {
	d := hookr1(t)
	p, e := profileFromDescriptor(d)
	if e != nil || p.Kind != ProfileKind || p.descriptor != d {
		t.Fatal(e)
	}
	want := officialProfile()
	if p.Rules != want.Rules || p.Router != want.Router || p.Pool != want.Pool || p.RootSlot != want.RootSlot || p.ConfigSlot != want.ConfigSlot ||
		p.RootCaps != want.RootCaps || p.BaseLpFee != want.BaseLpFee || !canonicalEqual(p.BaselineWords, want.BaselineWords) || len(p.Pins) != len(want.Pins) {
		t.Fatal("derived profile differs from the compiled Hookr profile")
	}
	for _, c := range []struct {
		name string
		edit func(map[string]any)
	}{
		{"chain id", func(v map[string]any) { v["chain"].(map[string]any)["chainId"] = json.Number("4664") }},
		{"ArbOS version", func(v map[string]any) { v["chain"].(map[string]any)["arbosVersion"] = json.Number("60") }},
		{"chain config hash", func(v map[string]any) { v["chain"].(map[string]any)["chainConfigSha256"] = strings.Repeat("e", 64) }},
		{"action amount", func(v map[string]any) { v["action"].(map[string]any)["amountInWei"] = "2000000000000000" }},
		{"action gas options", func(v map[string]any) { v["action"].(map[string]any)["gas"] = []any{json.Number("10000000")} }},
		{"action price limit", func(v map[string]any) { v["action"].(map[string]any)["sqrtPriceLimitX96"] = "4295128741" }},
		{"action ABI", func(v map[string]any) {
			abi := v["action"].(map[string]any)["abi"].([]any)
			abi[0].(map[string]any)["name"] = "swapExact"
		}},
		{"simulation actor seed", func(v map[string]any) { v["setup"].(map[string]any)["actor"].(map[string]any)["seed"] = "OTHER" }},
		{"funding", func(v map[string]any) { v["setup"].(map[string]any)["fundingWei"] = "2000000000000000000" }},
		{"Root flags swapped (bit 248 recapture, bit 249 Dynamic Fee)", func(v map[string]any) {
			for _, f := range v["fields"].([]any) {
				switch f := f.(map[string]any); f["name"] {
				case "rootDynamicFeeFlag":
					f["offset"] = json.Number("249")
				case "rootRecaptureFlag":
					f["offset"] = json.Number("248")
				}
			}
		}},
		{"reviewed Root caps word", func(v map[string]any) { setExact(v, "rootRecord", 1, "0x01") }},
		{"reviewed Rules word 2", func(v map[string]any) { setExact(v, "rulesConfig", 2, "0x01") }},
		{"reviewed original Root word (Dynamic Fee already OFF)", func(v map[string]any) {
			setExact(v, "rootRecord", 0, "0x020101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942")
		}},
	} {
		alt, e := ParseDescriptor(mutateDescriptor(t, c.edit))
		if e != nil {
			t.Fatalf("%s: descriptor itself must stay valid: %v", c.name, e)
		}
		if _, e = profileFromDescriptor(alt); codeOf(e) != "PROFILE_WORKER_BOUNDS" {
			t.Fatalf("%s: want PROFILE_WORKER_BOUNDS, got %v", c.name, e)
		}
	}
	raw, _ := buildProfileInput(t, syntheticBody(), d, []ProfileIntervention{piDynOff, piLp(23)})
	if _, e := profileForInput(raw, "NATIVE_EXECUTION", LoadAcceptedDescriptor); e != nil {
		t.Fatal("legacy-equivalent kinds pass the reviewed catalogue for native candidacy", e)
	}
	if _, e := admitRuntimeFor(raw, "NATIVE_EXECUTION"); e == nil {
		t.Fatal("legacy-linked runtime admitted a profile input")
	}
	tuning, _ := buildProfileInput(t, syntheticBody(), d, []ProfileIntervention{piTuning(8000, 1)})
	if _, e := AdmitProfile(tuning, "NATIVE_EXECUTION"); codeOf(e) != "PROFILE_KIND_REVIEW_INSUFFICIENT" {
		t.Fatal("Tuning must stay offline-only under the shipped catalogue", e)
	}
	if e := VerifyProfileEvidence(tuning, []byte("{}\n")); codeOf(e) != "PROFILE_KIND_REVIEW_INSUFFICIENT" {
		t.Fatal("evidence of an offline-only kind must be refused", e)
	}
}

// With the shipped (reviewed) catalogue and the worker linked as the profile runtime: every route into the
// controller refuses an offline-only or unreviewed kind, while the offline commands still admit it. Nothing here
// calls Controller.Execute with a native admission, so Nitro's producer is never entered.
func TestProfileShippedCatalogueNativeMatrix(t *testing.T) {
	_, src := acceptedSource(t)
	d := hookr1(t)
	linked := LinkedProfile
	LinkedProfile = ProfileRuntimeProfile
	defer func() { LinkedProfile = linked }()
	legacyKinds, _ := buildProfileInput(t, src.Body, d, []ProfileIntervention{piDynOff, piLp(23)})
	tuning, tuningSpec := buildProfileInput(t, src.Body, d, []ProfileIntervention{piTuning(8000, 1)})
	// An input naming a kind the catalogue does not list (re-committed; the descriptor never composed it).
	unknown := tuningSpec
	unknown.ProfileOverlay = func() *ProfileOverlay { o := *tuningSpec.ProfileOverlay; return &o }()
	unknown.ProfileOverlay.Interventions = append([]ProfileIntervention{}, tuningSpec.ProfileOverlay.Interventions...)
	unknown.ProfileOverlay.Interventions[0].Kind = "DYNAMIC_FEE_UNREVIEWED"
	uraw, _ := Canonical(Commit(unknown.Body))
	uraw = append(uraw, '\n')
	if _, e := admitRuntimeFor(legacyKinds, "NATIVE_EXECUTION"); e != nil {
		t.Fatal("legacy-equivalent kinds are native candidates on the witness", e)
	}
	for name, raw := range map[string][]byte{"offline-only kind": tuning, "unreviewed kind": uraw} {
		if _, e := admitRuntimeFor(raw, "NATIVE_EXECUTION"); codeOf(e) != "PROFILE_KIND_REVIEW_INSUFFICIENT" {
			t.Fatalf("%s: worker execute-once admission: %v", name, e)
		}
		if e := VerifyProfileEvidence(raw, []byte("{}\n")); codeOf(e) != "PROFILE_KIND_REVIEW_INSUFFICIENT" {
			t.Fatalf("%s: --verify: %v", name, e)
		}
	}
	// --authenticate and --profile-state (offline) still admit the Tuning input; its admission cannot be executed.
	offline, e := admitRuntime(tuning)
	if e != nil {
		t.Fatal("offline authentication of the Tuning input", e)
	}
	if _, e := profileStateReport(tuning); e != nil {
		t.Fatal("offline --profile-state of the Tuning input", e)
	}
	f := &countingFence{}
	dir := filepath.Join(t.TempDir(), "out")
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	if _, e := (&Controller{}).Execute(ctx, offline, f, dir); codeOf(e) != "PROFILE_NATIVE_PURPOSE_REQUIRED" || f.checks != 0 {
		t.Fatal("offline Tuning admission reached the controller", e)
	}
	if _, err := os.Stat(dir); !os.IsNotExist(err) {
		t.Fatal("output directory created")
	}
	if _, e := admitRuntime(uraw); codeOf(e) != "PROFILE_KIND_REVIEW_INSUFFICIENT" && codeOf(e) != "PROFILE_UNKNOWN_INTERVENTION" {
		t.Fatal("unreviewed kind admitted offline", e)
	}
}

func TestProfileRuntimeIsolationMatrix(t *testing.T) {
	d := hookr1(t)
	lp, _ := overlaySpec(lpItem(23))
	lp.Schema, lp.Overlay = Domain, nil
	dyn, _ := dynamicFixture()
	over, _ := overlaySpec(dynamicOffItem, lpItem(23))
	_, prof := buildProfileInput(t, syntheticBody(), d, []ProfileIntervention{piDynOff, piLp(23)})
	specs := map[string]Spec{RuntimeProfile: lp, DynamicRuntimeProfile: dyn, OverlayRuntimeProfile: over, ProfileRuntimeProfile: prof}
	for runtime := range specs {
		for owner, s := range specs {
			e := validateRuntimeSpec(s, runtime)
			if (owner == runtime) != (e == nil) {
				t.Fatalf("runtime %s with %s input: %v", runtime, owner, e)
			}
		}
	}
	// A profile input carrying a legacy intervention form, or a legacy input carrying a profile overlay, is no domain.
	mixed := over
	mixed.ProfileOverlay = prof.ProfileOverlay
	raw, _ := Canonical(Commit(mixed.Body))
	if _, e := Parse(append(raw, '\n')); codeOf(e) != "SCENARIO_DOMAIN_OR_COMMITMENT" {
		t.Fatal("mixed overlay forms accepted", e)
	}
	praw, _ := Canonical(prof)
	for name, admitFn := range map[string]func([]byte) (*Admission, error){"LP": Admit, "Dynamic Fee": AdmitDynamic, "config overlay": AdmitOverlay} {
		if _, e := admitFn(append(praw, '\n')); e == nil {
			t.Fatalf("%s admission accepted a profile-overlay input", name)
		}
	}
}

func TestProfileOperationBinding(t *testing.T) {
	d := hookr1(t)
	raw, s := buildProfileInput(t, syntheticBody(), d, []ProfileIntervention{piDynOff, piLp(23)})
	good := map[string]any{"profileDescriptor": map[string]any{"profileId": "hookr-1", "revision": float64(d.Revision), "sha256": d.Sha256()}}
	if e := profileOperationBinding(ProfileRuntimeProfile, raw, good); e != nil {
		t.Fatal(e)
	}
	for name, b := range map[string]map[string]any{
		"missing":        {},
		"other sha256":   {"profileDescriptor": map[string]any{"profileId": "hookr-1", "revision": float64(d.Revision), "sha256": strings.Repeat("f", 64)}},
		"other id":       {"profileDescriptor": map[string]any{"profileId": "hookr-2", "revision": float64(d.Revision), "sha256": d.Sha256()}},
		"other revision": {"profileDescriptor": map[string]any{"profileId": "hookr-1", "revision": float64(d.Revision - 1), "sha256": d.Sha256()}},
	} {
		if e := profileOperationBinding(ProfileRuntimeProfile, raw, b); codeOf(e) != "PROFILE_OPERATION_BINDING" {
			t.Fatalf("%s: %v", name, e)
		}
	}
	if e := profileOperationBinding(OverlayRuntimeProfile, raw, good); codeOf(e) != "PROFILE_OPERATION_BINDING" {
		t.Fatal("a legacy operation must not carry a descriptor binding", e)
	}
	if e := profileOperationBinding(OverlayRuntimeProfile, raw, map[string]any{}); e != nil {
		t.Fatal(e)
	}
	if s.ProfileOverlay.Descriptor.Sha256 != d.Sha256() {
		t.Fatal("prepared input must bind the descriptor")
	}
	if e := offlinePairOnly(ProfileRuntimeProfile, map[string]any{"discoveryProfile": "x"}); codeOf(e) != "PROFILE_OVERLAY_OFFLINE_PAIR_ONLY" {
		t.Fatal(e)
	}
	if _, e := profileStateReport(raw); codeOf(e) != "PROFILE_RUNTIME_REQUIRED" {
		t.Fatal("--profile-state needs the profile-linked worker", e)
	}
}

// Integrated G1: every SDK 0.4 configuration, admitted on the profile path against the accepted witness, gives
// the same common-setup root, the same initial root of both worlds and the same writes as the SDK 0.4 overlay.
func TestProfileIntegratedG1OnWitness(t *testing.T) {
	_, src := acceptedSource(t)
	d := hookr1(t)
	p := overlayProfile()
	var roots []string
	check := func(name string, legacy []TypedIntervention, items []ProfileIntervention) {
		raw, s := buildProfileInput(t, src.Body, d, items)
		a, e := AdmitProfile(raw, "OFFLINE_PREPARATION")
		if e != nil {
			t.Fatalf("%s: %v", name, e)
		}
		base, bf, e := deriveProfileOverlay(a.input, Baseline)
		if e != nil {
			t.Fatal(name, e)
		}
		variant, vf, e := deriveProfileOverlay(a.input, Variant)
		if e != nil {
			t.Fatal(name, e)
		}
		if base.InitialRoot != base.CommonRoot || variant.CommonRoot != base.CommonRoot || variant.InitialRoot == base.InitialRoot {
			t.Fatalf("%s: BASELINE must be the common setup; VARIANT must differ", name)
		}
		if base.Intervention != s.ProfileOverlay.Commitment || variant.ProfileDescriptor != d.Sha256() || len(base.Writes) != len(variant.Writes) {
			t.Fatalf("%s: overlay record binding", name)
		}
		for i, w := range variant.Writes {
			if base.Writes[i].After != w.Before || base.Writes[i].Before != w.Before {
				t.Fatalf("%s: BASELINE received a write", name)
			}
		}
		for k, v := range bf {
			assigned := false
			for _, item := range s.ProfileOverlay.Interventions {
				for _, asg := range d.kinds[item.Kind].Assign {
					assigned = assigned || asg.Field == k
				}
			}
			if !assigned && v.Cmp(vf[k]) != 0 {
				t.Fatalf("%s: unassigned field %s changed", name, k)
			}
		}
		if bf["rootRecaptureFlag"].Uint64() != 1 || vf["rootRecaptureFlag"].Uint64() != 1 || vf["rootFlagsReserved"].Sign() != 0 {
			t.Fatalf("%s: Root flags", name)
		}
		if legacy != nil {
			la, e := AdmitOverlay(overlayFromSource(t, src, p, legacy...))
			if e != nil {
				t.Fatal(name, e)
			}
			lbase, _, e := deriveConfigOverlay(la.input, Baseline)
			if e != nil {
				t.Fatal(e)
			}
			lvar, lvf, e := deriveConfigOverlay(la.input, Variant)
			if e != nil {
				t.Fatal(e)
			}
			if lbase.CommonRoot != base.CommonRoot || lvar.InitialRoot != variant.InitialRoot || !canonicalEqual(lvar.Writes, variant.Writes) ||
				lvar.Before != variant.Before || lvar.After != variant.After || lvar.Account != variant.Account || lvar.Slot != variant.Slot {
				t.Fatalf("%s: differs from the SDK 0.4 overlay", name)
			}
			mode := vf["rootDynamicFeeFlag"].Uint64() | vf["rootRecaptureFlag"].Uint64()<<1 | vf["rootFlagsReserved"].Uint64()<<2
			if vf["lpBps"].Uint64() != lvf.LpBps || vf["maxFeePips"].Uint64() != lvf.MaxFeePips || vf["dynamicFeeSens"].Uint64() != lvf.Sensitivity || mode != lvf.Mode {
				t.Fatalf("%s: read-back fields", name)
			}
		}
		roots = append(roots, variant.InitialRoot.Hex())
	}
	for _, legacy := range legacyRows() {
		check(strings.TrimSpace(strings.ReplaceAll(strings.ReplaceAll(func() string { b, _ := json.Marshal(legacy); return string(b) }(), "\"", ""), ",", " ")), legacy, toProfile(legacy))
	}
	check("tuning 8000/1", nil, []ProfileIntervention{piTuning(8000, 1)})
	check("tuning 8000/1 + LP23", nil, []ProfileIntervention{piTuning(8000, 1), piLp(23)})
	raw, _ := Canonical(roots)
	t.Logf("G1_INTEGRATED_WITNESS configurations=%d probes=2 initialRootsSha256=%s", len(roots)-2, digest(raw))
	if len(roots) != 203 {
		t.Fatal("count")
	}
}

// State overlay safety on the real StateDB: code, balances and nonces of every declared contract and of the
// actor are identical between BASELINE and VARIANT; only declared target words differ.
func TestProfileOverlaySafetyOnWitness(t *testing.T) {
	_, src := acceptedSource(t)
	d := hookr1(t)
	raw, _ := buildProfileInput(t, src.Body, d, []ProfileIntervention{piDynOff, piLp(23)})
	a, e := AdmitProfile(raw, "OFFLINE_PREPARATION")
	if e != nil {
		t.Fatal(e)
	}
	type view struct {
		codes, balances, nonces []string
		words                   map[string][]common.Hash
	}
	read := func(label string) view {
		b, e := openBridge(a.input)
		if e != nil {
			t.Fatal(e)
		}
		defer prestate.CloseScenarioBridge(b)
		var v view
		e = b.Protect(func() error {
			st, _, _, e := initializeWorld(b, a.input, label)
			if e != nil {
				return e
			}
			accounts := []common.Address{a.input.spec.Setup.Actor}
			for _, c := range d.Contracts {
				accounts = append(accounts, c.Address)
			}
			for _, x := range accounts {
				v.codes = append(v.codes, st.GetCodeHash(x).Hex())
				v.balances = append(v.balances, st.GetBalance(x).String())
				v.nonces = append(v.nonces, new(big.Int).SetUint64(st.GetNonce(x)).String())
			}
			v.words = map[string][]common.Hash{}
			for _, t2 := range d.Targets {
				for i := uint64(0); i < t2.Words; i++ {
					v.words[t2.Name] = append(v.words[t2.Name], st.GetState(d.contracts[t2.Contract].Address, wordAt(t2.Slot, int(i))))
				}
			}
			return st.Error()
		})
		if e != nil {
			t.Fatal(e)
		}
		return v
	}
	base, variant := read(Baseline), read(Variant)
	if !canonicalEqual(base.codes, variant.codes) || !canonicalEqual(base.balances, variant.balances) || !canonicalEqual(base.nonces, variant.nonces) {
		t.Fatal("code, balance or nonce changed between worlds")
	}
	c, _ := d.ComposeProfile([]ProfileIntervention{piDynOff, piLp(23)}, d.OriginalsFromDescriptor())
	for _, t2 := range d.Targets {
		for i := range base.words[t2.Name] {
			if base.words[t2.Name][i] != common.BigToHash(d.OriginalsFromDescriptor()[t2.Name][i]) || variant.words[t2.Name][i] != c.Words[t2.Name][i] {
				t.Fatalf("%s[%d]: target words", t2.Name, i)
			}
		}
	}
	if variant.words["rootRecord"][0] != dynamicRootOff || new(big.Int).Xor(base.words["rootRecord"][0].Big(), variant.words["rootRecord"][0].Big()).Cmp(new(big.Int).Lsh(big.NewInt(1), 248)) != 0 {
		t.Fatal("Root record must change in bit 248 only")
	}
}

type parityRow struct {
	Name    string `json:"name"`
	Check   string `json:"check"`
	Legacy  string `json:"legacy"`
	Profile string `json:"profile"`
	Stage   string `json:"stage"`
}

// Admission parity: one refusal per SDK 0.4 admission check, applied identically to the SDK 0.4 overlay input
// and to the profile input of the same intervention set (LP23 + Dynamic Fee OFF).
func TestProfileAdmissionParity(t *testing.T) {
	_, src := acceptedSource(t)
	d := hookr1(t)
	pp, e := profileFromDescriptor(d)
	if e != nil {
		t.Fatal(e)
	}
	items := []ProfileIntervention{piDynOff, piLp(23)}
	legacyItems := []TypedIntervention{dynamicOffItem, lpItem(23)}
	key, _ := crypto.ToECDSA(crypto.Keccak256([]byte(boundSeed)))
	if crypto.PubkeyToAddress(key.PublicKey) != src.Setup.Actor {
		t.Fatal("compiled seed must derive the accepted simulation actor")
	}
	resign := func(b *Body, edit func(*types.LegacyTx)) {
		var tx types.Transaction
		if e := tx.UnmarshalBinary(b.Actions[0].Raw); e != nil {
			t.Fatal(e)
		}
		inner := &types.LegacyTx{Nonce: tx.Nonce(), GasPrice: tx.GasPrice(), Gas: tx.Gas(), To: tx.To(), Value: tx.Value(), Data: tx.Data()}
		edit(inner)
		signed, e := types.SignNewTx(key, types.LatestSignerForChainID(big.NewInt(4663)), inner)
		if e != nil {
			t.Fatal(e)
		}
		raw, _ := signed.MarshalBinary()
		b.Actions = append([]Action{}, b.Actions...)
		b.Actions[0].Raw = raw
		b.Actions[0].ID = ActionID(b.Actions[0])
	}
	cloneActions := func(b *Body) { b.Actions = append([]Action{}, b.Actions...) }
	// repoint edits the checkpoint header JSON and re-points the checkpoint at the edited header, so the header
	// identity check passes and the check under test is the one that refuses.
	repoint := func(b *Body, edit func(map[string]json.RawMessage)) {
		var m map[string]json.RawMessage
		if e := json.Unmarshal(b.Parent, &m); e != nil {
			t.Fatal(e)
		}
		edit(m)
		delete(m, "hash")
		b.Parent, _ = json.Marshal(m)
		var h types.Header
		if e := json.Unmarshal(b.Parent, &h); e != nil {
			t.Fatal(e)
		}
		b.Checkpoint.BlockHash = h.Hash()
	}
	chainConfig := func(b *Body, edit func(map[string]any)) {
		var m map[string]any
		dec := json.NewDecoder(bytes.NewReader(b.ChainConfig))
		dec.UseNumber()
		if e := dec.Decode(&m); e != nil {
			t.Fatal(e)
		}
		edit(m)
		raw, e := Canonical(m)
		if e != nil {
			t.Fatal(e)
		}
		b.ChainConfig = raw
	}
	pinned := map[common.Hash]bool{crypto.Keccak256Hash(params.HistoryStorageCodeArbitrum): true}
	for _, h := range pp.Pins {
		pinned[h] = true
	}
	cases := []struct {
		name, check string
		body        func(*Body)
		prof        func(*profile)
		want        string
	}{
		{"two actions", "on-demand shape (single buy, public actor)", func(b *Body) { b.Actions = append(append([]Action{}, b.Actions...), b.Actions[0]) }, nil, "ON_DEMAND_SINGLE_BUY_AND_PUBLIC_ACTOR_REQUIRED"},
		{"other actor", "on-demand shape (single buy, public actor)", func(b *Body) { b.Setup.Actor = common.HexToAddress("0x01") }, nil, "ON_DEMAND_SINGLE_BUY_AND_PUBLIC_ACTOR_REQUIRED"},
		{"chain 4664", "chain identity", func(b *Body) { b.Checkpoint.ChainID = 4664 }, nil, "PROFILE_IDENTITY"},
		{"other pool", "pool identity", func(b *Body) { b.Pool = common.HexToHash("0x01") }, nil, "PROFILE_IDENTITY"},
		{"other release", "release manifest", func(b *Body) { b.Release = strings.Repeat("a", 64) }, nil, "PROFILE_IDENTITY"},
		{"unpinned engine", "engine pins", func(b *Body) { b.Engine.Binary = strings.Repeat("0", 64) }, nil, "PROFILE_IDENTITY"},
		{"other limits", "resource policy", func(b *Body) { b.Limits.Wall = 121 }, nil, "PROFILE_IDENTITY"},
		{"header number", "checkpoint header", func(b *Body) { b.Checkpoint.BlockNumber++ }, nil, "CHECKPOINT_HEADER"},
		{"state root", "checkpoint header", func(b *Body) { b.Checkpoint.StateRoot = common.HexToHash("0x01") }, nil, "CHECKPOINT_HEADER"},
		{"header extension", "header extensions", func(b *Body) {
			// The extension changes the header hash; the checkpoint is re-pointed at it so the extension
			// check, not the header check, is the one that refuses.
			var m map[string]json.RawMessage
			_ = json.Unmarshal(b.Parent, &m)
			m["withdrawalsRoot"] = json.RawMessage(`"0x` + strings.Repeat("00", 32) + `"`)
			delete(m, "hash")
			b.Parent, _ = json.Marshal(m)
			var h types.Header
			if e := json.Unmarshal(b.Parent, &h); e != nil {
				t.Fatal(e)
			}
			b.Checkpoint.BlockHash = h.Hash()
		}, nil, "UNSUPPORTED_HEADER_EXTENSION"},
		{"parent hash metadata", "header metadata", func(b *Body) {
			var m map[string]json.RawMessage
			_ = json.Unmarshal(b.Parent, &m)
			m["hash"] = json.RawMessage(`"0x` + strings.Repeat("11", 32) + `"`)
			b.Parent, _ = json.Marshal(m)
		}, nil, "PARENT_HASH_METADATA"},
		{"parent L1 metadata", "header metadata", func(b *Body) {
			var m map[string]json.RawMessage
			_ = json.Unmarshal(b.Parent, &m)
			m["l1BlockNumber"] = json.RawMessage(`"0x1"`)
			b.Parent, _ = json.Marshal(m)
		}, nil, "PARENT_L1_METADATA"},
		{"header ArbOS format 60", "ArbOS version (header)", func(b *Body) {
			repoint(b, func(m map[string]json.RawMessage) {
				var mix common.Hash
				_ = json.Unmarshal(m["mixHash"], &mix)
				binary.BigEndian.PutUint64(mix[16:24], 60)
				m["mixHash"], _ = json.Marshal(mix)
			})
		}, nil, "SCENARIO_ENVIRONMENT"},
		{"header gas limit below the action", "chain gas capacity", func(b *Body) {
			repoint(b, func(m map[string]json.RawMessage) { m["gasLimit"] = json.RawMessage(`"0x5b8d80"`) })
		}, nil, "ACTION_CHAIN_GAS_CAPACITY"},
		{"chain config field", "chain config (ArbOS)", func(b *Body) {
			chainConfig(b, func(m map[string]any) { m["shanghaiTime"] = json.Number("0") })
		}, nil, "UNSUPPORTED_CHAIN_CONFIG_FIELD"},
		{"chain config id", "chain config (ArbOS)", func(b *Body) {
			chainConfig(b, func(m map[string]any) { m["chainId"] = json.Number("4664") })
		}, nil, "INCORRECT_CHAIN_CONFIG_OR_ARBOS_VERSION"},
		{"chain config Nitro parameters", "chain config (ArbOS)", func(b *Body) {
			chainConfig(b, func(m map[string]any) { m["arbitrum"].(map[string]any)["InitialArbOSVersion"] = json.Number("50") })
		}, nil, "UNSUPPORTED_NITRO_CHAIN_CONFIG"},
		{"chain config differs from the authenticated ArbOS state", "authenticated ArbOS config", func(b *Body) {
			chainConfig(b, func(m map[string]any) {
				m["arbitrum"].(map[string]any)["InitialChainOwner"] = "0x0000000000000000000000000000000000000001"
			})
		}, nil, "AUTHENTICATED_ARBOS_CONFIG"},
		{"environment time", "transaction environment", func(b *Body) { b.Environment.Time++ }, nil, "SCENARIO_ENVIRONMENT"},
		{"L1 base fee", "transaction environment", func(b *Body) { b.Environment.L1BaseFee = "2" }, nil, "SCENARIO_ENVIRONMENT"},
		{"poster", "transaction environment", func(b *Body) { b.Environment.Poster = common.HexToAddress("0x02") }, nil, "SCENARIO_ENVIRONMENT"},
		{"funding", "common setup", func(b *Body) { b.Setup.Funding = "2000000000000000000" }, nil, "COMMON_SETUP"},
		{"actor may exist", "common setup", func(b *Body) { b.Setup.RequireAbsent = false }, nil, "COMMON_SETUP"},
		{"action gas", "action contract", func(b *Body) { cloneActions(b); b.Actions[0].Gas = 7000000; b.Actions[0].ID = ActionID(b.Actions[0]) }, nil, "ACTION_CONTRACT"},
		{"action deadline", "action contract", func(b *Body) { cloneActions(b); b.Actions[0].Deadline++; b.Actions[0].ID = ActionID(b.Actions[0]) }, nil, "ACTION_CONTRACT"},
		{"action id", "action contract", func(b *Body) { cloneActions(b); b.Actions[0].ID = strings.Repeat("a", 64) }, nil, "ACTION_CONTRACT"},
		{"gas price", "gas price", func(b *Body) { cloneActions(b); b.Actions[0].GasPrice = "1"; b.Actions[0].ID = ActionID(b.Actions[0]) }, nil, "GAS_PRICE"},
		{"transaction to another address", "action calldata and transaction shape", func(b *Body) {
			resign(b, func(tx *types.LegacyTx) { x := common.HexToAddress("0x03"); tx.To = &x })
		}, nil, "ACTION_TRANSACTION_MAPPING"},
		{"transaction calldata", "action calldata and transaction shape", func(b *Body) {
			resign(b, func(tx *types.LegacyTx) { tx.Data = append(append([]byte{}, tx.Data...), 0) })
		}, nil, "ACTION_TRANSACTION_MAPPING"},
		{"transaction value", "action calldata and transaction shape", func(b *Body) {
			resign(b, func(tx *types.LegacyTx) { tx.Value = big.NewInt(1) })
		}, nil, "ACTION_TRANSACTION_MAPPING"},
		{"declared funding below the spend", "declared funding", func(b *Body) {
			cloneActions(b)
			b.Actions[0].GasPrice = "1000000000000"
			resign(b, func(tx *types.LegacyTx) { tx.GasPrice = big.NewInt(1000000000000) })
		}, nil, "INSUFFICIENT_DECLARED_FUNDING"},
		{"unpinned code preimages removed", "witness completeness (token code preimage)", func(b *Body) {
			var codes []hexutil.Bytes
			for _, c := range b.Inventory.Codes {
				if pinned[crypto.Keccak256Hash(c)] {
					codes = append(codes, c)
				}
			}
			if len(codes) == len(b.Inventory.Codes) {
				t.Fatal("expected an unpinned (token) code preimage in the witness")
			}
			b.Inventory.Codes = codes
		}, nil, "CODE_SOURCE_UNAVAILABLE"},
		{"inventory order", "witness inventory", func(b *Body) {
			n := append([]hexutil.Bytes{}, b.Inventory.Nodes...)
			n[0], n[1] = n[1], n[0]
			b.Inventory.Nodes = n
		}, nil, "INVENTORY_ORDER_OR_LIMIT"},
		{"root preimage missing", "witness completeness", func(b *Body) {
			var parent types.Header
			_ = json.Unmarshal(b.Parent, &parent)
			var n []hexutil.Bytes
			for _, x := range b.Inventory.Nodes {
				if crypto.Keccak256Hash(x) != parent.Root {
					n = append(n, x)
				}
			}
			b.Inventory.Nodes = n
		}, nil, "CHECKPOINT_ROOT_PREIMAGE_REQUIRED"},
		{"witness without state", "witness completeness (history precondition)", func(b *Body) {
			var parent types.Header
			_ = json.Unmarshal(b.Parent, &parent)
			for _, x := range b.Inventory.Nodes {
				if crypto.Keccak256Hash(x) == parent.Root {
					b.Inventory.Nodes = []hexutil.Bytes{x}
				}
			}
		}, nil, "HISTORY_STORAGE_PRECONDITION"},
		{"release code identity", "pinned release code", nil, func(p *profile) { p.Pins[p.Rules] = common.HexToHash("0x01") }, "RELEASE_CODE_IDENTITY"},
		{"router identity", "pinned router", nil, func(p *profile) { p.Router = common.HexToAddress("0x04") }, "ACTION_TRANSACTION_MAPPING"},
		{"standard pool binding", "standard pool binding", nil, func(p *profile) { p.Rules = common.HexToAddress("0x05") }, "STANDARD_POOL_BINDING"},
		{"root caps", "Root caps", nil, func(p *profile) { p.RootCaps = common.HexToHash("0x01") }, "FIRST_PROFILE_POOL_CAPS"},
		// SDK 0.4 also derives its variant Root word from the base fee, so it refuses one step earlier.
		{"base fee", "Root base fee", nil, func(p *profile) { p.BaseLpFee = 2999 }, "FIRST_PROFILE_POOL_CAPS"},
	}
	// Only where SDK 0.4 refuses earlier for a documented reason; otherwise both paths name the same check.
	// SDK 0.4 binds the base fee into its variant Root word and the Rules/Root pins into its overlay record.
	legacyEarlier := map[string]string{"base fee": "CONFIG_OVERLAY_VARIANT_WORD", "release code identity": "CONFIG_OVERLAY_BINDING"}
	// Only where the profile path adds a stricter check that refuses first (see the combined case below).
	profileEarlier := map[string]string{"chain config differs from the authenticated ArbOS state": "PROFILE_CHAIN_CONFIG"}
	var rows []parityRow
	for _, c := range cases {
		lb, pb := src.Body, src.Body
		if c.body != nil {
			c.body(&lb)
			c.body(&pb)
		}
		lp, lpp := overlayProfile(), pp
		lp.Pins, lpp.Pins = map[common.Address]common.Hash{}, map[common.Address]common.Hash{}
		for k, v := range overlayProfile().Pins {
			lp.Pins[k] = v
		}
		for k, v := range pp.Pins {
			lpp.Pins[k] = v
		}
		if c.prof != nil {
			c.prof(&lp)
			c.prof(&lpp)
		}
		_, le := admit(overlayFromSource(t, Spec{Body: lb}, overlayProfile(), legacyItems...), lp)
		praw, _ := buildProfileInput(t, pb, d, items)
		_, pe := admit(praw, lpp)
		lc, pc := firstWord(le), firstWord(pe)
		lw := legacyEarlier[c.name]
		if lw == "" {
			lw = c.want
		}
		pw := profileEarlier[c.name]
		if pw == "" {
			pw = c.want
		}
		if lc != lw || pc != pw {
			t.Errorf("%s: legacy %v, profile %v, want %s / %s", c.name, le, pe, lw, pw)
		}
		rows = append(rows, parityRow{c.name, c.check, lc, pc, "admission"})
	}
	// Descriptor-level originals: the profile path refuses at the same legacy check, or at its own added one.
	for _, c := range []struct {
		name, check string
		edit        func(map[string]any)
		items       []ProfileIntervention
		want        string
	}{
		{"reviewed Root caps word differs from the witness", "Root caps (descriptor EXACT word)", func(v map[string]any) { setExact(v, "rootRecord", 1, "0x01") }, items, "FIRST_PROFILE_POOL_CAPS"},
		{"reviewed Rules word 2 differs from the witness", "authenticated exact original words", func(v map[string]any) { setExact(v, "rulesConfig", 2, "0x01") }, items, "AUTHENTICATED_BASELINE_WORD"},
		{"reviewed Root word differs from the witness", "authenticated exact original words (Root)", func(v map[string]any) {
			setExact(v, "rootRecord", 0, "0x010101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942")
		}, []ProfileIntervention{piLp(23)}, "PROFILE_ORIGINAL_WORD"},
		{"reviewed Rules code hash differs from the release manifest", "pinned release code (descriptor)", func(v map[string]any) {
			for _, c := range v["contracts"].([]any) {
				if c := c.(map[string]any); c["name"] == "rules" {
					c["runtimeCodeHash"] = "0x" + strings.Repeat("01", 32)
				}
			}
		}, items, "DESCRIPTOR_CONTRACT"},
	} {
		raw := mutateDescriptor(t, c.edit)
		alt, e := ParseDescriptor(raw)
		if e != nil {
			// The descriptor schema itself refuses this edit; nothing reaches admission.
			rows = append(rows, parityRow{c.name, c.check, "NOT_EXPRESSIBLE_WITHOUT_CODE_CHANGE", firstWord(e), "descriptor parse"})
			if firstWord(e) != c.want {
				t.Errorf("%s: want %s, got %v", c.name, c.want, e)
			}
			continue
		}
		praw, _ := buildProfileInput(t, src.Body, alt, c.items)
		_, pe := admitProfileWith(praw, "OFFLINE_PREPARATION", testLoader(t, raw, "OFFLINE_PREPARATION"))
		if firstWord(pe) != "PROFILE_WORKER_BOUNDS" {
			t.Errorf("%s: the compiled bounds must refuse first, got %v", c.name, pe)
		}
		rows = append(rows, parityRow{c.name, c.check, "NOT_EXPRESSIBLE_WITHOUT_CODE_CHANGE", firstWord(pe), "worker bounds (descriptor)"})
		// Defence in depth: with the bounds bypassed, the shared admission still refuses at the legacy check.
		bp := alt.legacyProfile()
		bp.Kind, bp.descriptor = ProfileKind, alt
		_, be := admit(praw, bp)
		if firstWord(be) != c.want {
			t.Errorf("%s (bounds bypassed): want %s, got %v", c.name, c.want, be)
		}
		rows = append(rows, parityRow{c.name + " (bounds bypassed)", c.check, "NOT_EXPRESSIBLE_WITHOUT_CODE_CHANGE", firstWord(be), "admission behind the bounds"})
	}
	// The descriptor's chainConfigSha256 adds a check; it does not replace the ArbOS state check. A descriptor
	// that names an edited chain configuration still stops at AUTHENTICATED_ARBOS_CONFIG.
	{
		pb := src.Body
		chainConfig(&pb, func(m map[string]any) {
			m["arbitrum"].(map[string]any)["InitialChainOwner"] = "0x0000000000000000000000000000000000000001"
		})
		raw := mutateDescriptor(t, func(v map[string]any) { v["chain"].(map[string]any)["chainConfigSha256"] = digest(pb.ChainConfig) })
		alt, e := ParseDescriptor(raw)
		if e != nil {
			t.Fatal(e)
		}
		praw, _ := buildProfileInput(t, pb, alt, items)
		_, pe := admitProfileWith(praw, "OFFLINE_PREPARATION", testLoader(t, raw, "OFFLINE_PREPARATION"))
		if firstWord(pe) != "PROFILE_WORKER_BOUNDS" {
			t.Errorf("descriptor naming an edited chain config: %v", pe)
		}
		bp := alt.legacyProfile()
		bp.Kind, bp.descriptor = ProfileKind, alt
		_, be := admit(praw, bp)
		if firstWord(be) != "AUTHENTICATED_ARBOS_CONFIG" {
			t.Errorf("descriptor naming an edited chain config (bounds bypassed): %v", be)
		}
		_, pe2 := admitProfileWith(praw, "OFFLINE_PREPARATION", testLoader(t, hookr1DescriptorRaw, "OFFLINE_PREPARATION"))
		rows = append(rows, parityRow{"descriptor names the edited chain config", "chain config hash (worker bounds)",
			"NOT_EXPRESSIBLE_WITHOUT_CODE_CHANGE", firstWord(pe), "worker bounds (descriptor + input)"})
		rows = append(rows, parityRow{"descriptor names the edited chain config (bounds bypassed)", "authenticated ArbOS config (descriptor and input agree)",
			"AUTHENTICATED_ARBOS_CONFIG", firstWord(be), "admission behind the bounds"})
		if firstWord(pe2) != "PROFILE_SPEC_BINDING" {
			t.Errorf("input bound to another descriptor: %v", pe2)
		}
	}
	// Transaction-filter precondition (the private saved-root fixture of TestSavedCheckpointStopsBeforeProducerOnFilterGap
	// is not shipped): the same gap is built on the accepted witness by removing the filter account's storage-root node.
	{
		a, e := AdmitProfile(func() []byte { r, _ := buildProfileInput(t, src.Body, d, items); return r }(), "OFFLINE_PREPARATION")
		if e != nil {
			t.Fatal(e)
		}
		br, e := openBridge(a.input)
		if e != nil {
			t.Fatal(e)
		}
		var root common.Hash
		e = br.Protect(func() error {
			st, err := br.State()
			if err != nil {
				return err
			}
			root = st.GetStorageRoot(types.FilteredTransactionsStateAddress)
			return st.Error()
		})
		prestate.CloseScenarioBridge(br)
		if e != nil || root == types.EmptyRootHash || root == (common.Hash{}) {
			t.Fatal("filter account storage root", e)
		}
		gap := src.Body
		gap.Inventory.Nodes = nil
		for _, n := range src.Body.Inventory.Nodes {
			if crypto.Keccak256Hash(n) != root {
				gap.Inventory.Nodes = append(gap.Inventory.Nodes, n)
			}
		}
		praw, _ := buildProfileInput(t, gap, d, items)
		_, pe := admit(praw, pp)
		_, le := admit(overlayFromSource(t, Spec{Body: gap}, overlayProfile(), legacyItems...), overlayProfile())
		if firstWord(pe) != "TRANSACTION_FILTER_PRECONDITION" || firstWord(le) != "TRANSACTION_FILTER_PRECONDITION" {
			t.Errorf("filter gap: legacy %v, profile %v", le, pe)
		}
		rows = append(rows, parityRow{"filter account storage root removed", "system precondition (transaction filter)", firstWord(le), firstWord(pe), "admission"})
	}
	// Prepared-input tampering (re-committed): each path refuses with its own intervention validator.
	for _, c := range []struct {
		name, check, legacyWant, want string
		edit                          func(*Body)
	}{
		{"BASELINE configuration word changed", "forbidden baseline changes", "CONFIG_OVERLAY_ORIGINAL_CONFIG", "PROFILE_SPEC_VARIANT_WORD",
			func(b *Body) {
				b.Configs.Baseline = append([]common.Hash{}, b.Configs.Baseline...)
				b.Configs.Baseline[1] = common.HexToHash("0x01")
			}},
		{"VARIANT word outside the declared fields", "undeclared bits / unrelated words", "CONFIG_OVERLAY_UNRELATED_CONFIG", "PROFILE_SPEC_VARIANT_WORD",
			func(b *Body) {
				b.Configs.Variant = append([]common.Hash{}, b.Configs.Variant...)
				b.Configs.Variant[3] = common.HexToHash("0x01")
			}},
	} {
		lraw := overlayFromSource(t, src, overlayProfile(), legacyItems...)
		praw, _ := buildProfileInput(t, src.Body, d, items)
		recommit := func(raw []byte) []byte {
			s, e := Parse(raw)
			if e != nil {
				t.Fatal(e)
			}
			c.edit(&s.Body)
			out, _ := Canonical(Commit(s.Body))
			return append(out, '\n')
		}
		_, le := admit(recommit(lraw), overlayProfile())
		_, pe := admit(recommit(praw), pp)
		if firstWord(le) != c.legacyWant || firstWord(pe) != c.want {
			t.Errorf("%s: legacy %v (want %s), profile %v (want %s)", c.name, le, c.legacyWant, pe, c.want)
		}
		rows = append(rows, parityRow{c.name, c.check, firstWord(le), firstWord(pe), "admission (prepared input)"})
	}
	if out := os.Getenv("RHOOK_PARITY_OUT"); out != "" {
		raw, _ := Canonical(rows)
		if e := os.WriteFile(out, append(raw, '\n'), 0o600); e != nil {
			t.Fatal(e)
		}
	}
	t.Logf("ADMISSION_PARITY cases=%d", len(rows))
}

// The controller never runs a profile-overlay admission that was not admitted for NATIVE_EXECUTION through the
// review-gated loader: neither an offline preparation nor an admission built without the loader reaches Nitro.
func TestProfileControllerRequiresNativePurpose(t *testing.T) {
	_, src := acceptedSource(t)
	d := hookr1(t)
	raw, _ := buildProfileInput(t, src.Body, d, []ProfileIntervention{piDynOff, piLp(23)})
	offline, e := AdmitProfile(raw, "OFFLINE_PREPARATION")
	if e != nil {
		t.Fatal(e)
	}
	pp, _ := profileFromDescriptor(d)
	direct, e := admit(raw, pp)
	if e != nil {
		t.Fatal(e)
	}
	for name, a := range map[string]*Admission{"offline preparation": offline, "admitted without the loader": direct} {
		f := &countingFence{}
		dir := filepath.Join(t.TempDir(), "out")
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		_, e := (&Controller{}).Execute(ctx, a, f, dir)
		cancel()
		if codeOf(e) != "PROFILE_NATIVE_PURPOSE_REQUIRED" || f.checks != 0 {
			t.Fatalf("%s: %v (fence checks %d)", name, e, f.checks)
		}
		if _, err := os.Stat(dir); !os.IsNotExist(err) {
			t.Fatalf("%s: output directory created before the refusal", name)
		}
	}
}

type countingFence struct{ checks int }

func (f *countingFence) Check(context.Context, Identity, string) error { f.checks++; return nil }

// Per-kind review: an offline-only kind stays offline-only even under a descriptor review admitting native use.
func TestProfileKindReview(t *testing.T) {
	d := hookr1(t)
	native := testLoader(t, hookr1DescriptorRaw, "OFFLINE_PREPARATION", "NATIVE_EXECUTION")
	tuning, _ := buildProfileInput(t, syntheticBody(), d, []ProfileIntervention{piTuning(8000, 1)})
	if _, e := profileForInput(tuning, "NATIVE_EXECUTION", native); codeOf(e) != "PROFILE_KIND_REVIEW_INSUFFICIENT" {
		t.Fatal("offline-probe kind admitted for native execution", e)
	}
	if _, e := profileForInput(tuning, "OFFLINE_PREPARATION", native); e != nil {
		t.Fatal(e)
	}
	both, _ := buildProfileInput(t, syntheticBody(), d, []ProfileIntervention{piDynOff, piLp(23)})
	if _, e := profileForInput(both, "NATIVE_EXECUTION", native); e != nil {
		t.Fatal(e)
	}
	kinds := testKinds(t)
	kinds["LP_REWARDS_BPS"] = "TEST_ONLY_UNKNOWN_STATUS"
	if _, e := profileForInput(both, "OFFLINE_PREPARATION", testLoaderKinds(t, hookr1DescriptorRaw, kinds, "OFFLINE_PREPARATION")); codeOf(e) != "PROFILE_CATALOGUE" {
		t.Fatal("unknown per-kind status accepted", e)
	}
}

func setExact(v map[string]any, target string, word int, value string) {
	h := common.HexToHash(value).Hex()
	for _, w := range v["originalState"].(map[string]any)["words"].([]any) {
		w := w.(map[string]any)
		if w["target"] == target && w["word"] == json.Number(strconv.Itoa(word)) {
			w["value"] = h
		}
	}
}

func firstWord(e error) string {
	if e == nil {
		return "ACCEPTED"
	}
	s := e.Error()
	if i := strings.IndexAny(s, " :"); i > 0 {
		return s[:i]
	}
	return s
}

// coherentWorld builds a synthetic world record that passes every per-world coherence check of the verifier
// (synthetic header, system transaction, action mapping, receipts, roots, blooms). It carries no execution
// result: like SDK 0.4, the verifier checks record coherence and re-derives the overlay; it does not re-run
// the EVM or prove that a producer ran. These records exist only to reach the overlay check of both worlds.
func coherentWorld(t *testing.T, s Spec, label string, o Overlay) *WorldResult {
	t.Helper()
	var parent types.Header
	if e := parent.UnmarshalJSON(s.Parent); e != nil {
		t.Fatal(e)
	}
	fee, e := decimal(s.Environment.L1BaseFee)
	if e != nil {
		t.Fatal(e)
	}
	h := &types.Header{ParentHash: s.Checkpoint.BlockHash, Number: new(big.Int).SetUint64(s.Environment.Number), Time: s.Environment.Time, Difficulty: big.NewInt(1)}
	system := types.NewTx(arbos.InternalTxStartBlock(big.NewInt(4663), fee, s.Environment.L1Number, h, &parent))
	txs := types.Transactions{system}
	w := &WorldResult{World: label, Scenario: s.Commitment, Overlay: o, SystemTransaction: system.Hash(), ActorBalanceBefore: s.Setup.Funding,
		ActorBalanceAfter: "0", ActorNonceAfter: uint64(len(s.Actions)), Witness: strings.Repeat("c", 64), ObservedDeltas: "TEST_ONLY_SYNTHETIC"}
	for j, a := range s.Actions {
		tx := new(types.Transaction)
		if e := tx.UnmarshalBinary(a.Raw); e != nil {
			t.Fatal(e)
		}
		txs = append(txs, tx)
		w.Actions = append(w.Actions, ActionMapping{ID: a.ID, Ordinal: j + 1, Hash: tx.Hash()})
	}
	var gas uint64
	for j, tx := range txs {
		gas += 21000
		r := &types.Receipt{Type: tx.Type(), Status: 1, CumulativeGasUsed: gas, GasUsed: 21000, TxHash: tx.Hash(), Logs: []*types.Log{}, TransactionIndex: uint(j)}
		r.Bloom = types.CreateBloom(r)
		w.Receipts = append(w.Receipts, r)
	}
	w.ReceiptsRoot = types.DeriveSha(w.Receipts, trie.NewStackTrie(nil))
	h.TxHash, h.ReceiptHash, h.Root, h.GasUsed, h.Bloom = types.DeriveSha(txs, trie.NewStackTrie(nil)), w.ReceiptsRoot, common.HexToHash("0xabc"), gas, types.MergeBloom(w.Receipts)
	w.StateRoot, w.Header = h.Root, h
	for _, r := range w.Receipts {
		r.BlockHash, r.BlockNumber = h.Hash(), h.Number
	}
	return w
}

// Evidence binding and tampering. Both worlds are coherent synthetic records (coherentWorld), so the verifier
// reaches the descriptor-derived overlay check of each world; a native run (G5) is still the only positive
// evidence. Every overlay, descriptor or domain tamper is refused.
func TestProfileEvidenceBindingAndTamper(t *testing.T) {
	dir, src := acceptedSource(t)
	d := hookr1(t)
	native := testLoader(t, hookr1DescriptorRaw, "OFFLINE_PREPARATION", "NATIVE_EXECUTION")
	raw, s := buildProfileInput(t, src.Body, d, []ProfileIntervention{piDynOff, piLp(23)})
	a, e := admitProfileWith(raw, "NATIVE_EXECUTION", native)
	if e != nil {
		t.Fatal(e)
	}
	base, _, e := deriveProfileOverlay(a.input, Baseline)
	if e != nil {
		t.Fatal(e)
	}
	variant, _, e := deriveProfileOverlay(a.input, Variant)
	if e != nil {
		t.Fatal(e)
	}
	outcome := func(edit func(*Outcome)) []byte {
		o := Outcome{Schema: ProfileDomain + "/evidence", Scenario: s.Commitment, Profile: ProfileKind, Status: "SCENARIO_EXECUTED_UNQUALIFIED",
			Worlds:              []*WorldResult{coherentWorld(t, s, Baseline, base), coherentWorld(t, s, Variant, variant)},
			ProducerInvocations: 2, Cleanup: true, ExternalDelivery: "HOLD"}
		if edit != nil {
			edit(&o)
		}
		o.Commitment = ""
		o.Commitment = hashValue(o.Schema, o)
		out, _ := Canonical(o)
		return append(out, '\n')
	}
	verify := func(input, output []byte) error {
		p, e := profileForInput(input, "NATIVE_EXECUTION", native)
		if e != nil {
			return e
		}
		return verifyEvidence(input, output, p)
	}
	if e := verify(raw, outcome(nil)); e != nil {
		t.Fatal("coherent records with the derived overlays must reach the end of the verifier", e)
	}
	for name, edit := range map[string]func(*Outcome){
		"VARIANT given the BASELINE overlay": func(o *Outcome) { v := *o.Worlds[1]; v.Overlay = base; o.Worlds[1] = &v },
		"BASELINE descriptor hash removed": func(o *Outcome) {
			b := *o.Worlds[0]
			b.Overlay.ProfileDescriptor = ""
			o.Worlds[0] = &b
		},
		"variant write edited": func(o *Outcome) {
			v := *o.Worlds[1]
			v.Overlay.Writes = append([]StorageWrite{}, v.Overlay.Writes...)
			v.Overlay.Writes[0].After = common.HexToHash("0x01")
			o.Worlds[1] = &v
		},
		"BASELINE given the variant overlay": func(o *Outcome) { b := *o.Worlds[0]; b.Overlay = variant; o.Worlds[0] = &b },
		"descriptor hash in the record": func(o *Outcome) {
			v := *o.Worlds[1]
			v.Overlay.ProfileDescriptor = strings.Repeat("f", 64)
			o.Worlds[1] = &v
		},
		"intervention commitment in the record": func(o *Outcome) {
			v := *o.Worlds[1]
			v.Overlay.Intervention = strings.Repeat("e", 64)
			o.Worlds[1] = &v
		},
	} {
		if e := verify(raw, outcome(edit)); codeOf(e) != "PROFILE_DERIVED_OVERLAY_EVIDENCE" {
			t.Errorf("%s: want PROFILE_DERIVED_OVERLAY_EVIDENCE, got %v", name, e)
		}
	}
	for name, edit := range map[string]func(*Outcome){
		"legacy evidence domain": func(o *Outcome) { o.Schema = OverlayDomain + "/evidence" },
		"legacy profile kind":    func(o *Outcome) { o.Profile = OverlayKind },
		"other scenario":         func(o *Outcome) { o.Scenario = strings.Repeat("d", 64) },
	} {
		if e := verify(raw, outcome(edit)); codeOf(e) != "SCENARIO_EVIDENCE_SCOPE" {
			t.Errorf("%s: want SCENARIO_EVIDENCE_SCOPE, got %v", name, e)
		}
	}
	tampered := bytes.Replace(outcome(nil), []byte(`"status":"SCENARIO_EXECUTED_UNQUALIFIED"`), []byte(`"status":"SCENARIO_EXECUTED_QUALIFIED"`), 1)
	if e := verify(raw, tampered); codeOf(e) != "EVIDENCE_COMMITMENT" {
		t.Fatal("edited evidence without its commitment", e)
	}
	combinedInput, _ := os.ReadFile(filepath.Join(dir, "combined/inputs/SCENARIO.json"))
	combinedFinal, _ := os.ReadFile(filepath.Join(dir, "combined/runtime/scenario/FINAL.json"))
	if e := verify(raw, combinedFinal); codeOf(e) != "SCENARIO_EVIDENCE_SCOPE" {
		t.Fatal("recorded SDK 0.4 evidence must not verify as profile evidence", e)
	}
	if _, e := profileForInput(combinedInput, "NATIVE_EXECUTION", native); codeOf(e) != "SCENARIO_RUNTIME_DOMAIN" {
		t.Fatal("legacy input under the profile verifier", e)
	}
	if e := VerifyOverlayEvidence(raw, outcome(nil)); e == nil {
		t.Fatal("overlay verifier accepted a profile input")
	}
	if e := VerifyOverlayEvidence(combinedInput, combinedFinal); e != nil {
		t.Fatal("recorded SDK 0.4 evidence must still verify under its own profile", e)
	}
	rep, e := profileStateReportWith(raw, native)
	if e != nil || rep["status"] != "PROFILE_OVERLAY_STATE_AUTHENTICATED" || rep["nativeExecutions"] != 0 {
		t.Fatal("offline profile-state report", e)
	}
}
