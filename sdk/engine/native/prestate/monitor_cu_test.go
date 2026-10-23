package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"testing"
	"time"
)

func virtualMeter() *monitorMeter {
	now := time.Unix(100, 0)
	m := newMonitorMeter()
	m.now = func() time.Time { return now }
	m.began = now
	m.wait = func(ctx context.Context, d time.Duration) error {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		now = now.Add(d)
		return nil
	}
	return m
}
func TestMonitoringCUCostTableAndNoBatchEscape(t *testing.T) {
	for method, want := range map[string]uint64{"eth_chainId": 5, "eth_blockNumber": 10, "eth_getBlockByNumber": 20, "eth_getLogs": 60} {
		got, e := monitoringCost(method)
		if e != nil || got != want {
			t.Fatal(method, got, e)
		}
	}
	for _, method := range []string{"batch", "[eth_getLogs,eth_getLogs]", "eth_getProof", ""} {
		if _, e := monitoringCost(method); e == nil {
			t.Fatal("unsupported monitoring method", method)
		}
	}
}
func TestMonitoringCUBudgetIncludesFailedRequestAndNoRetry(t *testing.T) {
	sends := 0
	r, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(q *http.Request) (*http.Response, error) {
		sends++
		return nil, errors.New("synthetic transport stop")
	})}, 1024, 4096)
	r.ConfigureMonitoringCU()
	r.meter.limit = 60
	_, e := r.callRaw(context.Background(), "eth_getLogs", []any{}, false)
	if e == nil || r.MonitoringCU() != 60 || sends != 1 {
		t.Fatal(e, r.MonitoringCU(), sends)
	}
	r.callRaw(context.Background(), "eth_getLogs", []any{}, false)
	if sends != 1 || r.MonitoringCU() != 60 {
		t.Fatal("retry or refund")
	}
}
func TestMonitoringCUExhaustionStopsBeforeHTTP(t *testing.T) {
	sends := 0
	r, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(q *http.Request) (*http.Response, error) {
		sends++
		var msg map[string]any
		if json.NewDecoder(q.Body).Decode(&msg) != nil {
			t.Fatal("batch/non-object request")
		}
		return respondJSON(uint64(msg["id"].(float64)), []any{}), nil
	})}, 1024, 4096)
	r.ConfigureMonitoringCU()
	r.meter = virtualMeter()
	r.meter.limit = 60
	r.callRaw(context.Background(), "eth_getLogs", []any{}, false)
	if _, e := r.callRaw(context.Background(), "eth_getLogs", []any{}, false); e == nil || e.Error() != "MONITOR_ESTIMATED_CU_EXHAUSTED" {
		t.Fatal(e)
	}
	if sends != 1 || r.id != 1 || r.meter.spent != 60 {
		t.Fatal(sends, r.id, r.meter.spent)
	}
}
func TestMonitoringCUStrictRollingSecondAndDelayedDispatch(t *testing.T) {
	m := virtualMeter()
	m.rate = 100
	ctx := context.Background()
	type entry struct {
		at   time.Time
		cost uint64
	}
	var sent []entry
	for _, method := range []string{"eth_getLogs", "eth_getLogs", "eth_getBlockByNumber", "eth_blockNumber", "eth_chainId", "eth_getLogs"} {
		cost, _, e := m.acquire(ctx, method)
		if e != nil {
			t.Fatal(e)
		}
		// Intent fsync/dispatch delayed by 2 seconds on first request. The slot
		// must remain charged until completion, rather than expiring in that gap.
		if len(sent) == 0 {
			m.wait(ctx, 2*time.Second)
		}
		at := m.now()
		used := cost
		for _, v := range sent {
			if at.Sub(v.at) < time.Second {
				used += v.cost
			}
		}
		if used > 100 {
			t.Fatal("actual dispatch burst", used)
		}
		sent = append(sent, entry{at, cost})
		m.complete()
	}
	if sent[1].at.Sub(sent[0].at) < time.Second {
		t.Fatal("slot expired before delayed dispatch")
	}
	if m.spent != 215 {
		t.Fatal(m.spent)
	}
}
func TestMonitoringCUWaitRespectsContextAndNoUnmeteredMethods(t *testing.T) {
	m := virtualMeter()
	m.acquire(context.Background(), "eth_getLogs")
	m.complete()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, _, e := m.acquire(ctx, "eth_getLogs"); e == nil || m.spent != 60 {
		t.Fatal(e, m.spent)
	}
	r, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", nil, 1024, 4096)
	r.ConfigureMonitoringCU()
	if _, e := r.callRaw(context.Background(), "eth_getProof", []any{}, false); e == nil || r.id != 0 {
		t.Fatal("native method bypassed monitor costs", e)
	}
	if r.ConfigureMonitoringCU() == nil {
		t.Fatal("meter reset")
	}
}

func TestMonitoringCUProduction200RollingLimit(t *testing.T) {
	m := virtualMeter()
	if m.rate != 200 {
		t.Fatal("production rate", m.rate)
	}
	var at []time.Time
	for i := 0; i < 4; i++ {
		if _, _, e := m.acquire(context.Background(), "eth_getLogs"); e != nil {
			t.Fatal(e)
		}
		at = append(at, m.now())
		m.complete()
	}
	if at[3].Sub(at[0]) < time.Second || m.spent != 240 {
		t.Fatal("200-CU burst bypass", at, m.spent)
	}
}
