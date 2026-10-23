package prestate

import (
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/crypto"
	"testing"
	"time"
)

func TestInitialWitnessBudgetIsCumulative(t *testing.T) {
	f := makeFixture(t)
	b, e := NewBridge(f.checkpoint, Budget{MaxRequests: 1, MaxBytes: 1, MaxResponseBytes: 1, ExpiresAt: time.Now().Add(time.Minute)}, nil)
	if e != nil {
		t.Fatal(e)
	}
	defer b.Close()
	first := []byte{0x00}
	second := []byte{0x01}
	if e = b.LoadWitness(f.checkpoint, nil, map[common.Hash]hexutil.Bytes{crypto.Keccak256Hash(first): first}); e != nil {
		t.Fatal(e)
	}
	e = b.LoadWitness(f.checkpoint, nil, map[common.Hash]hexutil.Bytes{crypto.Keccak256Hash(second): second})
	if !IsHostStop(e) {
		t.Fatalf("second prestate load bypassed cumulative bytes: %v", e)
	}
}
