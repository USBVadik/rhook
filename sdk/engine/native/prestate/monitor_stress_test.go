package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"math/big"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
)

type stressScenario struct {
	Legacy       bool
	Name         string
	Rate         float64
	Seconds      float64
	RateCU       uint64
	P95Latency   bool
	SpikeAt      int
	SpikeSeconds float64
	Stall        bool
	FailAt       int
	RegressionAt int
}
type stressResult struct {
	Name            string        `json:"name"`
	HeadRate        float64       `json:"simulatedHeadBlocksPerSecond"`
	Seconds         float64       `json:"simulatedSeconds"`
	Scanned         uint64        `json:"completedHeights"`
	BlocksPerSecond float64       `json:"completedBlocksPerSecond"`
	CUPerSecond     float64       `json:"estimatedCUPerSecond"`
	FinalBacklog    uint64        `json:"finalBacklog"`
	MaximumBacklog  uint64        `json:"maximumObservedBacklog"`
	RPC             uint64        `json:"rpcRequests"`
	CU              uint64        `json:"estimatedCU"`
	Ranges          int           `json:"queriedRanges"`
	Terminal        string        `json:"terminal"`
	Cause           string        `json:"cause"`
	Timing          MonitorTiming `json:"timing"`
	FixedWaitNs     int64         `json:"fixedWaitNs"`
	LatencyModel    string        `json:"latencyModel"`
}

func runStress(t *testing.T, s stressScenario) stressResult {
	t.Helper()
	data, e := os.ReadFile("../records/BASELINE_TIMING_ANALYSIS.json")
	if e != nil {
		t.Fatal(e)
	}
	var timing struct {
		Samples []struct {
			Method  string  `json:"method"`
			Seconds float64 `json:"proxySeconds"`
		}
	}
	if json.Unmarshal(data, &timing) != nil || len(timing.Samples) != 75 {
		t.Fatal("timing fixture")
	}
	latencies := map[string][]time.Duration{}
	for _, v := range timing.Samples {
		latencies[v.Method] = append(latencies[v.Method], time.Duration(v.Seconds*1e9))
	}
	_, _, raw, _ := inputFixture(t)
	var base types.Header
	json.Unmarshal(raw, &base)
	now := time.Unix(100, 0)
	began := now
	deadline := began.Add(time.Duration(s.Seconds * 1e9))
	var activation time.Time
	anchor := uint64(92090000)
	advertised := anchor
	requests := 0
	methodCounts := map[string]int{}
	var ranges [][2]uint64
	advance := func(d time.Duration) error {
		if now.Add(d).After(deadline) {
			now = deadline
			return context.DeadlineExceeded
		}
		now = now.Add(d)
		return nil
	}
	head := func() uint64 {
		if activation.IsZero() {
			return anchor
		}
		seconds := now.Sub(activation).Seconds()
		if s.Stall && seconds > 20 {
			seconds -= math.Min(seconds-20, 5)
		}
		return anchor + uint64(math.Floor(math.Max(0, seconds)*s.Rate))
	}
	header := func(n uint64) json.RawMessage {
		h := types.CopyHeader(&base)
		h.Number = new(big.Int).SetUint64(n)
		b, _ := json.Marshal(h)
		var m map[string]any
		json.Unmarshal(b, &m)
		m["hash"] = h.Hash()
		b, _ = json.Marshal(m)
		return b
	}
	client := &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		requests++
		var q struct {
			ID     uint64            `json:"id"`
			Method string            `json:"method"`
			Params []json.RawMessage `json:"params"`
		}
		if json.NewDecoder(req.Body).Decode(&q) != nil {
			t.Fatal("batch or malformed request")
		}
		if requests == s.FailAt {
			return nil, errors.New("synthetic transport stop")
		}
		ds := latencies[q.Method]
		if len(ds) == 0 {
			t.Fatal("unsupported scientific/native method", q.Method)
		}
		d := ds[methodCounts[q.Method]%len(ds)]
		methodCounts[q.Method]++
		if s.P95Latency {
			d = 150 * time.Millisecond
		}
		if requests == s.SpikeAt {
			d += time.Duration(s.SpikeSeconds * 1e9)
		}
		advance(d)
		switch q.Method {
		case "eth_chainId":
			return respondJSON(q.ID, "0x1237"), nil
		case "eth_blockNumber":
			advertised = head()
			if requests == s.RegressionAt {
				advertised = anchor - 1
			}
			return respondJSON(q.ID, hexutil.EncodeUint64(advertised)), nil
		case "eth_getBlockByNumber":
			var n string
			var full bool
			json.Unmarshal(q.Params[0], &n)
			json.Unmarshal(q.Params[1], &full)
			if full {
				t.Fatal("canary performed scientific candidate selection")
			}
			if n == "latest" {
				activation = now
				return respondJSON(q.ID, header(anchor)), nil
			}
			x, _ := hexutil.DecodeUint64(n)
			if x > advertised {
				t.Fatal("future header accepted")
			}
			return respondJSON(q.ID, header(x)), nil
		case "eth_getLogs":
			var f struct {
				From string `json:"fromBlock"`
				To   string `json:"toBlock"`
			}
			json.Unmarshal(q.Params[0], &f)
			a, _ := hexutil.DecodeUint64(f.From)
			b, _ := hexutil.DecodeUint64(f.To)
			previous := anchor
			if len(ranges) > 0 {
				previous = ranges[len(ranges)-1][1]
			}
			if a != previous+1 || b < a || b-a >= 10 || b > advertised {
				t.Fatal("gap/double count/future/oversized range", a, b, previous, advertised)
			}
			ranges = append(ranges, [2]uint64{a, b})
			return respondJSON(q.ID, []any{}), nil
		}
		t.Fatal("unexpected method", q.Method)
		return nil, nil
	})}
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", client, 1<<20, 64<<20)
	rpc.Configure(60000, time.Now().Add(time.Hour), func(string, RPCRecord) error { advance(time.Millisecond); return nil })
	rpc.ConfigureMonitoringCU()
	rpc.meter.now = func() time.Time { return now }
	rpc.meter.began = now
	rpc.meter.wait = advanceWait(advance)
	if s.RateCU != 0 {
		rpc.meter.rate = s.RateCU
	}
	writes := map[string][]byte{}
	var out *HookrMonitorResult
	write := func(name string, b []byte) error { writes[name] = common.CopyBytes(b); return nil }
	if s.Legacy {
		out = runFrozenBaselineMonitor(context.Background(), rpc, write, advanceWait(advance))
	} else {
		out = runHookrScanner(context.Background(), rpc, write, advanceWait(advance), func() time.Time { return now }, false)
	}
	out.Timing = rpc.MonitoringTiming()
	if out.Selected != nil || out.ScientificSelectionEnabled || writes["LOCKED_SELECTION.json"] != nil || out.ScientificNativeExecutions != 0 {
		t.Fatal("canary selected subject/native")
	}
	elapsed := now.Sub(began).Seconds()
	finalBacklog := head() - out.ScannedThrough
	model := "captured per-method intent/response mtime proxy + 1ms each record write"
	if s.P95Latency {
		model = "150ms per RPC + 1ms each record write"
	}
	return stressResult{s.Name, s.Rate, elapsed, out.ScannedThrough - anchor, float64(out.ScannedThrough-anchor) / elapsed, float64(out.EstimatedCU) / elapsed, finalBacklog, out.MaximumObservedBacklog, out.RPCRequests, out.EstimatedCU, len(ranges), out.Terminal, out.Cause, out.Timing, out.FixedWaitNs, model}
}
func advanceWait(advance func(time.Duration) error) func(context.Context, time.Duration) error {
	return func(ctx context.Context, d time.Duration) error {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return advance(d)
	}
}
func TestMonitorSustainedStress(t *testing.T) {
	scenarios := []stressScenario{
		{Name: "legacy100_9_6", Legacy: true, Rate: 9.6, Seconds: 600, RateCU: 100},
		{Name: "optimized100_9_6", Rate: 9.6, Seconds: 600, RateCU: 100},
		{Name: "captured_9_6", Rate: 9.6, Seconds: 600}, {Name: "captured_15", Rate: 15, Seconds: 600}, {Name: "captured_18", Rate: 18, Seconds: 600},
		{Name: "p95_18", Rate: 18, Seconds: 600, P95Latency: true},
		{Name: "p95_15", Rate: 15, Seconds: 600, P95Latency: true}, {Name: "captured_15_rate180", Rate: 15, Seconds: 600, RateCU: 180},
		{Name: "latency_spike_2s", Rate: 15, Seconds: 120, SpikeAt: 40, SpikeSeconds: 2}, {Name: "head_stall_5s", Rate: 15, Seconds: 120, Stall: true},
		{Name: "unsafe_latency_spike_12s", Rate: 15, Seconds: 120, SpikeAt: 40, SpikeSeconds: 12}, {Name: "transport_error", Rate: 15, Seconds: 120, FailAt: 40}, {Name: "head_regression", Rate: 15, Seconds: 120, RegressionAt: 7},
	}
	var results []stressResult
	for _, s := range scenarios {
		t.Run(s.Name, func(t *testing.T) {
			v := runStress(t, s)
			results = append(results, v)
			t.Logf("%+v", v)
			switch s.Name {
			case "legacy100_9_6", "optimized100_9_6", "unsafe_latency_spike_12s":
				if v.Terminal != "MONITOR_STOP" || v.Cause != "MONITOR_BACKLOG_OVER_100_NO_GAP_SKIP" {
					t.Fatal(v)
				}
			case "transport_error":
				if v.Cause != "RPC_TRANSPORT_FAILURE" || v.RPC != 40 {
					t.Fatal(v)
				}
			case "head_regression":
				if v.Cause != "HEAD_REGRESSION" {
					t.Fatal(v)
				}
			default:
				if v.MaximumBacklog > 100 || v.FinalBacklog > 30 || v.Seconds < s.Seconds-.001 || v.CUPerSecond > 200 {
					t.Fatal("not sustained", v)
				}
				if s.Name == "captured_15" || s.Name == "p95_15" {
					if v.BlocksPerSecond < 14.95 {
						t.Fatal("target 15 with finite tail", v)
					}
				}
			}
		})
	}
	if out := os.Getenv("RHOOK_STRESS_REPORT"); out != "" {
		b, _ := json.MarshalIndent(map[string]any{"kind": "DETERMINISTIC_OFFLINE_MODEL_NOT_LIVE_PERFORMANCE", "results": results}, "", "  ")
		if e := os.WriteFile(filepath.Clean(out), append(b, '\n'), 0600); e != nil {
			t.Fatal(e)
		}
	}
}
