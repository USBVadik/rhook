// Exact offline calibration entrypoint. --admit cannot call RunCanonical.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	prestate "local/rhook-robinhood"
	"os"
	"runtime"
	"syscall"
)

const packagePin = "7f478713923b687d4243507f0affa6d0184e19882e8d5ab280780f536f268531"
const inputPin = "97536d3563d47a2dbc6ac2ddb06e9a7003d46ca35fa1e87adb35a4b2cfc70046"
const witnessPin = "5b781f21a5cd8a89519752008ed57aba8dbef876d545d1e78c34e40a018bcaca"

func execute(mode, path string) (code int) {
	enc := json.NewEncoder(os.Stdout)
	defer func() {
		if p := recover(); p != nil {
			enc.Encode(map[string]any{"terminal": "RUNTIME_OR_RESOURCE_STOP", "cause": "UNEXPECTED_NATIVE_PANIC", "rpcRequests": 0})
			code = 2
		}
	}()
	file, err := os.Open(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, "INPUT_OPEN_FAILURE")
		return 2
	}
	raw, err := io.ReadAll(io.LimitReader(file, (32<<20)+1))
	file.Close()
	pin := sha256.Sum256(raw)
	if err != nil || len(raw) > 32<<20 || hex.EncodeToString(pin[:]) != packagePin {
		fmt.Fprintln(os.Stderr, "EXACT_PACKAGE_PIN_REJECTED")
		return 2
	}
	p, err := prestate.PrepareOfflineCalibration(raw, inputPin, witnessPin)
	if err != nil {
		fmt.Fprintln(os.Stderr, "OFFLINE_PREPARATION_REJECTED:", err)
		return 2
	}
	defer p.Bridge.Close()
	identity := map[string]any{"inventory": p.Inventory, "chainConfigSha256": p.ConfigSHA, "orderedTransactionHashes": p.TxHashes, "rpcRequests": 0}
	if mode == "--admit" {
		identity["mode"] = "OFFLINE_ADMISSION_ONLY"
		identity["historicalNativeExecutions"] = 0
		enc.Encode(identity)
		return 0
	}
	if mode != "--execute-once" || os.Getenv("RHOOK_EXACT_OPERATION") == "" {
		fmt.Fprintln(os.Stderr, "NO_EXACT_LAUNCHER_AUTHORIZATION")
		return 2
	}
	enc.Encode(map[string]any{"event": "NATIVE_REPLAY_ENTERED", "inputCommitment": inputPin, "operationCommitment": os.Getenv("RHOOK_EXACT_OPERATION"), "maximumInvocations": 1})
	out, err := prestate.RunCanonical(p.Candidate, p.Bridge)
	if err == nil && (out == nil || !out.Matched) {
		err = errors.New("NATIVE_SUCCESS_WITHOUT_MATCHED_RESULT")
	}
	terminal, cause := prestate.ClassifyCalibrationError(err)
	var usage syscall.Rusage
	usageErr := syscall.Getrusage(syscall.RUSAGE_SELF, &usage)
	usageReliable := usageErr == nil && usage.Maxrss > 0
	if !usageReliable {
		terminal, cause = "RUNTIME_OR_RESOURCE_STOP", "RESOURCE_USAGE_UNAVAILABLE"
	}
	var mem runtime.MemStats
	runtime.ReadMemStats(&mem)
	result := map[string]any{"terminal": terminal, "hostStopCode": cause, "result": out, "identity": identity,
		"missingStateAttempts": p.Attempts(), "rpcRequests": 0, "historicalNativeExecutions": 1,
		"resourceUsageReliable": usageReliable,
		"cpuUsedSeconds":        float64(usage.Utime.Sec+usage.Stime.Sec) + float64(usage.Utime.Usec+usage.Stime.Usec)/1000000,
		"maxRSSRaw":             usage.Maxrss, "maxRSSRawUnit": "bytes_on_darwin", "goHeapAllocBytes": mem.HeapAlloc, "goSysBytes": mem.Sys}
	if err != nil {
		text := err.Error()
		if len(text) > 4096 {
			text = text[:4096]
		}
		result["nativeError"] = text
	}
	enc.Encode(result)
	if terminal != "CANONICAL_ACTUAL_ROOTS_MATCH" {
		return 1
	}
	return 0
}

func main() {
	if len(os.Args) != 3 || (os.Args[1] != "--admit" && os.Args[1] != "--execute-once") {
		fmt.Fprintln(os.Stderr, "EXACT_MODE_AND_PACKAGE_REQUIRED")
		os.Exit(2)
	}
	os.Exit(execute(os.Args[1], os.Args[2]))
}
