package main

import (
	"github.com/ethereum/go-ethereum/common"
	"path/filepath"
	"syscall"
	"testing"
	"time"
)

func TestVariableArrivalAndSubjectScope(t *testing.T) {
	p := Plan{Transactions: 5, Observation: observation(1)}
	hashes := []common.Hash{{1}, {2}, {3}, {4}, {5}}
	p.Subject = hashes[1]
	p.Observation.Subject = p.Subject
	if e := validateScope(p, hashes); e != nil {
		t.Fatal(e)
	}
	p.Subject = hashes[3]
	if e := validateScope(p, hashes); e == nil {
		t.Fatal("wrong subject admitted")
	}
}
func TestEmptyArrivalScope(t *testing.T) {
	if validateScope(Plan{}, nil) == nil {
		t.Fatal("empty block admitted")
	}
}
func TestInputFIFOIsRejectedWithoutBlocking(t *testing.T) {
	root, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	p := filepath.Join(root, "fifo")
	if e := syscall.Mkfifo(p, 0600); e != nil {
		t.Fatal(e)
	}
	done := make(chan error, 1)
	go func() { _, e := limited(p, 1024); done <- e }()
	select {
	case e := <-done:
		if e == nil {
			t.Fatal("FIFO accepted")
		}
	case <-time.After(100 * time.Millisecond):
		t.Fatal("FIFO open blocked")
	}
}
