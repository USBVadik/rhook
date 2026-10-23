package prestate

// This prospective profile selects only among delivered notifications. It never
// advances the legacy verified-history cursor or calls historical reconciliation.
import (
	"context"
	"encoding/json"
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"os"
	"path/filepath"
	"time"
)

const observedVersion = "RHOOK_EVENT_OBSERVED_HOOKR_DEMO_01"
const observedAssurance = "FIRST_ELIGIBLE_DELIVERED_WSS_TRANSACTION; PROVIDER_DELIVERY_ORDER_TRUSTED; NO_CHAIN_GLOBAL_FIRSTNESS"

func ObservedEventPolicy() EventPolicy {
	p := DefaultEventPolicy()
	p.Version = observedVersion
	p.Reconnects = 0
	// Reuse the reviewed durable aggregate accounting and fail-closed journal
	// guards. This legacy-named carrier contains resource limits only: empty
	// endpoint, zero coverage RPC, no polling, and an invalid coverage provider.
	// NewEventRPC therefore cannot instantiate a coverage source in this mode.
	p.Coverage = &QuietCoveragePolicy{ProviderID: "NONE_OBSERVED_DELIVERY_ONLY", TotalHTTPBytes: 128 << 20, AggregateRPC: 400, Trust: observedAssurance}
	return p
}
func isObservedPolicy(p EventPolicy) bool { return p.Version == observedVersion }

type ObservedPosition struct {
	Number            uint64
	Hash              common.Hash
	TxIndex, LogIndex uint
}
type ObservedTransaction struct {
	Number        uint64
	Hash, TxHash  common.Hash
	TxIndex       uint
	FirstSequence uint64
	Decision      string
}
type ObservedDeliveryState struct {
	Started      int64
	Sequence     uint64
	Last         *ObservedPosition
	Transactions []ObservedTransaction
	Logs         map[string]string
}
type ObservedSelectionBinding struct {
	Assurance           string
	SubscriptionStarted int64
	FirstSequence       uint64
	ObservedPrefixSHA   string
	BlockLogsSHA        string
}

// Called inside the existing controller mutex and journal transaction. Exact
// duplicates are idempotent; any fresh ordering regression or position conflict
// is terminal, including after a scientific lock. Grouping is by transaction,
// while acquisition is shared once per observed block.
func recordObservedDelivery(s *EventState, l *types.Log, encoded []byte, p EventPolicy) (bool, error) {
	if s.Observed == nil || !s.Connected || s.Observed.Started == 0 {
		return false, errors.New("OBSERVED_SUBSCRIPTION_NOT_ACTIVE")
	}
	if l.BlockNumber <= s.Activation {
		return false, nil
	}
	if l.BlockHash == (common.Hash{}) || l.TxHash == (common.Hash{}) || l.TxIndex == 0 {
		return false, errors.New("OBSERVED_POSITION_IDENTITY")
	}
	id := eventID(l)
	if prior, ok := s.Seen[id]; ok {
		if prior.EncodedSHA != ByteDigest(encoded) {
			return false, errors.New("CONFLICTING_DUPLICATE")
		}
		return false, nil
	}
	if len(s.Seen) >= 512 {
		return false, errors.New("EVENT_ROW_BUDGET")
	}
	for _, prior := range s.Seen {
		if prior.BlockNumber == l.BlockNumber && prior.BlockHash != l.BlockHash {
			return false, errors.New("CHANGED_EVENT_BLOCK_HASH")
		}
	}
	if last := s.Observed.Last; last != nil {
		if l.BlockNumber < last.Number || (l.BlockNumber == last.Number && (l.BlockHash != last.Hash || l.TxIndex < last.TxIndex || l.Index <= last.LogIndex)) {
			return false, errors.New("OBSERVED_OUT_OF_ORDER_OR_REORG")
		}
	}
	entry := -1
	for i, prior := range s.Observed.Transactions {
		if prior.Number == l.BlockNumber && prior.TxIndex == l.TxIndex {
			if prior.Hash != l.BlockHash || prior.TxHash != l.TxHash {
				return false, errors.New("OBSERVED_TRANSACTION_POSITION_CONFLICT")
			}
			entry = i
		}
		if prior.TxHash == l.TxHash && (prior.Number != l.BlockNumber || prior.Hash != l.BlockHash || prior.TxIndex != l.TxIndex) {
			return false, errors.New("OBSERVED_TRANSACTION_MOVED")
		}
	}
	s.Observed.Sequence++
	s.Observed.Last = &ObservedPosition{l.BlockNumber, l.BlockHash, l.TxIndex, l.Index}
	s.Seen[id] = EventSeen{l.BlockNumber, l.BlockHash, ByteDigest(encoded)}
	if entry < 0 {
		s.Observed.Transactions = append(s.Observed.Transactions, ObservedTransaction{Number: l.BlockNumber, Hash: l.BlockHash, TxHash: l.TxHash, TxIndex: l.TxIndex, FirstSequence: s.Observed.Sequence})
	}
	if s.Lock != nil {
		return false, nil
	}
	if _, ok := s.Cases[l.BlockHash.Hex()]; ok {
		return false, nil
	}
	if len(s.Cases) >= p.Captures {
		return false, errors.New("PROVISIONAL_CAPTURE_BUDGET")
	}
	began := time.Now().UnixNano()
	deadline := min(began+int64(time.Duration(p.CaptureSeconds)*time.Second), s.Expires)
	if deadline <= began {
		return false, errors.New("CAPTURE_AUTHORITY_EXPIRED")
	}
	s.Cases[l.BlockHash.Hex()] = EventCase{Hash: l.BlockHash, Number: l.BlockNumber, Status: "PENDING", Began: began, Deadline: deadline}
	return true, nil
}

type ObservedLogsFunc func(context.Context, common.Hash, WriteEvidence) ([]*types.Log, error)

func firstObservedPending(s EventState) (int, *ObservedTransaction) {
	if s.Observed == nil {
		return -1, nil
	}
	for i := range s.Observed.Transactions {
		if s.Observed.Transactions[i].Decision == "" {
			x := s.Observed.Transactions[i]
			return i, &x
		}
	}
	return -1, nil
}

// Only one blockHash-scoped query per captured block. It supplies the router
// event required by the unchanged route predicate, not absence evidence for the
// quiet interval. The shared case meter includes this call in capture/64-RPC
// limits. All delivered notifications for the block must agree with its result.
func (c *EventController) observedBlockLogs(ctx context.Context, tx ObservedTransaction, fetch ObservedLogsFunc) ([]*types.Log, error) {
	path := filepath.Join(c.Journal.dir, eventCaptureDir(tx.Hash), "OBSERVED_BLOCK_LOGS.json")
	s := c.Journal.Snapshot()
	var raw []byte
	if pin := s.Observed.Logs[tx.Hash.Hex()]; pin != "" {
		var e error
		raw, e = os.ReadFile(path)
		if e != nil || ByteDigest(raw) != pin {
			return nil, errors.New("OBSERVED_LOGS_FILE_BINDING")
		}
	} else {
		logs, e := fetch(ctx, tx.Hash, EventWriter(c.Journal, c.Policy, eventCaptureDir(tx.Hash)))
		if e != nil {
			return nil, e
		}
		raw, e = json.Marshal(logs)
		if e != nil {
			return nil, e
		}
		if e = EventWriter(c.Journal, c.Policy, eventCaptureDir(tx.Hash))("OBSERVED_BLOCK_LOGS.json", raw); e != nil {
			return nil, e
		}
		if e = c.Journal.Update("OBSERVED_BLOCK_LOGS_BOUND", func(s *EventState) error {
			if s.Stop != "" || s.Draining || s.Lock != nil || !s.Connected {
				return errors.New("OBSERVED_LOGS_AFTER_STOP")
			}
			s.Observed.Logs[tx.Hash.Hex()] = ByteDigest(raw)
			return nil
		}); e != nil {
			return nil, e
		}
	}
	var logs []*types.Log
	if json.Unmarshal(raw, &logs) != nil {
		return nil, errors.New("OBSERVED_LOGS_ENCODING")
	}
	ids := map[string]string{}
	for _, l := range logs {
		if l == nil || l.Removed || l.BlockNumber != tx.Number || l.BlockHash != tx.Hash || len(l.Topics) < 2 || l.Topics[1] != hookrPoolID {
			return nil, errors.New("OBSERVED_BLOCK_LOG_IDENTITY")
		}
		if !(eventTarget(l) && abiWords(l, 3, 6) == nil) && !(l.Address == hookrRouter && l.Topics[0] == routerTopic && abiWords(l, 4, 2) == nil) {
			return nil, errors.New("OBSERVED_BLOCK_LOG_ABI")
		}
		id := eventID(l)
		if _, ok := ids[id]; ok {
			return nil, errors.New("OBSERVED_BLOCK_LOG_DUPLICATE")
		}
		b, _ := json.Marshal(l)
		ids[id] = ByteDigest(b)
	}
	for id, seen := range c.Journal.Snapshot().Seen {
		if seen.BlockHash == tx.Hash && ids[id] != seen.EncodedSHA {
			return nil, errors.New("OBSERVED_LOGS_OMIT_OR_CONTRADICT_NOTIFICATION")
		}
	}
	return logs, nil
}

func (c *EventController) rejectObserved(index int, tx ObservedTransaction, reason string) error {
	return c.Journal.Update("OBSERVED_TRANSACTION_INELIGIBLE", func(s *EventState) error {
		i, pending := firstObservedPending(*s)
		if i != index || pending == nil || pending.FirstSequence != tx.FirstSequence || s.Stop != "" || s.Draining || s.Lock != nil || !s.Connected {
			return errors.New("OBSERVED_DECISION_CONFLICT")
		}
		s.Observed.Transactions[index].Decision = reason
		return nil
	})
}

// Evaluate delivery order, never capture-completion order or execution results.
// Failure to establish an earlier candidate's eligibility is a STOP. There is no
// loop advancing to another transaction after an eligible capture/admission error.
func (c *EventController) CompleteObserved(ctx context.Context, fetch ObservedLogsFunc) (err error) {
	if !isObservedPolicy(c.Policy) {
		return errors.New("OBSERVED_PROFILE_REQUIRED")
	}
	defer func() {
		if err != nil && c.Journal.Snapshot().Stop == "" && !c.Journal.Snapshot().Draining {
			// No new selection or acquisition may enter. Already-admitted capture
			// keeps only its original deadline/budget and saves partial evidence.
			if e := c.BeginDrain(err.Error()); e != nil {
				c.Journal.Halt("OBSERVED_DRAIN_JOURNAL_UNCERTAIN")
			}
		}
	}()
	for {
		state := c.Journal.Snapshot()
		if state.Stop != "" || state.Draining || !state.Connected {
			return errors.New("OBSERVED_SELECTION_NOT_ACTIVE")
		}
		if state.Lock != nil {
			return nil
		}
		index, pending := firstObservedPending(state)
		if pending == nil {
			return nil
		}
		tx := *pending
		cap, e := c.load(ctx, tx.Hash)
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
			if e = c.rejectObserved(index, tx, reason); e != nil {
				return e
			}
			continue
		}
		if h.Hash() != tx.Hash || h.Number.Uint64() != tx.Number {
			return errors.New("OBSERVED_CAPTURE_BLOCK_MISMATCH")
		}
		logs, e := c.observedBlockLogs(ctx, tx, fetch)
		if e != nil {
			return e
		}
		txlogs := []*types.Log{}
		for _, l := range logs {
			if l.TxHash == tx.TxHash {
				txlogs = append(txlogs, l)
			}
		}
		subject, reason, e := selectHookrTradeLogs(pack.Block, h, txlogs, true)
		if e != nil {
			return e
		}
		if subject == nil {
			if e = c.rejectObserved(index, tx, reason); e != nil {
				return e
			}
			continue
		}
		if subject.Hash != tx.TxHash || subject.Ordinal != int(tx.TxIndex) {
			return errors.New("OBSERVED_SUBJECT_IDENTITY")
		}
		if cap.Error != "" {
			return errors.New("FIRST_OBSERVED_ELIGIBLE_CAPTURE_STOP:" + cap.Error)
		}
		if cap.Inventory == nil || cap.Intervention == nil || cap.Plan == nil || cap.Inventory.BlockHash != tx.Hash || cap.Inventory.BlockNumber != tx.Number || cap.Inventory.Checkpoint != pack.Checkpoint {
			return errors.New("FIRST_OBSERVED_ELIGIBLE_NATIVE_ADMISSION_MISSING")
		}
		if e = ValidateLPIntervention(*cap.Intervention, pack.Checkpoint); e != nil {
			return e
		}
		selection := LockedHookrSelection{state.Activation, state.ActivationHash, pack.Block, tx.Hash, tx.Number, subject, txlogs}
		if e = ValidateLockedHookrSelection(&selection); e != nil {
			return e
		}
		// Serialize the marker/journal commit with notification admission, so no
		// concurrent conflicting delivery can enter between prefix and lock.
		c.mu.Lock()
		e = c.lockObserved(index, tx, selection, cap, logs)
		c.mu.Unlock()
		return e
	}
}

func (c *EventController) lockObserved(index int, tx ObservedTransaction, selection LockedHookrSelection, cap *EventCapture, allLogs []*types.Log) error {
	state := c.Journal.Snapshot()
	i, pending := firstObservedPending(state)
	if i != index || pending == nil || pending.FirstSequence != tx.FirstSequence || state.Stop != "" || state.Draining || state.Lock != nil || state.Consumed || !state.Connected {
		return errors.New("OBSERVED_LOCK_CONFLICT")
	}
	ids := map[string]string{}
	for _, l := range allLogs {
		raw, _ := json.Marshal(l)
		ids[eventID(l)] = ByteDigest(raw)
	}
	for id, seen := range state.Seen {
		if seen.BlockHash == tx.Hash && ids[id] != seen.EncodedSHA {
			return errors.New("OBSERVED_LOGS_OMIT_CONCURRENT_NOTIFICATION")
		}
	}
	rawLogs, _ := json.Marshal(selection.Logs)
	if e := EventWriter(c.Journal, c.Policy, "records")("SELECTION_LOGS.json", rawLogs); e != nil {
		return e
	}
	prefix, _ := json.Marshal(state.Observed.Transactions[:index+1])
	observation := &ObservedSelectionBinding{observedAssurance, state.Observed.Started, tx.FirstSequence, ByteDigest(prefix), state.Observed.Logs[tx.Hash.Hex()]}
	selection.Block, selection.Logs = nil, nil
	lock := &EventLock{Selection: selection, Checkpoint: cap.Inventory.Checkpoint, PackageSHA: ByteDigest(cap.Package), LogsSHA: ByteDigest(rawLogs), Policy: state.Policy, Acquisition: state.Operation, Observation: observation}
	if e := c.Journal.Marker("FIRST_ELIGIBLE_LOCK.json", lock); e != nil {
		return e
	}
	return c.Journal.Update("FIRST_OBSERVED_ELIGIBLE_LOCK", func(s *EventState) error {
		if s.Stop != "" || s.Draining || s.Lock != nil || s.Consumed || !s.Connected {
			return errors.New("OBSERVED_LOCK_COMMIT_CONFLICT")
		}
		s.Lock = lock
		s.Observed.Transactions[index].Decision = "ELIGIBLE_LOCKED"
		// Cursor remains the H0 marker. No historical coverage is asserted.
		return nil
	})
}

// A completed block log response must also agree with later notifications,
// including duplicate Swap logs of the locked transaction during native work.
func validateBoundObservedLog(dir string, s *EventState, l *types.Log, encoded []byte) error {
	if s.Observed == nil {
		return nil
	}
	pin := s.Observed.Logs[l.BlockHash.Hex()]
	if pin == "" {
		return nil
	}
	raw, err := os.ReadFile(filepath.Join(dir, eventCaptureDir(l.BlockHash), "OBSERVED_BLOCK_LOGS.json"))
	if err != nil || ByteDigest(raw) != pin {
		return errors.New("OBSERVED_LOGS_FILE_BINDING")
	}
	var logs []*types.Log
	if json.Unmarshal(raw, &logs) != nil {
		return errors.New("OBSERVED_LOGS_ENCODING")
	}
	for _, item := range logs {
		if item != nil && eventID(item) == eventID(l) {
			b, _ := json.Marshal(item)
			if ByteDigest(b) != ByteDigest(encoded) {
				return errors.New("OBSERVED_NOTIFICATION_CONTRADICTS_BOUND_LOGS")
			}
			return nil
		}
	}
	return errors.New("OBSERVED_NOTIFICATION_OMITTED_BY_BOUND_LOGS")
}

// Verify the weaker selection assurance itself before spending science, not
// just the package digest and generic first-eligible marker.
func validateObservedLock(s EventState) error {
	if s.Lock == nil || s.Lock.Observation == nil || s.Observed == nil || s.Lock.Selection.Subject == nil {
		return errors.New("OBSERVED_LOCK_BINDING_MISSING")
	}
	b := s.Lock.Observation
	if b.Assurance != observedAssurance || b.SubscriptionStarted != s.Observed.Started || b.BlockLogsSHA == "" || b.BlockLogsSHA != s.Observed.Logs[s.Lock.Selection.BlockHash.Hex()] || s.Lock.Policy != s.Policy || s.Lock.Acquisition != s.Operation {
		return errors.New("OBSERVED_LOCK_BINDING_CHANGED")
	}
	for i, tx := range s.Observed.Transactions {
		if tx.Decision == "ELIGIBLE_LOCKED" {
			if tx.Hash != s.Lock.Selection.BlockHash || tx.Number != s.Lock.Selection.BlockNumber || tx.TxHash != s.Lock.Selection.Subject.Hash || int(tx.TxIndex) != s.Lock.Selection.Subject.Ordinal || tx.FirstSequence != b.FirstSequence {
				return errors.New("OBSERVED_LOCK_SUBJECT_CHANGED")
			}
			prefix := append([]ObservedTransaction{}, s.Observed.Transactions[:i+1]...)
			prefix[i].Decision = ""
			raw, _ := json.Marshal(prefix)
			if ByteDigest(raw) != b.ObservedPrefixSHA {
				return errors.New("OBSERVED_PREFIX_BINDING_CHANGED")
			}
			return nil
		}
		if tx.Decision == "" {
			return errors.New("OBSERVED_UNDECIDED_EARLIER_TRANSACTION")
		}
	}
	return errors.New("OBSERVED_LOCK_NOT_IN_DELIVERY_QUEUE")
}
