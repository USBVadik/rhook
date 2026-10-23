package prestate

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func TestRPCNeverRequestsLatestAndRejectsOversizedBody(t *testing.T) {
	f := makeFixture(t)
	requests := 0
	client := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		requests++
		var q struct {
			ID     int               `json:"id"`
			Params []json.RawMessage `json:"params"`
		}
		json.NewDecoder(r.Body).Decode(&q)
		if string(q.Params[len(q.Params)-1]) != "\"0x7b\"" {
			t.Fatal("unpinned state request")
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(strings.Repeat("x", 1000)))}, nil
	})}
	rpc, e := NewRPCSource("https://example.invalid/v2/fixture", client, 100, 1000)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = rpc.GetProof(context.Background(), f.checkpoint, addrA, nil); e == nil {
		t.Fatal("oversized wire body accepted")
	}
	if requests != 1 {
		t.Fatal("RPC retried")
	}
}
func TestRPCErrorsDoNotExposeEndpointCredential(t *testing.T) {
	rpc, e := NewRPCSource("https://example.invalid/v2/secret-fixture-only", &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) { return nil, context.DeadlineExceeded })}, 100, 1000)
	if e != nil {
		t.Fatal(e)
	}
	_, e = rpc.GetCode(context.Background(), makeFixture(t).checkpoint, addrA)
	if e == nil || strings.Contains(e.Error(), "secret-fixture-only") {
		t.Fatalf("transport secret leaked: %v", e)
	}
}

func TestWireBudgetStopsBeforeAnotherTransport(t *testing.T) {
	body := `{"jsonrpc":"2.0","id":1,"result":"0x00"}`
	calls := 0
	client := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 200, ContentLength: int64(len(body)), Body: io.NopCloser(strings.NewReader(body))}, nil
	})}
	rpc, e := NewRPCSource("https://example.invalid/v2/fixture", client, int64(len(body)), int64(len(body)))
	if e != nil {
		t.Fatal(e)
	}
	if _, e = rpc.GetCode(context.Background(), makeFixture(t).checkpoint, addrA); e != nil {
		t.Fatal(e)
	}
	if _, e = rpc.GetCode(context.Background(), makeFixture(t).checkpoint, addrA); e == nil {
		t.Fatal("exhausted budget accepted")
	}
	if calls != 1 {
		t.Fatalf("sent transport after budget exhausted: %d", calls)
	}
}
