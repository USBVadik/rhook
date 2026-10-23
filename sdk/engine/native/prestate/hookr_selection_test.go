package prestate

import (
	"context"
	"encoding/json"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"math/big"
	"net/http"
	"testing"
	"time"
)

func TestHookrSelectionKeepsFirstOrdinalWithoutLookingAtBranch(t *testing.T) {
	h := &types.Header{Number: big.NewInt(92080001), Difficulty: big.NewInt(1)}
	tx1, tx2 := common.HexToHash("0x01"), common.HexToHash("0x02")
	mk := func(hash common.Hash, index uint) *types.Log {
		return &types.Log{Address: hookrManager, Topics: []common.Hash{swapTopic, hookrPoolID, topicAddress(hookrRouter)}, Data: ints(-100, 200, 1, 1, 1, 11000), BlockHash: h.Hash(), BlockNumber: h.Number.Uint64(), TxHash: hash, TxIndex: index}
	}
	route := func(hash common.Hash, index uint) *types.Log {
		return &types.Log{Address: hookrRouter, Topics: []common.Hash{routerTopic, hookrPoolID, topicAddress(common.HexToAddress("0x11")), topicAddress(common.HexToAddress("0x22"))}, Data: ints(100, 200), BlockHash: h.Hash(), BlockNumber: h.Number.Uint64(), TxHash: hash, TxIndex: index}
	}
	logs := []*types.Log{mk(tx2, 2), route(tx2, 2), mk(tx1, 1), route(tx1, 1)}
	raw, _ := json.Marshal(map[string]any{"transactions": []any{map[string]any{"hash": common.HexToHash("0x03"), "type": "0x6a"}, map[string]any{"hash": tx1, "type": "0x2", "to": hookrRouter}, map[string]any{"hash": tx2, "type": "0x2", "to": hookrRouter}}})
	count := 0
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		var q struct {
			ID     uint64                       `json:"id"`
			Method string                       `json:"method"`
			Params []map[string]json.RawMessage `json:"params"`
		}
		json.NewDecoder(req.Body).Decode(&q)
		if q.Method != "eth_getLogs" || len(q.Params) != 1 || q.Params[0]["blockHash"] == nil || q.Params[0]["fromBlock"] != nil {
			t.Fatal("unbounded or height-selected log scan")
		}
		count++
		return respondJSON(q.ID, logs), nil
	})}, 1<<20, 2<<20)
	rpc.Configure(2, time.Now().Add(time.Minute), nil)
	selected, reason, e := selectHookrTrade(context.Background(), rpc, raw, h)
	if e != nil || reason != "ELIGIBLE" || selected.Ordinal != 1 || selected.Hash != tx1 || count != 1 {
		t.Fatal(selected, reason, e, count)
	}
	logs[3].Removed = true
	if _, _, e = selectHookrTrade(context.Background(), rpc, raw, h); e == nil {
		t.Fatal("removed observation accepted")
	}
}

func TestFullNativeObservedBranchWithMultiGasMatchesResident(t *testing.T) {
	completeNativeSystemBlockFixture(t, true, "lp-changed")
}

func TestFullNativeObserverDistinguishesCaughtRevertFromLaterSibling(t *testing.T) {
	completeNativeSystemBlockFixture(t, false, "lp-changed", "nested-revert")
}
