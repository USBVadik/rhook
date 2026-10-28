package scenario

import (
	"github.com/ethereum/go-ethereum/common"
	"os"
	"testing"
)

func dynamicFixture() (Spec, profile) {
	p := officialProfile()
	p.Kind = DynamicKind
	b := Body{Schema: DynamicDomain, Pool: p.Pool, Configs: Configurations{Baseline: append([]common.Hash{}, p.BaselineWords...), Variant: append([]common.Hash{}, p.BaselineWords...)}}
	b.Checkpoint.StateRoot = common.HexToHash("0x1234")
	d := &DynamicFeeOff{Schema: DynamicDomain + "/transform", OriginalRoot: b.Checkpoint.StateRoot, Pool: p.Pool, RootCode: p.Pins[p.PoolKey.Hooks], RulesCode: p.Pins[rulesAddress], Plan: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
	old := p.BaselineWords[0]
	next := dynamicConfigOff(old, p.BaseLpFee)
	b.Configs.Variant[0] = next
	d.Writes = []StorageWrite{{rulesAddress, p.ConfigSlot, old, next}, {p.PoolKey.Hooks, p.RootSlot, dynamicRootOn, dynamicRootOff}}
	d.Commitment = dynamicTransformID(*d)
	b.Intervention = d
	s := Commit(b)
	s.Origin = Origin{Kind: DynamicKind, Capsule: dynamicCapsule(s)}
	return Commit(s.Body), p
}
func TestDynamicRelationIsExactTwoWrites(t *testing.T) {
	s, p := dynamicFixture()
	if e := validateDynamic(s, p); e != nil {
		t.Fatal(e)
	}
	tests := []func(*Spec){
		func(s *Spec) { s.Configs.Variant[0][10] ^= 1 },
		func(s *Spec) { s.Intervention.Writes[0].After[31] ^= 1 },
		func(s *Spec) { s.Intervention.Writes[1].Address = rulesAddress },
		func(s *Spec) { s.Intervention.Writes[1].After[0] = 0 },
		func(s *Spec) { s.Intervention.Writes = append(s.Intervention.Writes, s.Intervention.Writes[0]) },
		func(s *Spec) { s.Intervention.RootCode = common.Hash{} },
		func(s *Spec) { s.Intervention.OriginalRoot = common.Hash{} },
	}
	for i, change := range tests {
		x, q := dynamicFixture()
		change(&x)
		x.Intervention.Commitment = dynamicTransformID(*x.Intervention)
		if validateDynamic(x, q) == nil {
			t.Fatalf("accepted unauthorized change %d", i)
		}
	}
}

type overlayFixture struct {
	words  map[[52]byte]common.Hash
	writes int
}

func key(a common.Address, k common.Hash) (out [52]byte) {
	copy(out[:20], a[:])
	copy(out[20:], k[:])
	return
}
func (f *overlayFixture) GetState(a common.Address, k common.Hash) common.Hash {
	return f.words[key(a, k)]
}
func (f *overlayFixture) SetState(a common.Address, k, v common.Hash) common.Hash {
	before := f.words[key(a, k)]
	f.words[key(a, k)] = v
	f.writes++
	return before
}
func TestDynamicOverlayChecksAllBeforeAnyWrite(t *testing.T) {
	s, p := dynamicFixture()
	newState := func() *overlayFixture {
		f := &overlayFixture{words: map[[52]byte]common.Hash{}}
		for _, w := range s.Intervention.Writes {
			f.words[key(w.Address, w.Slot)] = w.Before
		}
		return f
	}
	base := newState()
	if _, e := configurationOverlay(base, s, p, Baseline); e != nil || base.writes != 0 {
		t.Fatal(e)
	}
	variant := newState()
	rows, e := configurationOverlay(variant, s, p, Variant)
	if e != nil || variant.writes != 2 || len(rows) != 2 {
		t.Fatal(e)
	}
	if base.GetState(p.PoolKey.Hooks, p.RootSlot) != dynamicRootOn || variant.GetState(p.PoolKey.Hooks, p.RootSlot) != dynamicRootOff {
		t.Fatal("world alias or root overlay")
	}
	bad := newState()
	bad.words[key(p.PoolKey.Hooks, p.RootSlot)] = common.Hash{}
	if _, e = configurationOverlay(bad, s, p, Variant); e == nil || bad.writes != 0 {
		t.Fatal("partial patch")
	}
	if _, e = configurationOverlay(newState(), s, p, "OTHER"); e == nil {
		t.Fatal("unknown world")
	}
}
func TestDynamicDomainAndWorkerProfileCannotDowngrade(t *testing.T) {
	s, _ := dynamicFixture()
	raw, _ := Canonical(s)
	if _, e := Parse(append(raw, '\n')); e != nil {
		t.Fatal(e)
	}
	if validateRuntimeSpec(s, RuntimeProfile) == nil {
		t.Fatal("LP entry accepted dynamic input")
	}
	if e := validateRuntimeSpec(s, DynamicRuntimeProfile); e != nil {
		t.Fatal(e)
	}
	s.Schema = Domain
	s = Commit(s.Body)
	raw, _ = Canonical(s)
	if _, e := Parse(append(raw, '\n')); e == nil {
		t.Fatal("LP domain carried new intervention")
	}
}

// Optional retained-record regression supplies local paths, not network data.
func TestDynamicLegacyRecordedCompatibility(t *testing.T) {
	input, final := os.Getenv("RHOOK_LEGACY_INPUT"), os.Getenv("RHOOK_LEGACY_FINAL")
	if input == "" || final == "" {
		t.Skip("local retained fixtures not supplied")
	}
	raw, e := os.ReadFile(input)
	if e != nil {
		t.Fatal(e)
	}
	evidence, e := os.ReadFile(final)
	if e != nil {
		t.Fatal(e)
	}
	if e = VerifyEvidence(raw, evidence); e != nil {
		t.Fatal(e)
	}
	if VerifyDynamicEvidence(raw, evidence) == nil {
		t.Fatal("LP evidence accepted as Dynamic Fee execution")
	}
}
