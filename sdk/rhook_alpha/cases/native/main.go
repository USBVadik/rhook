package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"io"
	prestate "local/rhook-robinhood"
	"os"
	"path/filepath"
	"syscall"
	"time"
)

var sourceCommitment string
var policyCommitment string

const profile = "nitro-hookr-lp/0.1"

func digest(raw []byte) string { s := sha256.Sum256(raw); return hex.EncodeToString(s[:]) }
func observation(i int) prestate.EconomicObservationPlan {
	return prestate.EconomicObservationPlan{NativeOrdinal: i}
}
func validateScope(p Plan, hashes []common.Hash) error {
	i := p.Observation.NativeOrdinal
	if p.Transactions <= 0 || len(hashes) != p.Transactions || i < 1 || i >= len(hashes) || hashes[i] != p.Subject || p.Observation.Subject != p.Subject {
		return errors.New("ARRIVAL_OR_SUBJECT_SCOPE")
	}
	return nil
}

type capsule struct {
	Schema     string              `json:"schema"`
	ID         string              `json:"capsuleId"`
	Case       string              `json:"caseId"`
	Checkpoint prestate.Checkpoint `json:"checkpoint"`
	Target     struct {
		Number   uint64      `json:"blockNumber"`
		Hash     common.Hash `json:"blockHash"`
		State    common.Hash `json:"stateRoot"`
		Receipts common.Hash `json:"receiptsRoot"`
	} `json:"target"`
	Arrivals []common.Hash `json:"arrivals"`
	Assets   map[string]struct {
		SHA   string `json:"sha256"`
		Bytes int    `json:"bytes"`
	} `json:"assets"`
	Execution struct {
		Profile string `json:"profile"`
		Input   string `json:"inputCommitment"`
		Witness string `json:"witnessCommitment"`
	} `json:"execution"`
	Adapter struct {
		ID     string `json:"id"`
		Config struct {
			Code common.Hash `json:"rulesRuntimeHash"`
		} `json:"config"`
	} `json:"adapter"`
}
type request struct {
	Runtime Plan   `json:"runtimePlan"`
	Case    string `json:"caseId"`
	Capsule string `json:"capsuleId"`
}

func jsonValue(raw []byte, out any) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	if e := d.Decode(out); e != nil {
		return e
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		return errors.New("JSON_TRAILING")
	}
	return nil
}
func limited(path string, max int64) ([]byte, error) {
	for p := path; ; p = filepath.Dir(p) {
		st, e := os.Lstat(p)
		if e != nil {
			return nil, e
		}
		if st.Mode()&os.ModeSymlink != 0 {
			return nil, errors.New("SYMLINK")
		}
		if p == filepath.Dir(p) {
			break
		}
	}
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if e != nil {
		return nil, e
	}
	f := os.NewFile(uintptr(fd), path)
	defer f.Close()
	s, e := f.Stat()
	if e != nil {
		return nil, e
	}
	if !s.Mode().IsRegular() || s.Size() > max {
		return nil, errors.New("INPUT_TYPE_OR_SIZE")
	}
	b, e := io.ReadAll(io.LimitReader(f, max+1))
	if int64(len(b)) > max {
		return nil, errors.New("INPUT_LIMIT")
	}
	return b, e
}
func openInputs(cRaw, pRaw, raw []byte) (capsule, request, *prestate.OfflineCalibration, error) {
	var c capsule
	var p request
	if e := jsonValue(cRaw, &c); e != nil {
		return c, p, nil, e
	}
	if e := jsonValue(pRaw, &p); e != nil {
		return c, p, nil, e
	}
	r := p.Runtime
	if c.Schema != "rhook/case-capsule/0.1" || c.ID != p.Capsule || c.Case != p.Case || c.Execution.Profile != profile || c.Adapter.ID != "hookr-1.lp-bps/1" || c.Checkpoint.ChainID != 4663 {
		return c, p, nil, errors.New("CAPSULE_PROFILE_OR_IDENTITY")
	}
	asset, ok := c.Assets["BLOCK_PACKAGE.json"]
	if !ok || len(c.Assets) != 1 || asset.SHA != digest(raw) || asset.Bytes != len(raw) || r.PackageSHA != asset.SHA || c.Checkpoint != r.Checkpoint || c.Target.Number != r.Block || c.Target.Hash != r.BlockHash || c.Target.State != r.StateRoot || c.Target.Receipts != r.ReceiptsRoot || c.Execution.Input != r.Input || c.Execution.Witness != r.Witness {
		return c, p, nil, errors.New("CAPSULE_PLAN_PACKAGE_LINK")
	}
	if len(c.Arrivals) != r.Transactions {
		return c, p, nil, errors.New("ARRIVAL_COUNT")
	}
	if e := validateScope(r, c.Arrivals); e != nil {
		return c, p, nil, e
	}
	if e := prestate.ValidateCapsuleLP(r.Intervention, c.Checkpoint, c.Adapter.Config.Code); e != nil {
		return c, p, nil, e
	}
	o, e := prestate.PrepareOfflineCalibration(raw, r.Input, r.Witness)
	if e != nil {
		return c, p, nil, e
	}
	fail := func(e error) (capsule, request, *prestate.OfflineCalibration, error) {
		o.Bridge.Close()
		return c, p, nil, e
	}
	inv := o.Inventory
	if inv.Checkpoint != r.Checkpoint || inv.BlockNumber != r.Block || inv.BlockHash != r.BlockHash || inv.ExpectedStateRoot != r.StateRoot || inv.ExpectedReceiptsRoot != r.ReceiptsRoot || inv.Transactions != r.Transactions {
		return fail(errors.New("ADMITTED_TARGET_MISMATCH"))
	}
	if e = validateScope(r, o.TxHashes); e != nil {
		return fail(e)
	}
	for i, h := range o.TxHashes {
		if h != c.Arrivals[i] {
			return fail(errors.New("ARRIVAL_ORDER"))
		}
	}
	var pkg prestate.BlockPackage
	if e = jsonValue(raw, &pkg); e != nil {
		return fail(e)
	}
	var tx types.Transaction
	if e = tx.UnmarshalBinary(pkg.Raw[r.Observation.NativeOrdinal]); e != nil {
		return fail(e)
	}
	sender, e := types.Sender(types.LatestSignerForChainID(tx.ChainId()), &tx)
	if e != nil || sender != r.Sender || tx.To() == nil || *tx.To() != r.Router {
		return fail(errors.New("SUBJECT_SENDER_ROUTER"))
	}
	if e = o.Bridge.Protect(func() error { return prestate.CheckCapsuleLP(o.Bridge, r.Intervention, c.Adapter.Config.Code) }); e != nil {
		return fail(e)
	}
	return c, p, o, nil
}

type capsuleWorld struct {
	o       *prestate.OfflineCalibration
	p       Plan
	code    common.Hash
	phase   string
	failure *map[string]any
}

func (w *capsuleWorld) Run(i *prestate.LPIntervention) (*prestate.CalibrationResult, error) {
	r, e := prestate.RunCapsuleLP(w.o.Candidate, w.o.Bridge, i, w.p.Observation, w.code)
	if e != nil {
		var h *prestate.HostStop
		if errors.As(e, &h) {
			class, _ := prestate.ClassifyCalibrationError(e)
			*w.failure = map[string]any{"phase": w.phase, "code": h.Code, "classification": class}
		}
	}
	return r, e
}
func (w *capsuleWorld) Attempts() []prestate.Attempt { return w.o.Attempts() }
func (w *capsuleWorld) Close()                       { w.o.Bridge.Close() }
func main() {
	if e := entry(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
func entry() error {
	if len(os.Args) == 2 && os.Args[1] == "--identity" {
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"profile": profile, "sourceCommitment": sourceCommitment, "policySha256": policyCommitment})
	}
	if len(os.Args) == 5 && os.Args[1] == "--authenticate" {
		c, e := limited(os.Args[2], 65536)
		if e != nil {
			return e
		}
		p, e := limited(os.Args[3], 65536)
		if e != nil {
			return e
		}
		raw, e := limited(os.Args[4], 8<<20)
		if e != nil {
			return e
		}
		caps, _, o, e := openInputs(c, p, raw)
		if e != nil {
			return e
		}
		o.Bridge.Close()
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "PROOFS_VERIFIED_AT_DECLARED_ROOT", "capsuleId": caps.ID, "canonicality": "OPERATOR_CHECKPOINT_TRUST_REQUIRED", "witnessClosure": "NOT_EVALUATED", "nativeExecutions": 0})
	}
	if len(os.Args) != 2 || os.Args[1] != "--execute-once" {
		return errors.New("FRESH_CAPSULE_AUTHORITY_REQUIRED")
	}
	exe, e := os.Executable()
	if e != nil {
		return e
	}
	root := filepath.Dir(filepath.Dir(exe))
	rt := filepath.Join(root, "runtime")
	read := func(name string, max int64) ([]byte, error) { return limited(filepath.Join(root, name), max) }
	c, e := read("inputs/CAPSULE.json", 65536)
	if e != nil {
		return e
	}
	p, e := read("inputs/PLAN.json", 65536)
	if e != nil {
		return e
	}
	raw, e := read("inputs/BLOCK_PACKAGE.json", 8<<20)
	if e != nil {
		return e
	}
	authority, e := io.ReadAll(io.LimitReader(os.Stdin, 65537))
	if e != nil || len(authority) > 65536 {
		return errors.New("AUTHORITY_SIZE")
	}
	var a struct {
		Schema  string         `json:"schema"`
		Binding map[string]any `json:"binding"`
		Begin   int64          `json:"notBeforeUnix"`
		End     int64          `json:"expiresUnix"`
		Owner   bool           `json:"localOwnerConfirmed"`
		NoRetry bool           `json:"noRetry"`
	}
	if e = jsonValue(authority, &a); e != nil {
		return e
	}
	b := a.Binding
	binary, e := limited(exe, 256<<20)
	if e != nil {
		return e
	}
	now := time.Now().Unix()
	if a.Schema != "rhook/case-consent/0.1" || !a.Owner || !a.NoRetry || now < a.Begin || now >= a.End || a.End-a.Begin > 600 || a.End <= a.Begin {
		return errors.New("FRESH_AUTHORITY_WINDOW")
	}
	if b["binarySha256"] != digest(binary) || b["sourceCommitment"] != sourceCommitment || b["policySha256"] != policyCommitment || b["capsuleSha256"] != digest(c) || b["planSha256"] != digest(p) || b["packageSha256"] != digest(raw) || b["outputPath"] != root || b["profile"] != profile || sourceCommitment == "" || policyCommitment == "" {
		return errors.New("EXACT_ARTIFACT_AUTHORITY_REQUIRED")
	}
	var started map[string]any
	s, e := read("runtime/STARTED.json", 4096)
	if e != nil {
		return e
	}
	if e = jsonValue(s, &started); e != nil {
		return e
	}
	if started["authoritySha256"] != digest(authority) || started["operationCommitment"] != b["operationCommitment"] {
		return errors.New("CONSUMED_AUTHORITY_LINK")
	}
	var gate map[string]any
	s, e = read("runtime/HOST_ADMISSION.json", 65536)
	if e != nil {
		return e
	}
	if e = jsonValue(s, &gate); e != nil {
		return e
	}
	if gate["accepted"] != true || gate["policySha256"] != policyCommitment || gate["profile"] != profile {
		return errors.New("HOST_ADMISSION_REQUIRED")
	}
	var failure map[string]any
	calls := 0
	var pdoc request
	if e = jsonValue(p, &pdoc); e != nil {
		return e
	}
	controller := pair{dir: rt, plan: pdoc.Runtime, factory: func() (world, error) {
		phase := "ACTUAL"
		if calls > 0 {
			phase = "BRANCH"
		}
		calls++
		caps, req, o, e := openInputs(c, p, raw)
		if e != nil {
			var h *prestate.HostStop
			if errors.As(e, &h) {
				class, _ := prestate.ClassifyCalibrationError(e)
				failure = map[string]any{"phase": phase, "code": h.Code, "classification": class}
			}
			return nil, e
		}
		return &capsuleWorld{o, req.Runtime, caps.Adapter.Config.Code, phase, &failure}, nil
	}}
	result, e := controller.run()
	if e != nil {
		result.Terminal = "INTERRUPTED_UNVERIFIED"
		result.Cause = e.Error()
	}
	n := map[string]any{"operationCommitment": b["operationCommitment"], "result": result}
	if failure != nil {
		n["failureDetail"] = failure
	}
	if e := store(rt, "NATIVE_COMPLETION.json", n); e != nil {
		return e
	}
	if result.Terminal != "GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED" {
		return errors.New(result.Terminal)
	}
	return nil
}
