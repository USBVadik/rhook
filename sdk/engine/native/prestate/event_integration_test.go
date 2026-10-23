package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func eventTestJournal(t *testing.T) (*EventJournal, EventPolicy, *monitorFixture) {
	t.Helper()
	p := DefaultEventPolicy()
	j, e := OpenEventJournal(t.TempDir(), "OFFLINE_SYNTHETIC_ACQUISITION", p)
	if e != nil {
		t.Fatal(e)
	}
	f := newMonitorFixture(t)
	_, h, e := decodeFixtureHeader(f.headers[f.anchor])
	if e != nil {
		t.Fatal(e)
	}
	e = j.Update("TEST_ACTIVATION", func(s *EventState) error {
		s.Began = time.Now().UnixNano()
		s.Expires = time.Now().Add(time.Minute).UnixNano()
		s.Activation = f.anchor
		s.Cursor = f.anchor
		s.ActivationHash = h.Hash()
		s.CursorHash = h.Hash()
		s.Connected = true
		return nil
	})
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(j.Close)
	return j, p, f
}
func decodeFixtureHeader(b []byte) ([]byte, *types.Header, error) {
	h, e := decodeHeader(b)
	return b, h, e
}
func eventTestController(t *testing.T, j *EventJournal, p EventPolicy, f *monitorFixture, bad uint64, calls *atomic.Int32) *EventController {
	c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
		calls.Add(1)
		cp := Checkpoint{4663, l.BlockNumber - 1, common.HexToHash("0x1234"), common.HexToHash("0x5678")}
		pack := BlockPackage{Checkpoint: cp, Block: f.blocks[l.BlockNumber]}
		b, _ := json.Marshal(pack)
		req := testLPRequest()
		req.Checkpoint = cp
		cap := &EventCapture{Package: b, Inventory: &Inventory{BlockNumber: l.BlockNumber, BlockHash: l.BlockHash, Checkpoint: cp}, Intervention: &req, Plan: &EconomicObservationPlan{}}
		var e error
		if l.BlockNumber == bad {
			cap.Error = "SYNTHETIC_MISSING_PROOF"
			e = errors.New(cap.Error)
		}
		if x := w("BLOCK_PACKAGE.json", b); x != nil {
			t.Error(x)
		}
		if x := EmitJSON(w, "CAPTURE_META.json", cap); x != nil {
			t.Error(x)
		}
		return cap, e
	})
	t.Cleanup(func() {
		c.mu.Lock()
		channels := []chan struct{}{}
		for _, d := range c.done {
			channels = append(channels, d)
		}
		c.mu.Unlock()
		for _, d := range channels {
			<-d
		}
	})
	return c
}
func eventRows(f *monitorFixture, from, to uint64) []*types.Log {
	rows := []*types.Log{}
	for _, l := range f.logs {
		if l.BlockNumber >= from && l.BlockNumber <= to {
			rows = append(rows, l)
		}
	}
	return rows
}
func TestEventNormalTargetUnsupportedAndFirstEligible(t *testing.T) {
	j, p, f := eventTestJournal(t)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	ctx := context.Background()
	_, tail, _ := decodeFixtureHeader(f.headers[f.anchor+10])
	if e := c.CompleteRange(ctx, f.anchor+1, f.anchor+10, tail.Hash(), eventRows(f, f.anchor+1, f.anchor+10)); e != nil {
		t.Fatal(e)
	}
	if j.Snapshot().Lock != nil || calls.Load() != 1 {
		t.Fatal("unsupported route locked or not captured", calls.Load())
	}
	_, tail, _ = decodeFixtureHeader(f.headers[f.anchor+20])
	if e := c.CompleteRange(ctx, f.anchor+11, f.anchor+20, tail.Hash(), eventRows(f, f.anchor+11, f.anchor+20)); e != nil {
		t.Fatal(e)
	}
	s := j.Snapshot()
	if s.Lock == nil || s.Lock.Selection.BlockNumber != f.anchor+12 || s.Consumed {
		t.Fatal("first eligible/authority", s)
	}
}
func TestEventDuplicatesAndMultipleSwapRowsDoNotRepeatCapture(t *testing.T) {
	j, p, f := eventTestJournal(t)
	j.Update("TEST_CURSOR", func(s *EventState) error {
		s.Cursor = f.anchor + 11
		_, h, _ := decodeFixtureHeader(f.headers[s.Cursor])
		s.CursorHash = h.Hash()
		return nil
	})
	rows := eventRows(f, f.anchor+12, f.anchor+12)
	copyLog := *rows[0]
	copyLog.Index = 2
	rows = append(rows, &copyLog)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	for i := 0; i < 3; i++ {
		if e := c.Observe(context.Background(), rows[0]); e != nil {
			t.Fatal(e)
		}
	}
	_, tail, _ := decodeFixtureHeader(f.headers[f.anchor+12])
	if e := c.CompleteRange(context.Background(), f.anchor+12, f.anchor+12, tail.Hash(), rows); e != nil {
		t.Fatal(e)
	}
	if calls.Load() != 1 || j.Snapshot().Lock.Selection.Subject.Ordinal != 1 {
		t.Fatal("duplicate capture/selection")
	}
}
func TestEventSeveralCandidatesOutOfOrderStillChooseEarliest(t *testing.T) {
	j, p, f := eventTestJournal(t)
	j.Update("TEST_CURSOR", func(s *EventState) error {
		s.Cursor = f.anchor + 11
		_, h, _ := decodeFixtureHeader(f.headers[s.Cursor])
		s.CursorHash = h.Hash()
		return nil
	})
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	rows := eventRows(f, f.anchor+12, f.anchor+13)
	if e := c.Observe(context.Background(), rows[2]); e != nil {
		t.Fatal(e)
	}
	_, tail, _ := decodeFixtureHeader(f.headers[f.anchor+13])
	if e := c.CompleteRange(context.Background(), f.anchor+12, f.anchor+13, tail.Hash(), rows); e != nil {
		t.Fatal(e)
	}
	if j.Snapshot().Lock.Selection.BlockNumber != f.anchor+12 {
		t.Fatal("later event won")
	}
}
func TestEventMissingEarlierProofNeverFallsForward(t *testing.T) {
	j, p, f := eventTestJournal(t)
	j.Update("TEST_CURSOR", func(s *EventState) error {
		s.Cursor = f.anchor + 11
		_, h, _ := decodeFixtureHeader(f.headers[s.Cursor])
		s.CursorHash = h.Hash()
		return nil
	})
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, f.anchor+12, &calls)
	_, tail, _ := decodeFixtureHeader(f.headers[f.anchor+13])
	e := c.CompleteRange(context.Background(), f.anchor+12, f.anchor+13, tail.Hash(), eventRows(f, f.anchor+12, f.anchor+13))
	if e == nil || !strings.Contains(e.Error(), "FIRST_ELIGIBLE_CAPTURE_STOP") || j.Snapshot().Lock != nil {
		t.Fatal("missing proof selected later", e)
	}
}
func TestEventGapReconciliationRestartKeepsCursorAndCounters(t *testing.T) {
	j, p, f := eventTestJournal(t)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	_, tail, _ := decodeFixtureHeader(f.headers[f.anchor+10])
	if e := c.CompleteRange(context.Background(), f.anchor+1, f.anchor+10, tail.Hash(), eventRows(f, f.anchor+1, f.anchor+10)); e != nil {
		t.Fatal(e)
	}
	if e := (EventMeter{j, p, "monitor"}).Reserve(context.Background(), "eth_chainId"); e != nil {
		t.Fatal(e)
	}
	dir := j.dir
	j.Close()
	next, e := OpenEventJournal(dir, "OFFLINE_SYNTHETIC_ACQUISITION", p)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(next.Close)
	if e = EventResumeCheck(next.Snapshot()); e != nil || next.Snapshot().Cursor != f.anchor+10 || next.Snapshot().MonitorRPC != 1 {
		t.Fatal("restart reset", e)
	}
	var more atomic.Int32
	c2 := eventTestController(t, next, p, f, 0, &more)
	_, tail, _ = decodeFixtureHeader(f.headers[f.anchor+20])
	if e = c2.CompleteRange(context.Background(), f.anchor+11, f.anchor+20, tail.Hash(), eventRows(f, f.anchor+11, f.anchor+20)); e != nil {
		t.Fatal(e)
	}
	if next.Snapshot().Lock.Selection.BlockNumber != f.anchor+12 {
		t.Fatal("gap skipped")
	}
}
func TestEventReorgRemovalChangedHashAndOmittedLogStop(t *testing.T) {
	for _, kind := range []string{"removed", "hash", "omitted"} {
		t.Run(kind, func(t *testing.T) {
			j, p, f := eventTestJournal(t)
			var calls atomic.Int32
			c := eventTestController(t, j, p, f, 0, &calls)
			l := *eventRows(f, f.anchor+1, f.anchor+1)[0]
			if e := c.Observe(context.Background(), &l); e != nil {
				t.Fatal(e)
			}
			switch kind {
			case "removed":
				l.Removed = true
				if c.Observe(context.Background(), &l) == nil {
					t.Fatal("removed")
				}
			case "hash":
				l.BlockHash[0] ^= 1
				if c.Observe(context.Background(), &l) == nil {
					t.Fatal("changed hash")
				}
			case "omitted":
				_, h, _ := decodeFixtureHeader(f.headers[f.anchor+1])
				if c.CompleteRange(context.Background(), f.anchor+1, f.anchor+1, h.Hash(), nil) == nil {
					t.Fatal("omitted")
				}
			}
			if j.Snapshot().Lock != nil {
				t.Fatal("reorg locked")
			}
		})
	}
}
func TestEventUnknownIntervalAndElevenBlockRequestRejected(t *testing.T) {
	j, p, f := eventTestJournal(t)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	for _, bounds := range [][2]uint64{{f.anchor + 2, f.anchor + 3}, {f.anchor + 1, f.anchor + 11}} {
		if c.CompleteRange(context.Background(), bounds[0], bounds[1], common.Hash{}, nil) == nil {
			t.Fatal("gap/range allowed")
		}
	}
}
func TestEventCrashAfterLockOrDuringCaptureNeverResumes(t *testing.T) {
	j, _, _ := eventTestJournal(t)
	s := j.Snapshot()
	s.Lock = &EventLock{}
	if EventResumeCheck(s) == nil {
		t.Fatal("lock resumed")
	}
	s.Lock = nil
	s.Cases["synthetic"] = EventCase{Status: "PENDING"}
	if EventResumeCheck(s) == nil {
		t.Fatal("uncertain capture resumed")
	}
	s.Cases = map[string]EventCase{}
	s.Consumed = true
	if EventResumeCheck(s) == nil {
		t.Fatal("consumed resumed")
	}
}
func TestEventBudgetReservationsPersistAndNeverDispatchAfterCap(t *testing.T) {
	j, p, _ := eventTestJournal(t)
	j.Update("EXHAUSTED", func(s *EventState) error { s.MonitorRPC = p.MonitorRPC; return nil })
	before := j.Snapshot()
	if (EventMeter{j, p, "monitor"}).Reserve(context.Background(), "eth_getLogs") == nil {
		t.Fatal("budget passed")
	}
	if j.Snapshot().Billing != before.Billing {
		t.Fatal("undispatched charge")
	}
	j.Update("WS_EXHAUSTED", func(s *EventState) error { s.WSReads = p.WSMessages; return nil })
	if (EventMeter{j, p, "monitor"}).ReserveWSRead() == nil {
		t.Fatal("WS cap passed")
	}
}
func TestEventJournalPartialTailAndConcurrentOwnerRejected(t *testing.T) {
	j, p, _ := eventTestJournal(t)
	if other, e := OpenEventJournal(j.dir, "OFFLINE_SYNTHETIC_ACQUISITION", p); e == nil {
		other.Close()
		t.Fatal("concurrent owner")
	}
	dir := j.dir
	j.Close()
	f, _ := os.OpenFile(filepath.Join(dir, "journal.jsonl"), os.O_APPEND|os.O_WRONLY, 0600)
	f.WriteString("{partial")
	f.Close()
	if other, e := OpenEventJournal(dir, "OFFLINE_SYNTHETIC_ACQUISITION", p); e == nil {
		other.Close()
		t.Fatal("corrupt journal repaired")
	}
}
func TestEventAuthorityDomainsCannotActivateEachOther(t *testing.T) {
	p := DefaultEventPolicy()
	a := EventAuthority{Domain: "MONITORING_ACQUISITION", DecisionID: "synthetic-acq", Policy: p.Commitment(), BinarySHA: "binary", RuntimePath: "/synthetic/runtime", FounderApproved: true, FreeConfirmed: true, PaidOveragesDisabled: true, WitnessBurstAllowed: true, Expires: time.Now().Add(time.Minute).Unix()}
	s := EventAuthority{Domain: "ONE_SHOT_HOOKR_EXECUTION", DecisionID: "synthetic-science", Policy: p.Commitment(), BinarySHA: "binary", RuntimePath: a.RuntimePath, AcquisitionID: a.DecisionID, FounderApproved: true, Expires: a.Expires, Actual: 1, Branch: 1}
	if ValidateEventAuthorities(a, &s, p, "binary") != nil {
		t.Fatal("valid fake authority rejected")
	}
	s.Domain = a.Domain
	if ValidateEventAuthorities(a, &s, p, "binary") == nil {
		t.Fatal("domain confusion")
	}
	a.FounderApproved = false
	if ValidateEventAuthorities(a, nil, p, "binary") == nil {
		t.Fatal("proposal activates")
	}
}
func TestEventSavedCanaryAdmissionOnlyNoReplay(t *testing.T) {
	b, e := os.ReadFile("../inputs/SAVED_CANARY_PACKAGE.json")
	if e != nil {
		t.Fatal(e)
	}
	_, inv, e := AdmitPackage(b)
	if e != nil || inv.BlockNumber != 92684281 || inv.HistoricalNativeExecutions != 0 {
		t.Fatal(inv, e)
	}
}
func TestEventMissingProofPreservesPackageAndNeverRetries(t *testing.T) {
	b, _ := os.ReadFile("../inputs/SAVED_CANARY_PACKAGE.json")
	var p BlockPackage
	json.Unmarshal(b, &p)
	var calls int
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		calls++
		var q struct {
			ID     uint64
			Method string
		}
		json.NewDecoder(req.Body).Decode(&q)
		switch calls {
		case 1:
			return respondJSON(q.ID, p.Block), nil
		case 2:
			return respondJSON(q.ID, p.Parent), nil
		default:
			return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"jsonrpc":"2.0","id":3,"error":{"code":-32000,"message":"missing proof"}}`)), Header: make(http.Header)}, nil
		}
	})}, 8<<20, 32<<20)
	rpc.Configure(40, time.Now().Add(time.Minute), nil)
	h, _ := decodeHeader(p.Block)
	saved := map[string][]byte{}
	out, e := CaptureEventPackage(context.Background(), rpc, &types.Log{Address: hookrManager, Topics: []common.Hash{swapTopic, hookrPoolID}, BlockNumber: h.Number.Uint64(), BlockHash: h.Hash()}, func(n string, b []byte) error { saved[n] = b; return nil })
	if e == nil || calls != 3 || len(saved["BLOCK_PACKAGE.json"]) == 0 || out.Error == "" {
		t.Fatal("missing proof repaired/lost package", calls, e)
	}
}
func TestEventPairOrchestrationMocksGateBranchOnCanonicalMatch(t *testing.T) {
	b, _ := os.ReadFile("../inputs/SAVED_CANARY_PACKAGE.json")
	c, inv, e := AdmitPackage(b)
	if e != nil {
		t.Fatal(e)
	}
	subject := &SelectedHookrTrade{Hash: c.block.Transactions()[1].Hash(), Ordinal: 1}
	for _, matched := range []bool{false, true} {
		actualCalls, branchCalls := 0, 0
		cap := &EventCapture{Package: b, Inventory: inv, Plan: &EconomicObservationPlan{}, Intervention: &LPIntervention{}}
		rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) { t.Fatal("unexpected dispatch"); return nil, nil })}, 8<<20, 32<<20)
		rpc.Configure(64, time.Now().Add(time.Minute), nil)
		result := runPreparedEventPairWith(context.Background(), rpc, func(string, []byte) error { return nil }, func(string, any) error { return nil }, cap, subject, func(c *Candidate, b *Bridge, i *LPIntervention, p EconomicObservationPlan) (*CalibrationResult, error) {
			actualCalls++
			return &CalibrationResult{Matched: matched}, nil
		}, func(context.Context, *RPCSource, WriteEvidence, EmitEvent, []byte, *ProspectiveResult) (string, error) {
			branchCalls++
			return "GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED", nil
		})
		if actualCalls != 1 || branchCalls != map[bool]int{false: 0, true: 1}[matched] {
			t.Fatal("branch gate", result)
		}
	}
}
func TestEventSeveralCandidatesInSameBlockKeepFirstOrdinal(t *testing.T) {
	j, p, f := eventTestJournal(t)
	n := f.anchor + 12
	j.Update("TEST_CURSOR", func(s *EventState) error {
		s.Cursor = n - 1
		_, h, _ := decodeFixtureHeader(f.headers[n-1])
		s.CursorHash = h.Hash()
		return nil
	})
	var body map[string]json.RawMessage
	json.Unmarshal(f.blocks[n], &body)
	var txs []json.RawMessage
	json.Unmarshal(body["transactions"], &txs)
	var second map[string]json.RawMessage
	json.Unmarshal(txs[1], &second)
	h2 := common.HexToHash("0xabcdef")
	second["hash"], _ = json.Marshal(h2)
	b, _ := json.Marshal(second)
	txs = append(txs, b)
	body["transactions"], _ = json.Marshal(txs)
	f.blocks[n], _ = json.Marshal(body)
	rows := eventRows(f, n, n)
	swap, route := *rows[0], *rows[1]
	swap.TxHash = h2
	route.TxHash = h2
	swap.TxIndex = 2
	route.TxIndex = 2
	swap.Index = 2
	route.Index = 3
	rows = append(rows, &swap, &route)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	if e := c.Observe(context.Background(), &swap); e != nil {
		t.Fatal(e)
	}
	_, tail, _ := decodeFixtureHeader(f.headers[n])
	if e := c.CompleteRange(context.Background(), n, n, tail.Hash(), rows); e != nil {
		t.Fatal(e)
	}
	if j.Snapshot().Lock.Selection.Subject.Ordinal != 1 || calls.Load() != 1 {
		t.Fatal("one-block order/dedup")
	}
}
func TestEventPersistedSelectedLockBlocksReopenNative(t *testing.T) {
	j, p, _ := eventTestJournal(t)
	j.Update("SYNTHETIC_LOCK", func(s *EventState) error { s.Lock = &EventLock{}; return nil })
	dir := j.dir
	j.Close()
	next, e := OpenEventJournal(dir, "OFFLINE_SYNTHETIC_ACQUISITION", p)
	if e != nil {
		t.Fatal(e)
	}
	defer next.Close()
	if EventResumeCheck(next.Snapshot()) == nil {
		t.Fatal("persisted lock resumed")
	}
}

type eventFakeSocket struct {
	ctx    context.Context
	frames chan []byte
	closed chan struct{}
	once   sync.Once
}

func (s *eventFakeSocket) ReadMessage() (int, []byte, error) {
	select {
	case b := <-s.frames:
		return 1, b, nil
	case <-s.ctx.Done():
		return 0, nil, io.EOF
	case <-s.closed:
		return 0, nil, io.EOF
	}
}
func (s *eventFakeSocket) Close() error { s.once.Do(func() { close(s.closed) }); return nil }
func TestEventRecordedStartupStreamCapturesBeforeH1AndClosesBlindInterval(t *testing.T) {
	p := DefaultEventPolicy()
	j, e := OpenEventJournal(t.TempDir(), "synthetic-startup", p)
	if e != nil {
		t.Fatal(e)
	}
	defer j.Close()
	f := newMonitorFixture(t)
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	var latest atomic.Int32
	var beforeH1 atomic.Bool
	factory := func(_ string, _ *EventJournal, _ EventPolicy, scope, prefix string, write WriteEvidence) (*RPCSource, error) {
		r, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			var q struct {
				ID     uint64
				Method string
				Params []json.RawMessage
			}
			json.NewDecoder(req.Body).Decode(&q)
			switch q.Method {
			case "eth_chainId":
				return respondJSON(q.ID, "0x1237"), nil
			case "eth_getBlockByNumber":
				var tag string
				json.Unmarshal(q.Params[0], &tag)
				if tag == "latest" {
					if latest.Add(1) == 1 {
						return respondJSON(q.ID, f.headers[f.anchor]), nil
					}
					for len(j.Snapshot().Cases) == 0 {
						select {
						case <-req.Context().Done():
							return nil, req.Context().Err()
						case <-time.After(time.Millisecond):
						}
					}
					beforeH1.Store(true)
					return respondJSON(q.ID, f.headers[f.anchor+1]), nil
				}
				n := common.HexToHash(tag).Big().Uint64()
				var full bool
				json.Unmarshal(q.Params[1], &full)
				if full {
					return respondJSON(q.ID, f.blocks[n]), nil
				}
				return respondJSON(q.ID, f.headers[n]), nil
			case "eth_getLogs":
				return respondJSON(q.ID, eventRows(f, f.anchor+1, f.anchor+1)), nil
			default:
				return nil, errors.New("SYNTHETIC_PROOF_NOT_SUPPLIED")
			}
		})}, 8<<20, 32<<20)
		r.Configure(256, time.Now().Add(time.Minute), nil)
		return r, nil
	}
	sub := func(ctx context.Context, _ string, _ EventMeter, _ WriteEvidence) (eventSocket, string, error) {
		s := &eventFakeSocket{ctx: ctx, frames: make(chan []byte, 1), closed: make(chan struct{})}
		raw, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "method": "eth_subscription", "params": map[string]any{"subscription": "synthetic-sub", "result": eventRows(f, f.anchor+1, f.anchor+1)[0]}})
		s.frames <- raw
		return s, "synthetic-sub", nil
	}
	a := EventAuthority{DecisionID: "synthetic-startup", Expires: time.Now().Add(time.Minute).Unix()}
	out := runEventWatcherWith(ctx, EventLiveConfig{Endpoint: "IN_MEMORY_TEST_ONLY"}, j, p, a, nil, factory, sub)
	if !beforeH1.Load() || out.State.Cursor != f.anchor+1 || out.State.Lock != nil || out.State.Consumed || out.Pair != nil {
		t.Fatal("startup interval/capture/authority", out)
	}
}
func TestEventDelayedProofDeadlinePreservesPartialWithoutRetry(t *testing.T) {
	b, _ := os.ReadFile("../inputs/SAVED_CANARY_PACKAGE.json")
	var p BlockPackage
	json.Unmarshal(b, &p)
	calls := 0
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		calls++
		var q struct{ ID uint64 }
		json.NewDecoder(req.Body).Decode(&q)
		if calls == 1 {
			return respondJSON(q.ID, p.Block), nil
		}
		if calls == 2 {
			return respondJSON(q.ID, p.Parent), nil
		}
		<-req.Context().Done()
		return nil, req.Context().Err()
	})}, 8<<20, 32<<20)
	rpc.Configure(40, time.Now().Add(time.Minute), nil)
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	h, _ := decodeHeader(p.Block)
	saved := map[string][]byte{}
	out, e := CaptureEventPackage(ctx, rpc, &types.Log{Address: hookrManager, Topics: []common.Hash{swapTopic, hookrPoolID}, BlockNumber: h.Number.Uint64(), BlockHash: h.Hash()}, func(n string, b []byte) error { saved[n] = b; return nil })
	if e == nil || calls != 3 || len(saved["BLOCK_PACKAGE.json"]) == 0 || out.Inventory != nil {
		t.Fatal("delayed proof retried or dropped partial", calls, e)
	}
}
func TestEventLockMarkerDetectsAValidButRolledBackJournalPrefix(t *testing.T) {
	j, _, _ := eventTestJournal(t)
	if e := j.Marker("FIRST_ELIGIBLE_LOCK.json", &EventLock{}); e != nil {
		t.Fatal(e)
	}
	if j.CheckMarkers() == nil {
		t.Fatal("marker ignored when journal lost lock")
	}
	if e := j.Marker("FIRST_ELIGIBLE_LOCK.json", &EventLock{}); e == nil {
		t.Fatal("lock marker overwritten")
	}
}
func TestEventCaseBudgetIsSharedAcrossCaptureAndBothWorlds(t *testing.T) {
	j, p, _ := eventTestJournal(t)
	h := common.HexToHash("0x99")
	scope := h.Hex()
	j.Update("SYNTHETIC_CASE", func(s *EventState) error { s.Cases[scope] = EventCase{Hash: h, RPC: p.CaptureRPC}; return nil })
	m := EventMeter{j, p, scope}
	if m.Reserve(context.Background(), "eth_getProof") == nil {
		t.Fatal("capture budget exceeded")
	}
	j.Update("SYNTHETIC_CONSUMPTION", func(s *EventState) error {
		s.Consumed = true
		s.Lock = &EventLock{Selection: LockedHookrSelection{BlockHash: h}}
		return nil
	})
	if e := m.Reserve(context.Background(), "eth_getProof"); e != nil {
		t.Fatal(e)
	}
	j.Update("EXHAUST_TOTAL_CASE", func(s *EventState) error { x := s.Cases[scope]; x.RPC = p.CaseRPC; s.Cases[scope] = x; return nil })
	if m.Reserve(context.Background(), "eth_getProof") == nil {
		t.Fatal("shared case budget reset")
	}
}
func TestEventHTTPBodyLimitHandlesExactContentLengthWithoutOverread(t *testing.T) {
	for _, known := range []bool{false, true} {
		j, p, _ := eventTestJournal(t)
		p.HTTPBytes = 5
		reader := &eventBody{ReadCloser: io.NopCloser(strings.NewReader("12345")), meter: EventMeter{j, p, "monitor"}, remaining: 5, completeAtLimit: known}
		b, e := io.ReadAll(reader)
		if string(b) != "12345" || (known && e != nil) || (!known && e == nil) || j.Snapshot().HTTPBytes != 5 {
			t.Fatal("body cap", known, string(b), e)
		}
	}
}
func TestEventRecordedWSSCredentialEchoNeverBecomesEvidence(t *testing.T) {
	j, p, _ := eventTestJournal(t)
	socket := &eventFakeSocket{ctx: context.Background(), frames: make(chan []byte, 1), closed: make(chan struct{})}
	defer socket.Close()
	socket.frames <- []byte(`{"jsonrpc":"2.0","id":1,"result":"synthetic-secret"}`)
	writes := 0
	_, e := eventReadWS(socket, EventMeter{j, p, "monitor"}, func(string, []byte) error { writes++; return nil }, "synthetic-secret")
	if e == nil || writes != 0 {
		t.Fatal("credential echo persisted")
	}
}

func TestEventCompactLockReopensWithExactPayloadReferences(t *testing.T) {
	j, p, f := eventTestJournal(t)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	for _, n := range []uint64{10, 20} {
		_, h, _ := decodeFixtureHeader(f.headers[f.anchor+n])
		if e := c.CompleteRange(context.Background(), f.anchor+n-9, f.anchor+n, h.Hash(), eventRows(f, f.anchor+n-9, f.anchor+n)); e != nil {
			t.Fatal(e)
		}
	}
	c.Wait()
	s := j.Snapshot()
	if s.Lock == nil || (len(s.Lock.Selection.Block) > 0 && string(s.Lock.Selection.Block) != "null") || s.Lock.Selection.Logs != nil {
		t.Fatal("journal contains full payload")
	}
	raw, e := os.ReadFile(filepath.Join(j.dir, "records", "SELECTION_LOGS.json"))
	if e != nil || ByteDigest(raw) != s.Lock.LogsSHA {
		t.Fatal("log reference", e)
	}
	pkg, e := os.ReadFile(filepath.Join(j.dir, eventCaptureDir(s.Lock.Selection.BlockHash), "BLOCK_PACKAGE.json"))
	if e != nil || ByteDigest(pkg) != s.Lock.PackageSHA {
		t.Fatal("package reference", e)
	}
	if e = j.CheckMarkers(); e != nil {
		t.Fatal(e)
	}
	j.Close()
	next, e := OpenEventJournal(j.dir, "OFFLINE_SYNTHETIC_ACQUISITION", p)
	if e != nil {
		t.Fatal(e)
	}
	defer next.Close()
	if e = next.CheckMarkers(); e != nil {
		t.Fatal(e)
	}
	if EventResumeCheck(next.Snapshot()) == nil {
		t.Fatal("locked event resumed")
	}
}
func TestEventOversizedJournalRowRejectedBeforeAppend(t *testing.T) {
	j, _, _ := eventTestJournal(t)
	before, _ := os.ReadFile(filepath.Join(j.dir, "journal.jsonl"))
	e := j.Update("OVERSIZED_SYNTHETIC", func(s *EventState) error { s.Stop = strings.Repeat("x", 1<<20); return nil })
	after, _ := os.ReadFile(filepath.Join(j.dir, "journal.jsonl"))
	if e == nil || string(before) != string(after) || j.Snapshot().Stop != "" {
		t.Fatal("oversized state corrupted journal")
	}
}
func TestEventMalformedSwapRejectedBeforeCapture(t *testing.T) {
	j, p, f := eventTestJournal(t)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	l := *eventRows(f, f.anchor+12, f.anchor+12)[1]
	l.Data = make([]byte, 16384)
	if e := c.Observe(context.Background(), &l); e == nil || calls.Load() != 0 {
		t.Fatal("malformed event captured")
	}
}

func TestEventCorruptConsumptionMarkerFailsClosed(t *testing.T) {
	j, _, _ := eventTestJournal(t)
	lock := &EventLock{}
	if e := j.Marker("FIRST_ELIGIBLE_LOCK.json", lock); e != nil {
		t.Fatal(e)
	}
	if e := j.Marker("SCIENTIFIC_CONSUMED.json", map[string]any{"scienceAuthoritySHA": "wrong"}); e != nil {
		t.Fatal(e)
	}
	if e := j.Update("SYNTHETIC_CONSUMED", func(s *EventState) error {
		s.Lock = lock
		s.Consumed = true
		s.AcquisitionAuthoritySHA = "a"
		s.ScienceAuthoritySHA = "s"
		return nil
	}); e != nil {
		t.Fatal(e)
	}
	if j.CheckMarkers() == nil {
		t.Fatal("corrupt consumed marker accepted")
	}
}
func TestEventConflictingDuplicateAfterLockStops(t *testing.T) {
	j, p, f := eventTestJournal(t)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	for _, n := range []uint64{10, 20} {
		_, h, _ := decodeFixtureHeader(f.headers[f.anchor+n])
		if e := c.CompleteRange(context.Background(), f.anchor+n-9, f.anchor+n, h.Hash(), eventRows(f, f.anchor+n-9, f.anchor+n)); e != nil {
			t.Fatal(e)
		}
	}
	rows := eventRows(f, f.anchor+12, f.anchor+12)
	for _, l := range rows {
		if eventTarget(l) {
			copy := *l
			copy.Data = append([]byte{}, l.Data...)
			copy.Data[0] ^= 1
			if e := c.Observe(context.Background(), &copy); e == nil {
				t.Fatal("conflicting lock event accepted")
			}
			return
		}
	}
	t.Fatal("fixture target absent")
}
