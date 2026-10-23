package prestate

import (
	"encoding/json"
	"errors"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/offchainlabs/nitro/arbos/arbosState"
)

type CapturedProof struct {
	Address common.Address `json:"address"`
	Slots   []common.Hash  `json:"slots"`
	Proof   *RPCProof      `json:"proof"`
}
type BlockPackage struct {
	Checkpoint Checkpoint      `json:"checkpoint"`
	Parent     json.RawMessage `json:"parent"`
	Block      json.RawMessage `json:"block"`
	Raw        []hexutil.Bytes `json:"rawTransactions"`
	State      []hexutil.Bytes `json:"state"`
	Codes      []hexutil.Bytes `json:"codes"`
	Proofs     []CapturedProof `json:"proofs"`
}
type Inventory struct {
	InputCommitment            string      `json:"inputCommitment"`
	WitnessCommitment          string      `json:"witnessCommitment"`
	Checkpoint                 Checkpoint  `json:"checkpoint"`
	BlockNumber                uint64      `json:"blockNumber"`
	BlockHash                  common.Hash `json:"blockHash"`
	ExpectedStateRoot          common.Hash `json:"expectedStateRoot"`
	ExpectedReceiptsRoot       common.Hash `json:"expectedReceiptsRoot"`
	Transactions               int         `json:"transactions"`
	ArbOSVersion               uint64      `json:"arbosVersion"`
	ChainConfigBytes           int         `json:"chainConfigBytes"`
	NodeCount                  int         `json:"nodeCount"`
	CodeCount                  int         `json:"codeCount"`
	HistoricalNativeExecutions int         `json:"historicalNativeExecutions"`
}

// AdmitPackage performs proof/header/input admission only. It does not invoke
// the EVM, StateProcessor or any external transport.
func AdmitPackage(raw []byte) (*Candidate, *Inventory, error) {
	if len(raw) > 32*1024*1024 {
		return nil, nil, errors.New("PACKAGE_SIZE_LIMIT")
	}
	var p BlockPackage
	if e := json.Unmarshal(raw, &p); e != nil {
		return nil, nil, e
	}
	nodes := map[common.Hash]hexutil.Bytes{}
	codes := map[common.Hash]hexutil.Bytes{}
	for _, n := range p.State {
		nodes[crypto.Keccak256Hash(n)] = n
	}
	for _, n := range p.Codes {
		codes[crypto.Keccak256Hash(n)] = n
	}
	for _, proof := range p.Proofs {
		used, e := verifyProof(p.Checkpoint.StateRoot, proof.Address, proof.Slots, proof.Proof)
		if e != nil {
			return nil, nil, e
		}
		for h, n := range used {
			nodes[h] = n
		}
	}
	b, e := NewBridge(p.Checkpoint, Budget{MaxRequests: 1, MaxBytes: 32 * 1024 * 1024, MaxResponseBytes: 8 * 1024 * 1024, ExpiresAt: time.Now().Add(time.Minute)}, nil)
	if e != nil {
		return nil, nil, e
	}
	defer b.Close()
	if e = b.LoadWitness(p.Checkpoint, nodes, codes); e != nil {
		return nil, nil, e
	}
	var config []byte
	var version uint64
	if e = b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		a, e := arbosState.OpenSystemArbosState(s, nil, true)
		if e != nil {
			return b.stop("MISSING_NITRO_CONTEXT", e)
		}
		version = a.ArbOSVersion()
		config, e = a.ChainConfig()
		if e != nil {
			return b.stop("MISSING_CHAIN_CONFIG", e)
		}
		return s.Error()
	}); e != nil {
		return nil, nil, e
	}
	candidate, e := ImportBlock(p.Checkpoint, p.Parent, p.Block, p.Raw, config)
	if e != nil {
		return nil, nil, e
	}
	if _, e = ValidateConfig(config, version); e != nil {
		return nil, nil, e
	}
	pin, _, e := b.Seal()
	if e != nil {
		return nil, nil, e
	}
	h := candidate.block.Header()
	inventory := &Inventory{candidate.InputCommitment(), pin, p.Checkpoint, h.Number.Uint64(), h.Hash(), h.Root, h.ReceiptHash, len(p.Raw), version, len(config), len(nodes), len(codes), 0}
	return candidate, inventory, nil
}
