package scenario

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"syscall"
	"time"
)

const RuntimeProfile = "nitro-hookr-scenario/0.1"

type workerFence struct {
	engine  Identity
	count   int
	maximum int
}

func (f *workerFence) Check(ctx context.Context, i Identity, phase string) error {
	if e := ctx.Err(); e != nil {
		return e
	}
	if i != f.engine {
		return errors.New("ENGINE_BINDING")
	}
	return nil
}
func (f *workerFence) Enter(ctx context.Context, label string) error {
	want := Baseline
	if f.count == 1 {
		want = Variant
	}
	if e := ctx.Err(); e != nil {
		return e
	}
	maximum := f.maximum
	if maximum == 0 {
		maximum = 2
	}
	if f.count >= maximum || label != want {
		return errors.New("SCENARIO_INVOCATION_LIMIT")
	}
	f.count++
	return nil
}
func boundedFile(path string, maximum int64) ([]byte, error) {
	for p := path; ; p = filepath.Dir(p) {
		s, e := os.Lstat(p)
		if e != nil {
			return nil, e
		}
		if s.Mode()&os.ModeSymlink != 0 {
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
	if !s.Mode().IsRegular() || s.Size() > maximum {
		return nil, errors.New("FILE_TYPE_OR_SIZE")
	}
	b, e := io.ReadAll(io.LimitReader(f, maximum+1))
	if int64(len(b)) > maximum {
		return nil, errors.New("FILE_SIZE")
	}
	return b, e
}
func decode(raw []byte, out any) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	if e := d.Decode(out); e != nil {
		return e
	}
	var tail any
	if d.Decode(&tail) != io.EOF {
		return errors.New("JSON_TRAILING")
	}
	return nil
}

// WorkerEntry is separate from historical replay. Source and policy are linked
// into a derivative binary; no authenticated chain outcome is fabricated.
func WorkerEntry(source, policy string, args []string) (resultError error) {
	if len(args) == 1 && args[0] == "--identity" {
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"profile": LinkedProfile, "sourceCommitment": source, "policySha256": policy})
	}
	if len(args) == 2 && args[0] == "--authenticate" {
		raw, e := boundedFile(args[1], 8<<20)
		if e != nil {
			return e
		}
		a, e := admitRuntime(raw)
		if e != nil {
			return e
		}
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "AUTHENTICATED_SCENARIO_INPUT", "scenarioCommitment": a.input.spec.Commitment, "nativeExecutions": 0, "coverage": "KNOWN_PREREQUISITES_ONLY"})
	}
	if len(args) == 2 && args[0] == "--authenticate-overlay" {
		raw, e := boundedFile(args[1], 8<<20)
		if e != nil {
			return e
		}
		if LinkedProfile != DynamicRuntimeProfile {
			return errors.New("DYNAMIC_DERIVATIVE_REQUIRED")
		}
		a, e := admitRuntime(raw)
		if e != nil {
			return e
		}
		base, e := deriveDynamicOverlay(a.input, Baseline)
		if e != nil {
			return e
		}
		variant, e := deriveDynamicOverlay(a.input, Variant)
		if e != nil {
			return e
		}
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "DYNAMIC_OVERLAY_STATE_AUTHENTICATED", "scenarioCommitment": a.input.spec.Commitment, "interventionCommitment": a.input.spec.Intervention.Commitment, "baseline": base, "variant": variant, "nativeExecutions": 0, "EVMReexecution": false, "coverage": "TARGET_TRANSFORM_ONLY_NOT_EXECUTION_CLOSURE"})
	}
	if len(args) == 3 && args[0] == "--verify" {
		raw, e := boundedFile(args[1], 8<<20)
		if e != nil {
			return e
		}
		result, e := boundedFile(args[2], 8<<20)
		if e != nil {
			return e
		}
		if LinkedProfile == DynamicRuntimeProfile {
			e = VerifyDynamicEvidence(raw, result)
		} else {
			e = VerifyEvidence(raw, result)
		}
		if e != nil {
			return e
		}
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "SCENARIO_RECORDED_INTEGRITY_PASS", "EVMReexecution": false, "qualifiedClaims": 0})
	}
	if len(args) != 1 || args[0] != "--execute-once" {
		return errors.New("FRESH_SCENARIO_AUTHORITY_REQUIRED")
	}
	exe, e := os.Executable()
	if e != nil {
		return e
	}
	root := filepath.Dir(filepath.Dir(exe))
	rt := filepath.Join(root, "runtime")
	raw, e := boundedFile(filepath.Join(root, "inputs/SCENARIO.json"), 8<<20)
	if e != nil {
		return e
	}
	consent, e := io.ReadAll(io.LimitReader(os.Stdin, 65537))
	if e != nil || len(consent) > 65536 {
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
	if e = decode(consent, &a); e != nil {
		return e
	}
	now := time.Now().Unix()
	b := a.Binding
	if a.Schema != "rhook/case-consent/0.1" || !a.Owner || !a.NoRetry || now < a.Begin || now >= a.End || a.End <= a.Begin || a.End-a.Begin > 600 {
		return errors.New("FRESH_AUTHORITY_WINDOW")
	}
	binary, e := boundedFile(exe, 256<<20)
	if e != nil {
		return e
	}
	if source == "" || policy == "" || b["profile"] != LinkedProfile || b["binarySha256"] != digest(binary) || b["sourceCommitment"] != source || b["policySha256"] != policy || b["scenarioSha256"] != digest(raw) || b["outputPath"] != root {
		return errors.New("EXACT_SCENARIO_BINDING")
	}
	var started, gate map[string]any
	data, e := boundedFile(filepath.Join(rt, "STARTED.json"), 4096)
	if e != nil {
		return e
	}
	if e = decode(data, &started); e != nil {
		return e
	}
	if started["authoritySha256"] != digest(consent) || started["operationCommitment"] != b["operationCommitment"] {
		return errors.New("CONSUMED_AUTHORITY_LINK")
	}
	data, e = boundedFile(filepath.Join(rt, "HOST_ADMISSION.json"), 65536)
	if e != nil {
		return e
	}
	if e = decode(data, &gate); e != nil {
		return e
	}
	if gate["accepted"] != true || gate["profile"] != LinkedProfile || gate["policySha256"] != policy {
		return errors.New("HOST_ADMISSION_REQUIRED")
	}
	if LinkedProfile == DynamicRuntimeProfile && (b["discoveryProfile"] != nil || b["diagnosticProfile"] != nil) {
		return errors.New("DYNAMIC_OFFLINE_PAIR_ONLY")
	}
	var discovery *discoverySource
	var accepted *Admission
	if b["discoveryProfile"] != nil {
		parsed, err := Parse(raw)
		if err != nil {
			return err
		}
		discovery, e = discoveryFor(root, b, parsed.Checkpoint)
		if e != nil {
			return e
		}
		defer func() {
			remaining := int64(16 << 20)
			err := store(rt, "DISCOVERY_ACCESSES.json", map[string]any{"profile": DiscoveryProfile, "discoveryOnly": true, "checkpoint": parsed.Checkpoint, "sourceRequests": discovery.calls, "sourceResponseBytes": discovery.bytes, "accesses": discovery.rows}, &remaining)
			resultError = errors.Join(resultError, err)
		}()
		accepted, e = admitWithSource(raw, officialProfile(), discovery)
	} else {
		accepted, e = admitRuntime(raw)
	}
	if e != nil {
		return e
	}
	diagnostic := b["diagnosticProfile"] != nil
	if diagnostic {
		if e = enableDiagnostic(accepted, b); e != nil {
			return e
		}
	} else if accepted.input.spec.Engine != (Identity{source, digest(binary), policy}) {
		return errors.New("SPEC_ENGINE_BINDING")
	}
	remaining := int64(64 << 20)
	maximum := 2
	if diagnostic {
		maximum = 1
	}
	if e = store(rt, "SCENARIO_CONSUMED.json", map[string]any{"operationCommitment": b["operationCommitment"], "maximumWorlds": maximum}, &remaining); e != nil {
		return e
	}
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	fence := &workerFence{engine: accepted.input.spec.Engine, maximum: maximum}
	var controller Controller
	result, runError := controller.Execute(ctx, accepted, fence, filepath.Join(rt, "scenario"))
	lookups := 0
	if discovery != nil {
		lookups = discovery.calls
	}
	if e = store(rt, "NATIVE_COMPLETION.json", map[string]any{"operationCommitment": b["operationCommitment"], "result": result, "producerEntries": fence.count, "RPC": 0, "WSS": 0, "localDiscoveryLookups": lookups, "discoveryOnly": discovery != nil, "diagnosticOnly": diagnostic}, &remaining); e != nil {
		return e
	}
	if runError != nil {
		return runError
	}
	if diagnostic {
		if result.Status != "SCENARIO_DIAGNOSTIC_COMPLETED" || fence.count != 1 {
			return errors.New("DIAGNOSTIC_INCOMPLETE")
		}
		return nil
	}
	if discovery != nil {
		if result.Status != "SCENARIO_DISCOVERY_COMPLETED" || fence.count != 2 {
			return errors.New("DISCOVERY_INCOMPLETE")
		}
		return discovery.finish(ctx)
	}
	if result.Status != "SCENARIO_EXECUTED_UNQUALIFIED" {
		return fmt.Errorf("SCENARIO_STOP: %s", result.Status)
	}
	return nil
}
