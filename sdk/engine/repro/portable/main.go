package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
)

// This adapter changes file/authority admission only. pair.go is staged byte
// for byte from the preserved engine; no Source/provider is accepted here.
type portableBinding struct {
	Operation string `json:"operationCommitment"`
	Binary    string `json:"binarySha256"`
	Plan      string `json:"planSha256"`
	Package   string `json:"packagePath"`
	Output    string `json:"outputPath"`
}
type portableAuthority struct {
	Approved  bool                            `json:"founderApproved"`
	Domain    string                          `json:"domain"`
	Operation string                          `json:"operationCommitment"`
	Binary    string                          `json:"binarySha256"`
	Package   string                          `json:"packagePath"`
	Output    string                          `json:"outputPath"`
	NotBefore int64                           `json:"notBeforeUnix"`
	Expires   int64                           `json:"expiresUnix"`
	RPC       int                             `json:"RPC"`
	WSS       int                             `json:"WSS"`
	NoRetry   bool                            `json:"noRetry"`
	MacReady  bool                            `json:"macOnPowerOpenLid"`
	Context   string                          `json:"executionContext"`
	Maximum   struct{ ACTUAL, BRANCH, B int } `json:"maximumInvocations"`
}

func checkAuthority(a portableAuthority, b portableBinding, root, binary string, now time.Time) error {
	if !a.Approved || a.Domain != "PORTABLE_SAVED_PAIR03" || a.Operation == "" || a.Operation != b.Operation ||
		a.Binary != b.Binary || binary != b.Binary || b.Plan != digest(planBytes) ||
		a.Package != b.Package || a.Output != b.Output || a.Output != root || !filepath.IsAbs(a.Package) ||
		a.RPC != 0 || a.WSS != 0 || !a.NoRetry || !a.MacReady || a.Context != "require_escalated" ||
		a.Maximum.ACTUAL != 1 || a.Maximum.BRANCH != 1 || a.Maximum.B != 0 ||
		now.Unix() < a.NotBefore || now.Unix() >= a.Expires || a.Expires-a.NotBefore > 600 {
		return errors.New("EXACT_FRESH_PORTABLE_AUTHORITY_REQUIRED")
	}
	return nil
}

func checkedFresh(raw []byte, p Plan) (world, error) {
	w, e := fresh(raw, p) // unchanged MPT/header/config/input admission, nil Source
	if e != nil {
		return nil, e
	}
	s := w.(*savedWorld)
	var expected struct {
		Arrivals []common.Hash `json:"arrivals"`
	}
	if e = json.Unmarshal(planBytes, &expected); e == nil {
		if len(expected.Arrivals) != 7 || len(s.offline.TxHashes) != 7 {
			e = errors.New("ALL_SEVEN_ARRIVALS_REQUIRED")
		}
		for i, h := range expected.Arrivals {
			if e != nil {
				break
			}
			if h != s.offline.TxHashes[i] {
				e = errors.New("ORIGINAL_ARRIVAL_HASH_ORDER_REQUIRED")
			}
		}
	}
	if e == nil {
		e = s.offline.Bridge.Protect(func() error {
			state, err := s.offline.Bridge.State()
			if err != nil {
				return err
			}
			code := common.HexToHash("0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b")
			i := p.Intervention
			if !state.Exist(i.Account) || state.GetCodeHash(i.Account) != code ||
				crypto.Keccak256Hash(state.GetCode(i.Account)) != code || state.GetState(i.Account, i.Slot) != i.ExpectedOldWord {
				return errors.New("ORIGINAL_RULES_ACCOUNT_CODE_FULL_WORD_REQUIRED")
			}
			return state.Error()
		})
	}
	if e != nil {
		w.Close()
		return nil, e
	}
	return w, nil
}

func limitedFile(path string, maximum int64) ([]byte, error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return nil, errors.New("EXPLICIT_LOCAL_PATH_REQUIRED")
	}
	for current := path; ; current = filepath.Dir(current) {
		info, err := os.Lstat(current)
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, errors.New("SYMLINK_PATH_REJECTED")
		}
		if current == filepath.Dir(current) {
			break
		}
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > maximum {
		return nil, errors.New("LOCAL_FILE_SIZE_OR_TYPE")
	}
	raw, err := io.ReadAll(io.LimitReader(f, maximum+1))
	if int64(len(raw)) > maximum {
		return nil, errors.New("LOCAL_FILE_LIMIT")
	}
	return raw, err
}

func main() {
	if e := mainEntry(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
func mainEntry() error {
	if len(os.Args) != 2 || os.Args[1] != "--execute-once" {
		return errors.New("PORTABLE_SUPERVISOR_AND_FRESH_AUTHORITY_REQUIRED")
	}
	exe, e := os.Executable()
	if e != nil {
		return e
	}
	root := filepath.Dir(filepath.Dir(exe))
	dir := filepath.Join(root, "runtime")
	bindingRaw, e := limitedFile(filepath.Join(root, "proposal/AUTHORIZATION_BINDINGS.json"), 2<<20)
	if e != nil {
		return e
	}
	var b portableBinding
	if e = json.Unmarshal(bindingRaw, &b); e != nil {
		return e
	}
	payload, e := io.ReadAll(io.LimitReader(os.Stdin, 16384))
	if e != nil || len(payload) >= 16384 {
		return errors.New("AUTHORITY_PAYLOAD_LIMIT")
	}
	var a portableAuthority
	if e = json.Unmarshal(payload, &a); e != nil {
		return e
	}
	binary, e := limitedFile(exe, 256<<20)
	if e != nil {
		return e
	}
	if e = checkAuthority(a, b, root, digest(binary), time.Now()); e != nil {
		return e
	}
	started, e := limitedFile(filepath.Join(dir, "STARTED.json"), 16384)
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
	if start.Authority != digest(payload) || start.Operation != b.Operation {
		return errors.New("STARTED_AUTHORITY_LINK_MISMATCH")
	}
	host, e := limitedFile(filepath.Join(dir, "HOST_ADMISSION.json"), 65536)
	if e != nil {
		return e
	}
	var gate struct {
		Accepted bool `json:"accepted"`
	}
	if e = json.Unmarshal(host, &gate); e != nil || !gate.Accepted {
		return errors.New("FAIL_CLOSED_HOST_ADMISSION_REQUIRED")
	}
	p := loadPlan()
	if p.PackagePath != "" {
		return errors.New("HISTORICAL_ABSOLUTE_PACKAGE_PATH_FORBIDDEN")
	}
	raw, e := limitedFile(a.Package, 32<<20)
	if e != nil {
		return e
	}
	controller := pair{plan: p, dir: dir, factory: func() (world, error) { return checkedFresh(raw, p) }}
	out, e := controller.run()
	if e != nil {
		out.Terminal = "INTERRUPTED_UNVERIFIED"
		out.Cause = e.Error()
	}
	if se := store(dir, "NATIVE_COMPLETION.json", map[string]any{"operationCommitment": b.Operation, "result": out}); se != nil {
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
