package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/gorilla/websocket"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type eventHTTP struct {
	base  http.RoundTripper
	meter EventMeter
}

func (t eventHTTP) RoundTrip(q *http.Request) (*http.Response, error) {
	if q.GetBody == nil {
		return nil, errors.New("SINGLE_JSON_REQUEST_REQUIRED")
	}
	b, e := q.GetBody()
	if e != nil {
		return nil, e
	}
	raw, e := io.ReadAll(io.LimitReader(b, 65536))
	b.Close()
	if e != nil || len(raw) >= 65536 {
		return nil, errors.New("REQUEST_SIZE")
	}
	var request struct {
		Method string `json:"method"`
	}
	if json.Unmarshal(raw, &request) != nil {
		return nil, errors.New("REQUEST_ENCODING")
	}
	if t.meter.Scope == "coverage" {
		c := t.meter.Policy.Coverage
		if c == nil || q.URL.String() != c.Endpoint || (request.Method != "eth_chainId" && request.Method != "eth_getBlockByNumber" && request.Method != "eth_getLogs") {
			return nil, errors.New("COVERAGE_ENDPOINT_OR_METHOD")
		}
	}
	if e = t.meter.Reserve(q.Context(), request.Method); e != nil {
		if e.Error() != "ACQUISITION_DRAINING" {
			t.meter.Journal.Halt(e.Error())
		}
		return nil, e
	}
	r, e := t.base.RoundTrip(q)
	if e != nil {
		return nil, e
	}
	remaining := min(int64(8<<20), t.meter.RemainingBody())
	if remaining <= 0 || (r.ContentLength >= 0 && r.ContentLength > remaining) {
		r.Body.Close()
		t.meter.Journal.Halt("DECLARED_BODY_BUDGET")
		return nil, errors.New("DECLARED_BODY_BUDGET")
	}
	if r.Header.Get("Content-Encoding") != "" && r.Header.Get("Content-Encoding") != "identity" {
		r.Body.Close()
		return nil, errors.New("ENCODED_BODY_REJECTED")
	}
	if t.meter.Policy.Coverage != nil && r.ContentLength >= 0 {
		remaining = r.ContentLength
	}
	r.Body = &eventBody{ReadCloser: r.Body, meter: t.meter, remaining: remaining, completeAtLimit: r.ContentLength == remaining}
	return r, nil
}

type eventBody struct {
	io.ReadCloser
	meter            EventMeter
	remaining        int64
	completeAtLimit  bool
	credited, closed bool
	credit, used     int64
}

func (b *eventBody) Read(dst []byte) (int, error) {
	if b.remaining <= 0 {
		if b.completeAtLimit {
			return 0, io.EOF
		}
		b.meter.Journal.Halt("RESPONSE_BODY_BUDGET")
		return 0, errors.New("RESPONSE_BODY_BUDGET")
	}
	if int64(len(dst)) > b.remaining {
		dst = dst[:b.remaining]
	}
	if b.meter.Policy.Coverage != nil {
		state := b.meter.Journal.Snapshot()
		if state.Stop != "" || time.Now().UnixNano() >= state.Expires {
			return 0, errors.New("ACQUISITION_STOPPED_OR_EXPIRED")
		}
		if !b.credited {
			if e := b.meter.Body(b.remaining); e != nil {
				if e.Error() != "ACQUISITION_DRAINING" {
					b.meter.Journal.Halt(e.Error())
				}
				return 0, e
			}
			b.credit = b.remaining
			b.credited = true
		}
	}
	n, e := b.ReadCloser.Read(dst)
	b.used += int64(n)
	b.remaining -= int64(n)
	if n > 0 && b.meter.Policy.Coverage == nil {
		if x := b.meter.Body(int64(n)); x != nil {
			return n, x
		}
	}
	return n, e
}

// One durable pre-read reservation per response, not per io.ReadAll fragment.
// Unknown-length bodies reserve their maximum; unused credit is returned on close.
func (b *eventBody) Close() error {
	if b.closed {
		return nil
	}
	b.closed = true
	e := b.ReadCloser.Close()
	if b.meter.Policy.Coverage != nil && b.credited {
		if refund := b.meter.releaseBody(b.credit - b.used); refund != nil {
			b.meter.Journal.signalHardFailure("BODY_CREDIT_JOURNAL_FAILURE")
			b.meter.Journal.Halt("BODY_CREDIT_JOURNAL_FAILURE")
			return refund
		}
	}
	return e
}
func NewEventRPC(endpoint string, j *EventJournal, p EventPolicy, scope, prefix string, write WriteEvidence) (*RPCSource, error) {
	u, e := url.Parse(endpoint)
	valid := e == nil && u.Scheme == "https" && u.Host == "robinhood-mainnet.g.alchemy.com" && u.User == nil && u.RawQuery == "" && u.Fragment == "" && strings.HasPrefix(u.Path, "/v2/")
	if scope == "coverage" {
		valid = p.Coverage != nil && p.Coverage.Valid() && endpoint == p.Coverage.Endpoint
	}
	if !valid {
		return nil, errors.New("PINNED_ENDPOINT_REQUIRED")
	}
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true, DisableCompression: true, ForceAttemptHTTP2: false, MaxResponseHeaderBytes: 32768}
	m := EventMeter{j, p, scope}
	client := &http.Client{Transport: eventHTTP{transport, m}, CheckRedirect: func(req *http.Request, via []*http.Request) error { return errors.New("REDIRECT_REJECTED") }}
	total := p.CaseBytes
	if scope == "coverage" {
		total = p.Coverage.BodyBytes
	}
	r, e := NewRPCSource(endpoint, client, 8<<20, total)
	if e != nil {
		return nil, e
	}
	max := uint64(p.CaseRPC)
	if scope == "monitor" {
		max = uint64(p.MonitorRPC)
	}
	if scope == "coverage" {
		max = uint64(p.Coverage.RPC)
		if e = j.Update("COVERAGE_PROVIDER_BOUND", func(s *EventState) error {
			if s.CoverageProviderID != "" && s.CoverageProviderID != p.Coverage.ProviderID {
				return errors.New("COVERAGE_PROVIDER_CHANGED")
			}
			s.CoverageProviderID = p.Coverage.ProviderID
			return nil
		}); e != nil {
			return nil, e
		}
	}
	deadline := time.Unix(0, j.Snapshot().Expires)
	if scope != "monitor" && scope != "coverage" {
		deadline = minTime(time.Now().Add(180*time.Second), deadline)
		s := j.Snapshot()
		c := s.Cases[scope]
		native := s.Consumed && s.Lock != nil && s.Lock.Selection.BlockHash.Hex() == scope
		if p.Coverage != nil && !native && c.Deadline > 0 {
			deadline = minTime(deadline, time.Unix(0, c.Deadline))
		}
	}
	e = r.Configure(max, deadline, func(stage string, x RPCRecord) error {
		return EmitJSON(write, fmt.Sprintf("%s_%s_%03d.json", prefix, stage, x.Index), x)
	})
	return r, e
}
func eventHeader(ctx context.Context, rpc *RPCSource, n any) (json.RawMessage, *types.Header, error) {
	var raw json.RawMessage
	e := rpc.call(ctx, "eth_getBlockByNumber", []any{n, false}, &raw)
	if e != nil {
		return nil, nil, e
	}
	h, e := decodeHeader(raw)
	return raw, h, e
}
func ReconcileEventRange(ctx context.Context, rpc *RPCSource, c *EventController, to uint64) error {
	for {
		s := c.Journal.Snapshot()
		if s.Stop != "" {
			return errors.New(s.Stop)
		}
		if s.Lock != nil || s.Cursor >= to {
			return nil
		}
		if to-s.Cursor > uint64(c.Policy.MaximumGap) {
			return errors.New("GAP_EXCEEDS_FROZEN_BOUND")
		}
		end := min(to, s.Cursor+10)
		_, before, e := eventHeader(ctx, rpc, hexutil.EncodeUint64(s.Cursor))
		if e != nil {
			return e
		}
		if before.Hash() != s.CursorHash || before.Number.Uint64() != s.Cursor {
			return errors.New("CURSOR_REORG")
		}
		var logs []*types.Log
		e = rpc.call(ctx, "eth_getLogs", []any{map[string]any{"fromBlock": hexutil.EncodeUint64(s.Cursor + 1), "toBlock": hexutil.EncodeUint64(end), "address": []common.Address{hookrManager, hookrRouter}, "topics": []any{[]common.Hash{swapTopic, routerTopic}, hookrPoolID}}}, &logs)
		if e != nil {
			return e
		}
		_, tail, e := eventHeader(ctx, rpc, hexutil.EncodeUint64(end))
		if e != nil {
			return e
		}
		if tail.Number.Uint64() != end {
			return errors.New("RANGE_TAIL_NUMBER")
		}
		_, again, e := eventHeader(ctx, rpc, hexutil.EncodeUint64(s.Cursor))
		if e != nil {
			return e
		}
		if again.Hash() != s.CursorHash {
			return errors.New("CURSOR_REORG_DURING_COVERAGE")
		}
		if e = c.CompleteRange(ctx, s.Cursor+1, end, tail.Hash(), logs); e != nil {
			return e
		}
	}
}

type eventWSFrame struct {
	Version string          `json:"jsonrpc"`
	ID      int             `json:"id"`
	Method  string          `json:"method"`
	Result  json.RawMessage `json:"result"`
	Error   json.RawMessage `json:"error"`
	Params  struct {
		Subscription string     `json:"subscription"`
		Result       *types.Log `json:"result"`
	} `json:"params"`
}

type eventSocket interface {
	ReadMessage() (int, []byte, error)
	Close() error
}

func eventReadWS(conn eventSocket, m EventMeter, write WriteEvidence, secret string) (eventWSFrame, error) {
	var frame eventWSFrame
	if e := m.ReserveWSRead(); e != nil {
		return frame, e
	}
	typ, raw, e := conn.ReadMessage()
	if e != nil {
		if errors.Is(e, websocket.ErrReadLimit) {
			return frame, errors.New("WSS_READ_LIMIT")
		}
		return frame, errors.New("WSS_DISCONNECTED")
	}
	if typ != websocket.TextMessage || len(raw) > m.Policy.WSMessageBytes || json.Unmarshal(raw, &frame) != nil || frame.Version != "2.0" {
		return frame, errors.New("WSS_FRAME_ENCODING")
	}
	var decoded any
	json.Unmarshal(raw, &decoded)
	if containsCredential(decoded, secret) {
		return frame, errors.New("WSS_CREDENTIAL_ECHO")
	}
	if e = write(fmt.Sprintf("WS_%04d.json", m.Journal.Snapshot().WSReads), raw); e != nil {
		return frame, e
	}
	if len(frame.Error) > 0 && string(frame.Error) != "null" {
		return frame, errors.New("WSS_RPC_ERROR")
	}
	return frame, nil
}
func subscribeEventWS(ctx context.Context, endpoint string, m EventMeter, write WriteEvidence) (eventSocket, string, error) {
	u, e := url.Parse(endpoint)
	if e != nil {
		return nil, "", errors.New("WSS_ENDPOINT")
	}
	u.Scheme = "wss"
	if e = m.Reserve(ctx, "eth_subscribe"); e != nil {
		return nil, "", e
	}
	dial := websocket.Dialer{Proxy: nil, HandshakeTimeout: 10 * time.Second, EnableCompression: false, ReadBufferSize: 16384, WriteBufferSize: 4096}
	conn, response, e := dial.DialContext(ctx, u.String(), nil)
	if response != nil && response.Body != nil {
		response.Body.Close()
	}
	if e != nil {
		return nil, "", errors.New("WSS_DIAL_FAILED")
	}
	conn.SetReadLimit(int64(m.Policy.WSMessageBytes))
	conn.SetReadDeadline(minTime(time.Now().Add(10*time.Second), time.Unix(0, m.Journal.Snapshot().Expires)))
	conn.SetWriteDeadline(time.Now().Add(5 * time.Second))
	request := map[string]any{"jsonrpc": "2.0", "id": 1, "method": "eth_subscribe", "params": []any{"logs", map[string]any{"address": hookrManager, "topics": []common.Hash{swapTopic, hookrPoolID}}}}
	if e = conn.WriteJSON(request); e != nil {
		conn.Close()
		return nil, "", errors.New("WSS_SUBSCRIBE_WRITE")
	}
	frame, e := eventReadWS(conn, m, write, strings.TrimPrefix(u.Path, "/v2/"))
	var sub string
	if e == nil && (frame.ID != 1 || frame.Method != "" || json.Unmarshal(frame.Result, &sub) != nil || len(sub) == 0 || len(sub) > 256) {
		e = errors.New("WSS_SUBSCRIPTION_ACK")
	}
	if e != nil {
		conn.Close()
		return nil, "", e
	}
	conn.SetReadDeadline(time.Unix(0, m.Journal.Snapshot().Expires))
	return conn, sub, nil
}
