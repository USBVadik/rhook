package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func observedFixture(t *testing.T) (*EventJournal, EventPolicy, *monitorFixture) {
	t.Helper()
	p := ObservedEventPolicy()
	j, e := OpenEventJournal(t.TempDir(), "SYNTHETIC_OBSERVED_ACQUISITION", p)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(j.Close)
	f := newMonitorFixture(t)
	_, h, _ := decodeFixtureHeader(f.headers[f.anchor])
	if e = j.Update("SYNTHETIC_OBSERVATION_BEGIN", func(s *EventState) error {
		s.Began = time.Now().UnixNano()
		s.Expires = time.Now().Add(time.Minute).UnixNano()
		s.Activation = f.anchor
		s.Cursor = f.anchor
		s.ActivationHash = h.Hash()
		s.CursorHash = h.Hash()
		s.Connected = true
		s.Observed = &ObservedDeliveryState{Started: time.Now().UnixNano(), Logs: map[string]string{}}
		return nil
	}); e != nil {
		t.Fatal(e)
	}
	return j, p, f
}
func observedFetch(f *monitorFixture, calls *atomic.Int32) ObservedLogsFunc {
	return func(_ context.Context, hash common.Hash, _ WriteEvidence) ([]*types.Log, error) {
		calls.Add(1)
		out := []*types.Log{}
		for _, l := range f.logs {
			if l.BlockHash == hash {
				out = append(out, l)
			}
		}
		return out, nil
	}
}
func observeTarget(t *testing.T, c *EventController, rows []*types.Log) {
	t.Helper()
	for _, l := range rows {
		if eventTarget(l) {
			if e := c.Observe(context.Background(), l); e != nil {
				t.Fatal(e)
			}
		}
	}
}
func addObservedSecondTransaction(t *testing.T, f *monitorFixture, n uint64, firstIneligible bool) []*types.Log {
	t.Helper()
	var body map[string]json.RawMessage
	json.Unmarshal(f.blocks[n], &body)
	var txs []json.RawMessage
	json.Unmarshal(body["transactions"], &txs)
	var second map[string]json.RawMessage
	json.Unmarshal(txs[1], &second)
	hash := common.HexToHash("0xabcdef")
	second["hash"], _ = json.Marshal(hash)
	b, _ := json.Marshal(second)
	txs = append(txs, b)
	if firstIneligible {
		var first map[string]json.RawMessage
		json.Unmarshal(txs[1], &first)
		first["input"], _ = json.Marshal(hexutil.Bytes(monitorInput(100)))
		txs[1], _ = json.Marshal(first)
	}
	body["transactions"], _ = json.Marshal(txs)
	f.blocks[n], _ = json.Marshal(body)
	rows := eventRows(f, n, n)
	swap, route := *rows[0], *rows[1]
	swap.TxHash, route.TxHash = hash, hash
	swap.TxIndex, route.TxIndex = 2, 2
	swap.Index, route.Index = 2, 3
	f.logs = append(f.logs, &swap, &route)
	return eventRows(f, n, n)
}

func TestObservedQuietBeyond8000BlocksNeverRequestsCoverage(t *testing.T) {
	j, p, f := observedFixture(t)
	oldNumber, newNumber := f.anchor+12, f.anchor+9001
	_, h, _ := decodeFixtureHeader(f.headers[oldNumber])
	h.Number.SetUint64(newNumber)
	var body map[string]json.RawMessage
	json.Unmarshal(f.blocks[oldNumber], &body)
	body["number"], _ = json.Marshal("0x" + h.Number.Text(16))
	body["hash"], _ = json.Marshal(h.Hash())
	f.blocks[newNumber], _ = json.Marshal(body)
	for _, l := range f.logs {
		if l.BlockNumber == oldNumber {
			l.BlockNumber = newNumber
			l.BlockHash = h.Hash()
		}
	}
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, 0, &captures)
	observeTarget(t, c, eventRows(f, newNumber, newNumber))
	if e := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); e != nil {
		t.Fatal(e)
	}
	s := j.Snapshot()
	if s.Lock == nil || s.Lock.Observation == nil || s.Lock.Observation.Assurance != observedAssurance || s.Cursor != s.Activation || s.CoverageRPC != 0 || fetches.Load() != 1 || captures.Load() != 1 {
		t.Fatal("coverage required or assurance/cursor changed", s)
	}
}
func TestObservedIneligibleThenEligibleKeepsDeliveryOrder(t *testing.T) {
	j, p, f := observedFixture(t)
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, 0, &captures)
	observeTarget(t, c, eventRows(f, f.anchor+1, f.anchor+1))
	observeTarget(t, c, eventRows(f, f.anchor+12, f.anchor+12))
	if e := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); e != nil {
		t.Fatal(e)
	}
	s := j.Snapshot()
	if s.Lock == nil || s.Lock.Selection.BlockNumber != f.anchor+12 || s.Observed.Transactions[0].Decision != "NO_ELIGIBLE_DIRECT_ETH_RHOOK_BUY" || captures.Load() != 2 || fetches.Load() != 2 {
		t.Fatal(s)
	}
}
func TestObservedDuplicateAndTwoSwapLogsShareCaptureAndTransaction(t *testing.T) {
	j, p, f := observedFixture(t)
	n := f.anchor + 12
	rows := eventRows(f, n, n)
	extra := *rows[0]
	extra.Index = 2
	f.logs = append(f.logs, &extra)
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, 0, &captures)
	for i := 0; i < 3; i++ {
		observeTarget(t, c, rows)
	}
	if e := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); e != nil {
		t.Fatal(e)
	}
	if e := c.Observe(context.Background(), &extra); e != nil {
		t.Fatal("valid second Swap after lock rejected", e)
	}
	s := j.Snapshot()
	if len(s.Observed.Transactions) != 1 || s.Observed.Sequence != 2 || captures.Load() != 1 || fetches.Load() != 1 || s.Lock == nil {
		t.Fatal(s)
	}
}
func TestObservedSameBlockIneligibleThenEligibleReusesOnePackage(t *testing.T) {
	j, p, f := observedFixture(t)
	rows := addObservedSecondTransaction(t, f, f.anchor+12, true)
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, 0, &captures)
	observeTarget(t, c, rows)
	if e := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); e != nil {
		t.Fatal(e)
	}
	s := j.Snapshot()
	if s.Lock == nil || s.Lock.Selection.Subject.Ordinal != 2 || captures.Load() != 1 || fetches.Load() != 1 || len(s.Observed.Transactions) != 2 {
		t.Fatal(s)
	}
}
func TestObservedUnobservedEarlierTransactionDoesNotReplaceObservedSubject(t *testing.T) {
	j, p, f := observedFixture(t)
	rows := addObservedSecondTransaction(t, f, f.anchor+12, false)
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, 0, &captures)
	if e := c.Observe(context.Background(), rows[2]); e != nil {
		t.Fatal(e)
	}
	if e := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); e != nil {
		t.Fatal(e)
	}
	if j.Snapshot().Lock.Selection.Subject.Ordinal != 2 {
		t.Fatal("unobserved transaction silently won")
	}
	if e := c.Observe(context.Background(), rows[0]); e == nil || j.Snapshot().Stop == "" {
		t.Fatal("late ordering ambiguity admitted")
	}
}
func TestObservedCaptureStartsBeforeEligibilityAndCompletionDoesNotReorder(t *testing.T) {
	j, p, f := observedFixture(t)
	started := make(chan uint64, 2)
	release := make(chan struct{})
	var captures, fetches atomic.Int32
	base := eventTestController(t, j, p, f, 0, &captures)
	c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
		started <- l.BlockNumber
		if l.BlockNumber == f.anchor+12 {
			select {
			case <-release:
			case <-ctx.Done():
				return &EventCapture{}, ctx.Err()
			}
		}
		return base.Capture(ctx, l, w)
	})
	observeTarget(t, c, eventRows(f, f.anchor+12, f.anchor+13))
	<-started
	<-started
	result := make(chan error, 1)
	go func() { result <- c.CompleteObserved(context.Background(), observedFetch(f, &fetches)) }()
	if j.Snapshot().Lock != nil || len(j.Snapshot().Observed.Transactions) != 2 {
		t.Fatal("lock before capture")
	}
	close(release)
	if e := <-result; e != nil {
		t.Fatal(e)
	}
	c.Wait()
	if j.Snapshot().Lock.Selection.BlockNumber != f.anchor+12 {
		t.Fatal("capture completion order won")
	}
}
func TestObservedEligibleMissingProofNeverFallsForward(t *testing.T) {
	j, p, f := observedFixture(t)
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, f.anchor+12, &captures)
	observeTarget(t, c, eventRows(f, f.anchor+12, f.anchor+13))
	e := c.CompleteObserved(context.Background(), observedFetch(f, &fetches))
	if e == nil || !strings.Contains(e.Error(), "FIRST_OBSERVED_ELIGIBLE_CAPTURE_STOP") || j.Snapshot().Lock != nil || (!j.Snapshot().Draining && j.Snapshot().Stop == "") || fetches.Load() != 1 {
		t.Fatal(e, j.Snapshot())
	}
}
func TestObservedCaptureTimeoutPreservesPartialAndStops(t *testing.T) {
	j, p, f := observedFixture(t)
	p.CaptureSeconds = 0
	c := NewEventController(j, p, func(context.Context, *types.Log, WriteEvidence) (*EventCapture, error) {
		t.Fatal("expired capture entered")
		return nil, nil
	})
	if e := c.Observe(context.Background(), eventRows(f, f.anchor+12, f.anchor+12)[0]); e == nil || j.Snapshot().Stop != "CAPTURE_AUTHORITY_EXPIRED" {
		t.Fatal(e)
	}
}
func TestObservedReorgConflictingDuplicateAndOutOfOrderFailClosed(t *testing.T) {
	for _, kind := range []string{"removed", "duplicate", "outoforder", "hash", "moved"} {
		t.Run(kind, func(t *testing.T) {
			j, p, f := observedFixture(t)
			var calls atomic.Int32
			c := eventTestController(t, j, p, f, 0, &calls)
			first := *eventRows(f, f.anchor+12, f.anchor+12)[0]
			observeTarget(t, c, []*types.Log{&first})
			c.Wait()
			next := first
			switch kind {
			case "removed":
				next.Removed = true
			case "duplicate":
				next.Data = common.CopyBytes(first.Data)
				next.Data[0] ^= 1
			case "outoforder":
				next = *eventRows(f, f.anchor+1, f.anchor+1)[0]
			case "hash":
				next.BlockHash = common.HexToHash("0xbeef")
			case "moved":
				next.TxIndex++
				next.Index++
			}
			if e := c.Observe(context.Background(), &next); e == nil || j.Snapshot().Stop == "" {
				t.Fatal("ambiguity admitted", kind, e)
			}
		})
	}
}
func TestObservedLateNotificationMustMatchBoundBlockLogs(t *testing.T) {
	j, p, f := observedFixture(t)
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, 0, &captures)
	rows := eventRows(f, f.anchor+12, f.anchor+12)
	observeTarget(t, c, rows)
	if e := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); e != nil {
		t.Fatal(e)
	}
	next := *rows[0]
	next.Index = 99
	if e := c.Observe(context.Background(), &next); e == nil || j.Snapshot().Stop != "OBSERVED_NOTIFICATION_OMITTED_BY_BOUND_LOGS" {
		t.Fatal(e)
	}
}
func TestObservedOmittedNotificationAndFetchFailureStopWithoutReplacement(t *testing.T) {
	for _, kind := range []string{"omitted", "rpc"} {
		t.Run(kind, func(t *testing.T) {
			j, p, f := observedFixture(t)
			var captures atomic.Int32
			c := eventTestController(t, j, p, f, 0, &captures)
			observeTarget(t, c, eventRows(f, f.anchor+12, f.anchor+13))
			calls := 0
			e := c.CompleteObserved(context.Background(), func(context.Context, common.Hash, WriteEvidence) ([]*types.Log, error) {
				calls++
				if kind == "rpc" {
					return nil, errors.New("SYNTHETIC_RPC_STOP")
				}
				return nil, nil
			})
			if e == nil || calls != 1 || j.Snapshot().Lock != nil || (!j.Snapshot().Draining && j.Snapshot().Stop == "") {
				t.Fatal(e)
			}
		})
	}
}
func TestObservedCrashWithLockAndUncertainMarkersCannotResume(t *testing.T) {
	j, p, f := observedFixture(t)
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, 0, &captures)
	observeTarget(t, c, eventRows(f, f.anchor+12, f.anchor+12))
	if e := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); e != nil {
		t.Fatal(e)
	}
	dir := j.dir
	j.Close()
	next, e := OpenEventJournal(dir, "SYNTHETIC_OBSERVED_ACQUISITION", p)
	if e != nil {
		t.Fatal(e)
	}
	defer next.Close()
	if next.CheckMarkers() != nil || EventResumeCheck(next.Snapshot()) == nil {
		t.Fatal("persisted observed lock resumed")
	}
	if e = os.Remove(filepath.Join(dir, "FIRST_ELIGIBLE_LOCK.json")); e != nil {
		t.Fatal(e)
	}
	if next.CheckMarkers() == nil {
		t.Fatal("missing durable marker admitted")
	}
}
func TestObservedPolicyCannotInstantiateCoverageSource(t *testing.T) {
	j, p, _ := observedFixture(t)
	if p.Coverage.Valid() || p.Coverage.Endpoint != "" || p.Coverage.RPC != 0 || p.Reconnects != 0 {
		t.Fatal("coverage or reconnect policy present")
	}
	for _, endpoint := range []string{"https://robinhood.drpc.org", "https://lb.drpc.live/robinhood/synthetic"} {
		if _, e := NewEventRPC(endpoint, j, p, "coverage", "FORBIDDEN", EventWriter(j, p, "records")); e == nil {
			t.Fatal("coverage source accepted")
		}
	}
}
func TestObservedResourceBudgetCannotDispatchOrLock(t *testing.T) {
	j, p, _ := observedFixture(t)
	j.Update("SYNTHETIC_EXHAUSTED", func(s *EventState) error { s.Billing = p.BillingCU; return nil })
	rpc, e := NewEventRPC("https://robinhood-mainnet.g.alchemy.com/v2/synthetic", j, p, "monitor", "SYNTHETIC", EventWriter(j, p, "records"))
	if e != nil {
		t.Fatal(e)
	}
	rpc.client.Transport = eventHTTP{roundTripFunc(func(*http.Request) (*http.Response, error) { t.Fatal("dispatched after exhaustion"); return nil, nil }), EventMeter{j, p, "monitor"}}
	var out json.RawMessage
	if e = rpc.call(context.Background(), "eth_getBlockByNumber", []any{"latest", false}, &out); e == nil || j.Snapshot().Stop != "BILLING_BUDGET" || j.Snapshot().Lock != nil {
		t.Fatal(e)
	}
}

// Production watcher control flow with synthetic transport only. Even after an
// 8,000+ block quiet interval there are no coverage/head polls. No live socket,
// host command, capture, or native engine is invoked by these tests.
func TestObservedWatcherQuietAndDisconnectNeverBackfillOrReconnect(t *testing.T) {
	for _, disconnect := range []bool{false, true} {
		t.Run(map[bool]string{false: "quiet", true: "disconnect"}[disconnect], func(t *testing.T) {
			p := ObservedEventPolicy()
			j, e := OpenEventJournal(t.TempDir(), "SYNTHETIC_WATCHER_OBSERVED", p)
			if e != nil {
				t.Fatal(e)
			}
			defer j.Close()
			f := newMonitorFixture(t)
			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			var factoryCalls, requestCalls, subscriptions atomic.Int32
			factory := func(endpoint string, j *EventJournal, p EventPolicy, scope, prefix string, w WriteEvidence) (*RPCSource, error) {
				factoryCalls.Add(1)
				if scope != "monitor" {
					t.Errorf("unexpected scope%s", scope)
					return nil, errors.New("UNEXPECTED_SCOPE")
				}
				r, e := NewEventRPC(endpoint, j, p, scope, prefix, w)
				if e != nil {
					return nil, e
				}
				r.client.Transport = eventHTTP{roundTripFunc(func(q *http.Request) (*http.Response, error) {
					requestCalls.Add(1)
					var v struct {
						ID     uint64
						Method string
					}
					json.NewDecoder(q.Body).Decode(&v)
					if v.Method == "eth_chainId" {
						return respondJSON(v.ID, "0x1237"), nil
					}
					if v.Method == "eth_getBlockByNumber" {
						return respondJSON(v.ID, f.headers[f.anchor]), nil
					}
					t.Errorf("background polling%s", v.Method)
					return nil, errors.New("NO_BACKGROUND_RPC")
				}), EventMeter{j, p, scope}}
				return r, nil
			}
			subscribe := func(socketCtx context.Context, _ string, _ EventMeter, _ WriteEvidence) (eventSocket, string, error) {
				subscriptions.Add(1)
				s := &eventFakeSocket{ctx: socketCtx, frames: make(chan []byte), closed: make(chan struct{})}
				if disconnect {
					s.Close()
				} else {
					time.AfterFunc(50*time.Millisecond, cancel)
				}
				return s, "synthetic-subscription", nil
			}
			a := EventAuthority{DecisionID: "SYNTHETIC_WATCHER_OBSERVED", Expires: time.Now().Add(time.Minute).Unix()}
			o := runEventWatcherWith(ctx, EventLiveConfig{Endpoint: "https://robinhood-mainnet.g.alchemy.com/v2/synthetic"}, j, p, a, nil, factory, subscribe)
			if requestCalls.Load() != 2 || factoryCalls.Load() != 1 || subscriptions.Load() != 1 || o.State.CoverageRPC != 0 || o.State.Lock != nil {
				t.Fatal(o, requestCalls.Load(), factoryCalls.Load(), subscriptions.Load())
			}
			if disconnect && o.Cause != "OBSERVED_WSS_DISCONNECTED_NO_RECONNECT" {
				t.Fatal(o)
			}
		})
	}
}

func TestObservedCaptureDeadlinePreservesPartialAndNeverReplaces(t *testing.T) {
	j, p, f := observedFixture(t)
	p.CaptureSeconds = 1
	var captures, fetches atomic.Int32
	base := eventTestController(t, j, p, f, 0, &captures)
	c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
		cap, err := base.Capture(ctx, l, w)
		if err != nil {
			return cap, err
		}
		<-ctx.Done()
		if err = w("PARTIAL_TIMEOUT.json", []byte(`{"synthetic":true,"nativeInvocations":0}`)); err != nil {
			return cap, err
		}
		return cap, ctx.Err()
	})
	observeTarget(t, c, eventRows(f, f.anchor+12, f.anchor+13))
	err := c.CompleteObserved(context.Background(), observedFetch(f, &fetches))
	c.Wait()
	if err == nil || !strings.Contains(err.Error(), "FIRST_OBSERVED_ELIGIBLE_CAPTURE_STOP") || j.Snapshot().Lock != nil || fetches.Load() != 1 {
		t.Fatal(err, j.Snapshot())
	}
	hash := eventRows(f, f.anchor+12, f.anchor+12)[0].BlockHash
	if _, err = os.Stat(filepath.Join(j.dir, eventCaptureDir(hash), "PARTIAL_TIMEOUT.json")); err != nil {
		t.Fatal("partial evidence lost", err)
	}
}

func TestObservedAdmissionFailureDrainsExistingCapturesWithoutNewSelection(t *testing.T) {
	j, p, f := observedFixture(t)
	var captures, fetches atomic.Int32
	started := make(chan struct{})
	release := make(chan struct{})
	base := eventTestController(t, j, p, f, f.anchor+12, &captures)
	c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
		if l.BlockNumber == f.anchor+13 {
			close(started)
			select {
			case <-release:
			case <-ctx.Done():
				return &EventCapture{}, ctx.Err()
			}
		}
		return base.Capture(ctx, l, w)
	})
	observeTarget(t, c, eventRows(f, f.anchor+12, f.anchor+13))
	<-started
	before := j.Snapshot().Cases[eventRows(f, f.anchor+13, f.anchor+13)[0].BlockHash.Hex()].Deadline
	if err := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); err == nil {
		t.Fatal("missing proof admitted")
	}
	state := j.Snapshot()
	if !state.Draining || state.Lock != nil || state.Stop != "" {
		t.Fatal("soft admission STOP discarded bounded capture", state)
	}
	if err := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); err == nil || fetches.Load() != 1 {
		t.Fatal("replacement selection after drain")
	}
	close(release)
	c.Wait()
	hash := eventRows(f, f.anchor+13, f.anchor+13)[0].BlockHash
	if j.Snapshot().Cases[hash.Hex()].Deadline != before {
		t.Fatal("capture deadline extended")
	}
	if _, err := os.Stat(filepath.Join(j.dir, eventCaptureDir(hash), "BLOCK_PACKAGE.json")); err != nil {
		t.Fatal("admitted capture not preserved", err)
	}
	j.Halt(j.Snapshot().DrainReason)
	if j.Snapshot().Stop == "" || j.Snapshot().Lock != nil || j.Snapshot().Consumed {
		t.Fatal("drain did not close scientific path")
	}
}

func TestObservedExactNewAuthorityCannotReuseLegacyOrWrongScope(t *testing.T) {
	p := ObservedEventPolicy()
	now := time.Now().Unix()
	a := EventAuthority{Domain: "MONITORING_ACQUISITION", DecisionID: "SYNTHETIC_OBSERVED_ACQ", OperationCommitment: strings.Repeat("1", 64), Policy: p.Commitment(), BinarySHA: "synthetic-new-binary", RuntimePath: "/synthetic/observed/runtime", FounderApproved: true, FreeConfirmed: true, PaidOveragesDisabled: true, WitnessBurstAllowed: true, NotBefore: now, Expires: now + 60}
	science := EventAuthority{Domain: "ONE_SHOT_HOOKR_EXECUTION", DecisionID: "SYNTHETIC_OBSERVED_SCIENCE", OperationCommitment: a.OperationCommitment, Policy: p.Commitment(), BinarySHA: a.BinarySHA, RuntimePath: a.RuntimePath, AcquisitionID: a.DecisionID, FounderApproved: true, NotBefore: now, Expires: now + 60, Actual: 1, Branch: 1}
	if err := ValidateEventAuthorities(a, &science, p, a.BinarySHA); err != nil {
		t.Fatal(err)
	}
	for _, kind := range []string{"proposal", "expired", "legacy-policy", "binary", "operation", "domain", "same-id", "runtime", "oversized-window"} {
		x, y := a, science
		switch kind {
		case "proposal":
			x.FounderApproved = false
		case "expired":
			x.Expires = now - 1
		case "legacy-policy":
			x.Policy = DefaultQuietEventPolicy().Commitment()
		case "binary":
			y.BinarySHA = "old"
		case "operation":
			y.OperationCommitment = strings.Repeat("2", 64)
		case "domain":
			y.Domain = x.Domain
		case "same-id":
			y.DecisionID = x.DecisionID
		case "runtime":
			y.RuntimePath += "-old"
		case "oversized-window":
			x.NotBefore = now - 10800
		}
		if err := ValidateEventAuthorities(x, &y, p, a.BinarySHA); err == nil {
			t.Fatal("invalid authority accepted", kind)
		}
	}
}
func TestObservedRecordedAttempt02NotificationsGroupWithout7998BlockBackfill(t *testing.T) {
	j, p, _ := observedFixture(t)
	j.Update("SYNTHETIC_RECORDED_H0", func(s *EventState) error { s.Activation = 92810903; s.Cursor = s.Activation; return nil })
	var calls atomic.Int32
	c := NewEventController(j, p, func(context.Context, *types.Log, WriteEvidence) (*EventCapture, error) {
		calls.Add(1)
		return &EventCapture{Error: "SYNTHETIC_CAPTURE_NOT_REPLAY"}, nil
	})
	for _, name := range []string{"ATTEMPT02_WS_0002.json", "ATTEMPT02_WS_0003.json"} {
		raw, err := os.ReadFile("../inputs/" + name)
		if err != nil {
			t.Fatal(err)
		}
		var frame eventWSFrame
		if err = json.Unmarshal(raw, &frame); err != nil {
			t.Fatal(err)
		}
		if err = c.Observe(context.Background(), frame.Params.Result); err != nil {
			t.Fatal(err)
		}
	}
	c.Wait()
	s := j.Snapshot()
	if s.Stop != "" || s.CoverageRPC != 0 || s.Cursor != 92810903 || len(s.Observed.Transactions) != 1 || s.Observed.Sequence != 2 || calls.Load() != 1 || s.Observed.Transactions[0].Number != 92818901 {
		t.Fatal(s)
	}
}

func TestObservedLockObservationBindingMustRemainExact(t *testing.T) {
	j, p, f := observedFixture(t)
	var captures, fetches atomic.Int32
	c := eventTestController(t, j, p, f, 0, &captures)
	observeTarget(t, c, eventRows(f, f.anchor+12, f.anchor+12))
	if err := c.CompleteObserved(context.Background(), observedFetch(f, &fetches)); err != nil {
		t.Fatal(err)
	}
	if err := validateObservedLock(j.Snapshot()); err != nil {
		t.Fatal(err)
	}
	for _, kind := range []string{"assurance", "sequence", "prefix", "logs", "subject"} {
		s := j.Snapshot()
		switch kind {
		case "assurance":
			s.Lock.Observation.Assurance = "CHAIN_GLOBAL_FIRST"
		case "sequence":
			s.Lock.Observation.FirstSequence++
		case "prefix":
			s.Lock.Observation.ObservedPrefixSHA = "wrong"
		case "logs":
			s.Lock.Observation.BlockLogsSHA = "wrong"
		case "subject":
			s.Lock.Selection.Subject.Hash = common.HexToHash("0xbad")
		}
		if err := validateObservedLock(s); err == nil {
			t.Fatal("observation binding substitution admitted", kind)
		}
	}
}
