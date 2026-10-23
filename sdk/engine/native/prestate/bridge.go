// Package prestate integrates original-root proof hydration with the existing
// Go/Nitro StateDB. It never injects semantic values into the live write overlay.
package prestate

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/rawdb"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethdb"
	"github.com/ethereum/go-ethereum/triedb"
)

type Checkpoint struct {
	ChainID     uint64      `json:"chainId"`
	BlockNumber uint64      `json:"blockNumber"`
	BlockHash   common.Hash `json:"blockHash"`
	StateRoot   common.Hash `json:"stateRoot"`
}
type Budget struct {
	MaxRequests      int
	MaxBytes         int64
	MaxResponseBytes int64
	ExpiresAt        time.Time
	PerRequest       time.Duration
}
type Source interface {
	GetProof(context.Context, Checkpoint, common.Address, []common.Hash) (*RPCProof, error)
	GetCode(context.Context, Checkpoint, common.Address) ([]byte, error)
}
type HostStop struct {
	Code   string
	Detail string
}

func (e *HostStop) Error() string { return e.Code + ": " + e.Detail }
func IsHostStop(e error) bool     { var h *HostStop; return errors.As(e, &h) }

type Attempt struct {
	Index   int            `json:"index"`
	Kind    string         `json:"kind"`
	Address common.Address `json:"address"`
	Slots   []common.Hash  `json:"slots,omitempty"`
	Context Checkpoint     `json:"context"`
}
type Bridge struct {
	checkpoint       Checkpoint
	budget           Budget
	source           Source
	mu               sync.Mutex
	fetchMu          sync.Mutex
	fatal            *HostStop
	sealed           bool
	executionStarted bool
	lpPatched        bool
	observation      *NativeEconomicObservation
	requests         int
	bytes            int64
	disk             ethdb.Database
	tdb              *triedb.Database
	base             state.Database
	live             *state.StateDB
	nodes            map[common.Hash][]byte
	codes            map[common.Hash][]byte
	attempts         []Attempt
}

func NewBridge(c Checkpoint, l Budget, p Source) (*Bridge, error) {
	if c.ChainID != 4663 || c.StateRoot == (common.Hash{}) || c.BlockHash == (common.Hash{}) || l.MaxRequests <= 0 || l.MaxBytes <= 0 || l.MaxResponseBytes <= 0 || l.ExpiresAt.IsZero() {
		return nil, errors.New("invalid immutable checkpoint/budget")
	}
	d := rawdb.NewMemoryDatabase()
	td := triedb.NewDatabase(d, triedb.HashDefaults)
	return &Bridge{checkpoint: c, budget: l, source: p, disk: d, tdb: td, base: state.NewDatabase(td, nil), nodes: map[common.Hash][]byte{}, codes: map[common.Hash][]byte{}}, nil
}
func (b *Bridge) Close() { b.tdb.Close(); b.disk.Close() }
func (b *Bridge) Fatal() error {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.fatal == nil {
		return nil
	}
	return b.fatal
}
func (b *Bridge) stop(code string, err error) *HostStop {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.fatal == nil {
		b.fatal = &HostStop{code, fmt.Sprint(err)}
	}
	return b.fatal
}
func (b *Bridge) guard() {
	if e := b.Fatal(); e != nil {
		panic(e)
	}
}
func (b *Bridge) Protect(fn func() error) (err error) {
	defer func() {
		if p := recover(); p != nil {
			if h, ok := p.(*HostStop); ok {
				err = h
			} else {
				panic(p)
			}
		}
		if f := b.Fatal(); f != nil {
			err = f
		}
	}()
	b.guard()
	return fn()
}
func (b *Bridge) request(kind string, addr common.Address, slots []common.Hash) (context.Context, context.CancelFunc, error) {
	b.guard()
	if b.sealed {
		return nil, nil, b.stop("WITNESS_SEALED", nil)
	}
	if time.Now().After(b.budget.ExpiresAt) {
		return nil, nil, b.stop("CHECKPOINT_WINDOW_EXPIRED", nil)
	}
	if b.requests >= b.budget.MaxRequests {
		return nil, nil, b.stop("REQUEST_BUDGET_EXHAUSTED", nil)
	}
	b.requests++
	b.attempts = append(b.attempts, Attempt{b.requests, kind, addr, append([]common.Hash(nil), slots...), b.checkpoint})
	end := b.budget.ExpiresAt
	if b.budget.PerRequest > 0 && time.Now().Add(b.budget.PerRequest).Before(end) {
		end = time.Now().Add(b.budget.PerRequest)
	}
	ctx, cancel := context.WithDeadline(context.Background(), end)
	return ctx, cancel, nil
}
func (b *Bridge) response(body []byte) error {
	if time.Now().After(b.budget.ExpiresAt) {
		return b.stop("CHECKPOINT_WINDOW_EXPIRED", nil)
	}
	n := int64(len(body))
	if n > b.budget.MaxResponseBytes || b.bytes+n > b.budget.MaxBytes {
		return b.stop("BYTE_BUDGET_EXHAUSTED", nil)
	}
	b.bytes += n
	return nil
}
func (b *Bridge) hydrate(addr common.Address, slots []common.Hash) error {
	b.fetchMu.Lock()
	defer b.fetchMu.Unlock()
	ctx, cancel, e := b.request("eth_getProof", addr, slots)
	if e != nil {
		return e
	}
	defer cancel()
	if b.source == nil {
		return b.stop("PROOF_SOURCE_UNAVAILABLE", nil)
	}
	p, e := b.source.GetProof(ctx, b.checkpoint, addr, slots)
	if e != nil {
		return b.stop("PROOF_SOURCE_UNAVAILABLE", e)
	}
	if ctx.Err() != nil {
		return b.stop("RPC_DEADLINE_EXPIRED", nil)
	}
	raw, e := json.Marshal(p)
	if e != nil {
		return b.stop("MALFORMED_PROOF", e)
	}
	if e = b.response(raw); e != nil {
		return e
	}
	nodes, e := verifyProof(b.checkpoint.StateRoot, addr, slots, p)
	if e != nil {
		return b.stop("PROOF_AUTHENTICATION_FAILED", e)
	}
	for h, v := range nodes {
		b.nodes[h] = common.CopyBytes(v)
		rawdb.WriteLegacyTrieNode(b.disk, h, v)
	}
	return nil
}

type strictDB struct {
	state.Database
	bridge *Bridge
}

func (d *strictDB) Reader(root common.Hash) (state.Reader, error) {
	return &hydratingReader{db: d.Database, root: root, b: d.bridge}, nil
}

type hydratingReader struct {
	db   state.Database
	root common.Hash
	b    *Bridge
}

func (r *hydratingReader) reader() (state.Reader, error) { r.b.guard(); return r.db.Reader(r.root) }
func (r *hydratingReader) Account(a common.Address) (*types.StateAccount, error) {
	v, e := r.reader()
	var account *types.StateAccount
	if e == nil {
		account, e = v.Account(a)
	}
	if e != nil {
		if e = r.b.hydrate(a, nil); e != nil {
			panic(e)
		}
		v, e = r.reader()
		if e == nil {
			account, e = v.Account(a)
		}
	}
	if e != nil {
		panic(r.b.stop("ACCOUNT_PREIMAGE_UNAVAILABLE", e))
	}
	return account, nil
}
func (r *hydratingReader) Storage(a common.Address, k common.Hash) (common.Hash, error) {
	v, e := r.reader()
	var value common.Hash
	if e == nil {
		value, e = v.Storage(a, k)
	}
	if e != nil {
		if e = r.b.hydrate(a, []common.Hash{k}); e != nil {
			panic(e)
		}
		v, e = r.reader()
		if e == nil {
			value, e = v.Storage(a, k)
		}
	}
	if e != nil {
		panic(r.b.stop("STORAGE_PREIMAGE_UNAVAILABLE", e))
	}
	return value, nil
}
func (r *hydratingReader) Code(a common.Address, h common.Hash) ([]byte, error) {
	r.b.guard()
	if h == types.EmptyCodeHash {
		return nil, nil
	}
	v, e := r.reader()
	var code []byte
	if e == nil {
		code, e = v.Code(a, h)
	}
	if e == nil && crypto.Keccak256Hash(code) == h {
		return code, nil
	}
	account, e := r.Account(a)
	if e != nil || account == nil || common.BytesToHash(account.CodeHash) != h {
		panic(r.b.stop("CODE_ACCOUNT_BINDING_FAILED", e))
	}
	b := r.b
	b.fetchMu.Lock()
	defer b.fetchMu.Unlock()
	ctx, cancel, e := b.request("eth_getCode", a, nil)
	if e != nil {
		panic(e)
	}
	defer cancel()
	if b.source == nil {
		panic(b.stop("CODE_SOURCE_UNAVAILABLE", nil))
	}
	code, e = b.source.GetCode(ctx, b.checkpoint, a)
	if e != nil {
		panic(b.stop("CODE_SOURCE_UNAVAILABLE", e))
	}
	if ctx.Err() != nil {
		panic(b.stop("RPC_DEADLINE_EXPIRED", nil))
	}
	if e = b.response(code); e != nil {
		panic(e)
	}
	if crypto.Keccak256Hash(code) != h {
		panic(b.stop("CODE_PREIMAGE_HASH_MISMATCH", nil))
	}
	b.codes[h] = common.CopyBytes(code)
	rawdb.WriteCode(b.disk, h, code)
	return code, nil
}
func (r *hydratingReader) CodeSize(a common.Address, h common.Hash) (int, error) {
	v, e := r.Code(a, h)
	return len(v), e
}
func (b *Bridge) State() (*state.StateDB, error) {
	b.guard()
	if b.live != nil {
		return b.live, nil
	}
	s, e := state.New(b.checkpoint.StateRoot, &strictDB{b.base, b})
	if e != nil {
		return nil, b.stop("STATE_OPEN_FAILURE", e)
	}
	b.live = s
	return s, nil
}
func (b *Bridge) LoadWitness(c Checkpoint, nodes, codes map[common.Hash]hexutil.Bytes) error {
	b.fetchMu.Lock()
	defer b.fetchMu.Unlock()
	b.guard()
	if c != b.checkpoint || b.live != nil || b.sealed {
		return b.stop("INITIAL_WITNESS_BINDING_OR_LIFECYCLE", nil)
	}
	var size int64
	for _, set := range []map[common.Hash]hexutil.Bytes{nodes, codes} {
		for hash, raw := range set {
			size += int64(len(raw))
			if crypto.Keccak256Hash(raw) != hash {
				return b.stop("INITIAL_PREIMAGE_HASH_MISMATCH", nil)
			}
		}
	}
	if size > b.budget.MaxBytes-b.bytes {
		return b.stop("INITIAL_WITNESS_BYTE_BUDGET", nil)
	}
	for h, raw := range nodes {
		b.nodes[h] = common.CopyBytes(raw)
		rawdb.WriteLegacyTrieNode(b.disk, h, raw)
	}
	for h, raw := range codes {
		b.codes[h] = common.CopyBytes(raw)
		rawdb.WriteCode(b.disk, h, raw)
	}
	b.bytes += size
	return nil
}
func (b *Bridge) Commit(number uint64) (common.Hash, error) {
	b.guard()
	if b.live == nil {
		return common.Hash{}, b.stop("STATE_NOT_OPEN", nil)
	}
	root, e := b.live.Commit(number, true, false)
	if e != nil {
		return common.Hash{}, b.stop("TRIE_UPDATE_PREIMAGE_UNAVAILABLE", e)
	}
	b.guard()
	return root, nil
}
func (b *Bridge) Seal() (string, []byte, error) {
	b.fetchMu.Lock()
	defer b.fetchMu.Unlock()
	b.guard()
	if b.sealed {
		return "", nil, b.stop("WITNESS_SEALED", nil)
	}
	raw, e := json.Marshal(struct {
		Checkpoint Checkpoint             `json:"checkpoint"`
		Nodes      map[common.Hash][]byte `json:"nodes"`
		Codes      map[common.Hash][]byte `json:"codes"`
		Attempts   []Attempt              `json:"attempts"`
	}{b.checkpoint, b.nodes, b.codes, b.attempts})
	if e != nil {
		return "", nil, e
	}
	b.sealed = true
	hash := sha256.Sum256(append([]byte("rhook/native-prestate-witness/0.1\n"), raw...))
	return hex.EncodeToString(hash[:]), raw, nil
}
