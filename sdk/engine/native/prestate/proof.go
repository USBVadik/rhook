package prestate

import (
	"bytes"
	"errors"
	"fmt"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/rlp"
	"github.com/ethereum/go-ethereum/trie"
)

type RPCStorageProof struct {
	Key   common.Hash     `json:"key"`
	Value *hexutil.Big    `json:"value"`
	Proof []hexutil.Bytes `json:"proof"`
}
type RPCProof struct {
	Address      common.Address    `json:"address"`
	AccountProof []hexutil.Bytes   `json:"accountProof"`
	Balance      *hexutil.Big      `json:"balance"`
	Nonce        hexutil.Uint64    `json:"nonce"`
	CodeHash     common.Hash       `json:"codeHash"`
	StorageHash  common.Hash       `json:"storageHash"`
	StorageProof []RPCStorageProof `json:"storageProof"`
}
type proofDB struct {
	all  map[common.Hash][]byte
	used map[common.Hash][]byte
}

func (d *proofDB) Has(k []byte) (bool, error) { _, ok := d.all[common.BytesToHash(k)]; return ok, nil }
func (d *proofDB) Get(k []byte) ([]byte, error) {
	h := common.BytesToHash(k)
	v, ok := d.all[h]
	if !ok {
		return nil, errors.New("missing proof node")
	}
	d.used[h] = v
	return v, nil
}
func proofDBFor(nodes []hexutil.Bytes) *proofDB {
	d := &proofDB{all: map[common.Hash][]byte{}, used: map[common.Hash][]byte{}}
	for _, raw := range nodes {
		d.all[crypto.Keccak256Hash(raw)] = common.CopyBytes(raw)
	}
	return d
}
func verifyProof(root common.Hash, addr common.Address, keys []common.Hash, p *RPCProof) (map[common.Hash][]byte, error) {
	if p == nil || p.Address != addr || p.Balance == nil || (*big.Int)(p.Balance).Sign() < 0 || (*big.Int)(p.Balance).BitLen() > 256 {
		return nil, errors.New("account metadata")
	}
	adb := proofDBFor(p.AccountProof)
	raw, err := trie.VerifyProof(root, crypto.Keccak256(addr[:]), adb)
	if err != nil {
		return nil, fmt.Errorf("account proof: %w", err)
	}
	account := types.StateAccount{Root: types.EmptyRootHash, CodeHash: types.EmptyCodeHash.Bytes()}
	balance := new(big.Int)
	if raw != nil {
		if err = rlp.DecodeBytes(raw, &account); err != nil {
			return nil, err
		}
		balance = account.Balance.ToBig()
	}
	if uint64(p.Nonce) != account.Nonce || balance.Cmp((*big.Int)(p.Balance)) != 0 || p.StorageHash != account.Root || !bytes.Equal(p.CodeHash[:], account.CodeHash) {
		return nil, errors.New("account metadata differs from proved leaf")
	}
	if len(keys) != len(p.StorageProof) {
		return nil, errors.New("storage subject count")
	}
	expected := map[common.Hash]bool{}
	for _, k := range keys {
		if expected[k] {
			return nil, errors.New("duplicate requested slot")
		}
		expected[k] = true
	}
	used := adb.used
	for _, sp := range p.StorageProof {
		if !expected[sp.Key] || sp.Value == nil {
			return nil, errors.New("unexpected storage subject")
		}
		delete(expected, sp.Key)
		sdb := proofDBFor(sp.Proof)
		var v []byte
		if account.Root != types.EmptyRootHash {
			v, err = trie.VerifyProof(account.Root, crypto.Keccak256(sp.Key[:]), sdb)
			if err != nil {
				return nil, fmt.Errorf("storage proof: %w", err)
			}
		}
		value := new(big.Int)
		if v != nil {
			var content []byte
			if err = rlp.DecodeBytes(v, &content); err != nil {
				return nil, err
			}
			if len(content) > 32 || (len(content) > 0 && content[0] == 0) {
				return nil, errors.New("noncanonical storage integer")
			}
			value.SetBytes(content)
		}
		if value.Cmp((*big.Int)(sp.Value)) != 0 {
			return nil, errors.New("storage metadata differs from proved leaf")
		}
		for h, n := range sdb.used {
			used[h] = n
		}
	}
	return used, nil
}
