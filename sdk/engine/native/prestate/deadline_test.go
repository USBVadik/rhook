package prestate

import (
	"context"
	"github.com/ethereum/go-ethereum/common"
	"testing"
	"time"
)

type ignoringDeadlineSource struct{ *fixture }

func (s ignoringDeadlineSource) GetProof(ctx context.Context, c Checkpoint, a common.Address, k []common.Hash) (*RPCProof, error) {
	<-ctx.Done()
	return s.fixture.GetProof(context.Background(), c, a, k)
}
func TestLateProofCannotCrossPerRequestDeadline(t *testing.T) {
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	b.source = ignoringDeadlineSource{f}
	b.budget.PerRequest = time.Nanosecond
	e := b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		s.GetState(addrA, slot0)
		return nil
	})
	if !IsHostStop(e) {
		t.Fatalf("late valid proof admitted: %v", e)
	}
}
