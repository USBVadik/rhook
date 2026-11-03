package scenario

import (
	"math/big"
	"strings"
	"testing"

	"github.com/ethereum/go-ethereum/common"
)

func lpItem(v uint64) TypedIntervention {
	return TypedIntervention{Kind: InterventionLpRewards, LpBps: &v}
}

var dynamicOffItem = TypedIntervention{Kind: InterventionDynamicFee, DynamicFee: "OFF"}

// Expected words are written out, not recomputed, so the engine is checked against
// the merged word derived independently in the SDK 0.4 blocker analysis.
var (
	wordOriginal = common.HexToHash("0x0000000007d0000000000064000000020000000000000000002cec0000000000")
	wordLp23     = common.HexToHash("0x0000000007d0000000000017000000020000000000000000002cec0000000000")
	wordDynOff   = common.HexToHash("0x0000000007d0000000000064000000000000000000000000000bb80000000000")
	wordMerged   = common.HexToHash("0x0000000007d0000000000017000000000000000000000000000bb80000000000")
)

func overlaySpec(items ...TypedIntervention) (Spec, profile) {
	p := overlayProfile()
	b := Body{Schema: OverlayDomain, Pool: p.Pool, Configs: Configurations{Baseline: append([]common.Hash{}, p.BaselineWords...), Variant: append([]common.Hash{}, p.BaselineWords...)}}
	b.Checkpoint.StateRoot = common.HexToHash("0x1234")
	canonical, e := canonicalInterventions(items)
	if e != nil {
		panic(e)
	}
	c, e := composeOverlay(overlayRegistry, canonical, p, p.BaselineWords[0], dynamicRootOn)
	if e != nil {
		panic(e)
	}
	o := &ConfigOverlay{Schema: OverlayDomain + "/transform", OriginalRoot: b.Checkpoint.StateRoot, Pool: p.Pool, RootCode: p.Pins[p.PoolKey.Hooks], RulesCode: p.Pins[rulesAddress],
		Plan: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", Interventions: canonical, Writes: c.Writes}
	o.Commitment = overlayTransformID(*o)
	b.Overlay = o
	b.Configs.Variant[0] = c.Rules
	s := Commit(b)
	s.Origin = Origin{Kind: OverlayKind, Capsule: overlayCapsule(s)}
	return Commit(s.Body), p
}

func expectCode(t *testing.T, e error, code string) {
	t.Helper()
	if e == nil || e.Error() != code {
		t.Fatalf("want %s, got %v", code, e)
	}
}

func TestOverlayProfileWordsAndPins(t *testing.T) {
	p := overlayProfile()
	if p.BaselineWords[0] != wordOriginal || p.BaseLpFee != 3000 {
		t.Fatal("profile baseline")
	}
	f := decodeOverlayFields(wordOriginal, dynamicRootOn)
	if f.LpBps != 100 || f.MaxFeePips != 11500 || f.Sensitivity != 2 || f.Mode != 3 {
		t.Fatalf("original fields %+v", f)
	}
}

func TestOverlayComposesLpDynamicAndCombined(t *testing.T) {
	p := overlayProfile()
	cases := []struct {
		name  string
		items []TypedIntervention
		rules common.Hash
		root  common.Hash
		n     int
		f     OverlayFields
	}{
		{"lp", []TypedIntervention{lpItem(23)}, wordLp23, dynamicRootOn, 1, OverlayFields{LpBps: 23, MaxFeePips: 11500, Sensitivity: 2, Mode: 3}},
		{"dynamic", []TypedIntervention{dynamicOffItem}, wordDynOff, dynamicRootOff, 2, OverlayFields{LpBps: 100, MaxFeePips: 3000, Sensitivity: 0, Mode: 2}},
		{"combined", []TypedIntervention{dynamicOffItem, lpItem(23)}, wordMerged, dynamicRootOff, 2, OverlayFields{LpBps: 23, MaxFeePips: 3000, Sensitivity: 0, Mode: 2}},
	}
	for _, c := range cases {
		got, e := composeOverlay(overlayRegistry, c.items, p, p.BaselineWords[0], dynamicRootOn)
		if e != nil || got.Rules != c.rules || got.Root != c.root || len(got.Writes) != c.n {
			t.Fatalf("%s: %v %s %s %d", c.name, e, got.Rules.Hex(), got.Root.Hex(), len(got.Writes))
		}
		f := decodeOverlayFields(got.Rules, got.Root)
		f.RulesWord, f.RootWord = common.Hash{}, common.Hash{}
		if f != c.f {
			t.Fatalf("%s fields %+v", c.name, f)
		}
		if got.Writes[0] != (StorageWrite{rulesAddress, p.ConfigSlot, wordOriginal, c.rules}) {
			t.Fatalf("%s config write", c.name)
		}
		if c.n == 2 && got.Writes[1] != (StorageWrite{p.PoolKey.Hooks, p.RootSlot, dynamicRootOn, dynamicRootOff}) {
			t.Fatalf("%s root write", c.name)
		}
	}
	// The Dynamic-only overlay reproduces the existing Dynamic Fee OFF relation exactly.
	d, _ := composeOverlay(overlayRegistry, []TypedIntervention{dynamicOffItem}, p, p.BaselineWords[0], dynamicRootOn)
	if d.Rules != dynamicConfigOff(p.BaselineWords[0], p.BaseLpFee) {
		t.Fatal("dynamic relation drift")
	}
	// Applying the existing full Dynamic Fee word after an LP write would reset lpBps to 100.
	if decodeOverlayFields(wordDynOff, dynamicRootOff).LpBps != 100 || wordMerged == wordDynOff {
		t.Fatal("sequential replay check")
	}
}

func TestOverlayOrderIndependenceAndCanonicalForm(t *testing.T) {
	p := overlayProfile()
	a, e1 := composeOverlay(overlayRegistry, []TypedIntervention{lpItem(23), dynamicOffItem}, p, p.BaselineWords[0], dynamicRootOn)
	b, e2 := composeOverlay(overlayRegistry, []TypedIntervention{dynamicOffItem, lpItem(23)}, p, p.BaselineWords[0], dynamicRootOn)
	if e1 != nil || e2 != nil || a.Rules != b.Rules || a.Root != b.Root || len(a.Writes) != len(b.Writes) || a.Writes[0] != b.Writes[0] || a.Writes[1] != b.Writes[1] {
		t.Fatal("order dependent")
	}
	s1, _ := overlaySpec(lpItem(23), dynamicOffItem)
	s2, _ := overlaySpec(dynamicOffItem, lpItem(23))
	if s1.Commitment != s2.Commitment {
		t.Fatal("canonical set commitment")
	}
	// A spec that lists the set in non-canonical order is refused even with fresh commitments.
	x, q := overlaySpec(dynamicOffItem, lpItem(23))
	x.Overlay.Interventions = []TypedIntervention{lpItem(23), dynamicOffItem}
	x.Overlay.Commitment = overlayTransformID(*x.Overlay)
	x.Origin.Capsule = overlayCapsule(x)
	_, e := validateOverlay(Commit(x.Body), q)
	expectCode(t, e, "CONFIG_OVERLAY_CANONICAL_ORDER")
}

func TestOverlayRejectsUnknownDuplicateAndInvalidParameters(t *testing.T) {
	p := overlayProfile()
	v100, v65536 := uint64(100), uint64(65536)
	tests := []struct {
		items []TypedIntervention
		code  string
	}{
		{nil, "CONFIG_OVERLAY_INTERVENTION_COUNT"},
		{[]TypedIntervention{lpItem(23), lpItem(37)}, "CONFIG_OVERLAY_DUPLICATE_KIND"},
		{[]TypedIntervention{dynamicOffItem, dynamicOffItem}, "CONFIG_OVERLAY_DUPLICATE_KIND"},
		{[]TypedIntervention{{Kind: "ARBITRARY_STORAGE_WRITE"}}, "CONFIG_OVERLAY_UNKNOWN_INTERVENTION"},
		{[]TypedIntervention{{Kind: InterventionLpRewards, LpBps: &v100}}, "CONFIG_OVERLAY_LP_PARAMETER"},
		{[]TypedIntervention{{Kind: InterventionLpRewards, LpBps: &v65536}}, "CONFIG_OVERLAY_LP_PARAMETER"},
		{[]TypedIntervention{{Kind: InterventionLpRewards}}, "CONFIG_OVERLAY_LP_PARAMETER"},
		{[]TypedIntervention{{Kind: InterventionLpRewards, LpBps: &v100, DynamicFee: "OFF"}}, "CONFIG_OVERLAY_LP_PARAMETER"},
		{[]TypedIntervention{{Kind: InterventionDynamicFee, DynamicFee: "ON"}}, "CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER"},
		{[]TypedIntervention{{Kind: InterventionDynamicFee}}, "CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER"},
		{[]TypedIntervention{{Kind: InterventionDynamicFee, DynamicFee: "OFF", LpBps: &v100}}, "CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER"},
		{[]TypedIntervention{dynamicOffItem, lpItem(23), lpItem(24)}, "CONFIG_OVERLAY_INTERVENTION_COUNT"},
	}
	for i, c := range tests {
		_, e := composeOverlay(overlayRegistry, c.items, p, p.BaselineWords[0], dynamicRootOn)
		if e == nil || e.Error() != c.code {
			t.Fatalf("case %d: want %s got %v", i, c.code, e)
		}
	}
}

func TestOverlayDetectsMaskConflictAndPreconditions(t *testing.T) {
	p := overlayProfile()
	conflicting := map[string]interventionRule{
		InterventionLpRewards: overlayRegistry[InterventionLpRewards],
		"OVERLAPPING_LP_HIGH_BYTE": func(TypedIntervention, profile) ([]assignment, error) {
			return []assignment{{overlayField{"lpHigh", targetRules, 168, 8}, func(uint64) bool { return true }, 0}}, nil
		},
	}
	_, e := composeOverlay(conflicting, []TypedIntervention{lpItem(23), {Kind: "OVERLAPPING_LP_HIGH_BYTE"}}, p, p.BaselineWords[0], dynamicRootOn)
	expectCode(t, e, "CONFIG_OVERLAY_MASK_CONFLICT")
	outside := map[string]interventionRule{"OUT_OF_WORD": func(TypedIntervention, profile) ([]assignment, error) {
		return []assignment{{overlayField{"x", targetRoot, 250, 8}, func(uint64) bool { return true }, 1}}, nil
	}}
	_, e = composeOverlay(outside, []TypedIntervention{{Kind: "OUT_OF_WORD"}}, p, p.BaselineWords[0], dynamicRootOn)
	expectCode(t, e, "CONFIG_OVERLAY_FIELD_LAYOUT")
	// Original LP must be 100 and Dynamic Fee must be ON in the authenticated original words.
	notLp100 := new(big.Int).Or(new(big.Int).AndNot(wordOriginal.Big(), fieldLpBps.mask()), new(big.Int).Lsh(big.NewInt(99), 160))
	_, e = composeOverlay(overlayRegistry, []TypedIntervention{lpItem(23)}, p, common.BigToHash(notLp100), dynamicRootOn)
	expectCode(t, e, "CONFIG_OVERLAY_ORIGINAL_PRECONDITION")
	_, e = composeOverlay(overlayRegistry, []TypedIntervention{dynamicOffItem}, p, p.BaselineWords[0], dynamicRootOff)
	expectCode(t, e, "CONFIG_OVERLAY_ORIGINAL_PRECONDITION")
	_, e = composeOverlay(overlayRegistry, []TypedIntervention{dynamicOffItem}, p, wordDynOff, dynamicRootOn)
	expectCode(t, e, "CONFIG_OVERLAY_ORIGINAL_PRECONDITION")
}

func TestOverlayPreservesEveryNonTargetBit(t *testing.T) {
	p := overlayProfile()
	target := new(big.Int).Or(new(big.Int).Or(fieldLpBps.mask(), fieldMaxFee.mask()), fieldSensitivity.mask())
	patterns := []*big.Int{new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 256), big.NewInt(1)), big.NewInt(0)}
	seed := new(big.Int).SetBytes(common.FromHex("0x5a5aa5a5c3c33c3c0ff0f00f12345678deadbeef0badf00d13579bdf2468ace0"))
	patterns = append(patterns, seed, new(big.Int).Not(seed))
	for i, noise := range patterns {
		noise = new(big.Int).And(noise, new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 256), big.NewInt(1)))
		// Original target fields as in the profile (LP100, maxFee 11500, sensitivity 2); every other bit varies.
		rules := new(big.Int).Or(new(big.Int).AndNot(noise, target), new(big.Int).And(wordOriginal.Big(), target))
		rootNoise := new(big.Int).Or(new(big.Int).AndNot(noise, fieldMode.mask()), new(big.Int).Lsh(big.NewInt(3), 248))
		c, e := composeOverlay(overlayRegistry, []TypedIntervention{dynamicOffItem, lpItem(23)}, p, common.BigToHash(rules), common.BigToHash(rootNoise))
		if e != nil {
			t.Fatalf("pattern %d: %v", i, e)
		}
		if new(big.Int).AndNot(c.Rules.Big(), target).Cmp(new(big.Int).AndNot(rules, target)) != 0 ||
			new(big.Int).AndNot(c.Root.Big(), fieldMode.mask()).Cmp(new(big.Int).AndNot(rootNoise, fieldMode.mask())) != 0 {
			t.Fatalf("pattern %d changed a non-target bit", i)
		}
		f := decodeOverlayFields(c.Rules, c.Root)
		if f.LpBps != 23 || f.MaxFeePips != 3000 || f.Sensitivity != 0 || f.Mode != 2 {
			t.Fatalf("pattern %d fields %+v", i, f)
		}
	}
}

func TestOverlayValidationRejectsTampering(t *testing.T) {
	s, p := overlaySpec(dynamicOffItem, lpItem(23))
	if _, e := validateOverlay(s, p); e != nil {
		t.Fatal(e)
	}
	if s.Configs.Variant[0] != wordMerged {
		t.Fatal("variant word")
	}
	tests := []struct {
		change func(*Spec)
		code   string
		// keepCapsule leaves the origin capsule of the untampered set in place.
		keepCapsule bool
	}{
		{func(s *Spec) { s.Configs.Variant[0] = wordLp23 }, "CONFIG_OVERLAY_VARIANT_WORD", false},
		{func(s *Spec) { s.Configs.Variant[2][5] ^= 1 }, "CONFIG_OVERLAY_UNRELATED_CONFIG", false},
		{func(s *Spec) { s.Configs.Baseline[0] = wordLp23 }, "CONFIG_OVERLAY_ORIGINAL_CONFIG", false},
		{func(s *Spec) { s.Overlay.Writes[0].After = wordDynOff }, "CONFIG_OVERLAY_DERIVED_WRITES", false},
		{func(s *Spec) { s.Overlay.Writes = s.Overlay.Writes[:1] }, "CONFIG_OVERLAY_DERIVED_WRITES", false},
		{func(s *Spec) { s.Overlay.Writes = append(s.Overlay.Writes, s.Overlay.Writes[0]) }, "CONFIG_OVERLAY_DERIVED_WRITES", false},
		{func(s *Spec) { s.Overlay.Writes[1].Address = rulesAddress }, "CONFIG_OVERLAY_DERIVED_WRITES", false},
		{func(s *Spec) { v := uint64(24); s.Overlay.Interventions[1].LpBps = &v }, "CONFIG_OVERLAY_ORIGIN", true},
		{func(s *Spec) { v := uint64(24); s.Overlay.Interventions[1].LpBps = &v }, "CONFIG_OVERLAY_VARIANT_WORD", false},
		{func(s *Spec) { s.Overlay.RootCode = common.Hash{} }, "CONFIG_OVERLAY_BINDING", false},
		{func(s *Spec) { s.Overlay.OriginalRoot = common.Hash{} }, "CONFIG_OVERLAY_BINDING", false},
		{func(s *Spec) { s.Overlay.Plan = "" }, "CONFIG_OVERLAY_BINDING", false},
		{func(s *Spec) { s.Origin.Kind = DynamicKind }, "CONFIG_OVERLAY_ORIGIN", false},
	}
	for i, c := range tests {
		x, q := overlaySpec(dynamicOffItem, lpItem(23))
		c.change(&x)
		x.Overlay.Commitment = overlayTransformID(*x.Overlay)
		if !c.keepCapsule && x.Origin.Kind == OverlayKind {
			x.Origin.Capsule = overlayCapsule(x)
		}
		_, e := validateOverlay(Commit(x.Body), q)
		if e == nil || e.Error() != c.code {
			t.Fatalf("case %d: want %s got %v", i, c.code, e)
		}
	}
	// A stale interventionCommitment is a binding failure.
	x, q := overlaySpec(lpItem(23))
	x.Overlay.Writes[0].After = wordMerged
	_, e := validateOverlay(Commit(x.Body), q)
	expectCode(t, e, "CONFIG_OVERLAY_BINDING")
}

func TestOverlayAuthenticatesAllBeforeAnyWrite(t *testing.T) {
	s, p := overlaySpec(dynamicOffItem, lpItem(23))
	newState := func() *overlayFixture {
		f := &overlayFixture{words: map[[52]byte]common.Hash{}}
		f.words[key(rulesAddress, p.ConfigSlot)] = wordOriginal
		f.words[key(p.PoolKey.Hooks, p.RootSlot)] = dynamicRootOn
		return f
	}
	base := newState()
	rows, e := configurationOverlay(base, s, p, Baseline)
	if e != nil || base.writes != 0 || len(rows) != 2 || rows[0].After != wordOriginal || rows[1].After != dynamicRootOn {
		t.Fatal("baseline must not write", e)
	}
	variant := newState()
	rows, e = configurationOverlay(variant, s, p, Variant)
	if e != nil || variant.writes != 2 || len(rows) != 2 {
		t.Fatal(e)
	}
	if variant.GetState(rulesAddress, p.ConfigSlot) != wordMerged || variant.GetState(p.PoolKey.Hooks, p.RootSlot) != dynamicRootOff ||
		base.GetState(rulesAddress, p.ConfigSlot) != wordOriginal || base.GetState(p.PoolKey.Hooks, p.RootSlot) != dynamicRootOn {
		t.Fatal("world alias or overlay values")
	}
	bad := newState()
	bad.words[key(p.PoolKey.Hooks, p.RootSlot)] = dynamicRootOff
	_, e = configurationOverlay(bad, s, p, Variant)
	if e == nil || e.Error() != "CONFIG_OVERLAY_ORIGINAL_WORD_CHANGED" || bad.writes != 0 {
		t.Fatal("partial patch", e)
	}
	lp, q := overlaySpec(lpItem(37))
	only := newState()
	rows, e = configurationOverlay(only, lp, q, Variant)
	if e != nil || only.writes != 1 || len(rows) != 1 || only.GetState(p.PoolKey.Hooks, p.RootSlot) != dynamicRootOn {
		t.Fatal("LP-only overlay must leave the Root record", e)
	}
	if _, e = configurationOverlay(newState(), s, p, "OTHER"); e == nil {
		t.Fatal("unknown world")
	}
}

func TestOverlayRuntimeIsolation(t *testing.T) {
	s, _ := overlaySpec(dynamicOffItem, lpItem(23))
	raw, _ := Canonical(s)
	if _, e := Parse(append(raw, '\n')); e != nil {
		t.Fatal(e)
	}
	if validateRuntimeSpec(s, RuntimeProfile) == nil || validateRuntimeSpec(s, DynamicRuntimeProfile) == nil {
		t.Fatal("legacy profile accepted overlay input")
	}
	if e := validateRuntimeSpec(s, OverlayRuntimeProfile); e != nil {
		t.Fatal(e)
	}
	d, _ := dynamicFixture()
	if validateRuntimeSpec(d, OverlayRuntimeProfile) == nil {
		t.Fatal("overlay runtime accepted Dynamic Fee input")
	}
	lp := Commit(Body{Schema: Domain})
	if validateRuntimeSpec(lp, OverlayRuntimeProfile) == nil {
		t.Fatal("overlay runtime accepted LP input")
	}
	// Domains cannot carry another domain's intervention.
	for i, mutate := range []func(*Spec){
		func(x *Spec) { x.Schema = Domain },
		func(x *Spec) { x.Schema = DynamicDomain },
		func(x *Spec) { x.Intervention = d.Intervention },
		func(x *Spec) { x.Overlay = nil },
	} {
		x, _ := overlaySpec(dynamicOffItem, lpItem(23))
		mutate(&x)
		x = Commit(x.Body)
		raw, _ := Canonical(x)
		if _, e := Parse(append(raw, '\n')); e == nil || e.Error() != "SCENARIO_DOMAIN_OR_COMMITMENT" {
			t.Fatalf("mutation %d parsed: %v", i, e)
		}
	}
	// Unknown top-level and descriptor fields are refused by the strict decoder.
	top := []byte(string(raw[:len(raw)-1]) + `,"unexpected":1}`)
	inner := []byte(strings.Replace(string(raw), `"kind":"DYNAMIC_FEE"`, `"kind":"DYNAMIC_FEE","maxFeePips":0`, 1))
	if string(inner) == string(raw) {
		t.Fatal("fixture shape")
	}
	for _, bad := range [][]byte{top, inner} {
		if _, e := Parse(append(bad, '\n')); e == nil {
			t.Fatal("unknown field accepted")
		}
	}
	// The legacy profiles still parse their own inputs.
	draw, _ := Canonical(d)
	if _, e := Parse(append(draw, '\n')); e != nil {
		t.Fatal(e)
	}
}

func TestOverlayLpZeroIsExplicitAndOmissionIsRefused(t *testing.T) {
	s, p := overlaySpec(lpItem(0))
	if _, e := validateOverlay(s, p); e != nil {
		t.Fatal(e)
	}
	if f := decodeOverlayFields(s.Configs.Variant[0], dynamicRootOn); f.LpBps != 0 || f.MaxFeePips != 11500 || f.Sensitivity != 2 {
		t.Fatalf("lp0 fields %+v", f)
	}
	raw, _ := Canonical(s)
	if !strings.Contains(string(raw), `"interventions":[{"kind":"LP_REWARDS_BPS","lpBps":0}]`) {
		t.Fatal("lpBps 0 must stay present in the canonical encoding")
	}
	if _, e := Parse(append(raw, '\n')); e != nil {
		t.Fatal(e)
	}
	// null decodes to an omitted pointer, so the bytes are not canonical.
	null := strings.Replace(string(raw), `"lpBps":0`, `"lpBps":null`, 1)
	if _, e := Parse(append([]byte(null), '\n')); e == nil || e.Error() != "CANONICAL_SPEC_REQUIRED" {
		t.Fatal("null lpBps accepted", e)
	}
	// An omitted parameter is refused by the typed rule even when every commitment is fresh.
	x, q := overlaySpec(lpItem(0))
	x.Overlay.Interventions[0].LpBps = nil
	x.Overlay.Commitment = overlayTransformID(*x.Overlay)
	x.Origin.Capsule = overlayCapsule(x)
	_, e := validateOverlay(Commit(x.Body), q)
	expectCode(t, e, "CONFIG_OVERLAY_LP_PARAMETER")
}

func TestOverlayRuntimeRefusesDiscoveryAndDiagnostic(t *testing.T) {
	for _, b := range []map[string]any{{"discoveryProfile": "rhook/scenario-witness-discovery/0.1"}, {"diagnosticProfile": "x"}} {
		expectCode(t, offlinePairOnly(OverlayRuntimeProfile, b), "CONFIG_OVERLAY_OFFLINE_PAIR_ONLY")
		expectCode(t, offlinePairOnly(DynamicRuntimeProfile, b), "DYNAMIC_OFFLINE_PAIR_ONLY")
		if offlinePairOnly(RuntimeProfile, b) != nil {
			t.Fatal("LP profile keeps its discovery and diagnostic modes")
		}
	}
	if offlinePairOnly(OverlayRuntimeProfile, map[string]any{}) != nil {
		t.Fatal("plain pair refused")
	}
}
