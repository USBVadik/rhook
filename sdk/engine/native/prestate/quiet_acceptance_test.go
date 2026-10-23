package prestate

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
)

// These fixtures replace only provider I/O. Journal, metering, range admission,
// capture scheduling and STOP ordering use production code.
func quietFixture(t *testing.T) (*EventJournal, EventPolicy, *monitorFixture) {
	j, _, f := eventTestJournal(t)
	j.Close()
	p := DefaultQuietEventPolicy()
	j, e := OpenEventJournal(t.TempDir(), "synthetic-quiet", p)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(j.Close)
	_, h, _ := decodeFixtureHeader(f.headers[f.anchor])
	j.Update("SYNTHETIC_ACTIVATION", func(s *EventState) error {
		s.Began = time.Now().UnixNano()
		s.Expires = time.Now().Add(5 * time.Minute).UnixNano()
		s.Activation = f.anchor
		s.Cursor = f.anchor
		s.ActivationHash = h.Hash()
		s.CursorHash = h.Hash()
		s.Connected = true
		return nil
	})
	return j, p, f
}
func quietProvider(t *testing.T, j *EventJournal, p EventPolicy, f *monitorFixture, head *atomic.Uint64, fail string, drift bool) *RPCSource {
	t.Helper()
	r, e := NewEventRPC(p.Coverage.Endpoint, j, p, "coverage", "SYNTHETIC_COVERAGE", EventWriter(j, p, "records"))
	if e != nil {
		t.Fatal(e)
	}
	var tailReads atomic.Int32
	base := roundTripFunc(func(req *http.Request) (*http.Response, error) {
		var q struct {
			ID     uint64
			Method string
			Params []json.RawMessage
		}
		json.NewDecoder(req.Body).Decode(&q)
		if q.Method == fail {
			return nil, errors.New("synthetic provider outage")
		}
		switch q.Method {
		case "eth_getBlockByNumber":
			var tag string
			json.Unmarshal(q.Params[0], &tag)
			n := head.Load()
			if tag != "latest" {
				n = common.HexToHash(tag).Big().Uint64()
			}
			raw := f.headers[n]
			if raw == nil {
				return nil, fmt.Errorf("missing synthetic header%d", n)
			}
			if drift && n == head.Load() && tag != "latest" && tailReads.Add(1) > 1 {
				_, h, _ := decodeFixtureHeader(raw)
				h.Time++
				raw, _ = json.Marshal(h)
			}
			return respondJSON(q.ID, raw), nil
		case "eth_getLogs":
			var filter struct {
				From string `json:"fromBlock"`
				To   string `json:"toBlock"`
			}
			json.Unmarshal(q.Params[0], &filter)
			from := common.HexToHash(filter.From).Big().Uint64()
			to := common.HexToHash(filter.To).Big().Uint64()
			if to-from >= 500 {
				t.Error("oversized coverage range")
			}
			return respondJSON(q.ID, eventRows(f, from, to)), nil
		default:
			t.Errorf("unexpected coverage method%s", q.Method)
			return nil, errors.New("unexpected synthetic method")
		}
	})
	r.client.Transport = eventHTTP{base, EventMeter{j, p, "coverage"}}
	return r
}
func TestQuietEightThousandBlocksAdvanceOnlyOnCheckedRanges(t *testing.T) {
	j, p, f := quietFixture(t)
	f.logs = nil
	_, base, _ := decodeFixtureHeader(f.headers[f.anchor])
	previous := base.Hash()
	for n := f.anchor + 1; n <= f.anchor+8000; n++ {
		h := types.CopyHeader(base)
		h.Number = new(big.Int).SetUint64(n)
		h.ParentHash = previous
		raw, _ := json.Marshal(h)
		f.headers[n] = raw
		previous = h.Hash()
	}
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	var head atomic.Uint64
	rpc := quietProvider(t, j, p, f, &head, "", false)
	for distance := uint64(500); distance <= 8000; distance += 500 {
		// Each iteration represents a separate quiet interval; release only expired
		// rate history to avoid making this offline test wait 800 real seconds.
		j.Update("SYNTHETIC_NEXT_INTERVAL", func(s *EventState) error { s.Rates = nil; return nil })
		head.Store(f.anchor + distance)
		if e := QuietCoverageStep(context.Background(), rpc, c); e != nil {
			t.Fatal(distance, e)
		}
		if j.Snapshot().Cursor != f.anchor+distance {
			t.Fatal("quiet cursor frozen", distance, j.Snapshot().Cursor)
		}
	}
	if calls.Load() != 0 || j.Snapshot().Lock != nil || j.Snapshot().Consumed {
		t.Fatal("silence authorized science")
	}
}
func TestQuietOutageAndOversizeDoNotAdvance(t *testing.T) {
	for _, kind := range []string{"outage", "oversize", "reorg"} {
		t.Run(kind, func(t *testing.T) {
			j, p, f := quietFixture(t)
			f.logs = nil
			var head atomic.Uint64
			head.Store(f.anchor + 10)
			fail := ""
			if kind == "outage" {
				fail = "eth_getLogs"
			}
			if kind == "oversize" {
				head.Store(f.anchor + 7998)
			}
			rpc := quietProvider(t, j, p, f, &head, fail, kind == "reorg")
			var calls atomic.Int32
			c := eventTestController(t, j, p, f, 0, &calls)
			e := QuietCoverageStep(context.Background(), rpc, c)
			if e == nil || j.Snapshot().Cursor != f.anchor || j.Snapshot().Lock != nil {
				t.Fatal("unverified range advanced", e)
			}
		})
	}
}
func TestQuietCaptureDrainKeepsOriginalBudgetAndBlocksNewAdmission(t *testing.T) {
	j, p, f := quietFixture(t)
	started := make(chan struct{})
	release := make(chan struct{})
	done := make(chan error, 1)
	c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
		close(started)
		select {
		case <-release:
		case <-ctx.Done():
			return nil, ctx.Err()
		}
		e := (EventMeter{j, p, l.BlockHash.Hex()}).Reserve(ctx, "eth_getBlockByNumber")
		done <- e
		return &EventCapture{Error: "SYNTHETIC_RECORDED"}, e
	})
	if e := c.Observe(context.Background(), f.logs[0]); e != nil {
		t.Fatal(e)
	}
	<-started
	if e := c.BeginDrain("SYNTHETIC_COVERAGE_OUTAGE"); e != nil {
		t.Fatal(e)
	}
	s := j.Snapshot()
	if !s.Draining || s.Stop != "" || s.Lock != nil {
		t.Fatal("terminal STOP prematurely canceled capture", s.Stop)
	}
	if e := c.Observe(context.Background(), f.logs[2]); e == nil {
		t.Fatal("new capture admitted during drain")
	}
	if e := (EventMeter{j, p, "coverage"}).Reserve(context.Background(), "eth_getLogs"); e == nil {
		t.Fatal("coverage continued during drain")
	}
	close(release)
	c.Wait()
	if e := <-done; e != nil {
		t.Fatal("already-started bounded capture could not finish", e)
	}
	if e := EventResumeCheck(j.Snapshot()); e == nil {
		t.Fatal("draining journal resumed")
	}
	j.Halt("SYNTHETIC_COVERAGE_OUTAGE")
	if j.Snapshot().Stop != "SYNTHETIC_COVERAGE_OUTAGE" {
		t.Fatal("missing final stop")
	}
}
func TestQuietCaptureExpiryAndBudgetCannotBeExtendedByDrain(t *testing.T) {
	for _, kind := range []string{"expiry", "budget"} {
		t.Run(kind, func(t *testing.T) {
			j, p, f := quietFixture(t)
			started := make(chan struct{})
			release := make(chan struct{})
			result := make(chan error, 1)
			c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
				close(started)
				<-release
				e := (EventMeter{j, p, l.BlockHash.Hex()}).Reserve(ctx, "eth_getBlockByNumber")
				result <- e
				return &EventCapture{}, e
			})
			c.Observe(context.Background(), f.logs[0])
			<-started
			c.BeginDrain("SYNTHETIC_STOP")
			j.Update("SYNTHETIC_CAP", func(s *EventState) error {
				if kind == "expiry" {
					s.Expires = time.Now().Add(-time.Second).UnixNano()
				} else {
					s.Billing = 125000
				}
				return nil
			})
			close(release)
			c.Wait()
			if <-result == nil {
				t.Fatal("drain bypassed", kind)
			}
		})
	}
}
func TestQuietAggregateBodyCreditIsReservedBeforeRead(t *testing.T) {
	j, p, _ := quietFixture(t)
	j.Update("SYNTHETIC_NEAR_CAP", func(s *EventState) error { s.HTTPBytes = p.Coverage.TotalHTTPBytes - 1; return nil })
	m := EventMeter{j, p, "coverage"}
	body := eventBody{ReadCloser: ioNopCloser{Reader: strings.NewReader("xx")}, meter: m, remaining: 2}
	if n, e := body.Read(make([]byte, 2)); e == nil || n != 0 {
		t.Fatal("read exceeded atomic aggregate credit", n, e)
	}
}

type ioNopCloser struct{ *strings.Reader }

func (ioNopCloser) Close() error { return nil }

func TestQuietCandidateWaitsForCheckedFirstnessAndDuplicateCaptureIsOne(t *testing.T) {
	j, p, f := quietFixture(t)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	target := eventRows(f, f.anchor+12, f.anchor+12)[0]
	c.Observe(context.Background(), target)
	c.Observe(context.Background(), target)
	c.Wait()
	if j.Snapshot().Lock != nil || j.Snapshot().Cursor != f.anchor {
		t.Fatal("unreconciled event locked")
	}
	var head atomic.Uint64
	head.Store(f.anchor + 20)
	rpc := quietProvider(t, j, p, f, &head, "", false)
	if e := QuietCoverageStep(context.Background(), rpc, c); e != nil {
		t.Fatal(e)
	}
	if j.Snapshot().Lock == nil || j.Snapshot().Lock.Selection.BlockNumber != f.anchor+12 || j.Snapshot().Consumed {
		t.Fatal("earliest eligibility/authority changed")
	}
}

func TestQuietDrainRestartAndPartialJournalFailClosed(t *testing.T) {
	j, p, f := quietFixture(t)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	if e := c.BeginDrain("SYNTHETIC_PROVIDER_OUTAGE"); e != nil {
		t.Fatal(e)
	}
	dir := j.dir
	j.Close()
	next, e := OpenEventJournal(dir, "synthetic-quiet", p)
	if e != nil {
		t.Fatal(e)
	}
	if e = EventResumeCheck(next.Snapshot()); e == nil {
		t.Fatal("drain reset by reopening journal")
	}
	next.Close()
	file, e := os.OpenFile(filepath.Join(dir, "journal.jsonl"), os.O_APPEND|os.O_WRONLY, 0600)
	if e != nil {
		t.Fatal(e)
	}
	file.WriteString("{")
	file.Close()
	if reopened, e := OpenEventJournal(dir, "synthetic-quiet", p); e == nil {
		reopened.Close()
		t.Fatal("partial journal resumed")
	}
}

func TestQuietProviderIdentityMethodsAndRedirectsArePinned(t *testing.T) {
	j, p, _ := quietFixture(t)
	if _, e := NewEventRPC("https://example.invalid", j, p, "coverage", "BAD", EventWriter(j, p, "records")); e == nil {
		t.Fatal("unbound coverage source")
	}
	r, e := NewEventRPC(p.Coverage.Endpoint, j, p, "coverage", "PIN", EventWriter(j, p, "records"))
	if e != nil {
		t.Fatal(e)
	}
	req, _ := http.NewRequest("GET", "https://example.invalid", nil)
	if r.client.CheckRedirect(req, nil) == nil {
		t.Fatal("redirect accepted")
	}
	if e = r.call(context.Background(), "eth_getProof", []any{}, new(any)); e == nil {
		t.Fatal("coverage source used for witness/state")
	}
}

func TestQuietProductionWatcherAdvancesDuringActualTimerSilence(t *testing.T) {
	p := DefaultQuietEventPolicy()
	j, e := OpenEventJournal(t.TempDir(), "synthetic-real-timer", p)
	if e != nil {
		t.Fatal(e)
	}
	defer j.Close()
	f := newMonitorFixture(t)
	f.logs = nil
	ctx, cancel := context.WithTimeout(context.Background(), 32*time.Second)
	defer cancel()
	var head atomic.Uint64
	head.Store(f.anchor + 10)
	factory := func(endpoint string, j *EventJournal, p EventPolicy, scope, prefix string, w WriteEvidence) (*RPCSource, error) {
		if scope == "coverage" {
			r := quietProvider(t, j, p, f, &head, "", false)
			// Chain identity still goes through production record/meter transport.
			original := r.client.Transport.(eventHTTP)
			base := original.base
			original.base = roundTripFunc(func(req *http.Request) (*http.Response, error) {
				raw, _ := io.ReadAll(req.Body)
				req.Body = io.NopCloser(bytes.NewReader(raw))
				var q struct {
					ID     uint64
					Method string
				}
				json.Unmarshal(raw, &q)
				if q.Method == "eth_chainId" {
					return respondJSON(q.ID, "0x1237"), nil
				}
				return base.RoundTrip(req)
			})
			r.client.Transport = original
			return r, nil
		}
		r, _ := NewRPCSource("https://example.invalid/v2/synthetic", &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			var q struct {
				ID     uint64
				Method string
			}
			json.NewDecoder(req.Body).Decode(&q)
			if q.Method == "eth_chainId" {
				return respondJSON(q.ID, "0x1237"), nil
			}
			return respondJSON(q.ID, f.headers[f.anchor]), nil
		})}, 8<<20, 32<<20)
		r.Configure(256, time.Now().Add(time.Minute), nil)
		return r, nil
	}
	sub := func(ctx context.Context, _ string, _ EventMeter, _ WriteEvidence) (eventSocket, string, error) {
		return &eventFakeSocket{ctx: ctx, frames: make(chan []byte), closed: make(chan struct{})}, "synthetic-sub", nil
	}
	out := runEventWatcherWith(ctx, EventLiveConfig{Endpoint: "IN_MEMORY_ONLY"}, j, p, EventAuthority{DecisionID: "synthetic-real-timer", Expires: time.Now().Add(time.Minute).Unix()}, nil, factory, sub)
	if out.State.Cursor != f.anchor+10 || out.State.Lock != nil || out.State.Consumed || out.Pair != nil {
		t.Fatal("real timer did not maintain quiet coverage", out.Cause, out.State.Cursor)
	}
}

func TestQuietHardBudgetFailureDuringDrainCancelsSiblingImmediately(t *testing.T) {
	j, p, f := quietFixture(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	j.SetHardCancel(cancel)
	started := make(chan struct{}, 2)
	trigger := make(chan struct{})
	siblingCanceled := make(chan struct{})
	first := f.logs[0].BlockHash
	c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
		started <- struct{}{}
		if l.BlockHash != first {
			<-ctx.Done()
			close(siblingCanceled)
			return &EventCapture{}, ctx.Err()
		}
		<-trigger
		transport := eventHTTP{roundTripFunc(func(*http.Request) (*http.Response, error) {
			t.Error("network called after exhausted budget")
			return nil, errors.New("must not dispatch")
		}), EventMeter{j, p, l.BlockHash.Hex()}}
		req, _ := http.NewRequestWithContext(ctx, "POST", "https://robinhood-mainnet.g.alchemy.com/v2/synthetic", strings.NewReader(`{"method":"eth_getBlockByNumber"}`))
		_, e := transport.RoundTrip(req)
		return &EventCapture{}, e
	})
	c.Observe(ctx, f.logs[0])
	c.Observe(ctx, f.logs[2])
	<-started
	<-started
	if e := c.BeginDrain("SYNTHETIC_COVERAGE_ERROR"); e != nil {
		t.Fatal(e)
	}
	j.Update("SYNTHETIC_EXHAUSTION", func(s *EventState) error { s.Billing = 125000; return nil })
	close(trigger)
	select {
	case <-siblingCanceled:
	case <-time.After(250 * time.Millisecond):
		cancel()
		c.Wait()
		t.Fatal("sibling continued after terminal hard STOP")
	}
	c.Wait()
	if j.Snapshot().Stop != "BILLING_BUDGET" {
		t.Fatal("hard failure was treated as soft drain", j.Snapshot().Stop)
	}
}

func TestQuietThreeHourJournalAndCUCapacity(t *testing.T) {
	j, p, f := quietFixture(t)
	baseCursor := f.anchor + 20
	_, base, _ := decodeFixtureHeader(f.headers[baseCursor])
	f.logs = nil
	j.Update("SYNTHETIC_RETAINED_CASES", func(s *EventState) error {
		s.Cursor = baseCursor
		s.CursorHash = base.Hash()
		for i := uint64(1); i <= 3; i++ {
			h := common.BigToHash(new(big.Int).SetUint64(i))
			s.Cases[h.Hex()] = EventCase{Hash: h, Number: f.anchor + i, Status: "INELIGIBLE", PackageSHA: strings.Repeat("a", 64), Error: "SYNTHETIC_UNSUPPORTED_ROUTE"}
			for log := uint64(0); log < 2; log++ {
				s.Seen[fmt.Sprintf("%s/%s/%d", h, h, log)] = EventSeen{f.anchor + i, h, strings.Repeat("b", 64)}
			}
		}
		return nil
	})
	var head atomic.Uint64
	rpc := quietProvider(t, j, p, f, &head, "", false)
	var calls atomic.Int32
	c := eventTestController(t, j, p, f, 0, &calls)
	for i := uint64(1); i <= 360; i++ {
		n := baseCursor + i*300
		h := types.CopyHeader(base)
		h.Number = new(big.Int).SetUint64(n)
		h.ParentHash = common.BigToHash(new(big.Int).SetUint64(n - 1))
		f.headers[n], _ = json.Marshal(h)
		head.Store(n)
		j.Update("SYNTHETIC_NEXT_30_SECOND_CYCLE", func(s *EventState) error { s.Rates = nil; return nil })
		if e := QuietCoverageStep(context.Background(), rpc, c); e != nil {
			t.Fatal("three-hour capacity", i, e)
		}
	}
	s := j.Snapshot()
	stat, _ := j.file.Stat()
	if s.Cursor != baseCursor+108000 || s.CoverageRPC != 2160 || s.Billing != 57600 || stat.Size() > 64<<20 {
		t.Fatal("capacity accounting", s.CoverageRPC, s.Billing, stat.Size())
	}
	report := map[string]any{"kind": "ACCELERATED_OFFLINE_CAPACITY_NOT_LIVE_PERFORMANCE", "cycles": 360, "modelSeconds": 10800, "modelBlocks": 108000, "coverageRPC": s.CoverageRPC, "estimatedCoverageCU": s.Billing, "journalBytes": stat.Size(), "evidencePayloadBytes": s.StorageBytes, "retainedCases": 3, "retainedSwapRows": 6, "headerFixture": "synthetic full header payloads; cursor/end identities stable, no execution proof"}
	raw, _ := json.MarshalIndent(report, "", "  ")
	if e := os.WriteFile("../records/THREE_HOUR_CAPACITY.json", append(raw, '\n'), 0600); e != nil {
		t.Fatal(e)
	}
}

func TestQuietJournalFailureAndFailedStopPersistenceCancelImmediately(t *testing.T) {
	for _, kind := range []string{"update", "stop", "evidence"} {
		t.Run(kind, func(t *testing.T) {
			j, p, _ := quietFixture(t)
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			j.SetHardCancel(cancel)
			var e error
			if kind == "evidence" {
				w := EventWriter(j, p, "records")
				if e = w("same.json", []byte("{}")); e != nil {
					t.Fatal(e)
				}
				e = w("same.json", []byte("{}"))
			} else {
				j.file.Close()
				if kind == "stop" {
					e = j.Halt("SYNTHETIC_HARD_STOP")
				} else {
					e = j.Update("SYNTHETIC_WRITE", func(s *EventState) error { s.Cursor++; return nil })
				}
			}
			if e == nil {
				t.Fatal("fault was not injected")
			}
			select {
			case <-ctx.Done():
			default:
				t.Fatal("durability failure left other work active")
			}
		})
	}
}

func TestQuietProbeRequiresNewAuthorityBeforeAnyArchive(t *testing.T) {
	root := filepath.Join(t.TempDir(), "must-not-exist")
	if _, e := RunCoverageCapabilityProbe(root, EventAuthority{}, "synthetic", nil); e == nil {
		t.Fatal("probe activated without exact authority")
	}
	if _, e := os.Stat(root); !os.IsNotExist(e) {
		t.Fatal("probe created an archive before authorization")
	}
}

func TestQuietFatalLatchBlocksEveryNewAdmissionWithoutDurableStop(t *testing.T) {
	p := DefaultQuietEventPolicy()
	j, e := OpenEventJournal(t.TempDir(), "fatal-admission-fixture", p)
	if e != nil {
		t.Fatal(e)
	}
	defer j.Close()
	j.signalHardFailure("SYNTHETIC_UNPERSISTED_FATAL")
	if eventAdmissionReady(context.Background(), j) == nil {
		t.Fatal("fatal latch admitted host/native phase")
	}
	if j.Snapshot().Stop != "" {
		t.Fatal("fixture unexpectedly has a durable STOP")
	}
	for _, kind := range []string{"COVERAGE_COMPLETE", "FIRST_ELIGIBLE_LOCK", "SCIENTIFIC_AUTHORITY_CONSUMED"} {
		called := false
		if e := j.Update(kind, func(s *EventState) error { called = true; s.Consumed = true; return nil }); e == nil || called {
			t.Fatalf("fatal latch allowed admission %s", kind)
		}
	}
	if j.Snapshot().Consumed {
		t.Fatal("fatal latch allowed science consumption")
	}
	fresh, e := OpenEventJournal(t.TempDir(), "canceled-admission-fixture", p)
	if e != nil {
		t.Fatal(e)
	}
	defer fresh.Close()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if eventAdmissionReady(ctx, fresh) == nil {
		t.Fatal("canceled context admitted host/native phase")
	}
}
func TestQuietProbeKnownLogsAndRangeCompleteness(t *testing.T) {
	var logs []*types.Log
	for _, name := range []string{"ATTEMPT02_WS_0002.json", "ATTEMPT02_WS_0003.json"} {
		raw, e := os.ReadFile("../inputs/" + name)
		if e != nil {
			t.Fatal(e)
		}
		var f eventWSFrame
		json.Unmarshal(raw, &f)
		logs = append(logs, f.Params.Result)
	}
	if e := validateCoverageProbeLogs(logs, logs, logs); e != nil {
		t.Fatal(e)
	}
	if e := validateCoverageProbeLogs(logs, logs, logs[:1]); e == nil {
		t.Fatal("missing positive-control event accepted")
	}
	if e := validateCoverageProbeLogs(append(logs, logs[0]), logs, logs); e == nil {
		t.Fatal("duplicate logs accepted")
	}
	// The real controller's combined filter also returns router settlement logs.
	router := &types.Log{Address: hookrRouter, Topics: []common.Hash{routerTopic, hookrPoolID, {}, {}}, Data: make([]byte, 64), BlockHash: CoverageProbeHash, BlockNumber: CoverageProbeBlock, TxHash: CoverageProbeTx, TxIndex: 2, Index: 38}
	combined := append(append([]*types.Log{}, logs...), router)
	if e := validateCoverageProbeLogs(combined, combined, combined); e != nil {
		t.Fatal("production router log rejected by capability probe:", e)
	}
	if e := validateCoverageProbeLogs(combined, combined, logs); e == nil {
		t.Fatal("router omitted from single-block response accepted")
	}
}
