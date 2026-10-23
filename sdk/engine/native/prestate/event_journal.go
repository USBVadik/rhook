package prestate

// Small local durable journal and budget accounting. No scientific authority is
// created here; live authority is a separately provided trusted-local decision.
import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

type EventPolicy struct {
	Version                                                                           string `json:"version"`
	Seconds, MonitorRPC, WSMessages, WSMessageBytes, Reconnects, MaximumGap, Captures int
	CaptureRPC, CaseRPC, CaptureSeconds, NativeSeconds, NativeCPU                     int
	BillingCU, HTTPBytes, WSBytes, CaseBytes, StorageBytes                            int64
	Coverage                                                                          *QuietCoveragePolicy `json:"coverage,omitempty"`
}

func DefaultEventPolicy() EventPolicy {
	return EventPolicy{"RHOOK_EVENT_CAPTURE_01", 10800, 256, 128, 16384, 3, 1000, 3, 40, 64, 60, 120, 120, 125000, 32 << 20, 2 << 20, 32 << 20, 512 << 20, nil}
}
func (p EventPolicy) Commitment() string {
	b, _ := json.Marshal(p)
	return Digest("rhook/event-policy/0.1", b)
}

type EventCase struct {
	Hash                      common.Hash
	Number                    uint64
	Status, PackageSHA, Error string
	RPC                       int
	Bytes                     int64
	Began, Deadline           int64 `json:",omitempty"`
}
type EventLock struct {
	Selection                                LockedHookrSelection
	Observation                              *ObservedSelectionBinding `json:",omitempty"`
	Checkpoint                               Checkpoint
	PackageSHA, LogsSHA, Policy, Acquisition string
}
type EventRate struct {
	At      int64
	Cost    int64
	Witness bool
}
type EventSeen struct {
	BlockNumber uint64
	BlockHash   common.Hash
	EncodedSHA  string
}
type EventState struct {
	Observed                                     *ObservedDeliveryState `json:",omitempty"`
	Operation, Policy                            string
	AcquisitionAuthoritySHA, ScienceAuthoritySHA string
	Began, Expires                               int64
	Activation, Cursor                           uint64
	ActivationHash, CursorHash                   common.Hash
	Seen                                         map[string]EventSeen
	Cases                                        map[string]EventCase
	Lock                                         *EventLock
	Connected                                    bool
	Consumed                                     bool
	Stop                                         string
	MonitorRPC, WSReads, Reconnects              int
	Billing, HTTPBytes, WSBytes, StorageBytes    int64
	Rates                                        []EventRate
	CoverageProviderID                           string `json:",omitempty"`
	CoverageRPC                                  int    `json:",omitempty"`
	CoverageBytes                                int64  `json:",omitempty"`
	Draining                                     bool   `json:",omitempty"`
	DrainReason                                  string `json:",omitempty"`
}
type eventRow struct {
	Sequence       int
	Previous, Kind string
	State          EventState
	Hash           string
}
type EventJournal struct {
	mu          sync.Mutex
	file        *os.File
	dir         string
	seq         int
	previous    string
	state       EventState
	hardCancel  func()
	fatalReason string
	guardFatal  bool
}

func (j *EventJournal) SetHardCancel(cancel func()) {
	j.mu.Lock()
	j.hardCancel = cancel
	j.mu.Unlock()
}

func OpenEventJournal(dir, operation string, p EventPolicy) (*EventJournal, error) {
	if e := os.MkdirAll(dir, 0700); e != nil {
		return nil, e
	}
	if s, e := os.Lstat(dir); e != nil || s.Mode()&os.ModeSymlink != 0 {
		return nil, errors.New("JOURNAL_DIRECTORY")
	}
	path := filepath.Join(dir, "journal.jsonl")
	if s, e := os.Lstat(path); e == nil && s.Mode()&os.ModeSymlink != 0 {
		return nil, errors.New("JOURNAL_SYMLINK")
	}
	f, e := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0600)
	if e != nil {
		return nil, e
	}
	fail := func(e error) (*EventJournal, error) { f.Close(); return nil, e }
	if e = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		return fail(errors.New("JOURNAL_OWNED"))
	}
	j := &EventJournal{file: f, dir: dir, guardFatal: p.Coverage != nil, state: EventState{Operation: operation, Policy: p.Commitment(), Seen: map[string]EventSeen{}, Cases: map[string]EventCase{}}}
	s := bufio.NewScanner(f)
	s.Buffer(make([]byte, 65536), 1<<20)
	for s.Scan() {
		var x eventRow
		if json.Unmarshal(s.Bytes(), &x) != nil || x.Sequence != j.seq+1 || x.Previous != j.previous {
			return fail(errors.New("JOURNAL_CORRUPT"))
		}
		h := x.Hash
		x.Hash = ""
		b, _ := json.Marshal(x)
		if h != Digest("rhook/event-journal/0.1", b) {
			return fail(errors.New("JOURNAL_HASH"))
		}
		if x.State.Operation != operation || x.State.Policy != p.Commitment() {
			return fail(errors.New("JOURNAL_POLICY_OR_OPERATION"))
		}
		j.seq = x.Sequence
		j.previous = h
		j.state = x.State
	}
	if s.Err() != nil {
		return fail(errors.New("JOURNAL_READ"))
	}
	info, _ := f.Stat()
	if info.Size() > 64<<20 {
		return fail(errors.New("JOURNAL_SIZE"))
	}
	if info.Size() > 0 {
		last := make([]byte, 1)
		f.ReadAt(last, info.Size()-1)
		if last[0] != '\n' {
			return fail(errors.New("JOURNAL_PARTIAL_TAIL_UNCERTAIN"))
		}
	}
	_, e = f.Seek(0, io.SeekEnd)
	if e != nil {
		return fail(e)
	}
	return j, nil
}
func (j *EventJournal) Close() { j.file.Close() }
func (j *EventJournal) Marker(name string, value any) (err error) {
	defer func() {
		if err != nil {
			j.signalHardFailure("MARKER_DURABILITY_FAILURE")
		}
	}()
	if j.guardFatal && j.FatalReason() != "" {
		return errors.New("JOURNAL_FATAL_BEFORE_MARKER")
	}
	if filepath.Base(name) != name {
		return errors.New("MARKER_NAME")
	}
	raw, e := json.Marshal(value)
	if e != nil {
		return e
	}
	f, e := os.OpenFile(filepath.Join(j.dir, name), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return errors.New("MARKER_EXISTS_OR_UNAVAILABLE")
	}
	_, e = f.Write(append(raw, '\n'))
	if e == nil {
		e = f.Sync()
	}
	f.Close()
	if e != nil {
		return e
	}
	d, e := os.Open(j.dir)
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}
func (j *EventJournal) CheckMarkers() error {
	s := j.Snapshot()
	for _, name := range []string{"FIRST_ELIGIBLE_LOCK.json", "SCIENTIFIC_CONSUMED.json"} {
		b, e := os.ReadFile(filepath.Join(j.dir, name))
		if e != nil {
			if !os.IsNotExist(e) {
				return errors.New("MARKER_READ_UNCERTAIN")
			}
			if (name == "FIRST_ELIGIBLE_LOCK.json" && s.Lock != nil) || (name == "SCIENTIFIC_CONSUMED.json" && s.Consumed) {
				return errors.New("JOURNAL_MARKER_MISSING")
			}
			continue
		}
		if s.Lock == nil {
			return errors.New("MARKER_WITHOUT_JOURNAL_LOCK_UNCERTAIN")
		}
		if name == "FIRST_ELIGIBLE_LOCK.json" {
			var lock EventLock
			if json.Unmarshal(b, &lock) != nil {
				return errors.New("LOCK_MARKER_ENCODING")
			}
			x, _ := json.Marshal(s.Lock)
			y, _ := json.Marshal(lock)
			if string(x) != string(y) {
				return errors.New("LOCK_MARKER_MISMATCH")
			}
		}
		if name == "SCIENTIFIC_CONSUMED.json" {
			if !s.Consumed {
				return errors.New("CONSUMPTION_MARKER_WITHOUT_JOURNAL_UNCERTAIN")
			}
			var marker struct {
				AcquisitionAuthoritySHA, ScienceAuthoritySHA string
				Lock                                         *EventLock
				RetryAllowed                                 *bool
			}
			if json.Unmarshal(b, &marker) != nil || marker.Lock == nil || marker.RetryAllowed == nil || *marker.RetryAllowed || marker.AcquisitionAuthoritySHA != s.AcquisitionAuthoritySHA || marker.ScienceAuthoritySHA != s.ScienceAuthoritySHA {
				return errors.New("CONSUMPTION_MARKER_BINDING")
			}
			a, _ := json.Marshal(marker.Lock)
			b, _ := json.Marshal(s.Lock)
			if string(a) != string(b) {
				return errors.New("CONSUMPTION_MARKER_LOCK_MISMATCH")
			}
		}
	}
	return nil
}
func (j *EventJournal) Snapshot() EventState {
	j.mu.Lock()
	defer j.mu.Unlock()
	b, _ := json.Marshal(j.state)
	var s EventState
	json.Unmarshal(b, &s)
	return s
}
func (j *EventJournal) Update(kind string, change func(*EventState) error) (err error) {
	j.mu.Lock()
	physical := false
	defer func() {
		// Latch under the same mutex as admissions: no waiting transaction may
		// slip between a failed physical write and its hard cancellation.
		if physical && err != nil && j.fatalReason == "" {
			j.fatalReason = "JOURNAL_DURABILITY_FAILURE"
		}
		j.mu.Unlock()
		if physical && err != nil {
			j.cancelHard()
		}
	}()
	if j.guardFatal && j.fatalReason != "" && kind != "STOP" {
		return errors.New("JOURNAL_FATAL:" + j.fatalReason)
	}
	raw, _ := json.Marshal(j.state)
	var s EventState
	json.Unmarshal(raw, &s)
	if e := change(&s); e != nil {
		return e
	}
	physical = true
	row := eventRow{j.seq + 1, j.previous, kind, s, ""}
	raw, _ = json.Marshal(row)
	row.Hash = Digest("rhook/event-journal/0.1", raw)
	raw, _ = json.Marshal(row)
	raw = append(raw, '\n')
	if len(raw) >= 1<<20 {
		return errors.New("JOURNAL_ROW_SIZE")
	}
	st, e := j.file.Stat()
	if e != nil || st.Size()+int64(len(raw)) > 64<<20 {
		return errors.New("JOURNAL_SIZE")
	}
	if _, e = j.file.Write(raw); e != nil {
		return e
	}
	if e = j.file.Sync(); e != nil {
		return e
	}
	d, e := os.Open(j.dir)
	if e != nil {
		return e
	}
	e = d.Sync()
	d.Close()
	if e != nil {
		return e
	}
	j.seq++
	j.previous = row.Hash
	j.state = s
	return nil
}
func (j *EventJournal) cancelHard() {
	j.mu.Lock()
	cancel := j.hardCancel
	j.mu.Unlock()
	if cancel != nil {
		cancel()
	}
}
func (j *EventJournal) signalHardFailure(reason string) {
	j.mu.Lock()
	if j.fatalReason == "" {
		j.fatalReason = reason
	}
	j.mu.Unlock()
	j.cancelHard()
}
func (j *EventJournal) FatalReason() string { j.mu.Lock(); defer j.mu.Unlock(); return j.fatalReason }
func (j *EventJournal) Halt(reason string) error {
	err := j.Update("STOP", func(s *EventState) error {
		if s.Stop == "" {
			s.Stop = reason
		}
		return nil
	})
	j.signalHardFailure(reason)
	return err
}
func eventID(l *types.Log) string {
	return fmt.Sprintf("%s/%s/%d", l.BlockHash.Hex(), l.TxHash.Hex(), l.Index)
}
func eventCaseID(l *types.Log) string { return l.BlockHash.Hex() }
func eventTarget(l *types.Log) bool {
	return l != nil && l.Address == hookrManager && len(l.Topics) >= 2 && l.Topics[0] == swapTopic && l.Topics[1] == hookrPoolID
}

func EventWriter(j *EventJournal, p EventPolicy, sub string) WriteEvidence {
	return func(name string, raw []byte) (err error) {
		defer func() {
			if p.Coverage != nil && err != nil {
				j.signalHardFailure("EVIDENCE_WRITE_FAILURE")
				j.Halt("EVIDENCE_WRITE_FAILURE")
			}
		}()
		if filepath.Base(name) != name || strings.Contains(name, "..") || len(raw) > 64<<20 {
			return errors.New("EVIDENCE_NAME_OR_SIZE")
		}
		if e := j.Update("WRITE_RESERVED", func(s *EventState) error {
			if s.StorageBytes+int64(len(raw)) > p.StorageBytes {
				return errors.New("STORAGE_BUDGET")
			}
			s.StorageBytes += int64(len(raw))
			return nil
		}); e != nil {
			return e
		}
		dir := filepath.Join(j.dir, sub)
		if e := os.MkdirAll(dir, 0700); e != nil {
			return e
		}
		f, e := os.OpenFile(filepath.Join(dir, name), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if e != nil {
			return e
		}
		_, e = f.Write(raw)
		if e == nil {
			e = f.Sync()
		}
		f.Close()
		if e != nil {
			return e
		}
		d, e := os.Open(dir)
		if e != nil {
			return e
		}
		defer d.Close()
		return d.Sync()
	}
}

type EventMeter struct {
	Journal *EventJournal
	Policy  EventPolicy
	Scope   string
}

func eventCost(method string) (int64, int64, error) {
	switch method {
	case "eth_chainId":
		return 0, 5, nil
	case "eth_getLogs":
		return 60, 60, nil
	case "debug_executionWitness":
		return 40, 1000, nil
	case "eth_subscribe", "eth_unsubscribe":
		return 10, 10, nil
	case "eth_getBlockByNumber", "eth_getProof", "eth_getCode", "eth_getRawTransactionByHash":
		return 20, 20, nil
	}
	return 0, 0, errors.New("METHOD_OUTSIDE_EVENT_POLICY")
}

type eventRateWait struct{ delay time.Duration }

func (e eventRateWait) Error() string { return "RATE_WAIT" }
func (m EventMeter) Reserve(ctx context.Context, method string) error {
	bill, rate, e := eventCost(method)
	if e != nil {
		return e
	}
	witness := method == "debug_executionWitness"
	for {
		e = m.Journal.Update("RPC_RESERVED", func(s *EventState) error {
			now := time.Now().UnixNano()
			if s.Stop != "" || s.Expires == 0 || now >= s.Expires {
				return errors.New("ACQUISITION_STOPPED_OR_EXPIRED")
			}
			if m.Policy.Coverage != nil {
				if s.Draining && (m.Scope == "monitor" || m.Scope == "coverage") {
					return errors.New("ACQUISITION_DRAINING")
				}
				total := s.MonitorRPC + s.CoverageRPC
				for _, entry := range s.Cases {
					total += entry.RPC
				}
				if total >= m.Policy.Coverage.AggregateRPC {
					return errors.New("AGGREGATE_RPC_BUDGET")
				}
			}
			if s.Billing+bill > m.Policy.BillingCU {
				return errors.New("BILLING_BUDGET")
			}
			var one, ten int64
			kept := []EventRate{}
			var oldest int64
			for _, x := range s.Rates {
				age := now - x.At
				if age < 0 {
					return errors.New("CLOCK_REGRESSION")
				}
				if age < int64(10*time.Second) {
					kept = append(kept, x)
					ten += x.Cost
					if oldest == 0 || x.At < oldest {
						oldest = x.At
					}
					if age < int64(time.Second) && !x.Witness {
						one += x.Cost
					}
				}
			}
			if ten+rate > 2000 || (!witness && one+rate > 200) {
				return eventRateWait{100 * time.Millisecond}
			}
			if m.Scope == "coverage" {
				if m.Policy.Coverage == nil || s.CoverageRPC >= m.Policy.Coverage.RPC {
					return errors.New("COVERAGE_RPC_BUDGET")
				}
				s.CoverageRPC++
			} else if m.Scope == "monitor" {
				if s.MonitorRPC >= m.Policy.MonitorRPC {
					return errors.New("MONITOR_RPC_BUDGET")
				}
				s.MonitorRPC++
			} else {
				c, ok := s.Cases[m.Scope]
				if !ok {
					return errors.New("UNKNOWN_CASE_BUDGET")
				}
				nativeScope := s.Consumed && s.Lock != nil && s.Lock.Selection.BlockHash.Hex() == m.Scope
				if m.Policy.Coverage != nil && !nativeScope && (c.Deadline == 0 || now >= c.Deadline) {
					return errors.New("CAPTURE_FIXED_DEADLINE")
				}
				if s.Draining && c.Status != "PENDING" {
					return errors.New("NO_NEW_CAPTURE_DURING_DRAIN")
				}
				cap := m.Policy.CaptureRPC
				if s.Consumed && s.Lock != nil && s.Lock.Selection.BlockHash.Hex() == m.Scope {
					cap = m.Policy.CaseRPC
				}
				if c.RPC >= cap {
					return errors.New("CASE_RPC_BUDGET")
				}
				c.RPC++
				s.Cases[m.Scope] = c
			}
			s.Billing += bill
			s.Rates = append(kept, EventRate{now, rate, witness})
			return nil
		})
		if _, ok := e.(eventRateWait); !ok {
			return e
		}
		if e = waitCU(ctx, 100*time.Millisecond); e != nil {
			return e
		}
	}
}
func (m EventMeter) Body(n int64) error {
	return m.Journal.Update("HTTP_BYTES", func(s *EventState) error {
		if n < 0 {
			return errors.New("NEGATIVE_BYTES")
		}
		if m.Policy.Coverage != nil {
			if s.Stop != "" || time.Now().UnixNano() >= s.Expires {
				return errors.New("ACQUISITION_STOPPED_OR_EXPIRED")
			}
			if s.Draining && (m.Scope == "monitor" || m.Scope == "coverage") {
				return errors.New("ACQUISITION_DRAINING")
			}
		}
		if m.Policy.Coverage != nil && totalEventHTTP(s)+n > m.Policy.Coverage.TotalHTTPBytes {
			return errors.New("AGGREGATE_HTTP_BUDGET")
		}
		if m.Scope == "coverage" {
			if m.Policy.Coverage == nil || s.CoverageBytes+n > m.Policy.Coverage.BodyBytes {
				return errors.New("COVERAGE_BODY_BUDGET")
			}
			s.CoverageBytes += n
		} else if m.Scope == "monitor" {
			s.HTTPBytes += n
			if s.HTTPBytes > m.Policy.HTTPBytes {
				return errors.New("MONITOR_BODY_BUDGET")
			}
		} else {
			c := s.Cases[m.Scope]
			c.Bytes += n
			if c.Bytes > m.Policy.CaseBytes {
				return errors.New("CASE_BODY_BUDGET")
			}
			s.Cases[m.Scope] = c
		}
		return nil
	})
}
func totalEventHTTP(s *EventState) int64 {
	n := s.HTTPBytes + s.CoverageBytes
	for _, c := range s.Cases {
		n += c.Bytes
	}
	return n
}
func (m EventMeter) RemainingBody() int64 {
	s := m.Journal.Snapshot()
	var n int64
	if m.Scope == "monitor" {
		n = m.Policy.HTTPBytes - s.HTTPBytes
	} else if m.Scope == "coverage" && m.Policy.Coverage != nil {
		n = m.Policy.Coverage.BodyBytes - s.CoverageBytes
	} else {
		n = m.Policy.CaseBytes - s.Cases[m.Scope].Bytes
	}
	if m.Policy.Coverage != nil {
		n = min(n, m.Policy.Coverage.TotalHTTPBytes-totalEventHTTP(&s))
	}
	return n
}
func (m EventMeter) releaseBody(n int64) error {
	if n == 0 {
		return nil
	}
	return m.Journal.Update("HTTP_UNUSED_CREDIT_RELEASED", func(s *EventState) error {
		if n < 0 {
			return errors.New("NEGATIVE_REFUND")
		}
		if m.Scope == "monitor" {
			if s.HTTPBytes < n {
				return errors.New("REFUND_OVERFLOW")
			}
			s.HTTPBytes -= n
		} else if m.Scope == "coverage" {
			if s.CoverageBytes < n {
				return errors.New("REFUND_OVERFLOW")
			}
			s.CoverageBytes -= n
		} else {
			c := s.Cases[m.Scope]
			if c.Bytes < n {
				return errors.New("REFUND_OVERFLOW")
			}
			c.Bytes -= n
			s.Cases[m.Scope] = c
		}
		return nil
	})
}
func (m EventMeter) ReserveWSRead() error {
	return m.Journal.Update("WSS_READ_RESERVED", func(s *EventState) error {
		if s.Stop != "" || s.Draining || time.Now().UnixNano() >= s.Expires {
			return errors.New("ACQUISITION_STOPPED_OR_EXPIRED")
		}
		// Reserve maximum application bytes at documented 0.04 CU/byte before read.
		cost := (int64(m.Policy.WSMessageBytes) + 24) / 25
		if s.WSReads >= m.Policy.WSMessages || s.WSBytes+int64(m.Policy.WSMessageBytes) > m.Policy.WSBytes || s.Billing+cost > m.Policy.BillingCU {
			return errors.New("WSS_BUDGET")
		}
		s.WSReads++
		s.WSBytes += int64(m.Policy.WSMessageBytes)
		s.Billing += cost
		return nil
	})
}
