package prestate

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"github.com/ethereum/go-ethereum/accounts/abi"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"math/big"
	"net/http"
	"os"
	"testing"
	"time"
)

func monitorInput(amount int64) []byte {
	ns := []*big.Int{big.NewInt(0), rhookToken.Big(), big.NewInt(8388608), big.NewInt(60), hookrRoot.Big(), big.NewInt(1), big.NewInt(amount), big.NewInt(1), big.NewInt(1), big.NewInt(0x22), big.NewInt(9999999999), big.NewInt(0), big.NewInt(13 * 32), big.NewInt(0)}
	return append(common.CopyBytes(routerSwapSelector[:4]), encodedInts(ns...)...)
}
func TestSelectorExactInputMatchesSavedRouterABI(t *testing.T) {
	raw, e := os.ReadFile("../inputs/ROUTER_SWAP_ABI.json")
	if e != nil {
		t.Fatal(e)
	}
	a, e := abi.JSON(bytes.NewReader(raw))
	if e != nil || !bytes.Equal(a.Methods["swap"].ID, routerSwapSelector[:4]) {
		t.Fatal("saved ABI selector mismatch", e)
	}
	value := hexutil.Big(*big.NewInt(100))
	if !eligibleRouterInput(monitorInput(-100), &value) {
		t.Fatal("canonical exact-input buy rejected")
	}
	for _, kind := range []string{"exact-output", "value", "currency", "pool", "offset", "padding", "direction", "width"} {
		input := monitorInput(-100)
		v := value
		switch kind {
		case "exact-output":
			input = monitorInput(100)
		case "value":
			v = hexutil.Big(*big.NewInt(101))
		case "currency":
			input[35] = 1
		case "pool":
			input[4+5*32-1] ^= 1
		case "offset":
			input[4+13*32-1] ^= 1
		case "padding":
			input = append(input, 0)
		case "direction":
			input[4+6*32-1] = 0
		case "width":
			input[4+7*32-17] = 0
		}
		if eligibleRouterInput(input, &v) {
			t.Fatal("invalid selector input admitted", kind)
		}
	}
}

type monitorFixture struct {
	fullBlockRequests int
	afterLogsHead     uint64
	anchor            uint64
	headers           map[uint64]json.RawMessage
	blocks            map[uint64]json.RawMessage
	logs              []*types.Log
	requests          int
	ranges            [][2]uint64
	seen              map[string][]byte
	failLogs          bool
	regression        bool
	removed           bool
	reverse           bool
	head              uint64
}

func newMonitorFixture(t *testing.T) *monitorFixture {
	_, _, raw, _ := inputFixture(t)
	var base types.Header
	if json.Unmarshal(raw, &base) != nil {
		t.Fatal("header fixture")
	}
	f := &monitorFixture{anchor: 92080000, headers: map[uint64]json.RawMessage{}, blocks: map[uint64]json.RawMessage{}, seen: map[string][]byte{}, head: 92080021}
	for i := uint64(0); i <= 21; i++ {
		h := types.CopyHeader(&base)
		h.Number = new(big.Int).SetUint64(f.anchor + i)
		b, _ := json.Marshal(h)
		m := map[string]any{}
		json.Unmarshal(b, &m)
		m["hash"] = h.Hash()
		f.headers[f.anchor+i], _ = json.Marshal(m)
		user := common.BigToHash(new(big.Int).SetUint64(i + 1))
		amount := int64(-100)
		if i == 1 {
			amount = 100
		}
		m["transactions"] = []any{map[string]any{"hash": common.HexToHash("0x1234"), "type": "0x6a"}, map[string]any{"hash": user, "type": "0x2", "to": hookrRouter, "input": hexutil.Bytes(monitorInput(amount)), "value": "0x64"}}
		f.blocks[f.anchor+i], _ = json.Marshal(m)
		if i == 1 || i == 12 || i == 13 {
			f.logs = append(f.logs, &types.Log{Address: hookrManager, Topics: []common.Hash{swapTopic, hookrPoolID, topicAddress(hookrRouter)}, Data: ints(-100, 200, 1, 1, 1, 11000), BlockHash: h.Hash(), BlockNumber: f.anchor + i, TxHash: user, TxIndex: 1, Index: 0},
				&types.Log{Address: hookrRouter, Topics: []common.Hash{routerTopic, hookrPoolID, topicAddress(common.HexToAddress("0x11")), topicAddress(common.HexToAddress("0x22"))}, Data: ints(100, 200), BlockHash: h.Hash(), BlockNumber: f.anchor + i, TxHash: user, TxIndex: 1, Index: 1})
		}
	}
	return f
}
func (f *monitorFixture) rpc(t *testing.T) *RPCSource {
	client := &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		f.requests++
		var q struct {
			ID     uint64            `json:"id"`
			Method string            `json:"method"`
			Params []json.RawMessage `json:"params"`
		}
		json.NewDecoder(req.Body).Decode(&q)
		switch q.Method {
		case "eth_chainId":
			return respondJSON(q.ID, "0x1237"), nil
		case "eth_blockNumber":
			if f.regression {
				return respondJSON(q.ID, hexutil.EncodeUint64(f.anchor-1)), nil
			}
			return respondJSON(q.ID, hexutil.EncodeUint64(f.head)), nil
		case "eth_getBlockByNumber":
			var num string
			var full bool
			json.Unmarshal(q.Params[0], &num)
			json.Unmarshal(q.Params[1], &full)
			n := f.anchor
			if num != "latest" {
				n, _ = hexutil.DecodeUint64(num)
			}
			if full {
				f.fullBlockRequests++
				return respondJSON(q.ID, f.blocks[n]), nil
			}
			return respondJSON(q.ID, f.headers[n]), nil
		case "eth_getLogs":
			if f.failLogs {
				return nil, errors.New("synthetic no retry")
			}
			var filter struct {
				From string `json:"fromBlock"`
				To   string `json:"toBlock"`
			}
			json.Unmarshal(q.Params[0], &filter)
			a, _ := hexutil.DecodeUint64(filter.From)
			b, _ := hexutil.DecodeUint64(filter.To)
			if b < a || b-a >= 10 {
				t.Fatal("Free range exceeded")
			}
			f.ranges = append(f.ranges, [2]uint64{a, b})
			if f.afterLogsHead != 0 {
				f.head = f.afterLogsHead
			}
			logs := []*types.Log{}
			for _, l := range f.logs {
				if l.BlockNumber >= a && l.BlockNumber <= b {
					logs = append(logs, l)
				}
			}
			if f.removed && len(logs) > 0 {
				logs[0].Removed = true
			}
			if f.reverse {
				for i, j := 0, len(logs)-1; i < j; i, j = i+1, j-1 {
					logs[i], logs[j] = logs[j], logs[i]
				}
			}
			return respondJSON(q.ID, logs), nil
		}
		t.Fatal("unexpected monitor method", q.Method)
		return nil, nil
	})}
	rpc, e := NewRPCSource("https://example.invalid/v2/synthetic-secret", client, 1<<20, 64<<20)
	if e != nil {
		t.Fatal(e)
	}
	if e = rpc.Configure(60000, time.Now().Add(time.Minute), nil); e != nil {
		t.Fatal(e)
	}
	if rpc.ConfigureMonitoringCU() != nil {
		t.Fatal("meter setup")
	}
	rpc.meter = virtualMeter()
	return rpc
}
func (f *monitorFixture) run(t *testing.T) *HookrMonitorResult {
	rpc := f.rpc(t)
	began := rpc.meter.now()
	advance := rpc.meter.wait
	wait := func(ctx context.Context, d time.Duration) error {
		if rpc.meter.now().Sub(began) >= 5*time.Second {
			return context.DeadlineExceeded
		}
		return advance(ctx, d)
	}
	return runHookrScanner(context.Background(), rpc, func(n string, b []byte) error { f.seen[n] = common.CopyBytes(b); return nil }, wait, rpc.meter.now, true)
}
func TestMonitorContinuesPastTenBlocksAndLocksFirstExactInputBuy(t *testing.T) {
	f := newMonitorFixture(t)
	f.reverse = true
	o := f.run(t)
	if o.Terminal != "FIRST_ELIGIBLE_BUY_LOCKED" || o.Selected.BlockNumber != f.anchor+12 || o.ScientificNativeExecutions != 0 {
		t.Fatal(o)
	}
	if len(f.ranges) != 2 || f.ranges[0] != [2]uint64{f.anchor + 1, f.anchor + 10} || f.ranges[1] != [2]uint64{f.anchor + 11, f.anchor + 20} {
		t.Fatal("gaps or oversized logs", f.ranges)
	}
	if ValidateLockedHookrSelection(o.Selected) != nil || f.seen["ACTIVATION_BOUNDARY.json"] == nil || f.seen["LOCKED_SELECTION.json"] == nil {
		t.Fatal("selection not durable")
	}
	o.Selected.Subject.Ordinal = 2
	if ValidateLockedHookrSelection(o.Selected) == nil {
		t.Fatal("locked subject substituted")
	}
}
func TestMonitorExpiryDoesNotStartCaptureOrNative(t *testing.T) {
	f := newMonitorFixture(t)
	f.logs = nil
	o := f.run(t)
	if o.Terminal != "MONITOR_EXPIRED" || o.Selected != nil || o.ScientificNativeExecutions != 0 || f.seen["LOCKED_SELECTION.json"] != nil {
		t.Fatal(o)
	}
}
func TestMonitorErrorsDoNotSkipOrRetry(t *testing.T) {
	for _, kind := range []string{"rpc", "removed", "regression", "gap"} {
		f := newMonitorFixture(t)
		switch kind {
		case "rpc":
			f.failLogs = true
		case "removed":
			f.removed = true
		case "regression":
			f.regression = true
		case "gap":
			f.head = f.anchor + 101
		}
		o := f.run(t)
		if o.Terminal != "MONITOR_STOP" || o.Selected != nil || o.Cause == "" || o.ScientificNativeExecutions != 0 {
			t.Fatal(kind, o)
		}
		if kind == "rpc" && f.requests != 5 {
			t.Fatal("failed RPC retried", f.requests)
		}
	}
}
func TestInvalidLockedHandoffDoesNotSpendCaptureBudget(t *testing.T) {
	f := newMonitorFixture(t)
	rpc := f.rpc(t)
	writes := map[string][]byte{}
	o := RunLockedHookrProspective(context.Background(), rpc, func(n string, b []byte) error { writes[n] = b; return nil }, func(string, any) error { return nil }, time.Now().Add(time.Minute), &LockedHookrSelection{})
	if o.NativeAttempts != 0 || o.RpcRequests != 0 || o.Terminal != "RUNTIME_OR_RESOURCE_STOP" || f.requests != 0 {
		t.Fatal(o)
	}
	o = RunLockedHookrProspective(context.Background(), rpc, func(string, []byte) error { return nil }, func(string, any) error { return nil }, time.Now().Add(time.Minute), nil)
	if o.NativeAttempts != 0 || o.RpcRequests != 0 || f.requests != 0 || o.Cause != "LOCKED_SELECTION_REQUIRED_NO_LEGACY_FALLBACK" {
		t.Fatal("nil handoff started legacy selection", o)
	}
}

func TestLockedCaptureRevalidatesExactBlockAndCannotReselect(t *testing.T) {
	f := newMonitorFixture(t)
	monitor := f.run(t)
	if monitor.Selected == nil {
		t.Fatal(monitor)
	}
	// Empty selected-block response in a separately budgeted acquisition must
	// stop on its second request. It cannot scan another block or start native.
	count := 0
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		count++
		var q struct {
			ID     uint64 `json:"id"`
			Method string `json:"method"`
		}
		json.NewDecoder(req.Body).Decode(&q)
		if count == 1 && q.Method == "eth_chainId" {
			return respondJSON(q.ID, "0x1237"), nil
		}
		if count == 2 && q.Method == "eth_getBlockByNumber" {
			return respondJSON(q.ID, nil), nil
		}
		t.Fatal("unapproved reselection/extra acquisition")
		return nil, nil
	})}, 8<<20, 32<<20)
	rpc.Configure(64, time.Now().Add(time.Minute), nil)
	o := RunLockedHookrProspective(context.Background(), rpc, func(string, []byte) error { return nil }, func(string, any) error { return nil }, time.Now().Add(time.Minute), monitor.Selected)
	if count != 2 || o.RpcRequests != 2 || o.NativeAttempts != 0 || o.Terminal != "RUNTIME_OR_RESOURCE_STOP" {
		t.Fatal(o, count)
	}
}

func TestMonitorLagAfterRateLimitNeverLocksStaleTrade(t *testing.T) {
	for _, head := range []uint64{92080201, 92080020} {
		f := newMonitorFixture(t)
		f.afterLogsHead = head
		o := f.run(t)
		if o.Terminal != "MONITOR_STOP" || o.Selected != nil || f.seen["LOCKED_SELECTION.json"] != nil || len(f.ranges) != 1 {
			t.Fatal(o, f.ranges)
		}
		if o.Cause != "MONITOR_BACKLOG_OVER_100_NO_GAP_SKIP" && o.Cause != "HEAD_REGRESSION" {
			t.Fatal(o.Cause)
		}
	}
}
func TestMonitorEmptyRangesRemainConsecutive(t *testing.T) {
	f := newMonitorFixture(t)
	f.logs = nil
	o := f.run(t)
	want := [][2]uint64{{f.anchor + 1, f.anchor + 10}, {f.anchor + 11, f.anchor + 20}, {f.anchor + 21, f.anchor + 21}}
	if o.Terminal != "MONITOR_EXPIRED" || len(f.ranges) != 3 {
		t.Fatal(o, f.ranges)
	}
	for i, r := range f.ranges {
		if r != want[i] {
			t.Fatal("gap", f.ranges)
		}
	}
	if o.ScannedThrough != f.head {
		t.Fatal(o.ScannedThrough)
	}
}

func TestMonitorCanaryNeverSelectsPositiveLookingTrade(t *testing.T) {
	f := newMonitorFixture(t)
	rpc := f.rpc(t)
	began := rpc.meter.now()
	advance := rpc.meter.wait
	wait := func(ctx context.Context, d time.Duration) error {
		if rpc.meter.now().Sub(began) >= 5*time.Second {
			return context.DeadlineExceeded
		}
		return advance(ctx, d)
	}
	out := runHookrScanner(context.Background(), rpc, func(n string, b []byte) error { f.seen[n] = common.CopyBytes(b); return nil }, wait, rpc.meter.now, false)
	if out.Selected != nil || out.ScientificSelectionEnabled || out.MatchingLogs == 0 || f.fullBlockRequests != 0 || f.seen["LOCKED_SELECTION.json"] != nil {
		t.Fatal(out, f.fullBlockRequests)
	}
}
func TestMonitorStalledPartialRangeIsFlushedWithoutFutureQuery(t *testing.T) {
	f := newMonitorFixture(t)
	f.head = f.anchor + 7
	f.logs = nil
	out := f.run(t)
	if out.ScannedThrough != f.head || len(f.ranges) != 1 || f.ranges[0] != [2]uint64{f.anchor + 1, f.anchor + 7} {
		t.Fatal(out, f.ranges)
	}
}
