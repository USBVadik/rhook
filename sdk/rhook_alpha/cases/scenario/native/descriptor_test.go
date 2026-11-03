package scenario

// Profile Descriptor 0.1 tests: G1 (all 201 SDK 0.4 configurations), G2 (negatives, shared with the Python
// mirror through RHOOK_PROFILE_FIXTURES), the Dynamic Fee Tuning probe, prepared-input binding, and G3 on the
// accepted native inputs (RHOOK_ACCEPTED_RECORDS). Nothing here enters Nitro's producer or executes the EVM.
import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
	prestate "local/rhook-robinhood"
)

var wordTuned = common.HexToHash("0x0000000007d0000000000064000000010000000000000000001f400000000000")

func hookr1(t *testing.T) *Descriptor {
	t.Helper()
	d, e := LoadAcceptedDescriptor("hookr-1", "OFFLINE_PREPARATION")
	if e != nil {
		t.Fatal(e)
	}
	return d
}

func pi(kind string, params map[string]any) ProfileIntervention {
	p := map[string]json.RawMessage{}
	for k, v := range params {
		raw, _ := json.Marshal(v)
		p[k] = raw
	}
	return ProfileIntervention{Kind: kind, Parameters: p}
}
func piLp(v uint64) ProfileIntervention { return pi("LP_REWARDS_BPS", map[string]any{"lpBps": v}) }

var piDynOff = pi("DYNAMIC_FEE", map[string]any{"dynamicFee": "OFF"})

func piTuning(maxFee, sens uint64) ProfileIntervention {
	return pi("DYNAMIC_FEE_TUNING", map[string]any{"maxFeePips": maxFee, "dynamicFeeSens": sens})
}

func legacyRows() [][]TypedIntervention {
	var rows [][]TypedIntervention
	for v := uint64(0); v < 100; v++ {
		rows = append(rows, []TypedIntervention{lpItem(v)})
	}
	rows = append(rows, []TypedIntervention{dynamicOffItem})
	for v := uint64(0); v < 100; v++ {
		rows = append(rows, []TypedIntervention{dynamicOffItem, lpItem(v)})
	}
	return rows
}

func toProfile(items []TypedIntervention) []ProfileIntervention {
	var out []ProfileIntervention
	for _, i := range items {
		if i.Kind == InterventionLpRewards {
			out = append(out, piLp(*i.LpBps))
		} else {
			out = append(out, piDynOff)
		}
	}
	return out
}

func fixtures(t *testing.T) map[string]json.RawMessage {
	t.Helper()
	dir := os.Getenv("RHOOK_PROFILE_FIXTURES")
	if dir == "" {
		t.Skip("Python-generated fixtures not supplied")
	}
	raw, e := os.ReadFile(filepath.Join(dir, "profile-fixtures.json"))
	if e != nil {
		t.Fatal(e)
	}
	var out map[string]json.RawMessage
	if e = json.Unmarshal(raw, &out); e != nil {
		t.Fatal(e)
	}
	return out
}

func codeOf(e error) string {
	if e == nil {
		return "ACCEPTED"
	}
	return e.Error()
}

func TestDescriptorCatalogueAndReview(t *testing.T) {
	d := hookr1(t)
	if d.Sha256() != digest(hookr1DescriptorRaw) {
		t.Fatal("identity")
	}
	// Catalogue after the PASS review of revision 2: the descriptor is a native candidate, kind by kind. Tuning
	// stays offline-only; LP Rewards and Dynamic Fee OFF admit native use only together with the descriptor review.
	native, e := LoadAcceptedDescriptor("hookr-1", "NATIVE_EXECUTION")
	if e != nil {
		t.Fatal(e)
	}
	for kind, want := range map[string]bool{"LP_REWARDS_BPS": true, "DYNAMIC_FEE": true, "DYNAMIC_FEE_TUNING": false} {
		if kindReviewAdmits(native.reviewKinds[kind], "NATIVE_EXECUTION") != want || !kindReviewAdmits(native.reviewKinds[kind], "OFFLINE_PREPARATION") {
			t.Fatalf("%s: per-kind review", kind)
		}
	}
	var cat descriptorCatalogue
	if e := strictDecode(descriptorCatalogueRaw, &cat); e != nil || cat.Entries[0].Review.NativeExecution != "NOT_ACCEPTED_NO_ENGINE_IDENTITY_G4B_G5_REQUIRED" ||
		cat.Entries[0].Review.Status != "RHOOK_REVIEWED_NATIVE_CANDIDATE" || cat.Entries[0].Revision != 2 {
		t.Fatal("catalogue review record", e)
	}
	if _, e := LoadAcceptedDescriptor("hookr-2", "OFFLINE_PREPARATION"); codeOf(e) != "PROFILE_NOT_IN_CATALOGUE" {
		t.Fatal(e)
	}
	edited := bytes.Replace(hookr1DescriptorRaw, []byte(`"revision":2`), []byte(`"revision":3`), 1)
	if bytes.Equal(edited, hookr1DescriptorRaw) {
		t.Fatal("tamper edit did not apply")
	}
	if _, e := loadAcceptedFrom(descriptorCatalogueRaw, map[string][]byte{"hookr-1.json": edited}, "hookr-1", "OFFLINE_PREPARATION"); codeOf(e) != "PROFILE_DESCRIPTOR_HASH" {
		t.Fatal("tampered bytes must not load", e)
	}
}

func TestDescriptorReproducesLegacyProfile(t *testing.T) {
	d := hookr1(t)
	got, want := d.legacyProfile(), officialProfile()
	if !canonicalEqual(got.Manifest, want.Manifest) || !canonicalEqual(got.SwapABI, want.SwapABI) {
		t.Fatal("manifest or ABI")
	}
	if d.Release.ManifestCommitment != hashValue(Domain+"/release", json.RawMessage(want.Manifest)) {
		t.Fatal("release commitment")
	}
	got.Manifest, want.Manifest, got.SwapABI, want.SwapABI = nil, nil, nil, nil
	if !canonicalEqual(got, want) || len(got.Pins) != len(want.Pins) {
		t.Fatalf("legacy profile\n%+v\n%+v", got, want)
	}
	for a, h := range want.Pins {
		if got.Pins[a] != h {
			t.Fatal("pins")
		}
	}
}

func TestDescriptorG1AllConfigurationsMatchLegacyEngine(t *testing.T) {
	d := hookr1(t)
	p := overlayProfile()
	var table []map[string]any
	for _, legacy := range legacyRows() {
		canonical, e := canonicalInterventions(legacy)
		if e != nil {
			t.Fatal(e)
		}
		old, e := composeOverlay(overlayRegistry, canonical, p, p.BaselineWords[0], dynamicRootOn)
		if e != nil {
			t.Fatal(e)
		}
		got, e := d.ComposeProfile(toProfile(legacy), d.OriginalsFromDescriptor())
		if e != nil {
			t.Fatal(e)
		}
		if len(got.Writes) != len(old.Writes) {
			t.Fatalf("%v: write count", legacy)
		}
		for i, w := range got.Writes {
			if (StorageWrite{w.Address, w.Slot, w.Before, w.After}) != old.Writes[i] {
				t.Fatalf("%v: write %d", legacy, i)
			}
		}
		if got.Words["rulesConfig"][0] != old.Rules || got.Words["rootRecord"][0] != old.Root {
			t.Fatalf("%v: words", legacy)
		}
		f := decodeOverlayFields(old.Rules, old.Root)
		v := got.Variant
		mode := v["rootDynamicFeeFlag"].Uint64() | v["rootRecaptureFlag"].Uint64()<<1 | v["rootFlagsReserved"].Uint64()<<2
		if v["lpBps"].Uint64() != f.LpBps || v["maxFeePips"].Uint64() != f.MaxFeePips || v["dynamicFeeSens"].Uint64() != f.Sensitivity || mode != f.Mode {
			t.Fatalf("%v: fields", legacy)
		}
		assigned := map[string]bool{}
		for _, item := range got.Interventions {
			for _, a := range d.kinds[item.Kind].Assign {
				assigned[a.Field] = true
			}
		}
		for name, value := range v {
			if !assigned[name] && value.Cmp(got.Baseline[name]) != 0 {
				t.Fatalf("%v: unrelated field %s changed", legacy, name)
			}
		}
		for i := 1; i < 4; i++ {
			if got.Words["rulesConfig"][i] != p.BaselineWords[i] {
				t.Fatal("unrelated Rules word")
			}
		}
		if got.Words["rootRecord"][1] != p.RootCaps {
			t.Fatal("unrelated Root word")
		}
		table = append(table, map[string]any{"items": got.Interventions, "writes": got.Writes, "words": got.Words})
	}
	if len(table) != 201 {
		t.Fatal("count")
	}
	raw, _ := Canonical(table)
	t.Logf("G1_TABLE_SHA256 %s", digest(raw))
	if dir := os.Getenv("RHOOK_PROFILE_FIXTURES"); dir != "" {
		f := fixtures(t)
		if !canonicalEqual(json.RawMessage(f["g1"]), json.RawMessage(raw)) {
			t.Fatal("Go and Python G1 tables differ")
		}
		var sha string
		_ = json.Unmarshal(f["g1Sha256"], &sha)
		if sha != digest(raw) {
			t.Fatal("G1 table hash")
		}
		t.Logf("G1_TABLE_EQUALS_PYTHON %s", sha)
	}
	// The Dynamic-only set equals the SDK 0.3 derivative relation as well.
	c, _ := d.ComposeProfile([]ProfileIntervention{piDynOff}, d.OriginalsFromDescriptor())
	if c.Words["rulesConfig"][0] != dynamicConfigOff(p.BaselineWords[0], p.BaseLpFee) || c.Words["rootRecord"][0] != dynamicRootOff {
		t.Fatal("dynamic relation")
	}
}

func TestDescriptorProbeDynamicFeeTuning(t *testing.T) {
	d := hookr1(t)
	c, e := d.ComposeProfile([]ProfileIntervention{piTuning(8000, 1)}, d.OriginalsFromDescriptor())
	if e != nil || len(c.Writes) != 1 || c.Writes[0].After != wordTuned || c.Writes[0].Target != "rulesConfig" {
		t.Fatal(e, c.Writes)
	}
	if c.Variant["maxFeePips"].Uint64() != 8000 || c.Variant["dynamicFeeSens"].Uint64() != 1 || c.Variant["rootDynamicFeeFlag"].Uint64() != 1 || c.Variant["lpBps"].Uint64() != 100 {
		t.Fatal("fields")
	}
	both, e := d.ComposeProfile([]ProfileIntervention{piTuning(8000, 1), piLp(23)}, d.OriginalsFromDescriptor())
	if e != nil || both.Words["rulesConfig"][0] != common.HexToHash("0x0000000007d0000000000017000000010000000000000000001f400000000000") {
		t.Fatal("tuning with LP23", e)
	}
	for _, c := range []struct {
		items []ProfileIntervention
		want  string
	}{
		// Revision 2: the pool's Root caps bound maxFeePips at 11500 (vendor rulesFeeCeilings <= caps).
		{[]ProfileIntervention{piTuning(11500, 1)}, "ACCEPTED"},
		{[]ProfileIntervention{piTuning(11500, 10)}, "ACCEPTED"},
		{[]ProfileIntervention{piTuning(3001, 1)}, "ACCEPTED"},
		{[]ProfileIntervention{piTuning(8000, 10)}, "ACCEPTED"},
		{[]ProfileIntervention{piTuning(11501, 1)}, "PROFILE_INVARIANT"},
		{[]ProfileIntervention{piTuning(11501, 10)}, "PROFILE_INVARIANT"},
		{[]ProfileIntervention{piTuning(75000, 10)}, "PROFILE_INVARIANT"},
		{[]ProfileIntervention{piTuning(118266, 1)}, "PROFILE_INVARIANT"},
		{[]ProfileIntervention{piTuning(3000, 1)}, "PROFILE_INVARIANT"},
		{[]ProfileIntervention{piTuning(8000, 0)}, "PROFILE_PARAMETER"},
		{[]ProfileIntervention{piTuning(11500, 10), piLp(0)}, "ACCEPTED"},
		{[]ProfileIntervention{piTuning(11501, 1), piLp(23)}, "PROFILE_INVARIANT"},
		{[]ProfileIntervention{piTuning(11500, 2)}, "PROFILE_NO_EFFECT"},
		{[]ProfileIntervention{piTuning(8000, 11)}, "PROFILE_PARAMETER"},
		{[]ProfileIntervention{piTuning(8000, 1), piDynOff}, "PROFILE_KIND_CONFLICT"},
	} {
		if _, e := d.ComposeProfile(c.items, d.OriginalsFromDescriptor()); codeOf(e) != c.want {
			t.Fatalf("%v: want %s got %v", c.items, c.want, e)
		}
	}
}

// The Tuning acceptance table on maxFeePips 2990..12010 x sensitivity 0..11, alone and with LP 23, is
// byte-identical to the Python interpreter's (shared fixture tuningGrid).
func TestDescriptorTuningGridMatchesPython(t *testing.T) {
	f := fixtures(t)
	d := hookr1(t)
	var want struct {
		Points int    `json:"points"`
		Sha256 string `json:"sha256"`
	}
	if e := json.Unmarshal(f["tuningGrid"], &want); e != nil || want.Points == 0 {
		t.Fatal("tuningGrid fixture", e)
	}
	var rows []string
	for _, withLp := range []bool{false, true} {
		for m := uint64(2990); m <= 12010; m++ {
			for s := uint64(0); s <= 11; s++ {
				items := []ProfileIntervention{piTuning(m, s)}
				if withLp {
					items = append(items, piLp(23))
				}
				canon, _, e := d.canonicalProfileInterventions(items)
				if e == nil {
					_, e = d.ComposeProfile(canon, d.OriginalsFromDescriptor())
				}
				rows = append(rows, codeOf(e))
			}
		}
	}
	got := digest([]byte(strings.Join(rows, "\n")))
	t.Logf("TUNING_GRID points=%d sha256=%s", len(rows), got)
	if len(rows) != want.Points || got != want.Sha256 {
		t.Fatalf("Go table %s (%d) differs from Python %s (%d)", got, len(rows), want.Sha256, want.Points)
	}
}

func TestDescriptorSharedFixtures(t *testing.T) {
	f := fixtures(t)
	d := hookr1(t)
	var negatives []struct {
		Name      string `json:"name"`
		RawBase64 string `json:"rawBase64"`
		Expect    string `json:"expect"`
	}
	if e := json.Unmarshal(f["descriptorNegatives"], &negatives); e != nil || len(negatives) == 0 {
		t.Fatal(e)
	}
	for _, n := range negatives {
		raw, _ := base64.StdEncoding.DecodeString(n.RawBase64)
		if _, e := ParseDescriptor(raw); codeOf(e) != n.Expect {
			t.Errorf("descriptor %q: want %s got %v", n.Name, n.Expect, e)
		}
	}
	var comps []struct {
		Name      string              `json:"name"`
		Items     json.RawMessage     `json:"items"`
		Originals map[string][]string `json:"originals"`
		Expect    string              `json:"expect"`
	}
	if e := json.Unmarshal(f["compositionNegatives"], &comps); e != nil || len(comps) == 0 {
		t.Fatal(e)
	}
	for _, c := range comps {
		originals := Originals{}
		for k, row := range c.Originals {
			for _, w := range row {
				originals[k] = append(originals[k], common.HexToHash(w).Big())
			}
		}
		items, e := DecodeProfileInterventions(c.Items)
		if e == nil {
			_, e = d.ComposeProfile(items, originals)
		}
		if codeOf(e) != c.Expect {
			t.Errorf("composition %q: want %s got %v", c.Name, c.Expect, e)
		}
	}
	var mw []struct {
		Name      string          `json:"name"`
		RawBase64 string          `json:"rawBase64"`
		Items     json.RawMessage `json:"items"`
		Expect    string          `json:"expect"`
	}
	if e := json.Unmarshal(f["maskAndWidth"], &mw); e != nil || len(mw) != 2 {
		t.Fatal(e)
	}
	for _, c := range mw {
		raw, _ := base64.StdEncoding.DecodeString(c.RawBase64)
		alt, e := ParseDescriptor(raw)
		if e != nil {
			t.Fatal(c.Name, e)
		}
		items, e := DecodeProfileInterventions(c.Items)
		if e == nil {
			_, e = alt.ComposeProfile(items, alt.OriginalsFromDescriptor())
		}
		if codeOf(e) != c.Expect {
			t.Errorf("%q: want %s got %v", c.Name, c.Expect, e)
		}
	}
	var probe struct {
		Items    json.RawMessage `json:"items"`
		Writes   json.RawMessage `json:"writes"`
		Combined json.RawMessage `json:"combined"`
	}
	if e := json.Unmarshal(f["probe"], &probe); e != nil {
		t.Fatal(e)
	}
	items, _ := DecodeProfileInterventions(probe.Items)
	c, e := d.ComposeProfile(items, d.OriginalsFromDescriptor())
	if e != nil || !canonicalEqual(c.Writes, probe.Writes) {
		t.Fatal("probe writes differ from Python", e)
	}
	var binding []struct {
		Name   string          `json:"name"`
		Spec   json.RawMessage `json:"spec"`
		Expect string          `json:"expect"`
	}
	if e := json.Unmarshal(f["binding"], &binding); e != nil || len(binding) == 0 {
		t.Fatal(e)
	}
	var sha string
	_ = json.Unmarshal(f["descriptorSha256"], &sha)
	if sha != d.Sha256() {
		t.Fatal("descriptor hash differs between Go and Python")
	}
	for _, b := range binding {
		raw, _ := Canonical(b.Spec)
		raw = append(raw, '\n')
		s, e := ParseProfileSpec(raw)
		if e == nil {
			_, e = d.ValidateProfileSpec(s)
		}
		if codeOf(e) != b.Expect {
			t.Errorf("binding %q: want %s got %v", b.Name, b.Expect, e)
		}
		if b.Expect == "ACCEPTED" {
			// G4A: Parse knows the profile domain; every legacy runtime still refuses it.
			for _, runtime := range []string{RuntimeProfile, DynamicRuntimeProfile, OverlayRuntimeProfile} {
				if e := validateRuntimeSpec(s, runtime); e == nil {
					t.Errorf("%q: %s runtime accepted a profile-overlay input", b.Name, runtime)
				}
			}
			if _, e := Admit(raw); e == nil {
				t.Errorf("%q: legacy admission accepted a profile-overlay input", b.Name)
			}
			if _, e := AdmitOverlay(raw); e == nil {
				t.Errorf("%q: overlay admission accepted a profile-overlay input", b.Name)
			}
		}
	}
	t.Logf("SHARED_FIXTURES descriptor=%d composition=%d binding=%d", len(negatives), len(comps), len(binding))
}

// mutateDescriptor edits the hookr-1 descriptor as generic JSON and re-encodes it canonically.
func mutateDescriptor(t *testing.T, edit func(map[string]any)) []byte {
	t.Helper()
	var v map[string]any
	dec := json.NewDecoder(bytes.NewReader(hookr1DescriptorRaw))
	dec.UseNumber()
	if e := dec.Decode(&v); e != nil {
		t.Fatal(e)
	}
	edit(v)
	raw, e := Canonical(v)
	if e != nil {
		t.Fatal(e)
	}
	return append(raw, '\n')
}

// syntheticState is a profileState with explicit code preimages and storage; missing marks a witness gap.
type syntheticState struct {
	codes   map[common.Address][]byte
	words   map[[52]byte]common.Hash
	missing map[[52]byte]bool
	err     error
	writes  int
}

func (s *syntheticState) Exist(a common.Address) bool { _, ok := s.codes[a]; return ok }
func (s *syntheticState) GetCodeHash(a common.Address) common.Hash {
	if c, ok := s.codes[a]; ok {
		return crypto.Keccak256Hash(c)
	}
	return common.Hash{}
}
func (s *syntheticState) GetCode(a common.Address) []byte { return s.codes[a] }
func (s *syntheticState) GetState(a common.Address, k common.Hash) common.Hash {
	if s.missing[key(a, k)] {
		s.err = os.ErrNotExist
	}
	return s.words[key(a, k)]
}
func (s *syntheticState) SetState(a common.Address, k, v common.Hash) common.Hash {
	before := s.words[key(a, k)]
	s.words[key(a, k)] = v
	s.writes++
	return before
}
func (s *syntheticState) Error() error { return s.err }

// syntheticCodeDescriptor re-pins the code-pinned contracts to synthetic code so a test state can hold the
// matching preimages; the manifest commitment is recomputed. Everything else is hookr-1.
func syntheticCodeDescriptor(t *testing.T) (*Descriptor, map[common.Address][]byte) {
	t.Helper()
	var v map[string]any
	dec := json.NewDecoder(bytes.NewReader(hookr1DescriptorRaw))
	dec.UseNumber()
	if e := dec.Decode(&v); e != nil {
		t.Fatal(e)
	}
	codes := map[common.Address][]byte{}
	release := v["release"].(map[string]any)
	manifest := release["manifest"].(map[string]any)
	for _, c := range v["contracts"].([]any) {
		c := c.(map[string]any)
		a := common.HexToAddress(c["address"].(string))
		codes[a] = []byte("synthetic code of " + c["name"].(string))
		if c["requirement"] == "CODE_HASH_EQUALS" {
			h := crypto.Keccak256Hash(codes[a]).Hex()
			c["runtimeCodeHash"] = h
			for _, m := range manifest["contracts"].([]any) {
				m := m.(map[string]any)
				if m["address"] == c["address"] && m["role"] == c["releaseRole"] {
					m["runtimeHash"] = h
				}
			}
		}
	}
	mraw, _ := json.Marshal(manifest)
	release["manifestCommitment"] = hashValue(Domain+"/release", json.RawMessage(mraw))
	raw, e := Canonical(v)
	if e != nil {
		t.Fatal(e)
	}
	d, e := ParseDescriptor(append(raw, '\n'))
	if e != nil {
		t.Fatal(e)
	}
	return d, codes
}

func newSyntheticState(d *Descriptor, codes map[common.Address][]byte) *syntheticState {
	s := &syntheticState{codes: map[common.Address][]byte{}, words: map[[52]byte]common.Hash{}, missing: map[[52]byte]bool{}}
	for a, c := range codes {
		s.codes[a] = c
	}
	o := d.OriginalsFromDescriptor()
	for _, t := range d.Targets {
		for i := uint64(0); i < t.Words; i++ {
			s.words[key(d.contracts[t.Contract].Address, wordAt(t.Slot, int(i)))] = common.BigToHash(o[t.Name][i])
		}
	}
	return s
}

func TestDescriptorAuthenticationAndEnvelope(t *testing.T) {
	d, codes := syntheticCodeDescriptor(t)
	st := newSyntheticState(d, codes)
	got, e := d.AuthenticateProfile(st)
	if e != nil || !canonicalEqual(got, d.OriginalsFromDescriptor()) {
		t.Fatal("authentication", e)
	}
	rules := d.contracts["rules"].Address
	bad := newSyntheticState(d, codes)
	bad.codes[rules] = []byte("other code")
	if _, e = d.AuthenticateProfile(bad); codeOf(e) != "PROFILE_CODE_IDENTITY" {
		t.Fatal(e)
	}
	gap := newSyntheticState(d, codes)
	gap.missing[key(rules, wordAt(d.targets["rulesConfig"].Slot, 2))] = true
	if _, e = d.AuthenticateProfile(gap); codeOf(e) != "PROFILE_ORIGINAL_STATE_UNAVAILABLE" {
		t.Fatal("a missing node must not read as zero", e)
	}
	token := newSyntheticState(d, codes)
	token.codes[d.Pool.Currency1] = nil
	if _, e = d.AuthenticateProfile(token); codeOf(e) != "PROFILE_TOKEN_CODE_REQUIRED" {
		t.Fatal(e)
	}
	c, e := d.ComposeProfile([]ProfileIntervention{piLp(23), piDynOff}, got)
	if e != nil {
		t.Fatal(e)
	}
	base := newSyntheticState(d, codes)
	rows, e := d.ApplyProfileWrites(base, c.Writes, Baseline)
	if e != nil || base.writes != 0 || rows[0].After != rows[0].Before {
		t.Fatal("BASELINE must not write", e)
	}
	variant := newSyntheticState(d, codes)
	if _, e = d.ApplyProfileWrites(variant, c.Writes, Variant); e != nil || variant.writes != 2 {
		t.Fatal(e)
	}
	changed := newSyntheticState(d, codes)
	changed.words[key(d.contracts["root"].Address, d.targets["rootRecord"].Slot)] = dynamicRootOff
	if _, e = d.ApplyProfileWrites(changed, c.Writes, Variant); codeOf(e) != "PROFILE_ORIGINAL_WORD_CHANGED" || changed.writes != 0 {
		t.Fatal("partial overlay", e)
	}
	for _, edit := range []func(*ProfileWrite){
		func(w *ProfileWrite) { w.Slot = common.Hash{} },
		func(w *ProfileWrite) { w.Address = d.Pool.Currency1 },
		func(w *ProfileWrite) { w.Target = "rootRecord" },
		func(w *ProfileWrite) { w.Word = 9 },
	} {
		writes := append([]ProfileWrite{}, c.Writes...)
		edit(&writes[0])
		if _, e = d.ApplyProfileWrites(newSyntheticState(d, codes), writes, Variant); codeOf(e) != "PROFILE_WRITE_TARGET" {
			t.Fatal("write outside declared targets", e)
		}
	}
	if _, e = d.ApplyProfileWrites(base, c.Writes, "OTHER"); codeOf(e) != "PROFILE_WORLD" {
		t.Fatal(e)
	}
	// A kind that would write code, balance or nonce cannot be expressed: unknown descriptor fields are refused.
	for _, field := range []string{"balance", "nonce", "code"} {
		raw := mutateDescriptor(t, func(v map[string]any) {
			k := v["interventions"].([]any)[2].(map[string]any)
			k["set"] = map[string]any{field: "1"}
		})
		if _, e = ParseDescriptor(raw); codeOf(e) != "DESCRIPTOR_SCHEMA" {
			t.Fatalf("%s write accepted: %v", field, e)
		}
	}
}

// G3: the accepted native inputs keep their encodings, commitments and admission under this source, and the
// descriptor authenticates against the retained witness and reproduces their recorded writes.
func TestDescriptorAcceptedInputsAndWitness(t *testing.T) {
	dir := os.Getenv("RHOOK_ACCEPTED_RECORDS")
	if dir == "" {
		t.Skip("accepted run inputs not supplied")
	}
	d := hookr1(t)
	load := func(name string) ([]byte, Spec) {
		raw, e := os.ReadFile(filepath.Join(dir, name, "inputs/SCENARIO.json"))
		if e != nil {
			t.Fatal(e)
		}
		s, e := Parse(raw)
		if e != nil {
			t.Fatal(name, e)
		}
		return raw, s
	}
	lpRaw, lp := load("lp23")
	dynRaw, dyn := load("dynamic-fee-off")
	combRaw, comb := load("combined")
	t.Logf("G3_COMMITMENTS lp23=%s dynamic-fee-off=%s combined=%s", lp.Commitment, dyn.Commitment, comb.Commitment)
	if _, e := Admit(lpRaw); e != nil {
		t.Fatal("LP input", e)
	}
	if _, e := AdmitDynamic(dynRaw); e != nil {
		t.Fatal("Dynamic Fee input", e)
	}
	a, e := AdmitOverlay(combRaw)
	if e != nil {
		t.Fatal("overlay input", e)
	}
	if _, e := ParseProfileSpec(combRaw); e == nil {
		t.Fatal("profile parser accepted a legacy input")
	}
	final := func(name string) []byte {
		raw, e := os.ReadFile(filepath.Join(dir, name, "runtime/scenario/FINAL.json"))
		if e != nil {
			t.Fatal(e)
		}
		return raw
	}
	if e := VerifyEvidence(lpRaw, final("lp23")); e != nil {
		t.Fatal("LP evidence", e)
	}
	if e := VerifyDynamicEvidence(dynRaw, final("dynamic-fee-off")); e != nil {
		t.Fatal("Dynamic Fee evidence", e)
	}
	if e := VerifyOverlayEvidence(combRaw, final("combined")); e != nil {
		t.Fatal("overlay evidence", e)
	}
	t.Logf("G3_RECORDED_EVIDENCE_VERIFIES lp23 dynamic-fee-off combined")
	b, e := openBridge(a.input)
	if e != nil {
		t.Fatal(e)
	}
	var originals Originals
	e = b.Protect(func() error {
		st, err := b.State()
		if err != nil {
			return err
		}
		originals, err = d.AuthenticateProfile(st)
		return err
	})
	if e2 := prestate.CloseScenarioBridge(b); e == nil {
		e = e2
	}
	if e != nil || !canonicalEqual(originals, d.OriginalsFromDescriptor()) {
		t.Fatal("witness authentication", e)
	}
	check := func(items []ProfileIntervention, writes []StorageWrite) {
		c, e := d.ComposeProfile(items, originals)
		if e != nil || len(c.Writes) != len(writes) {
			t.Fatal(e)
		}
		for i, w := range c.Writes {
			if (StorageWrite{w.Address, w.Slot, w.Before, w.After}) != writes[i] {
				t.Fatal("recorded write", i)
			}
		}
	}
	check([]ProfileIntervention{piLp(23), piDynOff}, comb.Overlay.Writes)
	check([]ProfileIntervention{piDynOff}, dyn.Intervention.Writes)
	c, e := d.ComposeProfile([]ProfileIntervention{piLp(23)}, originals)
	if e != nil || c.Words["rulesConfig"][0] != lp.Configs.Variant[0] {
		t.Fatal("LP23 variant word", e)
	}
	probe, e := d.ComposeProfile([]ProfileIntervention{piTuning(8000, 1)}, originals)
	if e != nil || probe.Writes[0].After != wordTuned {
		t.Fatal("probe against the witness originals", e)
	}
}
