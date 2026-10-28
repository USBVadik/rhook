package scenario

import (
	"context"
	"encoding/json"
	"github.com/ethereum/go-ethereum/crypto"
	"os"
	"path/filepath"
	"testing"
)

func TestFenceCannotReuseOrEnterVariantFirst(t *testing.T) {
	f := &workerFence{}
	if f.Enter(context.Background(), Variant) == nil {
		t.Fatal("variant first")
	}
	for _, label := range []string{Baseline, Variant} {
		if e := f.Enter(context.Background(), label); e != nil {
			t.Fatal(e)
		}
	}
	if f.Enter(context.Background(), Baseline) == nil {
		t.Fatal("third invocation")
	}
	if f.Check(context.Background(), Identity{Source: "changed"}, "before") == nil {
		t.Fatal("engine drift")
	}
}
func TestScenarioDomainCannotAcceptHistoricalProfile(t *testing.T) {
	b := Body{Schema: Domain}
	s := Commit(b)
	raw, _ := Canonical(s)
	if _, e := Parse(append(raw, '\n')); e != nil {
		t.Fatal(e)
	}
	b.Schema = "rhook/case-plan/0.1"
	s = Commit(b)
	raw, _ = Canonical(s)
	if _, e := Parse(append(raw, '\n')); e == nil {
		t.Fatal("historical relabel")
	}
}
func TestCanonicalSpecRejectsUnknownAndDuplicateFields(t *testing.T) {
	raw, _ := Canonical(Commit(Body{Schema: Domain}))
	var v map[string]any
	json.Unmarshal(raw, &v)
	v["unexpected"] = true
	bad, _ := Canonical(v)
	if _, e := Parse(append(bad, '\n')); e == nil {
		t.Fatal("unknown field")
	}
	if _, e := Parse([]byte("{\"schema\":\"x\",\"schema\":\"y\"}\n")); e == nil {
		t.Fatal("duplicates")
	}
}
func TestBoundedWorkerReadRejectsSymlinkAndOversize(t *testing.T) {
	d := t.TempDir()
	p := filepath.Join(d, "file")
	os.WriteFile(p, []byte("abcdef"), 0600)
	os.Symlink(p, filepath.Join(d, "link"))
	if _, e := boundedFile(filepath.Join(d, "link"), 8); e == nil {
		t.Fatal("symlink")
	}
	if _, e := boundedFile(p, 5); e == nil {
		t.Fatal("size")
	}
}

func TestOnDemandCannotExpandTheReviewedBuyCountOrCaller(t *testing.T) {
	key, _ := crypto.ToECDSA(crypto.Keccak256([]byte("RHOOK BUILD04 PUBLIC SIMULATION SIGNER; NEVER FUND OR BROADCAST")))
	s := Spec{Body: Body{Setup: Setup{Actor: crypto.PubkeyToAddress(key.PublicKey)}, Actions: []Action{{}}}}
	if e := validateOnDemandShape(s); e != nil {
		t.Fatal(e)
	}
	s.Actions = append(s.Actions, Action{})
	if validateOnDemandShape(s) == nil {
		t.Fatal("expanded action count")
	}
	s.Actions = s.Actions[:1]
	s.Setup.Actor[0] ^= 1
	if validateOnDemandShape(s) == nil {
		t.Fatal("substituted caller")
	}
}
