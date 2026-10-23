package main

import (
	"encoding/json"
	"fmt"
	prestate "local/rhook-robinhood"
	"os"
	"path/filepath"
	"syscall"
	"testing"
	"time"
)

func TestRuntimePlanAcceptsAllValues(t *testing.T) {
	for n := 0; n < 100; n++ {
		raw, e := runtimeForValue(fmt.Sprint(n), caseBytes)
		if e != nil {
			t.Fatal(e)
		}
		p, e := AdmitRuntime(raw, caseBytes)
		if e != nil || p.Plan.Intervention.NewWord[11] != byte(n) {
			t.Fatalf("value%d: %v", n, e)
		}
	}
	for _, n := range []string{"100", "-1", "01", "true"} {
		if _, e := runtimeForValue(n, caseBytes); e == nil {
			t.Fatal(n)
		}
	}
}
func TestRuntimeRejectsRehashedScopeAndJSON(t *testing.T) {
	raw, _ := runtimeForValue("50", caseBytes)
	var v map[string]any
	json.Unmarshal(raw, &v)
	v["plan"].(map[string]any)["slot"] = "wrong"
	bad, _ := json.Marshal(v)
	if _, e := AdmitRuntime(bad, caseBytes); e == nil {
		t.Fatal("extra field")
	}
	for _, raw := range []string{`{"a":1,"a":2}`, `1e1`, `[`, string([]byte{'"', 255, '"'})} {
		if _, e := strictJSON([]byte(raw)); e == nil {
			t.Fatal(raw)
		}
	}
}
func TestRuntimeAuthorityBindsEveryPin(t *testing.T) {
	raw, _ := runtimeForValue("50", caseBytes)
	p, _ := AdmitRuntime(raw, caseBytes)
	sourceCommitment = "source"
	policyCommitment = "policy"
	b := testBinding(p)
	a := testApproval(b)
	if e := checkAuthority(a, b, p, "/private/tmp/work/runs/00000000000000000000000000000000", "binary", time.Unix(1000, 0)); e != nil {
		t.Fatal(e)
	}
	for k := range b {
		bad := cloneMap(a)
		bad[k] = "changed"
		if checkAuthority(bad, b, p, "/private/tmp/work/runs/00000000000000000000000000000000", "binary", time.Unix(1000, 0)) == nil {
			t.Fatal(k)
		}
	}
}
func testBinding(p RuntimePlan) map[string]any {
	b := map[string]any{"schema": "rhook/native-plan-request/0.2", "domain": domain, "profile": profile, "sourceCommitment": "source", "policySha256": "policy", "binarySha256": "binary", "caseDescriptorSha256": digest(caseBytes), "semanticPlanCommitment": p.Document["semanticPlanCommitment"], "runtimePlanSha256": digest(p.Raw), "packageSha256": p.Plan.PackageSHA, "inputCommitment": p.Plan.Input, "witnessCommitment": p.Plan.Witness, "outputPath": "/private/tmp/work/runs/00000000000000000000000000000000", "workspace": "/private/tmp/work", "planId": "00000000000000000000000000000000", "executionContext": "require_escalated", "maximumInvocations": map[string]any{"ACTUAL": json.Number("1"), "BRANCH": json.Number("1"), "B": json.Number("0")}, "RPC": json.Number("0"), "WSS": json.Number("0")}
	for _, k := range []string{"packagePath", "semanticPlanPath", "runtimePlanPath", "sensorPath", "sensorSha256", "nodePath", "nodeSha256", "verifierDependenciesCommitment", "limits", "workflowSeconds", "nativeStageSeconds", "externalDelivery"} {
		b[k] = "test-pin"
	}

	b["packagePath"] = "/private/tmp/work/BLOCK_PACKAGE.json"
	b["semanticPlanPath"] = "/private/tmp/work/plans/00000000000000000000000000000000/semantic.json"
	b["runtimePlanPath"] = "/private/tmp/work/plans/00000000000000000000000000000000/runtime.json"
	b["workflowSeconds"] = json.Number("180")
	b["nativeStageSeconds"] = json.Number("140")
	b["externalDelivery"] = "HOLD"
	b["limits"], _ = strictJSON([]byte(`{"GOMAXPROCS":2,"GOMEMLIMIT_advisoryBytes":536870912,"hostGateSeconds":8,"maximumTelemetryGapSeconds":2,"memoryEnforcement":"SAMPLED_NOT_HARD_RESERVATION_OR_EXACT_PEAK","overallAfterConsumptionSeconds":140,"ownedCleanupSeconds":5,"pairWallSeconds":120,"perFileKernelBytes":67108864,"sampledRuntimeBytes":134217728,"stdoutStderrBytes":67108864,"workerKernelCpuSeconds":120,"workerSampledRssBytes":1073741824,"workerTelemetryMs":100}`))
	b["requestCommitment"] = hashBody("rhook/native-plan-request/0.2", b)
	b["operationCommitment"] = hashBody("rhook/hookr-operation/0.2", b)
	return b
}
func cloneMap(b map[string]any) map[string]any {
	r := map[string]any{}
	for k, v := range b {
		r[k] = v
	}
	return r
}
func testApproval(b map[string]any) map[string]any {
	a := cloneMap(b)
	a["founderApproved"] = true
	a["macOnPowerOpenLid"] = true
	a["noRetry"] = true
	a["notBeforeUnix"] = json.Number("999")
	a["expiresUnix"] = json.Number("1300")
	return a
}
func TestRuntimeInputFilesRejectFIFOAndSymlink(t *testing.T) {
	root := t.TempDir()
	f := filepath.Join(root, "file")
	os.WriteFile(f, []byte("ok"), 0600)
	if _, e := limitedFile(f, 2); e != nil {
		t.Fatal(e)
	}
	l := filepath.Join(root, "link")
	os.Symlink(f, l)
	if _, e := limitedFile(l, 2); e == nil {
		t.Fatal("link")
	}
	fifo := filepath.Join(root, "fifo")
	syscall.Mkfifo(fifo, 0600)
	if _, e := limitedFile(fifo, 2); e == nil {
		t.Fatal("fifo")
	}
}
func TestRuntimeTypedMissingState(t *testing.T) {
	detail := failureDetail("BRANCH", &prestate.HostStop{Code: "CODE_SOURCE_UNAVAILABLE", Detail: "missing"})
	if detail["classification"] != "HOST_STOP_MISSING_STATE" {
		t.Fatal(detail)
	}
	if failureDetail("ACTUAL", nil) != nil {
		t.Fatal("receipt revert inferred")
	}
}
func TestRuntimeFactoryIsolation(t *testing.T) {
	raw, _ := runtimeForValue("99", caseBytes)
	p, _ := AdmitRuntime(raw, caseBytes)
	if _, e := freshRuntime([]byte("invalid-package"), p); e == nil {
		t.Fatal("bad package accepted")
	}
}

func TestRuntimeGoldenHashes(t *testing.T) {
	raw0, _ := runtimeForValue("0", caseBytes)
	if digest(raw0) != "0c4be9c11bc395f37b43f1c0646f76ab6d7035880ff7247e4a6dbf445eb1c554" {
		t.Fatal("cross-language runtime 0")
	}
	raw50, _ := runtimeForValue("50", caseBytes)
	if digest(raw50) != "d54448edc0cff6786f2b00281e4d2e83dc02af83b2bf163426c88bbcc659f110" {
		t.Fatal("cross-language runtime 50")
	}
	raw99, _ := runtimeForValue("99", caseBytes)
	if digest(raw99) != "6ac5072c0b89e0e8d0e05ffbedcb1d811381e4504c0963a7dc37ce419353cfaa" {
		t.Fatal("cross-language runtime 99")
	}
}

func TestRuntimeAuthorityRejectsUnknownBindingField(t *testing.T) {
	raw, _ := runtimeForValue("50", caseBytes)
	p, _ := AdmitRuntime(raw, caseBytes)
	sourceCommitment = "source"
	policyCommitment = "policy"
	b := testBinding(p)
	b["extra"] = true
	delete(b, "operationCommitment")
	delete(b, "requestCommitment")
	b["requestCommitment"] = hashBody("rhook/native-plan-request/0.2", b)
	b["operationCommitment"] = hashBody("rhook/hookr-operation/0.2", b)
	if checkAuthority(testApproval(b), b, p, "/private/tmp/work/runs/00000000000000000000000000000000", "binary", time.Unix(1000, 0)) == nil {
		t.Fatal("unknown field accepted")
	}
}

func TestRuntimeAuthorityRejectsCoherentlyRehashedUnsupportedScope(t *testing.T) {
	raw, _ := runtimeForValue("50", caseBytes)
	p, _ := AdmitRuntime(raw, caseBytes)
	sourceCommitment = "source"
	policyCommitment = "policy"
	for k, v := range map[string]any{"workflowSeconds": json.Number("181"), "nativeStageSeconds": json.Number("141"), "externalDelivery": "PUBLIC", "packagePath": "/private/tmp/other/BLOCK_PACKAGE.json", "semanticPlanPath": "/private/tmp/other/semantic.json", "runtimePlanPath": "/private/tmp/other/runtime.json", "limits": map[string]any{"workerSampledRssBytes": json.Number("4294967296")}} {
		b := testBinding(p)
		b[k] = v
		delete(b, "operationCommitment")
		delete(b, "requestCommitment")
		b["requestCommitment"] = hashBody("rhook/native-plan-request/0.2", b)
		b["operationCommitment"] = hashBody("rhook/hookr-operation/0.2", b)
		if checkAuthority(testApproval(b), b, p, "/private/tmp/work/runs/00000000000000000000000000000000", "binary", time.Unix(1000, 0)) == nil {
			t.Fatal("coherent unsupported binding: " + k)
		}
	}
}
