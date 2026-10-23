package prestate

// Test-only frozen baseline for scheduler/limiter ablation. Never built into
// the production worker; no RPC endpoint or scientific execution is used.
import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"sort"
	"time"
)

func runFrozenBaselineMonitor(ctx context.Context, rpc *RPCSource, write WriteEvidence, wait func(context.Context, time.Duration) error) (out *HookrMonitorResult) {
	out = &HookrMonitorResult{Terminal: "MONITOR_STOP", EstimatedCULimit: MonitoringEstimatedCULimit, EstimatedCUPerSecondLimit: MonitoringEstimatedCUPerSecond}
	defer func() {
		out.EstimatedCU = rpc.MonitoringCU()
		commitment, raw, count, size := rpc.Transcript()
		out.TranscriptCommitment = commitment
		out.RPCRequests = count
		out.ResponseBytes = size
		if e := write("MONITOR_RPC_TRANSCRIPT.json", raw); e != nil {
			out.Terminal = "MONITOR_STOP"
			out.Cause = "MONITOR_TRANSCRIPT_WRITE"
		}
	}()
	fail := func(e error) { out.Cause = e.Error() }
	rpc.mu.Lock()
	metered := rpc.meter != nil
	rpc.mu.Unlock()
	if !metered {
		fail(errors.New("MONITOR_CU_CONFIGURATION_REQUIRED"))
		return
	}
	var chain string
	if e := rpc.call(ctx, "eth_chainId", []any{}, &chain); e != nil {
		fail(e)
		return
	}
	if chain != "0x1237" {
		fail(errors.New("CHAIN_ID_MISMATCH"))
		return
	}
	var anchor json.RawMessage
	if e := rpc.call(ctx, "eth_getBlockByNumber", []any{"latest", false}, &anchor); e != nil {
		fail(e)
		return
	}
	ah, e := decodeHeader(anchor)
	if e != nil {
		fail(e)
		return
	}
	if ah.Number.Uint64() <= 92076104 || ah.Number.Uint64() == ^uint64(0) {
		fail(errors.New("ACTIVATION_ANCHOR_REJECTED"))
		return
	}
	cursor, marker := ah.Number.Uint64(), ah.Hash()
	out.ScannedThrough = cursor
	if e = EmitJSON(write, "ACTIVATION_BOUNDARY.json", map[string]any{"anchorNumber": cursor, "anchorHash": marker, "firstEligibleHeight": cursor + 1, "boundary": "EXCLUDE_ACTIVATION_BLOCK_AND_EARLIER", "maximumMonitoringSeconds": 14400}); e != nil {
		fail(e)
		return
	}
	lastHead := cursor
	freshHead := func(completed uint64) error {
		var n hexutil.Uint64
		if e := rpc.call(ctx, "eth_blockNumber", []any{}, &n); e != nil {
			return e
		}
		if uint64(n) < lastHead || uint64(n) < completed {
			return errors.New("HEAD_REGRESSION")
		}
		lastHead = uint64(n)
		if uint64(n)-completed > 100 {
			return errors.New("MONITOR_BACKLOG_OVER_100_NO_GAP_SKIP")
		}
		return nil
	}
	for {
		if e = wait(ctx, time.Second); e != nil {
			out.Terminal = "MONITOR_EXPIRED"
			out.Cause = "FIXED_WINDOW_EXPIRED"
			return
		}
		out.Polls++
		var number hexutil.Uint64
		if e = rpc.call(ctx, "eth_blockNumber", []any{}, &number); e != nil {
			fail(e)
			return
		}
		head := uint64(number)
		if head < cursor || head < lastHead {
			fail(errors.New("HEAD_REGRESSION"))
			return
		}
		lastHead = head
		if head == cursor {
			continue
		}
		if head-cursor > 100 {
			fail(errors.New("MONITOR_BACKLOG_OVER_100_NO_GAP_SKIP"))
			return
		}
		// Revalidate the preceding completed range boundary before advancing.
		var boundary json.RawMessage
		if e = rpc.call(ctx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(cursor), false}, &boundary); e != nil {
			fail(e)
			return
		}
		bh, e := decodeHeader(boundary)
		if e != nil || bh.Hash() != marker || bh.Number.Uint64() != cursor {
			fail(errors.New("OBSERVED_BOUNDARY_REORG"))
			return
		}
		for cursor < head {
			end := cursor + min(uint64(10), head-cursor)
			var logs []*types.Log
			filter := map[string]any{"fromBlock": hexutil.EncodeUint64(cursor + 1), "toBlock": hexutil.EncodeUint64(end), "address": []common.Address{hookrManager, hookrRouter}, "topics": []any{[]common.Hash{swapTopic, routerTopic}, hookrPoolID}}
			if e = rpc.call(ctx, "eth_getLogs", []any{filter}, &logs); e != nil {
				fail(e)
				return
			}
			// Rate limiting may delay a range. Recheck the head before accepting
			// any candidate; never jump over an unprocessed range to catch up.
			if e = freshHead(cursor); e != nil {
				fail(e)
				return
			}
			blocks := map[uint64][]*types.Log{}
			seen := map[string]bool{}
			for _, l := range logs {
				if l == nil || l.Removed || l.BlockNumber <= cursor || l.BlockNumber > end || l.BlockHash == (common.Hash{}) || l.TxHash == (common.Hash{}) || len(l.Topics) < 2 || l.Topics[1] != hookrPoolID || ((l.Address != hookrManager || l.Topics[0] != swapTopic) && (l.Address != hookrRouter || l.Topics[0] != routerTopic)) {
					fail(errors.New("MONITOR_LOG_IDENTITY"))
					return
				}
				key := fmt.Sprint(l.BlockHash, "/", l.Index)
				if seen[key] {
					fail(errors.New("DUPLICATE_MONITOR_LOG"))
					return
				}
				seen[key] = true
				blocks[l.BlockNumber] = append(blocks[l.BlockNumber], l)
			}
			heights := []uint64{}
			for n, ls := range blocks {
				for _, l := range ls {
					if l.Address == hookrManager && l.Topics[0] == swapTopic {
						heights = append(heights, n)
						break
					}
				}
			}
			sort.Slice(heights, func(i, j int) bool { return heights[i] < heights[j] })
			for _, n := range heights {
				var raw json.RawMessage
				if e = rpc.call(ctx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(n), true}, &raw); e != nil {
					fail(e)
					return
				}
				h, reason, e := eligibleHeader(raw)
				if e != nil || h.Number.Uint64() != n {
					fail(errors.New("MONITOR_CANDIDATE_HEADER"))
					return
				}
				// Structural support bounds are part of eligibility, not outcome sorting.
				if reason != "ELIGIBLE" {
					continue
				}
				selected, _, e := selectHookrTradeLogs(raw, h, blocks[n], true)
				if e != nil {
					fail(e)
					return
				}
				if selected != nil {
					if e = freshHead(cursor); e != nil {
						fail(e)
						return
					}
					out.Selected = &LockedHookrSelection{ah.Number.Uint64(), ah.Hash(), raw, h.Hash(), n, selected, blocks[n]}
					if e = EmitJSON(write, "LOCKED_SELECTION.json", out.Selected); e != nil {
						fail(e)
						return
					}
					out.Terminal = "FIRST_ELIGIBLE_BUY_LOCKED"
					return
				}
			}
			cursor = end
			out.ScannedThrough = cursor
		}
		var tail json.RawMessage
		if e = rpc.call(ctx, "eth_getBlockByNumber", []any{hexutil.EncodeUint64(cursor), false}, &tail); e != nil {
			fail(e)
			return
		}
		th, e := decodeHeader(tail)
		if e != nil || th.Number.Uint64() != cursor {
			fail(errors.New("MONITOR_TAIL_HEADER"))
			return
		}
		marker = th.Hash()
	}
}
