package main

import (
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	prestate "local/rhook-robinhood"
)

//go:embed plan.json
var planBytes []byte

type Plan struct {
	PackagePath  string                           `json:"packagePath"`
	PackageSHA   string                           `json:"packageSha256"`
	Input        string                           `json:"inputCommitment"`
	Witness      string                           `json:"witnessCommitment"`
	Checkpoint   prestate.Checkpoint              `json:"checkpoint"`
	Block        uint64                           `json:"blockNumber"`
	BlockHash    common.Hash                      `json:"blockHash"`
	StateRoot    common.Hash                      `json:"stateRoot"`
	ReceiptsRoot common.Hash                      `json:"receiptsRoot"`
	Transactions int                              `json:"transactions"`
	Subject      common.Hash                      `json:"subject"`
	Sender       common.Address                   `json:"sender"`
	Router       common.Address                   `json:"router"`
	Observation  prestate.EconomicObservationPlan `json:"observation"`
	Intervention prestate.LPIntervention          `json:"intervention"`
}

func digest(b []byte) string { v := sha256.Sum256(b); return hex.EncodeToString(v[:]) }
func loadPlan() Plan {
	var p Plan
	if e := json.Unmarshal(planBytes, &p); e != nil {
		panic(e)
	}
	return p
}

// Only this factory constructs execution bridges. The existing library creates
// a nil Source; it records the first missing lookup but cannot acquire state.
type world interface {
	Run(*prestate.LPIntervention) (*prestate.CalibrationResult, error)
	Attempts() []prestate.Attempt
	Close()
}
type savedWorld struct {
	offline *prestate.OfflineCalibration
	plan    Plan
}

func (w *savedWorld) Run(i *prestate.LPIntervention) (*prestate.CalibrationResult, error) {
	return prestate.RunHookrObserved(w.offline.Candidate, w.offline.Bridge, i, w.plan.Observation)
}
func (w *savedWorld) Attempts() []prestate.Attempt { return w.offline.Attempts() }
func (w *savedWorld) Close()                       { w.offline.Bridge.Close() }
func fresh(raw []byte, p Plan) (world, error) {
	if digest(raw) != p.PackageSHA {
		return nil, errors.New("PACKAGE_SHA256_MISMATCH")
	}
	o, e := prestate.PrepareOfflineCalibration(raw, p.Input, p.Witness)
	if e != nil {
		return nil, e
	}
	inv := o.Inventory
	if inv.Checkpoint != p.Checkpoint || inv.BlockNumber != p.Block || inv.BlockHash != p.BlockHash || inv.ExpectedStateRoot != p.StateRoot || inv.ExpectedReceiptsRoot != p.ReceiptsRoot || inv.Transactions != p.Transactions || len(o.TxHashes) != 7 || o.TxHashes[3] != p.Subject {
		o.Bridge.Close()
		return nil, errors.New("EXACT_SAVED_INPUT_IDENTITY_MISMATCH")
	}
	// Recheck the real sender/router; the old captured plan had zero placeholders.
	var pkg prestate.BlockPackage
	if e = json.Unmarshal(raw, &pkg); e != nil {
		o.Bridge.Close()
		return nil, e
	}
	var tx types.Transaction
	if e = tx.UnmarshalBinary(pkg.Raw[3]); e != nil {
		o.Bridge.Close()
		return nil, e
	}
	sender, e := types.Sender(types.LatestSignerForChainID(tx.ChainId()), &tx)
	if e != nil || sender != p.Sender || tx.To() == nil || *tx.To() != p.Router || tx.Hash() != p.Subject {
		o.Bridge.Close()
		return nil, errors.New("SUBJECT_SENDER_ROUTER_MISMATCH")
	}
	if e = prestate.ValidateLPIntervention(p.Intervention, p.Checkpoint); e != nil {
		o.Bridge.Close()
		return nil, e
	}
	return &savedWorld{o, p}, nil
}

func store(dir, name string, v any) error {
	b, e := json.MarshalIndent(v, "", "  ")
	if e != nil {
		return e
	}
	b = append(b, '\n')
	f, e := os.OpenFile(filepath.Join(dir, name), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	_, e = f.Write(b)
	if e == nil {
		e = f.Sync()
	}
	ce := f.Close()
	if e == nil {
		e = ce
	}
	if e != nil {
		return e
	}
	d, e := os.Open(dir)
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}

type journal struct {
	dir      string
	seq      int
	previous string
}

func (j *journal) event(kind string, data any) error {
	row := map[string]any{"sequence": j.seq, "previousSha256": j.previous, "utc": time.Now().UTC().Format(time.RFC3339Nano), "event": kind, "data": data}
	b, e := json.Marshal(row)
	if e != nil {
		return e
	}
	f, e := os.OpenFile(filepath.Join(j.dir, "JOURNAL.jsonl"), os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0600)
	if e != nil {
		return e
	}
	_, e = f.Write(append(b, '\n'))
	if e == nil {
		e = f.Sync()
	}
	ce := f.Close()
	if e == nil {
		e = ce
	}
	if e != nil {
		return e
	}
	j.previous = digest(b)
	j.seq++
	return nil
}

type Counts struct {
	Actual int `json:"ACTUAL"`
	Branch int `json:"BRANCH"`
	B      int `json:"B"`
}
type Outcome struct {
	Terminal          string `json:"terminal"`
	Cause             string `json:"cause,omitempty"`
	Counts            Counts `json:"nativeInvocations"`
	RPC               int    `json:"RPC"`
	WSS               int    `json:"WSS"`
	ActualValid       bool   `json:"canonicalActualValid"`
	EconomicAssurance string `json:"economicAssurance"`
	Heterogeneous     string `json:"heterogeneousAgreement"`
	ExternalDelivery  string `json:"externalDelivery"`
}

func canonical(r *prestate.CalibrationResult, p Plan) bool {
	return r != nil && r.World == "ACTUAL" && r.Matched && r.StateRoot == p.StateRoot && r.ReceiptsRoot == p.ReceiptsRoot && r.BlockHash == p.BlockHash && r.Transactions == 7 && r.InputCommitment == p.Input
}

type factory func() (world, error)
type pair struct {
	used    bool
	plan    Plan
	factory factory
	dir     string
}

func (c *pair) run() (out Outcome, err error) {
	out = Outcome{Terminal: "HOST_STOP", EconomicAssurance: "UNRESOLVED", Heterogeneous: "NOT_EVALUATED", ExternalDelivery: "HOLD"}
	if c.used {
		return out, errors.New("PAIR_ALREADY_CONSUMED")
	}
	c.used = true
	// O_EXCL is a second, durable latch. Even uncertain/interrupted entry consumes it.
	if err = store(c.dir, "PAIR_CONSUMED.json", map[string]any{"packageSha256": c.plan.PackageSHA, "maximumInvocations": Counts{1, 1, 0}}); err != nil {
		return
	}
	j := &journal{dir: c.dir}
	actual, e := c.factory()
	if e != nil {
		out.Cause = e.Error()
		return out, nil
	}
	defer actual.Close()
	if err = j.event("ACTUAL_ENTERED", Counts{1, 0, 0}); err != nil {
		return
	}
	out.Counts.Actual = 1
	a, ae := actual.Run(nil)
	if err = store(c.dir, "ACTUAL.json", map[string]any{"result": a, "error": errorText(ae), "missingLookupAttempts": actual.Attempts()}); err != nil {
		return
	}
	if ae != nil || !canonical(a, c.plan) {
		if ae != nil {
			out.Terminal, _ = prestate.ClassifyCalibrationError(ae)
			out.Cause = ae.Error()
		} else {
			out.Terminal = "CANONICAL_EXECUTION_MISMATCH"
			out.Cause = "EXPLICIT_CANONICAL_COMMITMENT_MISMATCH"
		}
		return out, j.event("ACTUAL_STOP", out)
	}
	out.ActualValid = true
	if err = j.event("CANONICAL_ACTUAL_MATCH", map[string]any{"stateRoot": a.StateRoot, "receiptsRoot": a.ReceiptsRoot, "blockHash": a.BlockHash}); err != nil {
		return
	}
	// Fresh factory call, identical immutable original package. Never reuse ACTUAL.
	branch, e := c.factory()
	if e != nil {
		out.Terminal = "BRANCH_HOST_STOP"
		out.Cause = e.Error()
		return out, nil
	}
	defer branch.Close()
	if branch == actual {
		out.Cause = "BRIDGE_REUSE_REJECTED"
		out.Terminal = "BRANCH_HOST_STOP"
		return out, nil
	}
	if err = j.event("BRANCH_ENTERED", Counts{1, 1, 0}); err != nil {
		return
	}
	out.Counts.Branch = 1
	b, be := branch.Run(&c.plan.Intervention)
	if err = store(c.dir, "BRANCH.json", map[string]any{"result": b, "error": errorText(be), "missingLookupAttempts": branch.Attempts()}); err != nil {
		return
	}
	if be != nil {
		out.Terminal = "BRANCH_HOST_STOP"
		out.Cause = be.Error()
		return out, j.event("BRANCH_STOP", out)
	}
	if b == nil || b.World != "BRANCH" || b.Transactions != 7 || b.InputCommitment != c.plan.Input || b.Patch == nil || b.Patch.Intervention != c.plan.Intervention || b.Patch.SemanticInitialWrites != 1 || !b.Patch.OriginalWitnessUnchanged {
		out.Terminal = "BRANCH_STOP"
		out.Cause = "BRANCH_EVIDENCE_INCOMPLETE"
		return out, nil
	}
	// BRANCH.Matched compares to original canonical roots; false is expected and
	// never an error. Reverted receipt status remains an actual EVM observation.
	out.Terminal = "GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED"
	if err = store(c.dir, "COMPARISON.json", map[string]any{"actualStateRoot": a.StateRoot, "branchStateRoot": b.StateRoot, "actualGasUsed": a.GasUsed, "branchGasUsed": b.GasUsed, "actualReceipts": a.Receipts, "branchReceipts": b.Receipts, "actualObservation": a.Observation, "branchObservation": b.Observation, "interpretation": "Raw logs/calls/state; no direct-buy projector, wallet qualification or economic assurance. EVM receipt status 0 is retained. Both worlds contain all seven arrivals."}); err != nil {
		return
	}
	return out, j.event("PAIR_OBSERVED_UNQUALIFIED", out)
}
func errorText(e error) string {
	if e == nil {
		return ""
	}
	return e.Error()
}
