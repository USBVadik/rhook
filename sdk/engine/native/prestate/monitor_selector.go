package prestate

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"math/big"
	"sort"
	"time"
)

// Static tuple from the locally saved exact-address Router ABI. Dynamic array
// offsets/padding must be canonical; this predicate never consults BRANCH.
var routerSwapSelector = eventTopic("swap(((address,address,uint24,int24,address),bool,int128,uint128,uint160,address,uint256),address,uint256[])")

func eligibleRouterInput(input []byte, value *hexutil.Big) bool {
	if len(input) < 4+14*32 || !bytes.Equal(input[:4], routerSwapSelector[:4]) || value == nil {
		return false
	}
	word := func(n int) *big.Int { return new(big.Int).SetBytes(input[4+n*32 : 4+(n+1)*32]) }
	address := func(n int, want common.Address) bool {
		a, e := abiAddress(common.BigToHash(word(n)))
		return e == nil && a == want
	}
	if !address(0, common.Address{}) || !address(1, rhookToken) || word(2).Cmp(big.NewInt(8388608)) != 0 || word(3).Cmp(big.NewInt(60)) != 0 || !address(4, hookrRoot) || word(5).Cmp(big.NewInt(1)) != 0 {
		return false
	}
	amount, e := signedABI(&types.Log{Data: input[4:]}, 6, 128)
	if e != nil || amount.Sign() >= 0 || new(big.Int).Neg(amount).Cmp(value.ToInt()) != 0 || value.ToInt().Sign() <= 0 || word(7).BitLen() > 128 || word(8).BitLen() > 160 {
		return false
	}
	for _, n := range []int{9, 11} {
		if _, e = abiAddress(common.BigToHash(word(n))); e != nil {
			return false
		}
	}
	if word(12).Cmp(big.NewInt(13*32)) != 0 || !word(13).IsUint64() {
		return false
	}
	count := word(13).Uint64()
	return count <= 256 && len(input) == 4+32*(14+int(count))
}

type LockedHookrSelection struct {
	ActivationNumber uint64              `json:"activationNumber"`
	ActivationHash   common.Hash         `json:"activationHash"`
	Block            json.RawMessage     `json:"block"`
	BlockHash        common.Hash         `json:"blockHash"`
	BlockNumber      uint64              `json:"blockNumber"`
	Subject          *SelectedHookrTrade `json:"subject"`
	Logs             []*types.Log        `json:"logs"`
}
type HookrMonitorResult struct {
	CompletedRanges            uint64                `json:"completedRanges"`
	ScientificSelectionEnabled bool                  `json:"scientificSelectionEnabled"`
	MaximumObservedBacklog     uint64                `json:"maximumObservedBacklog"`
	MatchingLogs               uint64                `json:"matchingLogs"`
	ElapsedNs                  int64                 `json:"elapsedNs"`
	FixedWaitNs                int64                 `json:"fixedWaitNs"`
	Timing                     MonitorTiming         `json:"timing"`
	EstimatedCU                uint64                `json:"estimatedCU"`
	EstimatedCULimit           uint64                `json:"estimatedCULimit"`
	EstimatedCUPerSecondLimit  uint64                `json:"estimatedCUPerSecondLimit"`
	Terminal                   string                `json:"terminal"`
	Cause                      string                `json:"cause,omitempty"`
	Selected                   *LockedHookrSelection `json:"selected,omitempty"`
	Polls                      uint64                `json:"polls"`
	ScannedThrough             uint64                `json:"scannedThrough"`
	RPCRequests                uint64                `json:"rpcRequests"`
	ResponseBytes              int64                 `json:"responseBytesRead"`
	TranscriptCommitment       string                `json:"transcriptCommitment"`
	ScientificNativeExecutions int                   `json:"scientificNativeExecutions"`
}

// One scanner implementation is shared by scientific selection and the
// performance canary. The canary never fetches candidate blocks or selects a
// scientific subject. Both retain the same validated chronological log ranges.
func RunHookrMonitor(ctx context.Context, rpc *RPCSource, write WriteEvidence, wait func(context.Context, time.Duration) error) *HookrMonitorResult {
	return runHookrScanner(ctx, rpc, write, wait, time.Now, true)
}
func RunHookrPerformanceCanary(ctx context.Context, rpc *RPCSource, write WriteEvidence, wait func(context.Context, time.Duration) error) *HookrMonitorResult {
	return runHookrScanner(ctx, rpc, write, wait, time.Now, false)
}
func runHookrScanner(ctx context.Context, rpc *RPCSource, write WriteEvidence, wait func(context.Context, time.Duration) error, now func() time.Time, scientific bool) (out *HookrMonitorResult) {
	began := now()
	out = &HookrMonitorResult{Terminal: "MONITOR_STOP", EstimatedCULimit: rpc.monitorLimit(), EstimatedCUPerSecondLimit: MonitoringEstimatedCUPerSecond, ScientificSelectionEnabled: scientific}
	defer func() {
		commitment, raw, count, size := rpc.Transcript()
		out.TranscriptCommitment = commitment
		out.RPCRequests = count
		out.ResponseBytes = size
		out.EstimatedCU = rpc.MonitoringCU()
		if e := write("MONITOR_RPC_TRANSCRIPT.json", raw); e != nil {
			out.Terminal = "MONITOR_STOP"
			out.Cause = "MONITOR_TRANSCRIPT_WRITE"
		}
		out.Timing = rpc.MonitoringTiming()
		out.ElapsedNs = now().Sub(began).Nanoseconds()
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
	head, lastHead := cursor, cursor
	out.ScannedThrough = cursor
	if e = EmitJSON(write, "ACTIVATION_BOUNDARY.json", map[string]any{"anchorNumber": cursor, "anchorHash": marker, "firstEligibleHeight": cursor + 1, "boundary": "EXCLUDE_ACTIVATION_BLOCK_AND_EARLIER", "maximumMonitoringSeconds": func() int {
		if scientific {
			return 14400
		}
		return 90
	}(), "scientificSelectionEnabled": scientific}); e != nil {
		fail(e)
		return
	}
	refresh := func(completed uint64) error {
		var n hexutil.Uint64
		if e := rpc.call(ctx, "eth_blockNumber", []any{}, &n); e != nil {
			return e
		}
		out.Polls++
		if uint64(n) < lastHead || uint64(n) < completed {
			return errors.New("HEAD_REGRESSION")
		}
		head, lastHead = uint64(n), uint64(n)
		if head-completed > out.MaximumObservedBacklog {
			out.MaximumObservedBacklog = head - completed
		}
		if head-completed > 100 {
			return errors.New("MONITOR_BACKLOG_OVER_100_NO_GAP_SKIP")
		}
		return nil
	}
	var partialSince time.Time
	haveHead := false
	for {
		if ctx.Err() != nil {
			out.Terminal = "MONITOR_EXPIRED"
			out.Cause = "FIXED_WINDOW_EXPIRED"
			return
		}
		if !haveHead {
			if e = refresh(cursor); e != nil {
				fail(e)
				return
			}
			haveHead = true
		}
		pending := head - cursor
		if pending > 0 && pending < 10 && partialSince.IsZero() {
			partialSince = now()
		}
		// Accumulate full ten-height ranges. A stalled partial range is flushed
		// within one second, rather than waiting indefinitely for future blocks.
		if pending == 0 || (pending < 10 && now().Sub(partialSince) < time.Second) {
			if pending == 0 {
				partialSince = time.Time{}
			}
			before := now()
			e = wait(ctx, 500*time.Millisecond)
			out.FixedWaitNs += now().Sub(before).Nanoseconds()
			if e != nil {
				out.Terminal = "MONITOR_EXPIRED"
				out.Cause = "FIXED_WINDOW_EXPIRED"
				return
			}
			if e = refresh(cursor); e != nil {
				fail(e)
				return
			}
			continue
		}
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
		batchStart := cursor
		for cursor < head && cursor-batchStart < 100 {
			pending = head - cursor
			if pending < 10 && (partialSince.IsZero() || now().Sub(partialSince) < time.Second) {
				break
			}
			end := cursor + min(uint64(10), pending)
			var logs []*types.Log
			filter := map[string]any{"fromBlock": hexutil.EncodeUint64(cursor + 1), "toBlock": hexutil.EncodeUint64(end), "address": []common.Address{hookrManager, hookrRouter}, "topics": []any{[]common.Hash{swapTopic, routerTopic}, hookrPoolID}}
			if e = rpc.call(ctx, "eth_getLogs", []any{filter}, &logs); e != nil {
				fail(e)
				return
			}
			// Reuse this fresh head as the next target. Do not return to an old head
			// and fixed sleep while complete ranges are already waiting.
			if e = refresh(cursor); e != nil {
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
			out.MatchingLogs += uint64(len(logs))
			if scientific {
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
					if reason != "ELIGIBLE" {
						continue
					}
					selected, _, e := selectHookrTradeLogs(raw, h, blocks[n], true)
					if e != nil {
						fail(e)
						return
					}
					if selected != nil {
						if e = refresh(cursor); e != nil {
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
			}
			cursor = end
			out.ScannedThrough = cursor
			out.CompletedRanges++
			if e = EmitJSON(write, fmt.Sprintf("SCAN_RANGE_%05d.json", out.CompletedRanges), map[string]any{"rangeStart": cursor - min(uint64(10), pending) + 1, "rangeEnd": cursor, "completedCursor": cursor, "observedHead": head, "completedBacklog": head - cursor, "elapsedNs": now().Sub(began).Nanoseconds(), "scientificSelectionEnabled": scientific}); e != nil {
				fail(e)
				return
			}
			partialSince = time.Time{}
			if head-cursor < 10 {
				break
			}
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

func ValidateLockedHookrSelection(s *LockedHookrSelection) error {
	if s == nil || s.Subject == nil || s.ActivationNumber <= 92076104 || s.BlockNumber <= s.ActivationNumber || s.ActivationHash == (common.Hash{}) {
		return errors.New("LOCKED_SELECTION_BOUNDARY")
	}
	h, reason, e := eligibleHeader(s.Block)
	if e != nil || reason != "ELIGIBLE" || h.Hash() != s.BlockHash || h.Number.Uint64() != s.BlockNumber {
		return errors.New("LOCKED_SELECTION_HEADER")
	}
	selected, _, e := selectHookrTradeLogs(s.Block, h, s.Logs, true)
	if e != nil || selected == nil || *selected != *s.Subject {
		return errors.New("LOCKED_SELECTION_SUBJECT")
	}
	return nil
}
