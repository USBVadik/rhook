package main

import (
	"encoding/json"
	"github.com/ethereum/go-ethereum/common"
	prestate "local/rhook-robinhood"
	"testing"
	"time"
)

// Only in-memory plans, arbitrary invalid bytes and fake worlds are used.
func TestExactPlanAuthority(t *testing.T) {
	// go test links the package under its module path, while the production
	// executable uses main.sourceCommitment. Exercise admission with a mock pin.
	previous := sourceCommitment
	sourceCommitment = "synthetic-reviewed-source"
	defer func() { sourceCommitment = previous }()
	p := planPins{sourceCommitment, profile, semanticCommitment, requestCommitment, policyCommitment, runtimeCommitment}
	b := portableBinding{planPins: p, Operation: "new", Binary: "binary", Plan: digest(planBytes), Package: "/input", Output: "/fresh"}
	a := portableAuthority{planPins: p, Approved: true, Domain: "HOOKR_PLAN_NATIVE_0_1", Operation: "new", Binary: "binary", Package: "/input", Output: "/fresh", NotBefore: 990, Expires: 1200, NoRetry: true, MacReady: true, Context: "require_escalated"}
	a.Maximum.ACTUAL, a.Maximum.BRANCH = 1, 1
	if e := checkAuthority(a, b, "/fresh", "binary", time.Unix(1000, 0)); e != nil {
		t.Fatal(e)
	}
	for _, change := range []func(*portableAuthority){
		func(x *portableAuthority) { x.Approved = false }, func(x *portableAuthority) { x.Domain = "DEVELOPER_SAVED_PAIR03_V2" },
		func(x *portableAuthority) { x.Source = "changed" }, func(x *portableAuthority) { x.Policy = "old-policy" },
		func(x *portableAuthority) { x.Runtime = "old-plan" }, func(x *portableAuthority) { x.Semantic = "changed" },
		func(x *portableAuthority) { x.Request = "changed" }, func(x *portableAuthority) { x.Binary = "changed" },
		func(x *portableAuthority) { x.Maximum.B = 1 }, func(x *portableAuthority) { x.RPC = 1 },
		func(x *portableAuthority) { x.Expires = 1000 }, func(x *portableAuthority) { x.NoRetry = false },
	} {
		bad := a
		change(&bad)
		if checkAuthority(bad, b, "/fresh", "binary", time.Unix(1000, 0)) == nil {
			t.Fatal("bad authority accepted")
		}
	}
	bad := b
	bad.Source = "unreviewed"
	if checkAuthority(a, bad, "/fresh", "binary", time.Unix(1000, 0)) == nil {
		t.Fatal("bad binding accepted")
	}
}

func TestScopedPlanRejectsChangedCheckpointWordOrInput(t *testing.T) {
	p := loadPlan()
	if e := validateScopedPlan(p); e != nil {
		t.Fatal(e)
	}
	for _, change := range []func(*Plan){
		func(x *Plan) { x.Checkpoint.BlockNumber++ }, func(x *Plan) { x.Intervention.ExpectedOldWord[31] ^= 1 },
		func(x *Plan) { x.Intervention.Slot = common.Hash{} }, func(x *Plan) { x.Witness = "incomplete" },
		func(x *Plan) { x.Subject = common.Hash{} }, func(x *Plan) { x.PackageSHA = "substituted" },
		func(x *Plan) { x.Transactions = 6 }, func(x *Plan) { x.Intervention.NewWord[11] = 0 },
	} {
		bad := p
		change(&bad)
		if validateScopedPlan(bad) == nil {
			t.Fatal("changed plan accepted")
		}
	}
	var full struct {
		Arrivals []common.Hash `json:"arrivals"`
	}
	if json.Unmarshal(planBytes, &full) != nil || len(full.Arrivals) != 7 || full.Arrivals[3] != p.Subject {
		t.Fatal("arrivals")
	}
	for _, raw := range [][]byte{nil, []byte(`{}`), []byte(`{"codes":["0x00"],"state":[]}`)} {
		if _, e := checkedFresh(raw, p); e == nil {
			t.Fatal("missing or substituted package bytes admitted")
		}
	}
}

func TestExactFiftyReplacementAndLegacyZeroRejection(t *testing.T) {
	p := loadPlan()
	got, e := prestate.CheckedLPReplacement(p.Intervention.ExpectedOldWord, p.Intervention.ExpectedOldWord)
	if e != nil || got != p.Intervention.NewWord || got[11] != 50 {
		t.Fatal("exact 100-to-50 guard", e)
	}
	bad := p.Intervention
	bad.NewWord[11] = 0
	if prestate.ValidateLPIntervention(bad, p.Checkpoint) == nil {
		t.Fatal("old zero accepted")
	}
	current := p.Intervention.ExpectedOldWord
	current[31] ^= 1
	if _, e := prestate.CheckedLPReplacement(current, p.Intervention.ExpectedOldWord); e == nil {
		t.Fatal("wrong old word accepted")
	}
}
