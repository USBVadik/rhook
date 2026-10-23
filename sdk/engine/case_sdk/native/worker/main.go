package main

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unicode/utf8"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	prestate "local/rhook-robinhood"
)

//go:embed case.json
var caseBytes []byte
var sourceCommitment string
var policyCommitment string

const domain = "HOOKR_UNIFIED_PLAN_NATIVE_0_1"
const profile = "hookr-case-darwin-arm64/0.1"

type RuntimePlan struct {
	Raw      []byte
	Document map[string]any
	Plan     Plan
}
type Binding = map[string]any
type Approval = map[string]any

func strictJSON(raw []byte) (any, error) {
	if !utf8.Valid(raw) {
		return nil, errors.New("INVALID_UTF8")
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	var parse func(int) (any, error)
	parse = func(depth int) (any, error) {
		if depth > 64 {
			return nil, errors.New("JSON_DEPTH")
		}
		t, e := d.Token()
		if e != nil {
			return nil, e
		}
		switch v := t.(type) {
		case json.Delim:
			if v == '{' {
				m := map[string]any{}
				for d.More() {
					k, e := d.Token()
					if e != nil {
						return nil, e
					}
					s, ok := k.(string)
					if !ok {
						return nil, errors.New("JSON_KEY")
					}
					if _, ok = m[s]; ok {
						return nil, errors.New("DUPLICATE_KEY")
					}
					x, e := parse(depth + 1)
					if e != nil {
						return nil, e
					}
					m[s] = x
				}
				_, e = d.Token()
				return m, e
			}
			if v == '[' {
				a := []any{}
				for d.More() {
					x, e := parse(depth + 1)
					if e != nil {
						return nil, e
					}
					a = append(a, x)
				}
				_, e = d.Token()
				return a, e
			}
			return nil, errors.New("JSON_DELIMITER")
		case json.Number:
			if !regexp.MustCompile(`^(0|-?[1-9][0-9]*)$`).MatchString(string(v)) {
				return nil, errors.New("INTEGER_REQUIRED")
			}
			n, e := strconv.ParseInt(string(v), 10, 64)
			if e != nil || math.Abs(float64(n)) > 9007199254740991 {
				return nil, errors.New("INTEGER_RANGE")
			}
			return v, nil
		default:
			return v, nil
		}
	}
	v, e := parse(0)
	if e != nil {
		return nil, e
	}
	if _, e = d.Token(); e != io.EOF {
		return nil, errors.New("JSON_TRAILING_CONTENT")
	}
	return v, nil
}
func quote(s string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			if r < 32 {
				fmt.Fprintf(&b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}
func canonicalJSON(v any) []byte {
	switch x := v.(type) {
	case map[string]any:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		items := []string{}
		for _, k := range keys {
			items = append(items, quote(k)+":"+string(canonicalJSON(x[k])))
		}
		return []byte("{" + strings.Join(items, ",") + "}")
	case []any:
		items := []string{}
		for _, v := range x {
			items = append(items, string(canonicalJSON(v)))
		}
		return []byte("[" + strings.Join(items, ",") + "]")
	case string:
		return []byte(quote(x))
	default:
		b, _ := json.Marshal(v)
		return b
	}
}
func hashBody(domain string, v map[string]any) string {
	return digest(append([]byte(domain+"\n"), canonicalJSON(v)...))
}
func runtimeForValue(value string, descriptor []byte) ([]byte, error) {
	if !regexp.MustCompile(`^(0|[1-9][0-9]?)$`).MatchString(value) {
		return nil, errors.New("CASE_LP_RANGE")
	}
	v, e := strictJSON(descriptor)
	if e != nil {
		return nil, e
	}
	d, ok := v.(map[string]any)
	if !ok {
		return nil, errors.New("DESCRIPTOR_OBJECT")
	}
	p := d["plan"].(map[string]any)
	i := p["intervention"].(map[string]any)
	old := common.HexToHash(i["expectedOldWord"].(string))
	next := old
	n, _ := strconv.Atoi(value)
	next[10] = 0
	next[11] = byte(n)
	i["newWord"] = next.Hex()
	body := map[string]any{"schema": "rhook/hookr-plan/0.2", "caseId": d["caseId"], "caseDescriptorSha256": digest(descriptor), "packageSha256": p["packageSha256"], "ruleId": d["ruleId"], "expectedOld": "100", "newValue": value, "intervention": i, "status": "PLANNED", "branchResult": nil, "executionAuthorized": false, "witnessClosure": "NOT_EVALUATED"}
	runtime := map[string]any{"schema": "rhook/hookr-runtime-plan/0.2", "caseDescriptorSha256": digest(descriptor), "semanticPlanCommitment": hashBody("rhook/hookr-plan/0.2", body), "newValue": value, "plan": p}
	return append(canonicalJSON(runtime), '\n'), nil
}
func AdmitRuntime(raw []byte, descriptor []byte) (RuntimePlan, error) {
	var p RuntimePlan
	if len(raw) > 32768 {
		return p, errors.New("RUNTIME_SIZE")
	}
	v, e := strictJSON(raw)
	if e != nil {
		return p, e
	}
	doc, ok := v.(map[string]any)
	if !ok {
		return p, errors.New("RUNTIME_OBJECT")
	}
	value, ok := doc["newValue"].(string)
	if !ok {
		return p, errors.New("DECIMAL_REQUIRED")
	}
	expected, e := runtimeForValue(value, descriptor)
	if e != nil {
		return p, e
	}
	if !bytes.Equal(raw, expected) {
		return p, errors.New("EXACT_RUNTIME_PLAN_REQUIRED")
	}
	encoded := canonicalJSON(doc["plan"])
	if e = json.Unmarshal(encoded, &p.Plan); e != nil {
		return p, e
	}
	if e = prestate.ValidateCaseLPIntervention(p.Plan.Intervention, p.Plan.Checkpoint); e != nil {
		return p, e
	}
	p.Raw = append([]byte(nil), raw...)
	p.Document = doc
	return p, nil
}
func number(v any) int64 {
	n, ok := v.(json.Number)
	if !ok {
		return -1
	}
	i, e := strconv.ParseInt(string(n), 10, 64)
	if e != nil {
		return -1
	}
	return i
}
func checkAuthority(a Approval, b Binding, p RuntimePlan, root, binary string, now time.Time) error {
	fail := errors.New("EXACT_FRESH_PLAN_AUTHORITY_REQUIRED")
	keys := strings.Fields("schema domain profile workspace planId outputPath packagePath semanticPlanPath runtimePlanPath sourceCommitment binarySha256 caseDescriptorSha256 policySha256 sensorPath sensorSha256 nodePath nodeSha256 verifierDependenciesCommitment semanticPlanCommitment runtimePlanSha256 packageSha256 inputCommitment witnessCommitment limits workflowSeconds nativeStageSeconds maximumInvocations RPC WSS executionContext externalDelivery requestCommitment operationCommitment")
	if len(b) != len(keys) {
		return fail
	}
	for _, k := range keys {
		if _, ok := b[k]; !ok {
			return fail
		}
	}

	expected := cloneBinding(b)
	for _, k := range []string{"founderApproved", "macOnPowerOpenLid", "noRetry"} {
		expected[k] = true
	}
	expected["notBeforeUnix"] = a["notBeforeUnix"]
	expected["expiresUnix"] = a["expiresUnix"]
	if !bytes.Equal(canonicalJSON(expected), canonicalJSON(a)) {
		return fail
	}
	begin, end := number(a["notBeforeUnix"]), number(a["expiresUnix"])
	if begin < 0 || end-begin > 600 || begin > now.Unix() || now.Unix() >= end {
		return fail
	}
	body := cloneBinding(b)
	delete(body, "operationCommitment")
	if b["operationCommitment"] != hashBody("rhook/hookr-operation/0.2", body) {
		return fail
	}
	delete(body, "requestCommitment")
	if b["requestCommitment"] != hashBody("rhook/native-plan-request/0.2", body) {
		return fail
	}
	checks := map[string]any{"schema": "rhook/native-plan-request/0.2", "domain": domain, "profile": profile, "sourceCommitment": sourceCommitment, "policySha256": policyCommitment, "binarySha256": binary, "caseDescriptorSha256": digest(caseBytes), "semanticPlanCommitment": p.Document["semanticPlanCommitment"], "runtimePlanSha256": digest(p.Raw), "packageSha256": p.Plan.PackageSHA, "inputCommitment": p.Plan.Input, "witnessCommitment": p.Plan.Witness, "outputPath": root, "executionContext": "require_escalated", "RPC": json.Number("0"), "WSS": json.Number("0"), "maximumInvocations": map[string]any{"ACTUAL": json.Number("1"), "BRANCH": json.Number("1"), "B": json.Number("0")}}
	if sourceCommitment == "" || policyCommitment == "" {
		return fail
	}
	for k, v := range checks {
		if !bytes.Equal(canonicalJSON(b[k]), canonicalJSON(v)) {
			return fail
		}
	}
	workspace, ok := b["workspace"].(string)
	id, ok2 := b["planId"].(string)
	if !ok || !ok2 || !regexp.MustCompile(`^[0-9a-f]{32}$`).MatchString(id) || filepath.Join(workspace, "runs", id) != root {
		return fail
	}

	if !filepath.IsAbs(workspace) || filepath.Clean(workspace) != workspace {
		return fail
	}
	fixedLimits, e := strictJSON([]byte(`{"GOMAXPROCS":2,"GOMEMLIMIT_advisoryBytes":536870912,"hostGateSeconds":8,"maximumTelemetryGapSeconds":2,"memoryEnforcement":"SAMPLED_NOT_HARD_RESERVATION_OR_EXACT_PEAK","overallAfterConsumptionSeconds":140,"ownedCleanupSeconds":5,"pairWallSeconds":120,"perFileKernelBytes":67108864,"sampledRuntimeBytes":134217728,"stdoutStderrBytes":67108864,"workerKernelCpuSeconds":120,"workerSampledRssBytes":1073741824,"workerTelemetryMs":100}`))
	if e != nil {
		return fail
	}
	fixed := map[string]any{"workflowSeconds": json.Number("180"), "nativeStageSeconds": json.Number("140"), "externalDelivery": "HOLD", "packagePath": filepath.Join(workspace, "BLOCK_PACKAGE.json"), "semanticPlanPath": filepath.Join(workspace, "plans", id, "semantic.json"), "runtimePlanPath": filepath.Join(workspace, "plans", id, "runtime.json"), "limits": fixedLimits}
	for k, v := range fixed {
		if !bytes.Equal(canonicalJSON(b[k]), canonicalJSON(v)) {
			return fail
		}
	}
	return nil
}
func cloneBinding(b map[string]any) map[string]any {
	r := map[string]any{}
	for k, v := range b {
		r[k] = v
	}
	return r
}
func limitedFile(path string, maximum int64) ([]byte, error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return nil, errors.New("EXPLICIT_PATH_REQUIRED")
	}
	for p := path; ; p = filepath.Dir(p) {
		info, e := os.Lstat(p)
		if e != nil {
			return nil, e
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, errors.New("SYMLINK_INPUT")
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
	info, e := f.Stat()
	if e != nil {
		return nil, e
	}
	if !info.Mode().IsRegular() || info.Size() > maximum {
		return nil, errors.New("INPUT_TYPE_OR_SIZE")
	}
	raw, e := io.ReadAll(io.LimitReader(f, maximum+1))
	if int64(len(raw)) > maximum {
		return nil, errors.New("INPUT_LIMIT")
	}
	return raw, e
}
func failureDetail(phase string, e error) map[string]any {
	if e == nil {
		return nil
	}
	var h *prestate.HostStop
	if !errors.As(e, &h) {
		return nil
	}
	classification, _ := prestate.ClassifyCalibrationError(e)
	return map[string]any{"phase": phase, "code": h.Code, "classification": classification}
}

type runtimeWorld struct {
	offline *prestate.OfflineCalibration
	plan    Plan
	failure *map[string]any
}

func (w *runtimeWorld) Run(i *prestate.LPIntervention) (*prestate.CalibrationResult, error) {
	r, e := prestate.RunHookrPlanned(w.offline.Candidate, w.offline.Bridge, i, w.plan.Observation)
	if w.failure != nil && e != nil {
		phase := "ACTUAL"
		if i != nil {
			phase = "BRANCH"
		}
		*w.failure = failureDetail(phase, e)
	}
	return r, e
}
func (w *runtimeWorld) Attempts() []prestate.Attempt { return w.offline.Attempts() }
func (w *runtimeWorld) Close()                       { w.offline.Bridge.Close() }
func freshRuntime(raw []byte, r RuntimePlan) (world, error) {
	p := r.Plan
	if digest(raw) != p.PackageSHA {
		return nil, errors.New("PACKAGE_SHA256_MISMATCH")
	}
	o, e := prestate.PrepareOfflineCalibration(raw, p.Input, p.Witness)
	if e != nil {
		return nil, e
	}
	fail := func(e error) (world, error) { o.Bridge.Close(); return nil, e }
	inv := o.Inventory
	if inv.Checkpoint != p.Checkpoint || inv.BlockNumber != p.Block || inv.BlockHash != p.BlockHash || inv.ExpectedStateRoot != p.StateRoot || inv.ExpectedReceiptsRoot != p.ReceiptsRoot || inv.Transactions != 7 || len(o.TxHashes) != 7 {
		return fail(errors.New("SAVED_INPUT_IDENTITY"))
	}
	arrivals := r.Document["plan"].(map[string]any)["arrivals"].([]any)
	for j, h := range o.TxHashes {
		if h.Hex() != arrivals[j] {
			return fail(errors.New("ARRIVAL_ORDER"))
		}
	}
	var pkg prestate.BlockPackage
	if e = json.Unmarshal(raw, &pkg); e != nil {
		return fail(e)
	}
	var tx types.Transaction
	if e = tx.UnmarshalBinary(pkg.Raw[3]); e != nil {
		return fail(e)
	}
	sender, e := types.Sender(types.LatestSignerForChainID(tx.ChainId()), &tx)
	if e != nil || sender != p.Sender || tx.To() == nil || *tx.To() != p.Router || tx.Hash() != p.Subject {
		return fail(errors.New("SUBJECT_IDENTITY"))
	}
	e = o.Bridge.Protect(func() error {
		s, e := o.Bridge.State()
		if e != nil {
			return e
		}
		code := common.HexToHash("0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b")
		i := p.Intervention
		if !s.Exist(i.Account) || s.GetCodeHash(i.Account) != code || crypto.Keccak256Hash(s.GetCode(i.Account)) != code || s.GetState(i.Account, i.Slot) != i.ExpectedOldWord {
			return errors.New("ORIGINAL_RULES_ACCOUNT_CODE_WORD")
		}
		return s.Error()
	})
	if e != nil {
		return fail(e)
	}
	return &runtimeWorld{offline: o, plan: p}, nil
}
func main() {
	if e := mainEntry(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
func mainEntry() error {
	if len(os.Args) != 2 || os.Args[1] != "--execute-once" {
		return errors.New("FRESH_APPROVAL_REQUIRED")
	}
	exe, e := os.Executable()
	if e != nil {
		return e
	}
	root := filepath.Dir(filepath.Dir(exe))
	rt := filepath.Join(root, "runtime")
	readObject := func(p string, max int64) (map[string]any, error) {
		raw, e := limitedFile(p, max)
		if e != nil {
			return nil, e
		}
		v, e := strictJSON(raw)
		if e != nil {
			return nil, e
		}
		m, ok := v.(map[string]any)
		if !ok {
			return nil, errors.New("OBJECT_REQUIRED")
		}
		return m, nil
	}
	b, e := readObject(filepath.Join(root, "proposal/AUTHORIZATION_BINDINGS.json"), 65536)
	if e != nil {
		return e
	}
	raw, e := limitedFile(filepath.Join(root, "inputs/RUNTIME_PLAN.json"), 32768)
	if e != nil {
		return e
	}
	p, e := AdmitRuntime(raw, caseBytes)
	if e != nil {
		return e
	}
	approval, e := io.ReadAll(io.LimitReader(os.Stdin, 16384))
	if e != nil || len(approval) >= 16384 {
		return errors.New("APPROVAL_SIZE")
	}
	v, e := strictJSON(approval)
	if e != nil {
		return e
	}
	a, ok := v.(map[string]any)
	if !ok {
		return errors.New("APPROVAL_OBJECT")
	}
	binary, e := limitedFile(exe, 256<<20)
	if e != nil {
		return e
	}
	if e = checkAuthority(a, b, p, root, digest(binary), time.Now()); e != nil {
		return e
	}
	started, e := readObject(filepath.Join(rt, "STARTED.json"), 16384)
	if e != nil {
		return e
	}
	if started["authoritySha256"] != digest(approval) || started["operationCommitment"] != b["operationCommitment"] {
		return errors.New("STARTED_LINK")
	}
	gate, e := readObject(filepath.Join(rt, "HOST_ADMISSION.json"), 65536)
	if e != nil {
		return e
	}
	if gate["accepted"] != true || gate["profile"] != profile || gate["policySha256"] != policyCommitment {
		return errors.New("HOST_ADMISSION_REQUIRED")
	}
	packageRaw, e := limitedFile(filepath.Join(root, "inputs/BLOCK_PACKAGE.json"), 2<<20)
	if e != nil {
		return e
	}
	var detail map[string]any
	calls := 0
	controller := pair{plan: p.Plan, dir: rt, factory: func() (world, error) {
		phase := "ACTUAL"
		if calls > 0 {
			phase = "BRANCH"
		}
		calls++
		w, e := freshRuntime(packageRaw, p)
		if e != nil {
			detail = failureDetail(phase, e)
			return nil, e
		}
		w.(*runtimeWorld).failure = &detail
		return w, nil
	}}
	result, e := controller.run()
	if e != nil {
		result.Terminal = "INTERRUPTED_UNVERIFIED"
		result.Cause = e.Error()
	}
	completion := map[string]any{"operationCommitment": b["operationCommitment"], "runtimePlanSha256": digest(p.Raw), "result": result}
	if detail != nil {
		completion["failureDetail"] = detail
	}
	if se := store(rt, "NATIVE_COMPLETION.json", completion); se != nil {
		return se
	}
	if e != nil {
		return e
	}
	if result.Terminal != "GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED" {
		return errors.New(result.Terminal)
	}
	return nil
}
