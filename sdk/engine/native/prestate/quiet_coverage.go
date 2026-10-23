package prestate

import (
	"context"
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"time"
)

type QuietCoveragePolicy struct {
	ProviderID     string
	Endpoint       string
	RangeBlocks    int
	PollSeconds    int
	CycleSeconds   int
	RPC            int
	BodyBytes      int64
	TotalHTTPBytes int64
	AggregateRPC   int
	Trust          string
}

func DefaultQuietEventPolicy() EventPolicy {
	p := DefaultEventPolicy()
	p.Version = "RHOOK_QUIET_COVERAGE_01"
	p.Coverage = &QuietCoveragePolicy{"DRPC_PUBLIC_ROBINHOOD_COVERAGE_01", "https://robinhood.drpc.org", 500, 30, 10, 2560, 64 << 20, 128 << 20, 3200, "Trusted provider completeness/coherence; not cryptographic absence; service/operator independence not established. Capability/access UNKNOWN until prospective smoke."}
	return p
}
func (q *QuietCoveragePolicy) Valid() bool {
	return q != nil && q.ProviderID == "DRPC_PUBLIC_ROBINHOOD_COVERAGE_01" && q.Endpoint == "https://robinhood.drpc.org" && q.RangeBlocks > 0 && q.RangeBlocks <= 500 && q.PollSeconds == 30 && q.CycleSeconds == 10 && q.RPC <= 2560 && q.RPC > 0 && q.BodyBytes > 0 && q.TotalHTTPBytes > 0 && q.AggregateRPC > 0 && q.Trust != ""
}

// One query shape for production reconciliation and its capability probe.
func quietCoverageLogFilter(from, to uint64) map[string]any {
	return map[string]any{"fromBlock": hexutil.EncodeUint64(from), "toBlock": hexutil.EncodeUint64(to), "address": []common.Address{hookrManager, hookrRouter}, "topics": []any{[]common.Hash{swapTopic, routerTopic}, hookrPoolID}}
}

// The network timeout bounds only range acquisition; eligibility may wait on a
// separately bounded hot capture. The original authority remains its outer bound.
func QuietCoverageStep(ctx context.Context, rpc *RPCSource, c *EventController) error {
	if !c.Policy.Coverage.Valid() {
		return errors.New("QUIET_POLICY_REQUIRED")
	}
	fetch, cancel := context.WithTimeout(ctx, time.Duration(c.Policy.Coverage.CycleSeconds)*time.Second)
	defer cancel()
	_, head, e := eventHeader(fetch, rpc, "latest")
	if e != nil {
		return e
	}
	state := c.Journal.Snapshot()
	if head.Number.Uint64() < state.Cursor {
		return errors.New("COVERAGE_HEAD_REGRESSION")
	}
	if head.Number.Uint64() == state.Cursor && head.Hash() != state.CursorHash {
		return errors.New("CURSOR_REORG")
	}
	return reconcileQuietRange(ctx, fetch, rpc, c, head.Number.Uint64())
}
func reconcileQuietRange(selectionCtx, fetchCtx context.Context, rpc *RPCSource, c *EventController, to uint64) error {
	for {
		s := c.Journal.Snapshot()
		if s.Stop != "" || s.Draining {
			return errors.New("COVERAGE_TERMINAL_OR_DRAINING")
		}
		if s.Lock != nil || s.Cursor >= to {
			return nil
		}
		if to-s.Cursor > uint64(c.Policy.MaximumGap) {
			return errors.New("GAP_EXCEEDS_FROZEN_BOUND")
		}
		end := min(to, s.Cursor+uint64(c.Policy.Coverage.RangeBlocks))
		_, before, e := eventHeader(fetchCtx, rpc, hexutil.EncodeUint64(s.Cursor))
		if e != nil {
			return e
		}
		if before.Number.Uint64() != s.Cursor || before.Hash() != s.CursorHash {
			return errors.New("CURSOR_REORG")
		}
		_, tailBefore, e := eventHeader(fetchCtx, rpc, hexutil.EncodeUint64(end))
		if e != nil {
			return e
		}
		if tailBefore.Number.Uint64() != end {
			return errors.New("RANGE_TAIL_NUMBER")
		}
		var logs []*types.Log
		e = rpc.call(fetchCtx, "eth_getLogs", []any{quietCoverageLogFilter(s.Cursor+1, end)}, &logs)
		if e != nil {
			return e
		}
		_, tailAfter, e := eventHeader(fetchCtx, rpc, hexutil.EncodeUint64(end))
		if e != nil {
			return e
		}
		_, again, e := eventHeader(fetchCtx, rpc, hexutil.EncodeUint64(s.Cursor))
		if e != nil {
			return e
		}
		if tailAfter.Number.Uint64() != end || tailAfter.Hash() != tailBefore.Hash() {
			return errors.New("RANGE_FORK_CHANGED")
		}
		if again.Number.Uint64() != s.Cursor || again.Hash() != s.CursorHash {
			return errors.New("CURSOR_REORG_DURING_COVERAGE")
		}
		if e = c.CompleteRange(selectionCtx, s.Cursor+1, end, tailAfter.Hash(), logs); e != nil {
			return e
		}
	}
}

// Synchronize with Observe's PENDING admission and done registration. DRAINING
// is not terminal STOP: only already-admitted bounded capture work may continue.
func (c *EventController) BeginDrain(reason string) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	s := c.Journal.Snapshot()
	if s.Draining {
		return nil
	}
	if s.Stop != "" {
		return errors.New("ALREADY_HARD_STOPPED")
	}
	err := c.Journal.Update("CAPTURE_DRAIN_BEGIN", func(s *EventState) error {
		if s.Stop != "" || s.Consumed {
			return errors.New("DRAIN_STATE_CONFLICT")
		}
		s.Draining = true
		s.DrainReason = reason
		return nil
	})
	if err != nil {
		c.Journal.cancelHard()
	}
	return err
}
