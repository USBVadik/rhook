// Bounded native execution harness. No RPC or canonical output state inputs.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"sync"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/consensus"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/core/vm"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethdb"
	"github.com/ethereum/go-ethereum/params"
	"github.com/offchainlabs/nitro/arbos"
	_ "github.com/offchainlabs/nitro/gethhook"
)

type input struct {
	Parent, Header        *types.Header
	Transactions          []hexutil.Bytes
	DocumentedChainConfig *params.ChainConfig
}
type witness struct {
	ParentStateRoot             common.Hash
	NodesByKeccak, CodeByKeccak map[common.Hash]hexutil.Bytes
}
type failure struct {
	Kind    string `json:"kind"`
	Address string `json:"address,omitempty"`
	Slot    string `json:"slot,omitempty"`
	Detail  string `json:"detail"`
}

func (f failure) Error() string { b, _ := json.Marshal(f); return string(b) }
func must(err error) {
	if err != nil {
		panic(err)
	}
}
func require(ok bool, text string) {
	if !ok {
		panic(fmt.Errorf("%s", text))
	}
}

type audit struct {
	mu    sync.Mutex
	reads map[string]bool
	nodes map[string]bool
}

func (a *audit) read(key string) { a.mu.Lock(); defer a.mu.Unlock(); a.reads[key] = true }
func (a *audit) node(key string) { a.mu.Lock(); defer a.mu.Unlock(); a.nodes[key] = true }
func keys(m map[string]bool) []string {
	v := make([]string, 0, len(m))
	for k := range m {
		v = append(v, k)
	}
	sort.Strings(v)
	return v
}

type disk struct {
	ethdb.Database
	audit *audit
}

func (d *disk) Get(key []byte) ([]byte, error) {
	v, e := d.Database.Get(key)
	if len(key) == 32 && e == nil {
		d.audit.node(hexutil.Encode(key))
	}
	return v, e
}

// Native trie reads distinguish proven absence from missing nodes. Fail before
// StateDB can turn a reader error into a zero value with a deferred dbErr.
type strictReader struct {
	state.Reader
	audit *audit
}

func (r *strictReader) Account(a common.Address) (*types.StateAccount, error) {
	r.audit.read("account:" + a.Hex())
	v, e := r.Reader.Account(a)
	if e != nil {
		panic(failure{"MISSING_ACCOUNT", a.Hex(), "", e.Error()})
	}
	return v, nil
}
func (r *strictReader) Storage(a common.Address, k common.Hash) (common.Hash, error) {
	r.audit.read("storage:" + a.Hex() + ":" + k.Hex())
	v, e := r.Reader.Storage(a, k)
	if e != nil {
		panic(failure{"MISSING_STORAGE", a.Hex(), k.Hex(), e.Error()})
	}
	return v, nil
}
func (r *strictReader) Code(a common.Address, h common.Hash) ([]byte, error) {
	r.audit.read("code:" + a.Hex() + ":" + h.Hex())
	v, e := r.Reader.Code(a, h)
	if e != nil || crypto.Keccak256Hash(v) != h {
		panic(failure{"MISSING_CODE", a.Hex(), "", fmt.Sprintf("code hash %s: %v", h, e)})
	}
	return v, nil
}
func (r *strictReader) CodeSize(a common.Address, h common.Hash) (int, error) {
	v, e := r.Code(a, h)
	return len(v), e
}

type strictDB struct {
	state.Database
	audit *audit
}

func (d *strictDB) Reader(root common.Hash) (state.Reader, error) {
	r, e := d.Database.Reader(root)
	if e != nil {
		return nil, e
	}
	return &strictReader{r, d.audit}, nil
}

type captureEngine struct {
	arbos.Engine
	finalized *types.Header
}

func (e *captureEngine) Finalize(c consensus.ChainHeaderReader, h *types.Header, s vm.StateDB, b *types.Body) {
	e.Engine.Finalize(c, h, s, b)
	e.finalized = types.CopyHeader(h)
}

type context struct {
	config  *params.ChainConfig
	parent  *types.Header
	engine  *captureEngine
	headers map[common.Hash]*types.Header
}

func (c *context) Config() *params.ChainConfig  { return c.config }
func (c *context) Engine() consensus.Engine     { return c.engine }
func (c *context) CurrentHeader() *types.Header { return types.CopyHeader(c.parent) }
func (c *context) GetHeader(h common.Hash, n uint64) *types.Header {
	if found, ok := c.headers[h]; ok && found.Number.Uint64() == n {
		return types.CopyHeader(found)
	}
	panic(failure{Kind: "MISSING_HEADER", Detail: fmt.Sprintf("%d %s", n, h)})
}
func (c *context) GetHeaderByNumber(n uint64) *types.Header { return c.GetHeader(c.parent.Hash(), n) }
func (c *context) GetHeaderByHash(h common.Hash) *types.Header {
	return c.GetHeader(h, c.parent.Number.Uint64())
}

func load(path string, v any) string {
	b, e := os.ReadFile(path)
	must(e)
	must(json.Unmarshal(b, v))
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
