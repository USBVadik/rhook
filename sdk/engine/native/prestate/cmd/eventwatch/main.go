// No default live mode. Both authorities are PROPOSAL_ONLY until the founder
// provides explicit exact trusted-local approval. No credential is in argv/env.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	prestate "local/rhook-robinhood"
	"os"
	"path/filepath"
	"syscall"
	"time"
)

func readAuthority(path string) (a prestate.EventAuthority) {
	b, e := os.ReadFile(path)
	if e != nil || len(b) > 65536 || json.Unmarshal(b, &a) != nil {
		panic("AUTHORITY_FILE_REQUIRED")
	}
	return
}
func main() {
	defer func() {
		if recover() != nil {
			fmt.Fprintln(os.Stderr, "EVENT_ENTRY_STOP_UNVERIFIED")
			os.Exit(2)
		}
	}()
	p := prestate.ObservedEventPolicy()
	if len(os.Args) == 2 && os.Args[1] == "--describe" {
		json.NewEncoder(os.Stdout).Encode(map[string]any{"mode": "PREPARED_NO_CONNECTION", "policy": p, "policyCommitment": p.Commitment(), "realNativeExecutions": 0, "WSSConnections": 0, "RPC": 0})
		return
	}
	if len(os.Args) == 3 && os.Args[1] == "--check-package" {
		b, e := os.ReadFile(os.Args[2])
		if e != nil {
			panic("PACKAGE_READ")
		}
		_, inv, e := prestate.AdmitPackage(b)
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			os.Exit(1)
		}
		json.NewEncoder(os.Stdout).Encode(map[string]any{"mode": "ADMISSION_ONLY", "inventory": inv, "nativeExecutions": 0, "RPC": 0})
		return
	}
	if len(os.Args) < 4 || (os.Args[1] != "--watch-read-only" && os.Args[1] != "--watch-pair") {
		fmt.Fprintln(os.Stderr, "EXPLICIT_MODE_AND_APPROVAL_REQUIRED")
		os.Exit(2)
	}

	a := readAuthority(os.Args[3])
	var science *prestate.EventAuthority
	if os.Args[1] == "--watch-pair" {
		if len(os.Args) != 5 {
			panic("SCIENTIFIC_AUTHORITY_REQUIRED")
		}
		s := readAuthority(os.Args[4])
		science = &s
	} else if len(os.Args) != 4 {
		panic("EXACT_ARGUMENTS")
	}
	binary, e := os.Executable()
	if e != nil {
		panic("BINARY_IDENTITY")
	}
	raw, e := os.ReadFile(binary)
	if e != nil {
		panic("BINARY_READ")
	}
	if e = prestate.ValidateEventAuthorities(a, science, p, prestate.ByteDigest(raw)); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(2)
	}
	if filepath.Clean(os.Args[2]) != filepath.Clean(a.RuntimePath) || !filepath.IsAbs(a.RuntimePath) {
		panic("EXACT_AUTHORIZED_RUNTIME_REQUIRED")
	}
	// Credential input is read only after authority validation. The prepared
	// launcher pins every implementation/dependency and loads this anonymous pipe.
	secret, e := io.ReadAll(io.LimitReader(os.Stdin, 8193))
	if e != nil || len(secret) > 8192 {
		panic("CREDENTIAL_PIPE_LIMIT")
	}
	var cfg prestate.EventLiveConfig
	if json.Unmarshal(secret, &cfg) != nil {
		panic("CREDENTIAL_PIPE_ENCODING")
	}
	for i := range secret {
		secret[i] = 0
	}
	j, e := prestate.OpenEventJournal(os.Args[2], a.DecisionID, p)
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(2)
	}
	defer j.Close()
	// Read-only process resource guard. Native gets a separate 120 CPU/wall
	// window in the existing pair adapter. The launcher also applies RLIMIT_CPU.
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				var r syscall.Rusage
				e := syscall.Getrusage(syscall.RUSAGE_SELF, &r)
				cpu := float64(r.Utime.Sec+r.Stime.Sec) + float64(r.Utime.Usec+r.Stime.Usec)/1e6
				if e != nil || r.Maxrss <= 0 || r.Maxrss > 4<<30 || cpu > 600 {
					fmt.Fprintln(os.Stderr, "CONTROLLER_RESOURCE_STOP")
					os.Exit(125)
				}
			}
		}
	}()
	summary := prestate.RunEventWatcher(ctx, cfg, j, p, a, science)
	b, e := json.MarshalIndent(summary, "", "  ")
	if e != nil || len(b) > 64<<20 {
		panic("FINAL_RESULT_SIZE_OR_ENCODING")
	}
	out := filepath.Join(os.Args[2], "FINAL_RESULT.json")
	f, e := os.OpenFile(out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		panic("FINAL_RESULT_EXCLUSIVE")
	}
	if _, e = f.Write(b); e != nil {
		f.Close()
		panic("FINAL_RESULT_WRITE")
	}
	if e = f.Sync(); e != nil {
		f.Close()
		panic("FINAL_RESULT_SYNC")
	}
	f.Close()
	d, e := os.Open(os.Args[2])
	if e != nil {
		panic("FINAL_DIRECTORY")
	}
	e = d.Sync()
	d.Close()
	if e != nil {
		panic("FINAL_DIRECTORY_SYNC")
	}
	json.NewEncoder(os.Stdout).Encode(map[string]any{"terminal": summary.Terminal, "cause": summary.Cause, "externalDelivery": "HOLD"})
}
