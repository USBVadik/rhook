package scenario

// Optional regressions against the retained private checkpoint witness and the
// retained legacy run records. They authenticate inputs and reconstruct the
// initial StateDB only; Nitro's producer is never entered and nothing is written.
// Skipped unless the local paths are supplied.
import (
	"bytes"
	"os"
	"sort"
	"strings"
	"testing"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/crypto"
)

func retainedSource(t *testing.T) Spec {
	t.Helper()
	path := os.Getenv("RHOOK_OVERLAY_SOURCE")
	if path == "" {
		t.Skip("retained checkpoint source not supplied")
	}
	raw, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	s, e := Parse(raw)
	if e != nil || s.Schema != Domain {
		t.Fatal("source must be the authenticated LP-domain checkpoint input", e)
	}
	return s
}

// overlayFromSource converts the retained LP-domain input into an overlay input
// for the given profile and set, with fresh commitments.
func overlayFromSource(t *testing.T, src Spec, p profile, items ...TypedIntervention) []byte {
	t.Helper()
	b := src.Body
	b.Schema = OverlayDomain
	b.Configs = Configurations{Baseline: append([]common.Hash{}, p.BaselineWords...), Variant: append([]common.Hash{}, p.BaselineWords...)}
	canonical, e := canonicalInterventions(items)
	if e != nil {
		t.Fatal(e)
	}
	c, e := composeOverlay(overlayRegistry, canonical, p, p.BaselineWords[0], dynamicRootOn)
	if e != nil {
		t.Fatal(e)
	}
	b.Configs.Variant[0] = c.Rules
	o := &ConfigOverlay{Schema: OverlayDomain + "/transform", OriginalRoot: b.Checkpoint.StateRoot, Pool: p.Pool, RootCode: p.Pins[p.PoolKey.Hooks], RulesCode: p.Pins[rulesAddress],
		Plan: "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", Interventions: canonical, Writes: c.Writes}
	o.Commitment = overlayTransformID(*o)
	b.Overlay = o
	b.Origin = Origin{Kind: OverlayKind}
	s := Commit(b)
	s.Origin.Capsule = overlayCapsule(s)
	s = Commit(s.Body)
	raw, e := Canonical(s)
	if e != nil {
		t.Fatal(e)
	}
	return append(raw, '\n')
}

func TestOverlayAdmitsRetainedWitnessAndReadsBackStateDB(t *testing.T) {
	src := retainedSource(t)
	p := overlayProfile()
	cases := []struct {
		name  string
		items []TypedIntervention
		want  OverlayFields
		roots bool
	}{
		{"lp23", []TypedIntervention{lpItem(23)}, OverlayFields{LpBps: 23, MaxFeePips: 11500, Sensitivity: 2, Mode: 3}, false},
		{"dynamic-off", []TypedIntervention{dynamicOffItem}, OverlayFields{LpBps: 100, MaxFeePips: 3000, Sensitivity: 0, Mode: 2}, true},
		{"lp23+dynamic-off", []TypedIntervention{lpItem(23), dynamicOffItem}, OverlayFields{LpBps: 23, MaxFeePips: 3000, Sensitivity: 0, Mode: 2}, true},
	}
	for _, c := range cases {
		raw := overlayFromSource(t, src, p, c.items...)
		a, e := AdmitOverlay(raw)
		if e != nil {
			t.Fatalf("%s: %v", c.name, e)
		}
		if _, e = Admit(raw); e == nil {
			t.Fatalf("%s: LP profile admitted overlay input", c.name)
		}
		if _, e = AdmitDynamic(raw); e == nil {
			t.Fatalf("%s: Dynamic Fee profile admitted overlay input", c.name)
		}
		base, bf, e := deriveConfigOverlay(a.input, Baseline)
		if e != nil {
			t.Fatal(e)
		}
		variant, vf, e := deriveConfigOverlay(a.input, Variant)
		if e != nil {
			t.Fatal(e)
		}
		if bf.LpBps != 100 || bf.MaxFeePips != 11500 || bf.Sensitivity != 2 || bf.Mode != 3 || bf.RulesWord != wordOriginal || bf.RootWord != dynamicRootOn {
			t.Fatalf("%s baseline read-back %+v", c.name, bf)
		}
		vf.RulesWord, vf.RootWord = common.Hash{}, common.Hash{}
		if vf != c.want {
			t.Fatalf("%s variant read-back %+v", c.name, vf)
		}
		if base.InitialRoot != base.CommonRoot || variant.InitialRoot == variant.CommonRoot || base.CommonRoot != variant.CommonRoot {
			t.Fatalf("%s initial roots", c.name)
		}
		if variant.Intervention != a.input.spec.Overlay.Commitment || len(variant.Writes) != len(a.input.spec.Overlay.Writes) {
			t.Fatalf("%s overlay evidence", c.name)
		}
	}
}

func TestOverlayAdmissionAuthenticatesOriginalWordsAgainstWitness(t *testing.T) {
	src := retainedSource(t)
	// A declared baseline that differs from the witness in any Rules word is refused by the StateDB check.
	for i := 0; i < 4; i++ {
		p := overlayProfile()
		w := p.BaselineWords[i]
		w[0] ^= 0x80 // bit 255: outside every overlay field, so composition itself still succeeds
		p.BaselineWords[i] = w
		raw := overlayFromSource(t, src, p, lpItem(23), dynamicOffItem)
		_, e := admit(raw, p)
		expectCode(t, e, "AUTHENTICATED_BASELINE_WORD")
	}
	// A declared Root record that differs from the witness is refused before any overlay.
	on, off := dynamicRootOn, dynamicRootOff
	defer func() { dynamicRootOn, dynamicRootOff = on, off }()
	dynamicRootOn[2] ^= 1
	dynamicRootOff[2] ^= 1
	raw := overlayFromSource(t, src, overlayProfile(), lpItem(23), dynamicOffItem)
	_, e := AdmitOverlay(raw)
	expectCode(t, e, "CONFIG_OVERLAY_ORIGINAL_ROOT_WORD")
}

func TestOverlayRefusesCorruptedWitness(t *testing.T) {
	src := retainedSource(t)
	resort := func(rows []hexutil.Bytes) []hexutil.Bytes {
		sort.Slice(rows, func(i, j int) bool { return crypto.Keccak256Hash(rows[i]).Hex() < crypto.Keccak256Hash(rows[j]).Hex() })
		return rows
	}
	mutations := map[string]func(*Spec){
		"root preimage removed": func(s *Spec) {
			var rows []hexutil.Bytes
			for _, n := range s.Inventory.Nodes {
				if crypto.Keccak256Hash(n) != s.Checkpoint.StateRoot {
					rows = append(rows, n)
				}
			}
			s.Inventory.Nodes = rows
		},
		"every second node removed": func(s *Spec) {
			var rows []hexutil.Bytes
			for i, n := range s.Inventory.Nodes {
				if i%2 == 0 || crypto.Keccak256Hash(n) == s.Checkpoint.StateRoot {
					rows = append(rows, n)
				}
			}
			s.Inventory.Nodes = rows
		},
		"node byte flipped": func(s *Spec) {
			rows := make([]hexutil.Bytes, len(s.Inventory.Nodes))
			for i, n := range s.Inventory.Nodes {
				rows[i] = append(hexutil.Bytes{}, n...)
				if crypto.Keccak256Hash(n) == s.Checkpoint.StateRoot {
					rows[i][len(rows[i])-1] ^= 1
				}
			}
			s.Inventory.Nodes = resort(rows)
		},
		"unsorted inventory": func(s *Spec) {
			rows := append([]hexutil.Bytes{}, s.Inventory.Nodes...)
			rows[0], rows[1] = rows[1], rows[0]
			s.Inventory.Nodes = rows
		},
		// Admission authenticates the initial prerequisites only: the pinned release
		// code is one of them. A code that only execution would read is not checked
		// here; its absence stops the native run instead (dynamic coverage).
		"Rules code preimage removed": func(s *Spec) {
			var rows []hexutil.Bytes
			for _, c := range s.Inventory.Codes {
				if crypto.Keccak256Hash(c) != overlayProfile().Pins[rulesAddress] {
					rows = append(rows, c)
				}
			}
			if len(rows) != len(s.Inventory.Codes)-1 {
				panic("fixture: Rules code not in inventory")
			}
			s.Inventory.Codes = rows
		},
	}
	for name, mutate := range mutations {
		raw := overlayFromSource(t, src, overlayProfile(), lpItem(23), dynamicOffItem)
		s, e := Parse(raw)
		if e != nil {
			t.Fatal(e)
		}
		mutate(&s)
		s = Commit(s.Body)
		mutated, _ := Canonical(s)
		if _, e = AdmitOverlay(append(mutated, '\n')); e == nil {
			t.Fatalf("%s: corrupted witness admitted", name)
		}
	}
}

// Legacy prepared inputs keep byte-identical canonical encodings and commitments
// under this source, and the overlay profile refuses them.
func TestLegacyInputsKeepEncodingAndProfile(t *testing.T) {
	list := os.Getenv("RHOOK_LEGACY_SPECS")
	if list == "" {
		t.Skip("retained legacy prepared inputs not supplied")
	}
	for _, path := range strings.Split(list, ":") {
		raw, e := os.ReadFile(path)
		if e != nil {
			t.Fatal(e)
		}
		s, e := Parse(raw)
		if e != nil {
			t.Fatalf("%s: %v", path, e)
		}
		again, _ := Canonical(s)
		if !bytes.Equal(append(again, '\n'), raw) || s.Commitment != hashValue(s.Schema, s.Body) || s.Overlay != nil {
			t.Fatalf("%s: encoding or commitment drift", path)
		}
		switch s.Schema {
		case Domain:
			_, e = Admit(raw)
		case DynamicDomain:
			_, e = AdmitDynamic(raw)
		default:
			t.Fatalf("%s: unexpected legacy domain %s", path, s.Schema)
		}
		if e != nil {
			t.Fatalf("%s: legacy profile refused its own input: %v", path, e)
		}
		if _, e = AdmitOverlay(raw); e == nil {
			t.Fatalf("%s: overlay profile admitted a legacy input", path)
		}
	}
}

// Retained legacy run evidence still verifies under its own profile and never as overlay evidence.
func TestLegacyEvidenceVerifiesOnlyUnderItsOwnProfile(t *testing.T) {
	list := os.Getenv("RHOOK_LEGACY_RUNS")
	if list == "" {
		t.Skip("retained legacy run records not supplied")
	}
	for _, run := range strings.Split(list, ":") {
		input, e := os.ReadFile(run + "/inputs/SCENARIO.json")
		if e != nil {
			t.Fatal(e)
		}
		final, e := os.ReadFile(run + "/runtime/scenario/FINAL.json")
		if e != nil {
			t.Fatal(e)
		}
		s, e := Parse(input)
		if e != nil {
			t.Fatal(e)
		}
		own, other := VerifyEvidence, VerifyDynamicEvidence
		if s.Schema == DynamicDomain {
			own, other = VerifyDynamicEvidence, VerifyEvidence
		}
		if e = own(input, final); e != nil {
			t.Fatalf("%s: %v", run, e)
		}
		if other(input, final) == nil || VerifyOverlayEvidence(input, final) == nil {
			t.Fatalf("%s: evidence accepted under another profile", run)
		}
	}
}
