package prestate

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
)

type RPCRecord struct {
	MonitoringDispatchNs    int64           `json:"monitoringDispatchNs,omitempty"`
	MonitoringHTTPBodyNs    int64           `json:"monitoringHTTPBodyNs,omitempty"`
	MonitoringCUWaitNs      int64           `json:"monitoringCUWaitNs,omitempty"`
	MonitoringIntentWriteNs int64           `json:"monitoringIntentWriteNs,omitempty"`
	EstimatedCU             uint64          `json:"estimatedCU,omitempty"`
	CumulativeEstimatedCU   uint64          `json:"cumulativeEstimatedCU,omitempty"`
	MonitoringReservationNs int64           `json:"monitoringReservationNs,omitempty"`
	Index                   uint64          `json:"index"`
	Method                  string          `json:"method"`
	Params                  json.RawMessage `json:"params"`
	Status                  int             `json:"httpStatus"`
	ResponseBytes           int64           `json:"responseBytesRead"`
	Body                    string          `json:"sanitizedBody"`
	Error                   string          `json:"error,omitempty"`
	CredentialEcho          bool            `json:"credentialEcho"`
	TransportIncomplete     bool            `json:"transportIncomplete"`
}
type RPCSource struct {
	monitorTiming            MonitorTiming
	meter                    *monitorMeter
	endpoint                 string
	secret                   string
	client                   *http.Client
	maxBody, maxTotal, total int64
	maxRequests              uint64
	deadline                 time.Time
	perCall                  time.Duration
	record                   func(string, RPCRecord) error
	records                  []RPCRecord
	mu                       sync.Mutex
	id                       uint64
	fatal                    error
}

func NewRPCSource(endpoint string, client *http.Client, maxBody, maxTotal int64) (*RPCSource, error) {
	u, e := url.Parse(endpoint)
	if e != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.Fragment != "" || u.RawQuery != "" || maxBody <= 0 || maxTotal < maxBody {
		return nil, errors.New("INVALID_RPC_SOURCE")
	}
	if client == nil {
		client = &http.Client{Transport: &http.Transport{Proxy: nil, DisableKeepAlives: true, DisableCompression: true, ForceAttemptHTTP2: false, MaxResponseHeaderBytes: 32768}}
	}
	copied := *client
	copied.CheckRedirect = func(*http.Request, []*http.Request) error { return errors.New("REDIRECT_REFUSED") }
	return &RPCSource{endpoint: endpoint, secret: strings.TrimPrefix(u.Path, "/v2/"), client: &copied, maxBody: maxBody, maxTotal: maxTotal, maxRequests: 64, perCall: 15 * time.Second}, nil
}
func (r *RPCSource) Configure(max uint64, deadline time.Time, record func(string, RPCRecord) error) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.id != 0 || max == 0 || deadline.IsZero() {
		return errors.New("RPC_CONFIGURATION_LIFECYCLE")
	}
	r.maxRequests = max
	r.deadline = deadline
	r.record = record
	return nil
}

var rpcURL = regexp.MustCompile(`https?://[^\s"<>]+`)

func (r *RPCSource) callRaw(ctx context.Context, method string, params []any, allowNull bool) (answer json.RawMessage, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.fatal != nil {
		return nil, r.fatal
	}
	if r.id >= r.maxRequests {
		r.fatal = errors.New("RPC_REQUEST_BUDGET_EXHAUSTED")
		return nil, r.fatal
	}
	if r.total >= r.maxTotal {
		r.fatal = errors.New("RPC_WIRE_BUDGET_EXHAUSTED")
		return nil, r.fatal
	}
	if !r.deadline.IsZero() && !time.Now().Before(r.deadline) {
		r.fatal = errors.New("RPC_OPERATION_DEADLINE")
		return nil, r.fatal
	}
	switch method {
	case "eth_blockNumber", "eth_getLogs", "eth_chainId", "eth_getBlockByNumber", "eth_getRawTransactionByHash", "debug_executionWitness", "eth_getProof", "eth_getCode":
	default:
		return nil, errors.New("RPC_METHOD_NOT_ADMITTED")
	}
	var pipelineBegan time.Time
	var previousWaitNs int64
	if r.meter != nil {
		pipelineBegan = r.meter.now()
		previousWaitNs = r.meter.waitNs
		defer func() { r.monitorTiming.RPCPipelineNs += r.meter.now().Sub(pipelineBegan).Nanoseconds() }()
	}
	var cu uint64
	var reservedNs int64
	if r.meter != nil {
		waitCtx := ctx
		cancelWait := func() {}
		if !r.deadline.IsZero() {
			waitCtx, cancelWait = context.WithDeadline(ctx, r.deadline)
		}
		cu, reservedNs, err = r.meter.acquire(waitCtx, method)
		cancelWait()
		if err != nil {
			r.fatal = err
			return nil, err
		}
		defer r.meter.complete()
	}
	end := time.Now().Add(r.perCall)
	if !r.deadline.IsZero() && r.deadline.Before(end) {
		end = r.deadline
	}
	ctx, cancel := context.WithDeadline(ctx, end)
	defer cancel()
	if ctx.Err() != nil {
		r.fatal = errors.New("RPC_DEADLINE_EXPIRED")
		return nil, r.fatal
	}
	r.id++
	qparams, _ := json.Marshal(params)
	rec := RPCRecord{Index: r.id, Method: method, Params: qparams, EstimatedCU: cu, MonitoringReservationNs: reservedNs}
	if r.meter != nil {
		rec.CumulativeEstimatedCU = r.meter.spent
		rec.MonitoringCUWaitNs = r.meter.waitNs - previousWaitNs
	}
	defer func() {
		if err != nil {
			rec.Error = err.Error()
			r.fatal = err
		}
		r.records = append(r.records, rec)
		if r.record != nil {
			var before time.Time
			if r.meter != nil {
				before = r.meter.now()
			}
			if e := r.record("RESPONSE", rec); e != nil {
				err = errors.New("RPC_RESPONSE_RECORD_FAILURE")
				r.fatal = err
				answer = nil
			}
			if r.meter != nil {
				r.monitorTiming.ResponseWriteNs += r.meter.now().Sub(before).Nanoseconds()
			}
		}
	}()
	if r.record != nil {
		var before time.Time
		if r.meter != nil {
			before = r.meter.now()
		}
		if e := r.record("INTENT", rec); e != nil {
			return nil, errors.New("RPC_INTENT_RECORD_FAILURE")
		}
		if r.meter != nil {
			rec.MonitoringIntentWriteNs = r.meter.now().Sub(before).Nanoseconds()
			r.monitorTiming.IntentWriteNs += rec.MonitoringIntentWriteNs
		}
	}
	request, _ := json.Marshal(struct {
		Version string `json:"jsonrpc"`
		ID      uint64 `json:"id"`
		Method  string `json:"method"`
		Params  []any  `json:"params"`
	}{"2.0", r.id, method, params})
	q, e := http.NewRequestWithContext(ctx, http.MethodPost, r.endpoint, bytes.NewReader(request))
	if e != nil {
		return nil, errors.New("RPC_REQUEST_INVALID")
	}
	q.Header.Set("Content-Type", "application/json")
	var dispatch time.Time
	if r.meter != nil {
		dispatch = r.meter.now()
		rec.MonitoringDispatchNs = dispatch.Sub(r.meter.began).Nanoseconds()
	}
	response, e := r.client.Do(q)
	if e != nil {
		rec.TransportIncomplete = true
		return nil, errors.New("RPC_TRANSPORT_FAILURE")
	}
	defer response.Body.Close()
	rec.Status = response.StatusCode
	cap := min(r.maxBody, r.maxTotal-r.total)
	raw, e := io.ReadAll(io.LimitReader(response.Body, cap))
	if r.meter != nil {
		rec.MonitoringHTTPBodyNs = r.meter.now().Sub(dispatch).Nanoseconds()
		r.monitorTiming.HTTPBodyNs += rec.MonitoringHTTPBodyNs
	}
	r.total += int64(len(raw))
	rec.ResponseBytes = int64(len(raw))
	rec.CredentialEcho = len(r.secret) >= 8 && bytes.Contains(raw, []byte(r.secret))
	var decoded any
	if json.Unmarshal(raw, &decoded) == nil && containsCredential(decoded, r.secret) {
		rec.CredentialEcho = true
	}
	text := string(raw)
	if len(r.secret) >= 8 {
		text = strings.ReplaceAll(text, r.secret, "[REDACTED]")
	}
	rec.Body = rpcURL.ReplaceAllString(text, "[URL_REDACTED]")
	if rec.CredentialEcho {
		rec.Body = "[REDACTED_CREDENTIAL_ECHO_RESPONSE]"
	}
	if e != nil {
		rec.TransportIncomplete = true
		return nil, errors.New("RPC_BODY_READ_FAILURE")
	}
	if int64(len(raw)) == cap && response.ContentLength != cap {
		return nil, errors.New("RPC_WIRE_BODY_LIMIT")
	}
	if ctx.Err() != nil {
		r.fatal = errors.New("RPC_DEADLINE_EXPIRED")
		return nil, r.fatal
	}
	if rec.CredentialEcho {
		return nil, errors.New("RPC_CREDENTIAL_ECHO_REJECTED")
	}
	if response.StatusCode != 200 {
		return nil, errors.New("RPC_HTTP_FAILURE")
	}
	var reply struct {
		Version string          `json:"jsonrpc"`
		ID      uint64          `json:"id"`
		Result  json.RawMessage `json:"result"`
		Error   json.RawMessage `json:"error"`
	}
	if json.Unmarshal(raw, &reply) != nil || reply.Version != "2.0" || reply.ID != r.id || len(reply.Result) == 0 || (len(reply.Error) > 0 && !bytes.Equal(reply.Error, []byte("null"))) {
		return nil, errors.New("RPC_INVALID_RESPONSE")
	}
	if !allowNull && bytes.Equal(reply.Result, []byte("null")) {
		return nil, errors.New("RPC_RESULT_UNAVAILABLE")
	}
	return reply.Result, nil
}
func (r *RPCSource) call(ctx context.Context, method string, params []any, target any) error {
	raw, e := r.callRaw(ctx, method, params, false)
	if e != nil {
		return e
	}
	if json.Unmarshal(raw, target) != nil {
		return errors.New("RPC_RESULT_ENCODING")
	}
	return nil
}
func (r *RPCSource) GetProof(ctx context.Context, c Checkpoint, a common.Address, slots []common.Hash) (*RPCProof, error) {
	if slots == nil {
		slots = []common.Hash{}
	}
	var p RPCProof
	e := r.call(ctx, "eth_getProof", []any{a, slots, hexutil.EncodeUint64(c.BlockNumber)}, &p)
	return &p, e
}
func (r *RPCSource) GetCode(ctx context.Context, c Checkpoint, a common.Address) ([]byte, error) {
	var code hexutil.Bytes
	e := r.call(ctx, "eth_getCode", []any{a, hexutil.EncodeUint64(c.BlockNumber)}, &code)
	return code, e
}
func (r *RPCSource) Transcript() (string, []byte, uint64, int64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	raw, _ := json.Marshal(r.records)
	h := sha256.Sum256(append([]byte("rhook/prospective-rpc-transcript/0.1\n"), raw...))
	return hex.EncodeToString(h[:]), raw, r.id, r.total
}

func containsCredential(v any, secret string) bool {
	if len(secret) < 8 {
		return false
	}
	switch x := v.(type) {
	case string:
		return strings.Contains(x, secret)
	case []any:
		for _, y := range x {
			if containsCredential(y, secret) {
				return true
			}
		}
	case map[string]any:
		for k, y := range x {
			if strings.Contains(k, secret) || containsCredential(y, secret) {
				return true
			}
		}
	}
	return false
}
