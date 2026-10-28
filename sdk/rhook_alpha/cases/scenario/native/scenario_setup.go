// This additive file is staged alongside unchanged prestate sources. It is not
// installed into the accepted engine. Historical entry points do not call it.
package prestate

import (
	"errors"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/trie"
)

// CloseScenarioBridge preserves both close errors instead of discarding them.
func CloseScenarioBridge(b *Bridge) error { return errors.Join(b.tdb.Close(), b.disk.Close()) }

func ScenarioLookupAttempts(b *Bridge) []Attempt {
	rows := append([]Attempt(nil), b.attempts...)
	for i := range rows {
		rows[i].Slots = append([]common.Hash(nil), rows[i].Slots...)
	}
	return rows
}

// CommitScenarioSetup records an explicit simulation mint as a derived state,
// then opens a fresh StateDB for Nitro's clean-block accounting. The immutable
// proof checkpoint remains the original root; missing unchanged subtrees still
// resolve only there. This function never changes that checkpoint or its Source.
func CommitScenarioSetup(b *Bridge, c Checkpoint, expectedMint *big.Int) (root common.Hash, err error) {
	err = b.Protect(func() error {
		if b.checkpoint != c || b.live == nil || b.executionStarted || b.sealed || expectedMint == nil || expectedMint.Sign() <= 0 {
			return b.stop("SCENARIO_SETUP_LIFECYCLE", nil)
		}
		if b.live.GetUnexpectedBalanceDelta().Cmp(expectedMint) != 0 {
			return b.stop("SCENARIO_SETUP_MINT_MISMATCH", nil)
		}
		var e error
		root, e = CommitScenarioState(b, c.BlockNumber)
		if e != nil {
			return e
		}
		if e = b.tdb.Commit(root, false); e != nil {
			return b.stop("SCENARIO_SETUP_PERSISTENCE", e)
		}
		next, e := state.New(root, &strictDB{b.base, b})
		if e != nil {
			return b.stop("SCENARIO_SETUP_REOPEN", e)
		}
		if next.GetUnexpectedBalanceDelta().Sign() != 0 {
			return b.stop("SCENARIO_SETUP_ACCOUNTING", nil)
		}
		b.live = next
		b.executionStarted = true
		return nil
	})
	return
}

// The observer reports backing-reader coverage, not every StateDB cache hit.
// It never supplies values or changes hydration/authentication behavior.
type ScenarioAccess struct {
	Kind        string         `json:"kind"`
	Address     common.Address `json:"address"`
	Key         common.Hash    `json:"key,omitempty"`
	Root        common.Hash    `json:"readerRoot"`
	Success     bool           `json:"success"`
	Error       string         `json:"error,omitempty"`
	MissingNode common.Hash    `json:"missingNodeHash,omitempty"`
	Owner       common.Hash    `json:"ownerHash,omitempty"`
	Path        []byte         `json:"nibblePath,omitempty"`
}
type scenarioDB struct {
	state.Database
	observe func(ScenarioAccess)
}
type scenarioReader struct {
	state.Reader
	root    common.Hash
	observe func(ScenarioAccess)
}

func (d *scenarioDB) Reader(root common.Hash) (state.Reader, error) {
	r, e := d.Database.Reader(root)
	if e != nil {
		return nil, e
	}
	return &scenarioReader{r, root, d.observe}, nil
}
func (r *scenarioReader) record(kind string, a common.Address, k common.Hash, e error) {
	row := ScenarioAccess{Kind: kind, Address: a, Key: k, Root: r.root, Success: e == nil}
	if e != nil {
		row.Error = e.Error()
	}
	var missing *trie.MissingNodeError
	if errors.As(e, &missing) {
		row.MissingNode = missing.NodeHash
		row.Owner = missing.Owner
		row.Path = append([]byte(nil), missing.Path...)
	}
	r.observe(row)
}
func (r *scenarioReader) Account(a common.Address) (v *types.StateAccount, e error) {
	v, e = r.Reader.Account(a)
	r.record("ACCOUNT", a, common.Hash{}, e)
	return
}
func (r *scenarioReader) Storage(a common.Address, k common.Hash) (v common.Hash, e error) {
	v, e = r.Reader.Storage(a, k)
	r.record("STORAGE", a, k, e)
	return
}
func (r *scenarioReader) Code(a common.Address, k common.Hash) (v []byte, e error) {
	v, e = r.Reader.Code(a, k)
	observed := e
	if e == nil && crypto.Keccak256Hash(v) != k {
		observed = errors.New("CODE_PREIMAGE_UNAVAILABLE")
	}
	r.record("CODE", a, k, observed)
	return
}
func (r *scenarioReader) CodeSize(a common.Address, k common.Hash) (int, error) {
	v, e := r.Code(a, k)
	return len(v), e
}
func ObserveScenarioBridge(b *Bridge, observe func(ScenarioAccess)) {
	b.base = &scenarioDB{b.base, observe}
}
func CommitScenarioState(b *Bridge, number uint64) (common.Hash, error) {
	b.guard()
	if b.live == nil {
		return common.Hash{}, b.stop("STATE_NOT_OPEN", nil)
	}
	root, e := b.live.Commit(number, true, false)
	if e != nil {
		if d, ok := b.base.(*scenarioDB); ok {
			r := scenarioReader{root: b.checkpoint.StateRoot, observe: d.observe}
			r.record("TRIE_UPDATE", common.Address{}, common.Hash{}, e)
		}
		return common.Hash{}, b.stop("TRIE_UPDATE_PREIMAGE_UNAVAILABLE", e)
	}
	b.guard()
	return root, nil
}
