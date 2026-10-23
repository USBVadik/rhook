package prestate

// A separately authorized fixed historical capability probe. It has no WSS,
// checkpoint/witness access, host gate, scientific authority or replay call path.
import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"os"
	"path/filepath"
	"time"
)

const CoverageProbeBlock uint64 = 92818901

var CoverageProbeHash = common.HexToHash("0xe8d8c479f47f7ec2b0c01d60ae63110f7979fee9c20154e84b2cacc78853a211")
var CoverageProbeTx = common.HexToHash("0x9f528ffbcb4cc4f5dd980694432a4d514281c8b1f12ce5798eb3ce201d56f71a")

func CoverageProbePolicy() EventPolicy {
	p := DefaultQuietEventPolicy()
	p.Version = "RHOOK_HISTORICAL_COVERAGE_PROBE_01"
	p.Seconds = 60
	p.BillingCU = 1000
	p.Coverage.RPC = 12
	p.Coverage.BodyBytes = 16 << 20
	p.Coverage.TotalHTTPBytes = 16 << 20
	p.Coverage.AggregateRPC = 12
	return p
}
func RunCoverageCapabilityProbe(root string, a EventAuthority, binary string, rawAuthority []byte) (result map[string]any, err error) {
	p := CoverageProbePolicy()
	now := time.Now().Unix()
	if a.Domain != "COVERAGE_CAPABILITY_READ_ONLY" || !a.FounderApproved || !a.FreeConfirmed || !a.PaidOveragesDisabled || a.Policy != p.Commitment() || a.BinarySHA != binary || a.NotBefore > now || a.Expires <= now || a.Expires-a.NotBefore > 60 || a.Actual != 0 || a.Branch != 0 || a.B != 0 || len(a.DecisionID) < 8 || !filepath.IsAbs(root) || root != a.RuntimePath {
		return nil, errors.New("EXACT_NEW_COVERAGE_PROBE_AUTHORITY_REQUIRED")
	}
	// Exclusive archive creation is the irreversible no-repeat marker.
	if e := os.Mkdir(root, 0700); e != nil {
		return nil, errors.New("PROBE_ARCHIVE_ALREADY_EXISTS_OR_UNAVAILABLE")
	}
	j, e := OpenEventJournal(filepath.Join(root, "runtime"), a.DecisionID, p)
	if e != nil {
		return nil, e
	}
	defer j.Close()
	if e = writeCoverageProbeFile(root, "RAW_AUTHORITY.json", rawAuthority); e != nil {
		return nil, e
	}
	if e = j.Update("BEGIN_COVERAGE_PROBE", func(s *EventState) error {
		s.Began = time.Now().UnixNano()
		s.Expires = time.Unix(a.Expires, 0).UnixNano()
		s.AcquisitionAuthoritySHA = ByteDigest(rawAuthority)
		return nil
	}); e != nil {
		return nil, e
	}
	ctx, cancel := context.WithDeadline(context.Background(), time.Unix(a.Expires, 0))
	defer cancel()
	j.SetHardCancel(cancel)
	write := EventWriter(j, p, "records")
	began := time.Now()
	defer func() {
		terminal := "COVERAGE_CAPABILITY_OBSERVED_NOT_SCIENTIFIC"
		if err != nil {
			terminal = "COVERAGE_CAPABILITY_STOP"
		}
		result = map[string]any{"terminal": terminal, "elapsedSeconds": time.Since(began).Seconds(), "state": j.Snapshot(), "nativeInvocations": 0, "WSS": 0, "freeAccess": "founder-attested; RPC does not prove billing terms", "completeness": "trusted source, not cryptographic log absence", "externalDelivery": "HOLD", "retry": false}
		if err != nil {
			result["cause"] = err.Error()
		}
		raw, encode := json.MarshalIndent(result, "", "  ")
		if encode != nil {
			err = encode
			return
		}
		if save := writeCoverageProbeFile(root, "FINAL_RESULT.json", append(raw, '\n')); save != nil && err == nil {
			err = save
		}
	}()
	rpc, e := NewEventRPC(p.Coverage.Endpoint, j, p, "coverage", "PROBE", write)
	if e != nil {
		return nil, e
	}
	var chain string
	if e = rpc.call(ctx, "eth_chainId", []any{}, &chain); e != nil {
		return nil, e
	}
	if chain != "0x1237" {
		return nil, errors.New("COVERAGE_CHAIN_ID")
	}
	end := CoverageProbeBlock + 250
	cursor := end - 500
	// These six calls model one normal coverage cycle's head/end/cursor/log checks.
	sixBegan := time.Now()
	_, tail, e := eventHeader(ctx, rpc, formatHeight(end))
	if e != nil {
		return nil, e
	}
	_, before, e := eventHeader(ctx, rpc, formatHeight(cursor))
	if e != nil {
		return nil, e
	}
	logs := func(from, to uint64) ([]*types.Log, error) {
		var out []*types.Log
		e := rpc.call(ctx, "eth_getLogs", []any{quietCoverageLogFilter(from, to)}, &out)
		return out, e
	}
	wide, e := logs(cursor+1, end)
	if e != nil {
		return nil, e
	}
	if _, _, e = eventHeader(ctx, rpc, "latest"); e != nil {
		return nil, e
	}
	_, afterTail, e := eventHeader(ctx, rpc, formatHeight(end))
	if e != nil {
		return nil, e
	}
	_, afterCursor, e := eventHeader(ctx, rpc, formatHeight(cursor))
	if e != nil {
		return nil, e
	}
	elapsed := time.Since(sixBegan).Seconds()
	if tail.Hash() != afterTail.Hash() || before.Hash() != afterCursor.Hash() {
		return nil, errors.New("COVERAGE_FORK_CHANGED")
	}
	if e = EmitJSON(write, "CYCLE_TIMING.json", map[string]any{"sixRPCSeconds": elapsed, "prospectiveCycleCeilingSeconds": 10, "oneSampleNotSLA": true}); e != nil {
		return nil, e
	}
	if elapsed > 10 {
		return nil, errors.New("COVERAGE_CYCLE_LATENCY_NOT_FIT")
	}
	narrow, e := logs(CoverageProbeBlock-4, CoverageProbeBlock+5)
	if e != nil {
		return nil, e
	}
	single, e := logs(CoverageProbeBlock, CoverageProbeBlock)
	if e != nil {
		return nil, e
	}
	_, known, e := eventHeader(ctx, rpc, formatHeight(CoverageProbeBlock))
	if e != nil {
		return nil, e
	}
	if known.Hash() != CoverageProbeHash {
		return nil, errors.New("KNOWN_BLOCK_HASH_MISMATCH")
	}
	if e = validateCoverageProbeLogs(wide, narrow, single); e != nil {
		return nil, e
	}
	if e = EmitJSON(write, "POSITIVE_CONTROL.json", map[string]any{"knownBlock": CoverageProbeBlock, "knownHash": CoverageProbeHash, "knownTx": CoverageProbeTx, "knownLogIndices": []int{13, 37}, "wideCount": len(wide), "narrowCount": len(narrow), "singleCount": len(single), "wideRange": []uint64{cursor + 1, end}, "oneHistoricalSampleNotAvailabilityGuarantee": true}); e != nil {
		return nil, e
	}
	return nil, nil
}
func formatHeight(n uint64) string { return fmt.Sprintf("0x%x", n) }
func writeCoverageProbeFile(root, name string, raw []byte) error {
	f, e := os.OpenFile(filepath.Join(root, name), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
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
	d, e := os.Open(root)
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}
func validateCoverageProbeLogs(wide, narrow, single []*types.Log) error {
	index := func(rows []*types.Log, from, to uint64) (map[string]string, error) {
		out := map[string]string{}
		for _, l := range rows {
			if l == nil || l.Removed || l.BlockNumber < from || l.BlockNumber > to || len(l.Topics) < 2 || l.Topics[1] != hookrPoolID {
				return nil, errors.New("PROBE_LOG_IDENTITY_OR_RANGE")
			}
			swap := eventTarget(l) && abiWords(l, 3, 6) == nil
			router := l.Address == hookrRouter && l.Topics[0] == routerTopic && abiWords(l, 4, 2) == nil
			if !swap && !router {
				return nil, errors.New("PROBE_LOG_TYPE_OR_ABI")
			}
			id := eventID(l)
			if _, ok := out[id]; ok {
				return nil, errors.New("PROBE_DUPLICATE_LOG")
			}
			raw, _ := json.Marshal(l)
			out[id] = ByteDigest(raw)
		}
		return out, nil
	}
	w, e := index(wide, CoverageProbeBlock-249, CoverageProbeBlock+250)
	if e != nil {
		return e
	}
	n, e := index(narrow, CoverageProbeBlock-4, CoverageProbeBlock+5)
	if e != nil {
		return e
	}
	s, e := index(single, CoverageProbeBlock, CoverageProbeBlock)
	if e != nil {
		return e
	}
	for _, l := range wide {
		if l.BlockNumber >= CoverageProbeBlock-4 && l.BlockNumber <= CoverageProbeBlock+5 {
			if n[eventID(l)] != w[eventID(l)] {
				return errors.New("PROBE_WIDE_NARROW_MISMATCH")
			}
		}
	}
	for id, value := range n {
		if w[id] != value {
			return errors.New("PROBE_NARROW_OMITTED_FROM_WIDE")
		}
	}
	for _, l := range narrow {
		if l.BlockNumber == CoverageProbeBlock {
			if s[eventID(l)] != n[eventID(l)] {
				return errors.New("PROBE_SINGLE_MISMATCH")
			}
		}
	}
	for id, value := range s {
		if n[id] != value {
			return errors.New("PROBE_SINGLE_OMITTED_FROM_NARROW")
		}
	}
	for _, log := range []uint{13, 37} {
		id := fmt.Sprintf("%s/%s/%d", CoverageProbeHash, CoverageProbeTx, log)
		if s[id] == "" {
			return errors.New("KNOWN_ATTEMPT02_LOG_MISSING")
		}
	}
	return nil
}
