package prestate

import (
	"context"
	"errors"
	"time"
)

const MonitoringEstimatedCULimit uint64 = 1200000
const MonitoringEstimatedCUPerSecond uint64 = 200

// max(documented billed CU, documented throughput CU). eth_chainId bills 0
// but costs 5 throughput CU, so charging 5 also to the total is conservative.
func monitoringCost(method string) (uint64, error) {
	switch method {
	case "eth_chainId":
		return 5, nil
	case "eth_blockNumber":
		return 10, nil
	case "eth_getBlockByNumber":
		return 20, nil
	case "eth_getLogs":
		return 60, nil
	default:
		return 0, errors.New("MONITOR_CU_METHOD_NOT_ADMITTED_NO_BATCHING")
	}
}

type cuSlot struct {
	at   time.Time
	cost uint64
}
type monitorMeter struct {
	waitNs             int64
	limit, rate, spent uint64
	now                func() time.Time
	wait               func(context.Context, time.Duration) error
	began              time.Time
	recent             []cuSlot
}

func waitCU(ctx context.Context, d time.Duration) error {
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
func newMonitorMeter() *monitorMeter {
	return &monitorMeter{limit: MonitoringEstimatedCULimit, rate: MonitoringEstimatedCUPerSecond, now: time.Now, wait: waitCU, began: time.Now()}
}

// Called under RPCSource.mu. Serial reservations include failures; no refunds.
func (m *monitorMeter) acquire(ctx context.Context, method string) (uint64, int64, error) {
	cost, e := monitoringCost(method)
	if e != nil {
		return 0, 0, e
	}
	if cost > m.rate || m.spent > m.limit || cost > m.limit-m.spent {
		return 0, 0, errors.New("MONITOR_ESTIMATED_CU_EXHAUSTED")
	}
	for {
		if ctx.Err() != nil {
			return 0, 0, errors.New("MONITOR_CU_WAIT_DEADLINE")
		}
		now := m.now()
		used := uint64(0)
		kept := m.recent[:0]
		for _, s := range m.recent {
			if now.Sub(s.at) < time.Second {
				kept = append(kept, s)
				used += s.cost
			}
		}
		m.recent = kept
		if used+cost <= m.rate {
			m.spent += cost
			m.recent = append(m.recent, cuSlot{now, cost})
			return cost, now.Sub(m.began).Nanoseconds(), nil
		}
		before := m.now()
		e = m.wait(ctx, time.Second-now.Sub(m.recent[0].at))
		m.waitNs += m.now().Sub(before).Nanoseconds()
		if e != nil {
			return 0, 0, errors.New("MONITOR_CU_WAIT_DEADLINE")
		}
	}
}

// Hold each charged slot until one second after completion, which is later
// than dispatch. Intent fsync/network scheduling cannot compress wire bursts.
func (m *monitorMeter) complete() {
	if len(m.recent) > 0 {
		m.recent[len(m.recent)-1].at = m.now()
	}
}
func (r *RPCSource) ConfigureMonitoringCU() error {
	return r.ConfigureMonitoringCUBudget(MonitoringEstimatedCULimit)
}
func (r *RPCSource) ConfigureMonitoringCUBudget(limit uint64) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.id != 0 || r.meter != nil || limit == 0 || limit > MonitoringEstimatedCULimit {
		return errors.New("MONITOR_CU_CONFIGURATION_LIFECYCLE")
	}
	r.meter = newMonitorMeter()
	r.meter.limit = limit
	return nil
}
func (r *RPCSource) MonitoringCU() uint64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.meter == nil {
		return 0
	}
	return r.meter.spent
}

func (r *RPCSource) monitorLimit() uint64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.meter == nil {
		return 0
	}
	return r.meter.limit
}

type MonitorTiming struct {
	CUWaitNs        int64 `json:"cuWaitNs"`
	HTTPBodyNs      int64 `json:"httpBodyNs"`
	IntentWriteNs   int64 `json:"intentWriteNs"`
	ResponseWriteNs int64 `json:"responseWriteNs"`
	RPCPipelineNs   int64 `json:"rpcPipelineNs"`
}

func (r *RPCSource) MonitoringTiming() MonitorTiming {
	r.mu.Lock()
	defer r.mu.Unlock()
	v := r.monitorTiming
	if r.meter != nil {
		v.CUWaitNs = r.meter.waitNs
	}
	return v
}
