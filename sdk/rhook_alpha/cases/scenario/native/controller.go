package scenario

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sync/atomic"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	prestate "local/rhook-robinhood"
)

// Fence is a required integration with the external owner-authorized supervisor.
// It must validate engine pins, authority and resources; this library grants none.
// An in-process context cannot preempt Nitro. Production needs an OS process fence.
type Fence interface {
	Check(context.Context, Identity, string) error
}

type ActionMapping struct {
	ID      string      `json:"actionId"`
	Ordinal int         `json:"transactionOrdinal"`
	Hash    common.Hash `json:"transactionHash"`
}
type Overlay struct {
	Intervention string         `json:"interventionCommitment,omitempty"`
	Writes       []StorageWrite `json:"storageWrites,omitempty"`
	Common       Setup          `json:"commonSimulationSetup"`
	CommonRoot   common.Hash    `json:"commonSetupRoot"`
	InitialRoot  common.Hash    `json:"worldInitialRoot"`
	Account      common.Address `json:"configurationAccount"`
	Slot         common.Hash    `json:"configurationSlot"`
	Before       common.Hash    `json:"originalWord"`
	After        common.Hash    `json:"initialWord"`
}
type WorldResult struct {
	World              string          `json:"world"`
	Scenario           string          `json:"scenarioCommitment"`
	Overlay            Overlay         `json:"overlay"`
	Header             *types.Header   `json:"producedSyntheticHeader"`
	StateRoot          common.Hash     `json:"stateRoot"`
	ReceiptsRoot       common.Hash     `json:"receiptsRoot"`
	SystemTransaction  common.Hash     `json:"systemTransactionHash"`
	Actions            []ActionMapping `json:"actionMapping"`
	Receipts           types.Receipts  `json:"receipts"`
	ActorBalanceBefore string          `json:"actorBalanceBefore"`
	ActorBalanceAfter  string          `json:"actorBalanceAfter"`
	ActorNonceAfter    uint64          `json:"actorNonceAfter"`
	Witness            string          `json:"originalWitnessCommitment"`
	ObservedDeltas     string          `json:"stateDeltaCoverage"`
}
type Outcome struct {
	Schema              string         `json:"schema"`
	Scenario            string         `json:"scenarioCommitment"`
	Profile             string         `json:"profile"`
	Status              string         `json:"status"`
	Cause               string         `json:"cause,omitempty"`
	Failure             *FailureDetail `json:"failure,omitempty"`
	Worlds              []*WorldResult `json:"worlds"`
	ProducerInvocations int            `json:"producerInvocations"`
	Cleanup             bool           `json:"ownedBridgesClosed"`
	QualifiedClaims     int            `json:"qualifiedClaims"`
	ExternalDelivery    string         `json:"externalDelivery"`
	Commitment          string         `json:"evidenceCommitment,omitempty"`
	DiscoveryOnly       bool           `json:"discoveryOnly,omitempty"`
	DiagnosticOnly      bool           `json:"diagnosticOnly,omitempty"`
}

type FailureDetail struct {
	World          string             `json:"world"`
	Cause          string             `json:"cause"`
	HostCode       string             `json:"hostCode,omitempty"`
	MissingLookups []prestate.Attempt `json:"missingLookupAttempts"`
}

type Controller struct{ used atomic.Bool }

func store(dir, name string, v any, remaining *int64) error {
	raw, e := Canonical(v)
	if e != nil {
		return e
	}
	raw = append(raw, '\n')
	if int64(len(raw)) > *remaining {
		return errors.New("EVIDENCE_OUTPUT_LIMIT")
	}
	f, e := os.OpenFile(filepath.Join(dir, name), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	if _, e = f.Write(raw); e == nil {
		e = f.Sync()
	}
	ce := f.Close()
	if e == nil {
		e = ce
	}
	if e != nil {
		return e
	}
	*remaining -= int64(len(raw))
	return syncDir(dir)
}
func syncDir(dir string) error {
	f, e := os.Open(dir)
	if e != nil {
		return e
	}
	defer f.Close()
	return f.Sync()
}

// Execute runs no acquisition and has no historical mode. Output must be fresh.
// The SDK worker supplies a separately bound one-shot permit and OS supervision.
func (c *Controller) Execute(ctx context.Context, a *Admission, fence Fence, dir string) (out Outcome, err error) {
	return c.execute(ctx, a, fence, dir)
}

func (c *Controller) execute(ctx context.Context, a *Admission, fence Fence, dir string) (out Outcome, err error) {
	if !c.used.CompareAndSwap(false, true) {
		return out, errors.New("CONTROLLER_ALREADY_USED")
	}
	if a == nil || a.input == nil || fence == nil {
		return out, errors.New("ADMISSION_AND_EXTERNAL_FENCE_REQUIRED")
	}
	x := a.input
	copyInput := *x
	x = &copyInput
	if gate, ok := fence.(NativeGate); ok {
		x.producerGate = gate
	}
	deadline, ok := ctx.Deadline()
	if !ok || time.Until(deadline) <= 0 || time.Until(deadline) > 120*time.Second {
		return out, errors.New("BOUNDED_EXECUTION_CONTEXT_REQUIRED")
	}
	if err = os.Mkdir(dir, 0700); err != nil {
		return out, err
	}
	if err = syncDir(filepath.Dir(dir)); err != nil {
		return out, err
	}
	remaining := int64(x.spec.Limits.Output)
	if err = store(dir, "SCENARIO_INPUT.json", x.spec, &remaining); err != nil {
		return out, err
	}
	out = Outcome{Schema: x.spec.Schema + "/evidence", Scenario: x.spec.Commitment, Profile: x.profile.Kind, Status: "HOST_STOP", Worlds: []*WorldResult{}, ExternalDelivery: "HOLD"}
	out.DiscoveryOnly = x.discovery != nil
	out.DiagnosticOnly = x.diagnostic != nil
	cleanup := true
	defer func() {
		if x.diagnostic != nil {
			err = errors.Join(err, store(dir, "DIAGNOSTIC.json", x.diagnostic, &remaining))
		}
		out.Cleanup = cleanup
		if err != nil {
			out.Status = "HOST_STOP"
			out.Cause = err.Error()
		}
		copy := out
		copy.Commitment = ""
		out.Commitment = hashValue(x.spec.Schema+"/evidence", copy)
		if e := store(dir, "FINAL.json", out, &remaining); e != nil {
			err = errors.Join(err, e)
			out.Status = "EVIDENCE_STOP"
			out.Cause = err.Error()
			copy = out
			copy.Commitment = ""
			out.Commitment = hashValue(x.spec.Schema+"/evidence", copy)
		}
	}()
	labels := []string{Baseline, Variant}
	if out.DiagnosticOnly {
		labels = []string{Baseline}
	}
	for _, label := range labels {
		if err = ctx.Err(); err != nil {
			return
		}
		if err = fence.Check(ctx, x.spec.Engine, label+"_BEFORE"); err != nil {
			return
		}
		var r *WorldResult
		cleanup = false
		r, cleanup, err = runWorld(ctx, x, label, func() { out.ProducerInvocations++ }, func(f FailureDetail) { out.Failure = &f })
		if r != nil {
			out.Worlds = append(out.Worlds, r)
			if e := store(dir, label+".json", r, &remaining); e != nil {
				err = errors.Join(err, e)
				return
			}
		}
		if err != nil {
			return
		}
		if err = fence.Check(ctx, x.spec.Engine, label+"_AFTER"); err != nil {
			return
		}
	}
	if !out.DiagnosticOnly && out.Worlds[0].Overlay.CommonRoot != out.Worlds[1].Overlay.CommonRoot {
		return out, errors.New("INDEPENDENT_COMMON_SETUP_MISMATCH")
	}
	out.Status = "SCENARIO_EXECUTED_UNQUALIFIED"
	if out.DiscoveryOnly {
		out.Status = "SCENARIO_DISCOVERY_COMPLETED"
	}
	if out.DiagnosticOnly {
		out.Status = "SCENARIO_DIAGNOSTIC_COMPLETED"
	}
	return
}

// DecodeOutcome is a convenience for consumers; commitments are independently
// checked before accepting evidence from disk.
func DecodeOutcome(raw []byte) (Outcome, error) {
	var out Outcome
	if len(raw) > 64<<20 {
		return out, errors.New("EVIDENCE_SIZE")
	}
	if e := json.Unmarshal(raw, &out); e != nil {
		return out, e
	}
	canonical, e := Canonical(out)
	if e != nil {
		return out, e
	}
	if string(append(canonical, '\n')) != string(raw) {
		return out, errors.New("CANONICAL_EVIDENCE_REQUIRED")
	}
	pin := out.Commitment
	out.Commitment = ""
	if (out.Schema != Domain+"/evidence" && out.Schema != DynamicDomain+"/evidence") || pin != hashValue(out.Schema, out) {
		return out, errors.New("EVIDENCE_COMMITMENT")
	}
	out.Commitment = pin
	return out, nil
}
