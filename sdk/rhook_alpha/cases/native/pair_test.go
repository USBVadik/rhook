package main

import (
	"bytes"
	"errors"
	"os"
	"strings"
	"testing"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	prestate "local/rhook-robinhood"
)

type fakeWorld struct {
	result *prestate.CalibrationResult
	err    error
	calls  int
	branch bool
}

func (w *fakeWorld) Run(i *prestate.LPIntervention) (*prestate.CalibrationResult, error) {
	w.calls++
	w.branch = i != nil
	return w.result, w.err
}
func (w *fakeWorld) Attempts() []prestate.Attempt { return nil }
func (w *fakeWorld) Close()                       {}
func goodActual(p Plan) *prestate.CalibrationResult {
	return &prestate.CalibrationResult{World: "ACTUAL", Matched: true, StateRoot: p.StateRoot, ReceiptsRoot: p.ReceiptsRoot, BlockHash: p.BlockHash, Transactions: p.Transactions, InputCommitment: p.Input}
}
func TestActualFailureOrAnyCommitmentMismatchClosesBranch(t *testing.T) {
	for _, which := range []string{"missing", "matched", "state", "receipts", "hash", "arrivals", "input"} {
		t.Run(which, func(t *testing.T) {
			p := syntheticPlan()
			a := &fakeWorld{result: goodActual(p)}
			switch which {
			case "missing":
				a.result = nil
				a.err = &prestate.HostStop{Code: "PROOF_SOURCE_UNAVAILABLE"}
			case "matched":
				a.result.Matched = false
			case "state":
				a.result.StateRoot = common.Hash{}
			case "receipts":
				a.result.ReceiptsRoot = common.Hash{}
			case "hash":
				a.result.BlockHash = common.Hash{}
			case "arrivals":
				a.result.Transactions = p.Transactions - 1
			case "input":
				a.result.InputCommitment = "changed"
			}
			n := 0
			c := pair{plan: p, dir: t.TempDir(), factory: func() (world, error) { n++; return a, nil }}
			out, e := c.run()
			if e != nil || n != 1 || a.calls != 1 || out.Counts.Branch != 0 || out.ActualValid {
				t.Fatalf("branch guard failed: %+v %v factories=%d", out, e, n)
			}
		})
	}
}
func TestIndependentBranchAndOneShotDespiteUnchangedOrRevertedOutcomes(t *testing.T) {
	p := syntheticPlan()
	a := &fakeWorld{result: goodActual(p)}
	b := &fakeWorld{result: &prestate.CalibrationResult{World: "BRANCH", Transactions: p.Transactions, InputCommitment: p.Input, Matched: false, Receipts: types.Receipts{&types.Receipt{Status: 0, CumulativeGasUsed: 123, Logs: []*types.Log{}}}, Patch: &prestate.LPWriteRecord{Intervention: p.Intervention, SemanticInitialWrites: 1, OriginalWitnessUnchanged: true}}}
	n := 0
	dir := t.TempDir()
	factory := func() (world, error) {
		n++
		if n == 1 {
			return a, nil
		}
		return b, nil
	}
	c := pair{plan: p, dir: dir, factory: factory}
	out, e := c.run()
	if e != nil || out.Terminal != "GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED" || n != 2 || a.branch || !b.branch || a.calls != 1 || b.calls != 1 {
		t.Fatalf("bad pair %+v %v", out, e)
	}
	retained, e := os.ReadFile(dir + "/BRANCH.json")
	if e != nil || !bytes.Contains(retained, []byte(`"status": "0x0"`)) {
		t.Fatalf("EVM failure receipt not preserved: %v", e)
	}
	if _, e = c.run(); e == nil {
		t.Fatal("same controller reused")
	}
	second := pair{plan: p, dir: dir, factory: factory}
	if _, e = second.run(); e == nil || n != 2 {
		t.Fatal("durable consumption bypass")
	}
}
func TestBranchMissingStatePreservesCanonicalActualAndExactCause(t *testing.T) {
	p := syntheticPlan()
	a := &fakeWorld{result: goodActual(p)}
	b := &fakeWorld{err: &prestate.HostStop{Code: "CODE_SOURCE_UNAVAILABLE", Detail: "exact missing code"}}
	n := 0
	c := pair{plan: p, dir: t.TempDir(), factory: func() (world, error) {
		n++
		if n == 1 {
			return a, nil
		}
		return b, nil
	}}
	out, e := c.run()
	if e != nil || !out.ActualValid || out.Terminal != "BRANCH_HOST_STOP" || out.Counts.Actual != 1 || out.Counts.Branch != 1 || !strings.Contains(out.Cause, "exact missing code") {
		t.Fatalf("lost partial result %+v %v", out, e)
	}
}
func TestReusedBridgeAndBranchPreparationFailurePreserveActual(t *testing.T) {
	for _, reuse := range []bool{true, false} {
		p := syntheticPlan()
		a := &fakeWorld{result: goodActual(p)}
		n := 0
		c := pair{plan: p, dir: t.TempDir(), factory: func() (world, error) {
			n++
			if n == 2 && !reuse {
				return nil, errors.New("missing branch state")
			}
			return a, nil
		}}
		out, e := c.run()
		if e != nil || !out.ActualValid || out.Counts.Branch != 0 || a.calls != 1 || out.Terminal != "BRANCH_HOST_STOP" {
			t.Fatalf("bad branch stop %+v %v", out, e)
		}
	}
}

func syntheticPlan() Plan {
	return Plan{Transactions: 5, StateRoot: common.Hash{1}, ReceiptsRoot: common.Hash{2}, BlockHash: common.Hash{3}, Input: "synthetic-no-chain-claim"}
}
