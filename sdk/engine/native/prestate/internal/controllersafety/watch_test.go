package controllersafety

import (
	"os"
	"testing"
	"time"
)

func TestControllerWatchEOFAndTimeout(t *testing.T) {
	for _, mode := range []string{"eof", "stuck"} {
		t.Run(mode, func(t *testing.T) {
			r, w, e := os.Pipe()
			if e != nil {
				t.Fatal(e)
			}
			defer w.Close()
			w.Write([]byte("H"))
			lost := make(chan string, 1)
			stop, e := Start(int(r.Fd()), 50*time.Millisecond, func(s string) { lost <- s })
			if e != nil {
				t.Fatal(e)
			}
			defer stop()
			if mode == "eof" {
				w.Close()
			}
			select {
			case s := <-lost:
				if s == "" {
					t.Fatal("empty cause")
				}
			case <-time.After(time.Second):
				t.Fatal("worker would remain alive")
			}
		})
	}
}
func TestControllerWatchInitialHeartbeatAndPipeRequired(t *testing.T) {
	f, e := os.CreateTemp(t.TempDir(), "not-pipe")
	if e != nil {
		t.Fatal(e)
	}
	defer f.Close()
	if _, e = Start(int(f.Fd()), time.Second, func(string) {}); e == nil {
		t.Fatal("regular file accepted")
	}
	r, w, _ := os.Pipe()
	defer w.Close()
	if _, e = Start(int(r.Fd()), 10*time.Millisecond, func(string) {}); e == nil {
		t.Fatal("missing initial beat accepted")
	}
}
func TestControllerWatchStopDisarmsCallback(t *testing.T) {
	r, w, _ := os.Pipe()
	w.Write([]byte("H"))
	lost := make(chan string, 1)
	stop, e := Start(int(r.Fd()), 20*time.Millisecond, func(s string) { lost <- s })
	if e != nil {
		t.Fatal(e)
	}
	stop()
	w.Close()
	select {
	case <-lost:
		t.Fatal("callback after normal stop")
	case <-time.After(50 * time.Millisecond):
	}
}
