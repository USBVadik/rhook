package prestate

import (
	"context"
	"errors"
	"math/big"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/rawdb"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethdb/memorydb"
	"github.com/ethereum/go-ethereum/rlp"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/ethereum/go-ethereum/triedb"
	"github.com/holiman/uint256"
)

var addrA = common.HexToAddress("0x1111111111111111111111111111111111111111")
var addrB = common.HexToAddress("0x2222222222222222222222222222222222222222")
var slot0 common.Hash
var one = common.HexToHash("0x01")

type fixture struct {
	accounts   *trie.Trie
	storage    map[common.Address]*trie.Trie
	code       map[common.Address][]byte
	checkpoint Checkpoint
	calls      int
	fail       bool
	wrong      bool
}

func makeFixture(t *testing.T) *fixture {
	t.Helper()
	db := triedb.NewDatabase(rawdb.NewMemoryDatabase(), triedb.HashDefaults)
	st := trie.NewEmpty(db)
	value, _ := rlp.EncodeToBytes(uint64(1))
	if err := st.Update(crypto.Keccak256(slot0[:]), value); err != nil {
		t.Fatal(err)
	}
	a := trie.NewEmpty(db)
	f := &fixture{accounts: a, storage: map[common.Address]*trie.Trie{addrA: st, addrB: st}, code: map[common.Address][]byte{addrA: {0x60, 0x00, 0x54, 0x00}, addrB: {0x00}}}
	for _, addr := range []common.Address{addrA, addrB} {
		account := types.StateAccount{Nonce: 1, Balance: uint256.NewInt(100), Root: st.Hash(), CodeHash: crypto.Keccak256(f.code[addr])}
		raw, _ := rlp.EncodeToBytes(&account)
		if err := a.Update(crypto.Keccak256(addr[:]), raw); err != nil {
			t.Fatal(err)
		}
	}
	f.checkpoint = Checkpoint{ChainID: 4663, BlockNumber: 123, BlockHash: common.HexToHash("0x1234"), StateRoot: a.Hash()}
	return f
}
func proofNodes(t *trie.Trie, key []byte) []hexutil.Bytes {
	db := memorydb.New()
	if err := t.Prove(key, db); err != nil {
		panic(err)
	}
	it := db.NewIterator(nil, nil)
	defer it.Release()
	var nodes []hexutil.Bytes
	for it.Next() {
		nodes = append(nodes, common.CopyBytes(it.Value()))
	}
	return nodes
}
func (f *fixture) GetProof(_ context.Context, c Checkpoint, addr common.Address, slots []common.Hash) (*RPCProof, error) {
	f.calls++
	if c != f.checkpoint {
		return nil, errors.New("checkpoint mismatch")
	}
	if f.fail {
		return nil, errors.New("fixture unavailable")
	}
	p := &RPCProof{Address: addr, AccountProof: proofNodes(f.accounts, crypto.Keccak256(addr[:])), StorageHash: types.EmptyRootHash, CodeHash: types.EmptyCodeHash, Balance: (*hexutil.Big)(big.NewInt(0))}
	if st := f.storage[addr]; st != nil {
		p.Nonce = 1
		p.Balance = (*hexutil.Big)(big.NewInt(100))
		p.CodeHash = crypto.Keccak256Hash(f.code[addr])
		p.StorageHash = st.Hash()
		for _, k := range slots {
			v := big.NewInt(0)
			if k == slot0 {
				v = big.NewInt(1)
			}
			p.StorageProof = append(p.StorageProof, RPCStorageProof{Key: k, Value: (*hexutil.Big)(v), Proof: proofNodes(st, crypto.Keccak256(k[:]))})
		}
	}
	if f.wrong {
		p.AccountProof = []hexutil.Bytes{{0xc0}}
	}
	return p, nil
}
func (f *fixture) GetCode(_ context.Context, c Checkpoint, a common.Address) ([]byte, error) {
	f.calls++
	if f.fail {
		return nil, errors.New("unavailable")
	}
	return common.CopyBytes(f.code[a]), nil
}
func fixtureBridge(t *testing.T, f *fixture) *Bridge {
	t.Helper()
	b, e := NewBridge(f.checkpoint, Budget{MaxRequests: 20, MaxBytes: 1000000, MaxResponseBytes: 100000, ExpiresAt: time.Now().Add(time.Minute)}, f)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { b.Close() })
	return b
}
func TestNativeHydrationAndProvenZero(t *testing.T) {
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	if e := b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		if got := s.GetState(addrA, slot0); got != one {
			t.Fatalf("read %s", got)
		}
		if got := s.GetState(addrA, common.HexToHash("0x02")); got != (common.Hash{}) {
			t.Fatalf("absence %s", got)
		}
		if string(s.GetCode(addrA)) != string(f.code[addrA]) {
			t.Fatal("code")
		}
		return s.Error()
	}); e != nil {
		t.Fatal(e)
	}
	if f.calls < 2 {
		t.Fatal("native missing state did not hydrate")
	}
}
func TestNativeWritesSurviveLaterHydration(t *testing.T) {
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	if e := b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		s.SetState(addrA, slot0, common.HexToHash("0x2a"))
		before := f.calls
		if s.GetState(addrB, slot0) != one {
			t.Fatal("B storage")
		}
		if f.calls <= before {
			t.Fatal("no later hydration")
		}
		if s.GetState(addrA, slot0) != common.HexToHash("0x2a") {
			t.Fatal("write replaced by original state")
		}
		return s.Error()
	}); e != nil {
		t.Fatal(e)
	}
}
func TestWrongRootCannotBecomeKnownZero(t *testing.T) {
	f := makeFixture(t)
	f.wrong = true
	b := fixtureBridge(t, f)
	e := b.Protect(func() error {
		s, err := b.State()
		if err != nil {
			return err
		}
		s.GetState(addrA, slot0)
		return nil
	})
	if !IsHostStop(e) {
		t.Fatalf("expected host stop, got %v", e)
	}
}
func TestExpiredProofAndUnavailableSourceStayFatal(t *testing.T) {
	for _, mode := range []string{"expired", "source"} {
		t.Run(mode, func(t *testing.T) {
			f := makeFixture(t)
			b := fixtureBridge(t, f)
			if mode == "source" {
				f.fail = true
			} else {
				b.budget.ExpiresAt = time.Now().Add(-time.Second)
			}
			e := b.Protect(func() error {
				s, err := b.State()
				if err != nil {
					return err
				}
				s.GetState(addrA, slot0)
				return nil
			})
			if !IsHostStop(e) || b.Fatal() == nil {
				t.Fatalf("missing sticky host STOP: %v", e)
			}
		})
	}
}
func TestHashOnlyUpdateSiblingStopsWithoutRPCGuess(t *testing.T) {
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	before := 0
	e := b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		s.GetBalance(addrA)
		s.SelfDestruct(addrA)
		before = f.calls
		_, e = b.Commit(124)
		return e
	})
	if !IsHostStop(e) {
		t.Fatalf("expected missing canonical update sibling, got %v", e)
	}
	if f.calls != before {
		t.Fatal("hash-only failure triggered speculative RPC")
	}
}
func TestDeterministicNativeWitnessSeal(t *testing.T) {
	var commitments []string
	for i := 0; i < 2; i++ {
		f := makeFixture(t)
		b := fixtureBridge(t, f)
		e := b.Protect(func() error {
			s, e := b.State()
			if e != nil {
				return e
			}
			s.GetState(addrA, slot0)
			s.GetCode(addrA)
			return nil
		})
		if e != nil {
			t.Fatal(e)
		}
		pin, _, e := b.Seal()
		if e != nil {
			t.Fatal(e)
		}
		commitments = append(commitments, pin)
		if e = b.hydrate(addrB, nil); !IsHostStop(e) {
			t.Fatal("sealed store accepted additions")
		}
	}
	if commitments[0] != commitments[1] {
		t.Fatal("nondeterministic witness commitment")
	}
}
