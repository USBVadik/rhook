package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"
)

func main() {
	if e := mainEntry(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
func mainEntry() error {
	p := loadPlan()
	if len(os.Args) == 2 && os.Args[1] == "--describe" {
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"plan": p, "embeddedPlanSha256": digest(planBytes), "nativeInvocations": Counts{}, "RPC": 0, "WSS": 0})
	}
	if len(os.Args) != 2 || os.Args[1] != "--execute-once" {
		return errors.New("EXACT_FOUNDER_AUTHORITY_AND_SUPERVISOR_REQUIRED")
	}
	exe, e := os.Executable()
	if e != nil {
		return e
	}
	root := filepath.Dir(filepath.Dir(exe))
	dir := filepath.Join(root, "runtime")
	b, e := os.ReadFile(filepath.Join(root, "proposal/AUTHORIZATION_BINDINGS.json"))
	if e != nil {
		return e
	}
	var binding struct {
		Operation string `json:"operationCommitment"`
		Binary    string `json:"binarySha256"`
		Plan      string `json:"planSha256"`
	}
	if e = json.Unmarshal(b, &binding); e != nil {
		return e
	}
	// Payload comes only from the already consumed supervisor. This is a trusted
	// local workflow latch, not a cryptographic authorization service.
	payload, e := io.ReadAll(io.LimitReader(os.Stdin, 16385))
	if e != nil || len(payload) > 16384 {
		return errors.New("AUTHORITY_PAYLOAD_LIMIT")
	}
	var auth struct {
		Approved  bool   `json:"founderApproved"`
		Operation string `json:"operationCommitment"`
		Binary    string `json:"binarySha256"`
		Runtime   string `json:"runtimePath"`
		Expires   int64  `json:"expiresUnix"`
	}
	if e = json.Unmarshal(payload, &auth); e != nil {
		return e
	}
	binary, e := os.ReadFile(exe)
	if e != nil {
		return e
	}
	if !auth.Approved || auth.Operation != binding.Operation || auth.Binary != binding.Binary || digest(binary) != binding.Binary || binding.Plan != digest(planBytes) || auth.Runtime != dir || time.Now().Unix() >= auth.Expires {
		return errors.New("EXACT_AUTHORITY_BINDINGS_REQUIRED")
	}
	started, e := os.ReadFile(filepath.Join(dir, "STARTED.json"))
	if e != nil {
		return e
	}
	var start struct {
		Authority string `json:"authoritySha256"`
		Operation string `json:"operationCommitment"`
	}
	if e = json.Unmarshal(started, &start); e != nil {
		return e
	}
	if start.Authority != digest(payload) || start.Operation != binding.Operation {
		return errors.New("STARTED_AUTHORITY_LINK_MISMATCH")
	}
	host, e := os.ReadFile(filepath.Join(dir, "HOST_ADMISSION.json"))
	if e != nil {
		return e
	}
	var gate struct {
		Accepted bool `json:"accepted"`
	}
	if e = json.Unmarshal(host, &gate); e != nil || !gate.Accepted {
		return errors.New("FAIL_CLOSED_HOST_ADMISSION_REQUIRED")
	}
	raw, e := os.ReadFile(p.PackagePath)
	if e != nil {
		return e
	}
	controller := pair{plan: p, dir: dir, factory: func() (world, error) { return fresh(raw, p) }}
	out, e := controller.run()
	if e != nil {
		out.Terminal = "INTERRUPTED_UNVERIFIED"
		out.Cause = e.Error()
	}
	if se := store(dir, "NATIVE_COMPLETION.json", map[string]any{"operationCommitment": binding.Operation, "result": out}); se != nil {
		return se
	}
	if e != nil {
		return e
	}
	if out.Terminal != "GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED" {
		return errors.New(out.Terminal + ": " + out.Cause)
	}
	return nil
}
