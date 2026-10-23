package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"sync/atomic"
	"testing"

	"github.com/ethereum/go-ethereum/core/types"
)

// Regression control: recorded identities and the legacy reconciliation path,
// no provider transport. Open WSS alone cannot authenticate 7,998 quiet blocks.
func TestQuietBaselineRecordedAttempt02Gap(t *testing.T) {
	j, p, _ := eventTestJournal(t)
	j.Update("RECORDED_CURSOR", func(s *EventState) error { s.Activation = 92810900; s.Cursor = 92810903; return nil })
	raw, e := os.ReadFile("../inputs/ATTEMPT02_WS_0002.json")
	if e != nil {
		t.Fatal(e)
	}
	var frame eventWSFrame
	if e = json.Unmarshal(raw, &frame); e != nil {
		t.Fatal(e)
	}
	var calls atomic.Int32
	c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
		calls.Add(1)
		return &EventCapture{Error: "SYNTHETIC_ONLY"}, nil
	})
	if e = c.Observe(context.Background(), frame.Params.Result); e != nil {
		t.Fatal(e)
	}
	c.Wait()
	if j.Snapshot().Cursor != 92810903 || calls.Load() != 1 {
		t.Fatal("notification incorrectly advanced coverage")
	}
	if e = ReconcileEventRange(context.Background(), nil, c, 92818901); e == nil || e.Error() != "GAP_EXCEEDS_FROZEN_BOUND" {
		t.Fatal(e)
	}
}

func TestQuietBaselineSharedCancellationLosesPendingCapture(t *testing.T) {
	j, p, f := eventTestJournal(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	started := make(chan struct{})
	result := make(chan error, 1)
	c := NewEventController(j, p, func(ctx context.Context, l *types.Log, w WriteEvidence) (*EventCapture, error) {
		close(started)
		<-ctx.Done()
		result <- ctx.Err()
		return &EventCapture{Error: ctx.Err().Error()}, ctx.Err()
	})
	if e := c.Observe(ctx, f.logs[0]); e != nil {
		t.Fatal(e)
	}
	<-started
	j.Halt("SYNTHETIC_COVERAGE_STOP")
	cancel()
	c.Wait()
	if !errors.Is(<-result, context.Canceled) {
		t.Fatal("shared cancellation was not reproduced")
	}
	if j.Snapshot().Lock != nil || j.Snapshot().Consumed {
		t.Fatal("science entered")
	}
}
