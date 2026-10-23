package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
)

func respondJSON(id uint64, result any) *http.Response {
	raw, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": id, "result": result})
	return &http.Response{StatusCode: 200, ContentLength: int64(len(raw)), Body: io.NopCloser(strings.NewReader(string(raw)))}
}
func TestSharedRPCRequestBudgetAndDurableIntent(t *testing.T) {
	calls := 0
	intents := 0
	client := &http.Client{Transport: roundTripFunc(func(q *http.Request) (*http.Response, error) {
		calls++
		if intents != calls {
			t.Fatal("wire before durable intent")
		}
		var req struct {
			ID uint64 `json:"id"`
		}
		json.NewDecoder(q.Body).Decode(&req)
		return respondJSON(req.ID, "0x1237"), nil
	})}
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", client, 1000, 10000)
	rpc.Configure(2, time.Now().Add(time.Minute), func(stage string, r RPCRecord) error {
		if stage == "INTENT" {
			intents++
		}
		return nil
	})
	var v string
	if e := rpc.call(context.Background(), "eth_chainId", []any{}, &v); e != nil {
		t.Fatal(e)
	}
	// Same budget object after capture; no new allowance at hydration boundary.
	if e := rpc.call(context.Background(), "eth_chainId", []any{}, &v); e != nil {
		t.Fatal(e)
	}
	if e := rpc.call(context.Background(), "eth_chainId", []any{}, &v); e == nil {
		t.Fatal("third request sent")
	}
	if calls != 2 || intents != 2 {
		t.Fatalf("unexpected accounting %d %d", calls, intents)
	}
}
func TestFailedIntentPreventsHTTPDispatch(t *testing.T) {
	calls := 0
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) { calls++; return nil, errors.New("unexpected") })}, 1000, 10000)
	rpc.Configure(64, time.Now().Add(time.Minute), func(stage string, r RPCRecord) error {
		if stage == "INTENT" {
			return errors.New("synthetic disk failure")
		}
		return nil
	})
	_, e := rpc.GetCode(context.Background(), makeFixture(t).checkpoint, addrA)
	if e == nil || calls != 0 {
		t.Fatal("request escaped failed journal")
	}
}
func TestResponseCapNeverReadsOnePastRemainingBudget(t *testing.T) {
	calls := 0
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 200, ContentLength: -1, Body: io.NopCloser(strings.NewReader(strings.Repeat("x", 1000)))}, nil
	})}, 100, 100)
	_, e := rpc.GetCode(context.Background(), makeFixture(t).checkpoint, addrA)
	if e == nil {
		t.Fatal("truncated reply accepted")
	}
	_, _, _, n := rpc.Transcript()
	if n != 100 {
		t.Fatalf("read past authorized bytes: %d", n)
	}
	rpc.GetCode(context.Background(), makeFixture(t).checkpoint, addrA)
	if calls != 1 {
		t.Fatal("poisoned source retried")
	}
}
func TestEscapedCredentialEchoNeverEntersEvidence(t *testing.T) {
	secret := "secret-fixture-only"
	body := `{"jsonrpc":"2.0","id":1,"result":"\u0073ecret-fixture-only"}`
	rpc, _ := NewRPCSource("https://example.invalid/v2/"+secret, &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, ContentLength: int64(len(body)), Body: io.NopCloser(strings.NewReader(body))}, nil
	})}, 1000, 10000)
	_, e := rpc.GetCode(context.Background(), makeFixture(t).checkpoint, addrA)
	if e == nil {
		t.Fatal("credential echo admitted")
	}
	_, raw, _, _ := rpc.Transcript()
	if strings.Contains(string(raw), secret) || strings.Contains(string(raw), "ecret-fixture-only") {
		t.Fatal("escaped credential leaked")
	}
}
func TestProductionTransportDisablesReuseCompressionAndRedirect(t *testing.T) {
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", nil, 1000, 10000)
	tr := rpc.client.Transport.(*http.Transport)
	if !tr.DisableKeepAlives || !tr.DisableCompression || tr.Proxy != nil || tr.MaxResponseHeaderBytes != 32768 {
		t.Fatal("production transport permits hidden extra requests/unbounded header")
	}
	if rpc.client.CheckRedirect(nil, nil) == nil {
		t.Fatal("redirect allowed")
	}
}
func TestNoEligibleTargetStopsAfterExactlyTenConsecutiveBlocks(t *testing.T) {
	_, parent, _, _ := inputFixture(t)
	var ph types.Header
	json.Unmarshal(parent, &ph)
	previous := ph.Hash()
	blocks := map[string]json.RawMessage{}
	for i := uint64(1); i <= 10; i++ {
		h := types.CopyHeader(&ph)
		h.Number = new(big.Int).SetUint64(ph.Number.Uint64() + i)
		h.ParentHash = previous
		previous = h.Hash()
		raw, _ := json.Marshal(h)
		var object map[string]any
		json.Unmarshal(raw, &object)
		object["hash"] = h.Hash()
		object["transactions"] = []any{map[string]any{"hash": common.Hash{}, "type": "0x6a"}}
		blocks[hexutil.EncodeUint64(h.Number.Uint64())], _ = json.Marshal(object)
	}
	observations := 0
	rpc, _ := NewRPCSource("https://example.invalid/v2/synthetic-secret", &http.Client{Transport: roundTripFunc(func(q *http.Request) (*http.Response, error) {
		var req struct {
			ID     uint64            `json:"id"`
			Method string            `json:"method"`
			Params []json.RawMessage `json:"params"`
		}
		json.NewDecoder(q.Body).Decode(&req)
		if req.Method == "eth_chainId" {
			return respondJSON(req.ID, "0x1237"), nil
		}
		var height string
		json.Unmarshal(req.Params[0], &height)
		if height == "latest" {
			return respondJSON(req.ID, json.RawMessage(parent)), nil
		}
		observations++
		raw, ok := blocks[height]
		if !ok {
			t.Fatal("outside window or repeated height")
		}
		delete(blocks, height)
		return respondJSON(req.ID, raw), nil
	})}, 8<<20, 32<<20)
	rpc.Configure(64, time.Now().Add(time.Minute), nil)
	out := RunProspective(context.Background(), rpc, func(string, []byte) error { return nil }, func(string, any) error { return nil }, func(time.Duration) {}, time.Now().Add(time.Minute))
	if out.Terminal != "PROSPECTIVE_TARGET_NOT_FOUND" || out.NativeAttempts != 0 || observations != 10 || out.RpcRequests != 12 {
		t.Fatalf("selection escaped frozen window: %+v", out)
	}
}
