// Package controllersafety only observes an inherited read-only liveness pipe.
// It never looks up or terminates other processes. The CLI exits its own process
// on loss; no final durable record is promised after controller/power loss.
package controllersafety

import (
	"errors"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

const Timeout = 3 * time.Second

// Start requires an initial heartbeat before returning. Parent alone owns the
// write end. EOF detects SIGKILL; timeout also fails closed on a stuck parent.
func Start(fd int, timeout time.Duration, lost func(string)) (func(), error) {
	if fd < 3 || fd > 255 || timeout <= 0 || lost == nil {
		return nil, errors.New("SUPERVISION_ARGUMENT")
	}
	f := os.NewFile(uintptr(fd), "controller-liveness")
	stat, e := f.Stat()
	if e != nil || stat.Mode()&os.ModeNamedPipe == 0 {
		f.Close()
		return nil, errors.New("SUPERVISION_PIPE_REQUIRED")
	}
	events := make(chan string, 1)
	done := make(chan struct{})
	var stopped atomic.Bool
	var once sync.Once
	stop := func() { once.Do(func() { stopped.Store(true); close(done); f.Close() }) }
	go func() {
		var b [1]byte
		for {
			n, e := f.Read(b[:])
			v := "BEAT"
			if e != nil || n != 1 {
				v = "EOF_OR_READ_ERROR"
			} else if b[0] != 'H' {
				v = "INVALID_HEARTBEAT"
			}
			select {
			case events <- v:
			case <-done:
				return
			}
			if v != "BEAT" {
				return
			}
		}
	}()
	timer := time.NewTimer(timeout)
	select {
	case v := <-events:
		if v != "BEAT" {
			timer.Stop()
			stop()
			return nil, errors.New("SUPERVISION_INITIAL_HEARTBEAT")
		}
	case <-timer.C:
		stop()
		return nil, errors.New("SUPERVISION_INITIAL_TIMEOUT")
	}
	if !timer.Stop() {
		select {
		case <-timer.C:
		default:
		}
	}
	timer.Reset(timeout)
	go func() {
		defer timer.Stop()
		for {
			select {
			case <-done:
				return
			case v := <-events:
				if v != "BEAT" {
					if !stopped.Load() {
						lost(v)
					}
					return
				}
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				timer.Reset(timeout)
			case <-timer.C:
				if !stopped.Load() {
					lost("HEARTBEAT_TIMEOUT")
				}
				return
			}
		}
	}()
	return stop, nil
}
