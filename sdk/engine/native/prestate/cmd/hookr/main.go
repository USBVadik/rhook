package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	prestate "local/rhook-robinhood"
	"local/rhook-robinhood/internal/controllersafety"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"
)

var namePattern = regexp.MustCompile(`^[A-Z0-9_]+\.json$`)

func writer(dir string) prestate.WriteEvidence {
	return func(name string, raw []byte) error {
		if !namePattern.MatchString(name) {
			return errors.New("EVIDENCE_NAME")
		}
		p := filepath.Join(dir, name)
		f, e := os.OpenFile(p, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if e != nil {
			return errors.New("EVIDENCE_EXCLUSIVE_OPEN")
		}
		_, e = f.Write(raw)
		if e == nil {
			e = f.Sync()
		}
		closeErr := f.Close()
		if e == nil {
			e = closeErr
		}
		if e != nil {
			return errors.New("EVIDENCE_WRITE")
		}
		d, e := os.Open(dir)
		if e != nil {
			return errors.New("EVIDENCE_DIRECTORY")
		}
		defer d.Close()
		if d.Sync() != nil {
			return errors.New("EVIDENCE_DIRECTORY_SYNC")
		}
		return nil
	}
}
func main() {
	if len(os.Args) == 2 && os.Args[1] == "--identity" {
		json.NewEncoder(os.Stdout).Encode(map[string]any{"mode": "IDENTITY_ONLY", "nativeExecutions": 0, "rpcRequests": 0, "chainId": 4663, "selection": "first eligible ETH/RHOOK buy after frozen activation boundary; bounded HTTP polling proposal", "maximumMonitoringSeconds": 14400, "ACTUAL": 1, "BRANCH": 1, "B": 0, "qualifiedEconomicClaims": 0, "monitoringEstimatedCUPerSecond": prestate.MonitoringEstimatedCUPerSecond, "performanceCanaryMaximumSeconds": 90, "performanceCanaryNativeInvocations": 0, "maxOriginalTransactions": 8, "maxRpcRequests": 64, "maxResponseBytes": 32 << 20, "maxBodyBytes": 8 << 20, "captureSeconds": 60, "overallSeconds": 180, "nativeWallSeconds": 120, "nativeCpuSeconds": 120, "knownPreludeSlot": prestate.ArbOSPerBlockGasLimitSlot})
		return
	}
	canary := len(os.Args) == 3 && os.Args[1] == "--monitor-canary"
	monitor := (len(os.Args) == 3 && os.Args[1] == "--monitor-hookr") || canary
	lockedMode := len(os.Args) == 4 && os.Args[1] == "--run-hookr-locked"
	if (!monitor && !lockedMode) || os.Getenv("RHOOK_EXACT_OPERATION") == "" {
		fmt.Fprintln(os.Stderr, "EXACT_AUTHORIZED_MODE_REQUIRED")
		os.Exit(2)
	}
	supervisionFD, err := strconv.Atoi(os.Getenv("RHOOK_SUPERVISION_FD"))
	if err != nil {
		fmt.Fprintln(os.Stderr, "SUPERVISION_FD_REQUIRED")
		os.Exit(2)
	}
	stopWatch, err := controllersafety.Start(supervisionFD, controllersafety.Timeout, func(reason string) { fmt.Fprintln(os.Stderr, "CONTROLLER_SUPERVISION_LOST_"+reason); os.Exit(76) })
	if err != nil {
		fmt.Fprintln(os.Stderr, "SUPERVISION_SETUP_REJECTED")
		os.Exit(2)
	}
	defer stopWatch()
	remaining, e := strconv.ParseInt(os.Getenv("RHOOK_REMAINING_MS"), 10, 64)
	maximumRemaining := int64(180000)
	if monitor {
		maximumRemaining = 14400000
		if canary {
			maximumRemaining = 90000
		}
	}
	if e != nil || remaining <= 0 || remaining > maximumRemaining {
		fmt.Fprintln(os.Stderr, "INVALID_REMAINING_OPERATION_BUDGET")
		os.Exit(2)
	}
	end := time.Now().Add(time.Duration(remaining) * time.Millisecond)
	secret, e := io.ReadAll(io.LimitReader(os.Stdin, 8193))
	if e != nil || len(secret) > 8192 {
		fmt.Fprintln(os.Stderr, "CREDENTIAL_CHANNEL_REJECTED")
		os.Exit(2)
	}
	var cfg struct {
		Endpoint string `json:"endpoint"`
	}
	if json.Unmarshal(secret, &cfg) != nil {
		fmt.Fprintln(os.Stderr, "CREDENTIAL_CHANNEL_REJECTED")
		os.Exit(2)
	}
	for i := range secret {
		secret[i] = 0
	}
	u, e := url.Parse(cfg.Endpoint)
	if e != nil || u.Scheme != "https" || u.Host != "robinhood-mainnet.g.alchemy.com" || !strings.HasPrefix(u.Path, "/v2/") || len(strings.TrimPrefix(u.Path, "/v2/")) < 8 || u.RawQuery != "" || u.User != nil || u.Fragment != "" {
		fmt.Fprintln(os.Stderr, "ENDPOINT_BINDING_REJECTED")
		os.Exit(2)
	}
	bodyCap, totalCap, maxRequests := int64(8<<20), int64(32<<20), uint64(64)
	if monitor {
		bodyCap, totalCap, maxRequests = 1<<20, 64<<20, 60000
		if canary {
			totalCap, maxRequests = 2<<20, 200
		}
	}
	rpc, e := prestate.NewRPCSource(cfg.Endpoint, nil, bodyCap, totalCap)
	cfg.Endpoint = ""
	if e != nil {
		fmt.Fprintln(os.Stderr, "RPC_SOURCE_SETUP_REJECTED")
		os.Exit(2)
	}
	baseWrite := writer(os.Args[2])
	write := func(name string, raw []byte) error {
		if name == "INPUT_PRECOMMIT.json" {
			var m map[string]any
			if json.Unmarshal(raw, &m) != nil {
				return errors.New("PRECOMMIT_ENCODING")
			}
			m["prospectiveOperationCommitment"] = os.Getenv("RHOOK_EXACT_OPERATION")
			m["acquisitionExecutionPolicyFrozenBeforeCapture"] = true
			raw, _ = json.MarshalIndent(m, "", "  ")
		}
		return baseWrite(name, raw)
	}
	e = rpc.Configure(maxRequests, end, func(stage string, record prestate.RPCRecord) error {
		return prestate.EmitJSON(write, fmt.Sprintf("RPC_%s_%03d.json", stage, record.Index), record)
	})
	if e != nil {
		fmt.Fprintln(os.Stderr, "RPC_BUDGET_SETUP_REJECTED")
		os.Exit(2)
	}
	monitoringCU := prestate.MonitoringEstimatedCULimit
	if canary {
		monitoringCU = 15000
	}
	if monitor && rpc.ConfigureMonitoringCUBudget(monitoringCU) != nil {
		fmt.Fprintln(os.Stderr, "MONITOR_CU_SETUP_REJECTED")
		os.Exit(2)
	}
	enc := json.NewEncoder(os.Stdout)
	var nativeTimer *time.Timer
	emit := func(event string, value any) error {
		if event == "NATIVE_REPLAY_ENTERED" {
			nativeTimer = time.AfterFunc(120*time.Second, func() { fmt.Fprintln(os.Stderr, "NATIVE_WALL_DEADLINE"); os.Exit(124) })
		}
		return enc.Encode(map[string]any{"event": event, "data": value, "operationCommitment": os.Getenv("RHOOK_EXACT_OPERATION")})
	}
	ctx, cancel := context.WithDeadline(context.Background(), end)
	defer cancel()
	if monitor {
		runScanner := prestate.RunHookrMonitor
		if canary {
			runScanner = prestate.RunHookrPerformanceCanary
		}
		result := runScanner(ctx, rpc, write, func(ctx context.Context, d time.Duration) error {
			timer := time.NewTimer(d)
			defer timer.Stop()
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-timer.C:
				return nil
			}
		})
		var usage syscall.Rusage
		usageErr := syscall.Getrusage(syscall.RUSAGE_SELF, &usage)
		final := map[string]any{"result": result, "operationCommitment": os.Getenv("RHOOK_EXACT_OPERATION"), "resourceUsageReliable": usageErr == nil && usage.Maxrss > 0, "maxRSSBytes": usage.Maxrss, "performanceCanary": canary, "cpuUsedSeconds": float64(usage.Utime.Sec+usage.Stime.Sec) + float64(usage.Utime.Usec+usage.Stime.Usec)/1000000}
		if prestate.EmitJSON(write, "MONITOR_COMPLETION.json", final) != nil {
			os.Exit(2)
		}
		enc.Encode(map[string]any{"event": "MONITOR_COMPLETION", "terminal": result.Terminal})
		if result.Terminal != "FIRST_ELIGIBLE_BUY_LOCKED" || usageErr != nil || usage.Maxrss <= 0 {
			os.Exit(1)
		}
		return
	}
	stat, e := os.Lstat(os.Args[3])
	if e != nil || !stat.Mode().IsRegular() || stat.Size() > 2<<20 {
		fmt.Fprintln(os.Stderr, "LOCKED_SELECTION_FILE_REQUIRED")
		os.Exit(2)
	}
	raw, e := os.ReadFile(os.Args[3])
	var locked prestate.LockedHookrSelection
	if e != nil || prestate.ByteDigest(raw) != os.Getenv("RHOOK_LOCKED_SELECTION_SHA") || json.Unmarshal(raw, &locked) != nil || prestate.ValidateLockedHookrSelection(&locked) != nil {
		fmt.Fprintln(os.Stderr, "LOCKED_SELECTION_BINDING")
		os.Exit(2)
	}
	result := prestate.RunLockedHookrProspective(ctx, rpc, write, emit, minTime(time.Now().Add(60*time.Second), end), &locked)
	if nativeTimer != nil {
		nativeTimer.Stop()
	}
	var usage syscall.Rusage
	usageErr := syscall.Getrusage(syscall.RUSAGE_SELF, &usage)
	if usageErr != nil || usage.Maxrss <= 0 {
		result.Terminal = "RUNTIME_OR_RESOURCE_STOP"
		result.Cause = "RESOURCE_USAGE_UNAVAILABLE"
	}
	final := map[string]any{"result": result, "resourceUsageReliable": usageErr == nil && usage.Maxrss > 0, "maxRSSBytes": usage.Maxrss, "cpuUsedSeconds": float64(usage.Utime.Sec+usage.Stime.Sec) + float64(usage.Utime.Usec+usage.Stime.Usec)/1000000, "operationCommitment": os.Getenv("RHOOK_EXACT_OPERATION")}
	if prestate.EmitJSON(write, "NATIVE_COMPLETION.json", final) != nil {
		fmt.Fprintln(os.Stderr, "NATIVE_COMPLETION_RECORD_FAILURE")
		os.Exit(2)
	}
	enc.Encode(map[string]any{"event": "NATIVE_COMPLETION", "data": map[string]any{"terminal": result.Terminal, "nativeAttempts": result.NativeAttempts, "rpcRequests": result.RpcRequests}, "operationCommitment": os.Getenv("RHOOK_EXACT_OPERATION")})
	if result.Terminal != "GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED" {
		os.Exit(1)
	}
}
func minTime(a, b time.Time) time.Time {
	if b.Before(a) {
		return b
	}
	return a
}
