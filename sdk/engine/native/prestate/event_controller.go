package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"
)

type EventCaptureFunc func(context.Context, *types.Log, WriteEvidence) (*EventCapture, error)
type EventController struct {
	Journal *EventJournal
	Policy  EventPolicy
	Capture EventCaptureFunc
	mu      sync.Mutex
	done    map[string]chan struct{}
}

func NewEventController(j *EventJournal, p EventPolicy, capture EventCaptureFunc) *EventController {
	return &EventController{Journal: j, Policy: p, Capture: capture, done: map[string]chan struct{}{}}
}
func (c *EventController) Wait() {
	c.mu.Lock()
	channels := []chan struct{}{}
	for _, d := range c.done {
		channels = append(channels, d)
	}
	c.mu.Unlock()
	for _, d := range channels {
		<-d
	}
}
func (c *EventController) Observe(ctx context.Context, l *types.Log) error {
	if !eventTarget(l) {
		return errors.New("NOT_TARGET_SWAP")
	}
	// Freeze ownership: notification providers/tests may reuse the input object.
	encoded, _ := json.Marshal(l)
	var owned types.Log
	if json.Unmarshal(encoded, &owned) != nil {
		return errors.New("NOTIFICATION_ENCODING")
	}
	l = &owned
	if l.Removed {
		c.Journal.Halt("REORG_NOTIFICATION")
		return errors.New("REORG_NOTIFICATION")
	}
	if abiWords(l, 3, 6) != nil {
		return errors.New("TARGET_SWAP_LAYOUT")
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	key := eventCaseID(l)
	fresh := false
	e := c.Journal.Update("TARGET_NOTIFICATION", func(s *EventState) error {
		if s.Stop != "" || s.Draining {
			return errors.New("OPERATION_TERMINAL_OR_DRAINING")
		}
		if isObservedPolicy(c.Policy) {
			if err := validateBoundObservedLog(c.Journal.dir, s, l, encoded); err != nil {
				return err
			}
			var err error
			fresh, err = recordObservedDelivery(s, l, encoded, c.Policy)
			return err
		}
		if s.Lock != nil {
			old, known := s.Seen[eventID(l)]
			if known && old.EncodedSHA != ByteDigest(encoded) {
				return errors.New("CONFLICTING_DUPLICATE_AFTER_LOCK")
			}
			if l.BlockNumber <= s.Lock.Selection.BlockNumber && !known {
				return errors.New("LATE_EARLIER_LOG_AFTER_LOCK")
			}
			return nil
		}
		if l.BlockNumber <= s.Activation {
			return nil
		}
		if old, ok := s.Seen[eventID(l)]; ok {
			if old.EncodedSHA != ByteDigest(encoded) {
				return errors.New("CONFLICTING_DUPLICATE")
			}
			return nil
		}
		if l.BlockNumber <= s.Cursor {
			return errors.New("NEW_LOG_IN_VERIFIED_COVERAGE")
		}
		if len(s.Seen) >= 512 {
			return errors.New("EVENT_ROW_BUDGET")
		}
		for _, old := range s.Seen {
			if old.BlockNumber == l.BlockNumber && old.BlockHash != l.BlockHash {
				return errors.New("CHANGED_EVENT_BLOCK_HASH")
			}
		}
		s.Seen[eventID(l)] = EventSeen{l.BlockNumber, l.BlockHash, ByteDigest(encoded)}
		if _, ok := s.Cases[key]; !ok {
			if len(s.Cases) >= c.Policy.Captures {
				return errors.New("PROVISIONAL_CAPTURE_BUDGET")
			}
			entry := EventCase{Hash: l.BlockHash, Number: l.BlockNumber, Status: "PENDING"}
			if c.Policy.Coverage != nil {
				entry.Began = time.Now().UnixNano()
				entry.Deadline = min(entry.Began+int64(time.Duration(c.Policy.CaptureSeconds)*time.Second), s.Expires)
				if entry.Deadline <= entry.Began {
					return errors.New("CAPTURE_AUTHORITY_EXPIRED")
				}
			}
			s.Cases[key] = entry
			fresh = true
		}
		return nil
	})
	if e != nil {
		if !c.Journal.Snapshot().Draining {
			c.Journal.Halt(e.Error())
		}
		return e
	}
	if !fresh {
		return nil
	}
	// Acquisition starts before eligibility/reconciliation. The three-case cap
	// and shared durable rate/CU ledger bound concurrency; EVM stays sequential.
	done := make(chan struct{})
	c.done[key] = done
	go func() {
		defer close(done)
		write := EventWriter(c.Journal, c.Policy, eventCaptureDir(l.BlockHash))
		captureCtx := ctx
		cancel := func() {}
		if c.Policy.Coverage != nil {
			captureCtx, cancel = context.WithDeadline(ctx, time.Unix(0, c.Journal.Snapshot().Cases[key].Deadline))
		}
		defer cancel()
		cap, e := c.Capture(captureCtx, l, write)
		if cap == nil {
			cap = &EventCapture{Error: "CAPTURE_RETURNED_NO_RECORD"}
		}
		errText := cap.Error
		if e != nil {
			errText = e.Error()
		}
		if e := c.Journal.Update("PROVISIONAL_CAPTURE_FINISHED", func(s *EventState) error {
			x := s.Cases[key]
			x.Status = "CAPTURED"
			x.Error = errText
			x.PackageSHA = ByteDigest(cap.Package)
			s.Cases[key] = x
			return nil
		}); e != nil {
			c.Journal.Halt("CAPTURE_JOURNAL_WRITE")
		}
	}()
	return nil
}
func (c *EventController) load(ctx context.Context, hash common.Hash) (*EventCapture, error) {
	c.mu.Lock()
	done := c.done[hash.Hex()]
	c.mu.Unlock()
	if done != nil {
		select {
		case <-done:
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	dir := filepath.Join(c.Journal.dir, eventCaptureDir(hash))
	b, e := os.ReadFile(filepath.Join(dir, "BLOCK_PACKAGE.json"))
	if e != nil {
		return nil, errors.New("EARLIER_CANDIDATE_EVIDENCE_MISSING")
	}
	meta, e := os.ReadFile(filepath.Join(dir, "CAPTURE_META.json"))
	if e != nil {
		return nil, errors.New("CAPTURE_META_MISSING")
	}
	var cap EventCapture
	if json.Unmarshal(meta, &cap) != nil {
		return nil, errors.New("CAPTURE_META_ENCODING")
	}
	cap.Package = b
	x := c.Journal.Snapshot().Cases[hash.Hex()]
	if x.Status != "CAPTURED" || ByteDigest(b) != x.PackageSHA {
		return nil, errors.New("CAPTURE_NOT_COMPLETE_OR_HASH_MISMATCH")
	}
	if x.Error != "" {
		cap.Error = x.Error
	}
	return &cap, nil
}
func (c *EventController) CompleteRange(ctx context.Context, from, to uint64, tail common.Hash, logs []*types.Log) error {
	state := c.Journal.Snapshot()
	limit := uint64(10)
	if c.Policy.Coverage != nil {
		limit = uint64(c.Policy.Coverage.RangeBlocks)
	}
	if state.Stop != "" || state.Draining || from != state.Cursor+1 || to < from || to-from >= limit {
		return errors.New("COVERAGE_GAP_OR_RANGE_LIMIT")
	}
	rows := append([]*types.Log{}, logs...)
	for _, l := range rows {
		if l == nil || l.Removed || l.BlockNumber < from || l.BlockNumber > to || len(l.Topics) < 2 || l.Topics[1] != hookrPoolID || (l.Address != hookrManager && l.Address != hookrRouter) {
			return errors.New("COVERAGE_LOG_IDENTITY")
		}
	}
	sort.Slice(rows, func(i, j int) bool {
		a, b := rows[i], rows[j]
		if a.BlockNumber != b.BlockNumber {
			return a.BlockNumber < b.BlockNumber
		}
		if a.TxIndex != b.TxIndex {
			return a.TxIndex < b.TxIndex
		}
		return a.Index < b.Index
	})
	blocks := []common.Hash{}
	numbers := map[uint64]common.Hash{}
	blockLogs := map[common.Hash][]*types.Log{}
	seen := map[string]bool{}
	for _, l := range rows {
		if old, ok := numbers[l.BlockNumber]; ok && old != l.BlockHash {
			return errors.New("RANGE_REORG")
		}
		numbers[l.BlockNumber] = l.BlockHash
		if seen[eventID(l)] {
			return errors.New("DUPLICATE_ROW_IN_GETLOGS")
		}
		seen[eventID(l)] = true
		blockLogs[l.BlockHash] = append(blockLogs[l.BlockHash], l)
		if eventTarget(l) {
			if e := c.Observe(ctx, l); e != nil {
				return e
			}
			found := false
			for _, h := range blocks {
				if h == l.BlockHash {
					found = true
				}
			}
			if !found {
				blocks = append(blocks, l.BlockHash)
			}
		}
	}
	// A previously delivered notification omitted by the coverage response is a
	// contradiction, not evidence that the candidate disappeared harmlessly.
	for id, l := range state.Seen {
		if l.BlockNumber >= from && l.BlockNumber <= to && !seen[id] {
			return errors.New("COVERAGE_OMITS_NOTIFIED_LOG")
		}
	}
	for _, hash := range blocks {
		cap, e := c.load(ctx, hash)
		if e != nil {
			return e
		}
		var pack BlockPackage
		if json.Unmarshal(cap.Package, &pack) != nil {
			return errors.New("PACKAGE_ENCODING")
		}
		h, reason, e := eligibleHeader(pack.Block)
		if e != nil {
			return e
		}
		if reason != "ELIGIBLE" {
			if e = c.reject(hash, reason); e != nil {
				return e
			}
			continue
		}
		if h.Hash() != hash {
			return errors.New("CAPTURE_EVENT_HASH_MISMATCH")
		}
		subject, reason, e := selectHookrTradeLogs(pack.Block, h, blockLogs[hash], true)
		if e != nil {
			return e
		}
		if subject == nil {
			if e = c.reject(hash, reason); e != nil {
				return e
			}
			continue
		}
		if cap.Error != "" {
			return errors.New("FIRST_ELIGIBLE_CAPTURE_STOP:" + cap.Error)
		}
		if cap.Inventory == nil || cap.Intervention == nil || cap.Plan == nil || cap.Inventory.BlockHash != hash || cap.Inventory.BlockNumber != h.Number.Uint64() || cap.Inventory.Checkpoint != pack.Checkpoint {
			return errors.New("FIRST_ELIGIBLE_NATIVE_ADMISSION_MISSING")
		}
		if e = ValidateLPIntervention(*cap.Intervention, pack.Checkpoint); e != nil {
			return e
		}
		selection := LockedHookrSelection{state.Activation, state.ActivationHash, pack.Block, hash, h.Number.Uint64(), subject, blockLogs[hash]}
		if e = ValidateLockedHookrSelection(&selection); e != nil {
			return e
		}
		// Journal/markers contain compact immutable references; full raw payloads
		// are stored once, outside every subsequent state snapshot.
		rawLogs, _ := json.Marshal(selection.Logs)
		if e = EventWriter(c.Journal, c.Policy, "records")("SELECTION_LOGS.json", rawLogs); e != nil {
			return e
		}
		selection.Block = nil
		selection.Logs = nil
		lock := &EventLock{Selection: selection, Checkpoint: pack.Checkpoint, PackageSHA: ByteDigest(cap.Package), LogsSHA: ByteDigest(rawLogs), Policy: state.Policy, Acquisition: state.Operation}
		if e = c.Journal.Marker("FIRST_ELIGIBLE_LOCK.json", lock); e != nil {
			return e
		}
		return c.Journal.Update("FIRST_ELIGIBLE_LOCK", func(s *EventState) error {
			if s.Lock != nil || s.Consumed || s.Stop != "" || s.Draining || s.Cursor+1 != from || !s.Connected {
				return errors.New("LOCK_STATE_CONFLICT_OR_DISCONNECTED")
			}
			for id, l := range s.Seen {
				if l.BlockNumber >= from && l.BlockNumber <= to && !seen[id] {
					return errors.New("COVERAGE_OMITS_CONCURRENT_NOTIFICATION")
				}
			}
			s.Lock = lock
			s.Cursor = h.Number.Uint64()
			s.CursorHash = hash
			return nil
		})
	}
	return c.Journal.Update("COVERAGE_COMPLETE", func(s *EventState) error {
		if s.Cursor+1 != from || s.Lock != nil || s.Stop != "" || s.Draining || !s.Connected {
			return errors.New("COVERAGE_STATE_CONFLICT")
		}
		for id, l := range s.Seen {
			if l.BlockNumber >= from && l.BlockNumber <= to && !seen[id] {
				return errors.New("COVERAGE_OMITS_CONCURRENT_NOTIFICATION")
			}
		}
		s.Cursor = to
		s.CursorHash = tail
		return nil
	})
}
func (c *EventController) reject(hash common.Hash, reason string) error {
	return c.Journal.Update("INELIGIBLE", func(s *EventState) error {
		x := s.Cases[hash.Hex()]
		x.Status = "INELIGIBLE"
		x.Error = reason
		s.Cases[hash.Hex()] = x
		return nil
	})
}
