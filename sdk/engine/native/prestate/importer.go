package prestate

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/params"
	"github.com/ethereum/go-ethereum/rlp"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/offchainlabs/nitro/arbos/util"
)

type Candidate struct {
	checkpoint      Checkpoint
	parent          *types.Header
	block           *types.Block
	config          *params.ChainConfig
	configRaw       []byte
	inputCommitment string
}

func (c *Candidate) InputCommitment() string { return c.inputCommitment }
func ValidateConfig(raw []byte, version uint64) (*params.ChainConfig, error) {
	var cfg params.ChainConfig
	if err := json.Unmarshal(raw, &cfg); err != nil {
		return nil, err
	}
	var m map[string]json.RawMessage
	if err := json.Unmarshal(raw, &m); err != nil {
		return nil, err
	}
	allowed := map[string]bool{"chainId": true, "homesteadBlock": true, "daoForkBlock": true, "daoForkSupport": true, "eip150Block": true, "eip150Hash": true, "eip155Block": true, "eip158Block": true, "byzantiumBlock": true, "constantinopleBlock": true, "petersburgBlock": true, "istanbulBlock": true, "muirGlacierBlock": true, "berlinBlock": true, "londonBlock": true, "clique": true, "arbitrum": true}
	for k := range m {
		if !allowed[k] {
			return nil, fmt.Errorf("UNSUPPORTED_CHAIN_CONFIG_FIELD: %s", k)
		}
	}
	if version != 61 || cfg.ChainID == nil || cfg.ChainID.Cmp(big.NewInt(4663)) != 0 || cfg.DAOForkBlock != nil || !cfg.IsArbitrum() {
		return nil, errors.New("INCORRECT_CHAIN_CONFIG_OR_ARBOS_VERSION")
	}
	for _, v := range []*big.Int{cfg.HomesteadBlock, cfg.EIP150Block, cfg.EIP155Block, cfg.EIP158Block, cfg.ByzantiumBlock, cfg.ConstantinopleBlock, cfg.PetersburgBlock, cfg.IstanbulBlock, cfg.MuirGlacierBlock, cfg.BerlinBlock, cfg.LondonBlock} {
		if v == nil || v.Sign() != 0 {
			return nil, errors.New("UNSUPPORTED_FORK_SCHEDULE")
		}
	}
	arb := cfg.ArbitrumChainParams
	if arb.MaxCodeSize != 98304 || arb.MaxInitCodeSize != 196608 || arb.AllowDebugPrecompiles || arb.DataAvailabilityCommittee || arb.GenesisBlockNum != 0 || arb.InitialArbOSVersion != 51 {
		return nil, errors.New("UNSUPPORTED_NITRO_CHAIN_CONFIG")
	}
	return &cfg, nil
}
func decodeHeader(raw []byte) (*types.Header, error) {
	var h types.Header
	if err := json.Unmarshal(raw, &h); err != nil {
		return nil, err
	}
	var m map[string]json.RawMessage
	if err := json.Unmarshal(raw, &m); err != nil {
		return nil, err
	}
	var hash common.Hash
	if err := json.Unmarshal(m["hash"], &hash); err != nil || hash != h.Hash() {
		return nil, errors.New("HEADER_HASH_MISMATCH")
	}
	for _, name := range []string{"withdrawalsRoot", "blobGasUsed", "excessBlobGas", "parentBeaconBlockRoot", "requestsHash", "blockAccessListHash", "slotNumber"} {
		if v := m[name]; v != nil && !bytes.Equal(v, []byte("null")) {
			return nil, fmt.Errorf("UNSUPPORTED_HEADER_EXTENSION: %s", name)
		}
	}
	if h.Number == nil || !h.Number.IsUint64() || h.Difficulty == nil || h.BaseFee == nil || h.Difficulty.Cmp(big.NewInt(1)) != 0 || len(h.Extra) != 32 {
		return nil, errors.New("INCOMPLETE_NITRO_HEADER")
	}
	return &h, nil
}
func ImportBlock(c Checkpoint, parentJSON, blockJSON []byte, rawTxs []hexutil.Bytes, configRaw []byte) (*Candidate, error) {
	cfg, err := ValidateConfig(configRaw, 61)
	if err != nil {
		return nil, err
	}
	p, err := decodeHeader(parentJSON)
	if err != nil {
		return nil, err
	}
	h, err := decodeHeader(blockJSON)
	if err != nil {
		return nil, err
	}
	if c.ChainID != 4663 || p.Hash() != c.BlockHash || p.Root != c.StateRoot || p.Number.Uint64() != c.BlockNumber || c.BlockNumber == ^uint64(0) || h.Number.Uint64() != c.BlockNumber+1 || h.ParentHash != p.Hash() || h.Time < p.Time {
		return nil, errors.New("CHECKPOINT_OR_PARENT_LINK_MISMATCH")
	}
	if types.DeserializeHeaderExtraInformation(h).ArbOSFormatVersion != 61 || types.DeserializeHeaderExtraInformation(p).ArbOSFormatVersion != 61 {
		return nil, errors.New("MISSING_NITRO_HEADER_CONTEXT")
	}
	var body struct {
		Transactions []json.RawMessage `json:"transactions"`
	}
	if err = json.Unmarshal(blockJSON, &body); err != nil {
		return nil, err
	}
	if len(rawTxs) == 0 || len(rawTxs) != len(body.Transactions) {
		return nil, errors.New("COMPLETE_ORDERED_INPUTS_REQUIRED")
	}
	txs := make(types.Transactions, len(rawTxs))
	runCtx := core.NewMessageReplayContext()
	signer := types.MakeSigner(cfg, h.Number, h.Time, 61)
	for i, raw := range rawTxs {
		tx := new(types.Transaction)
		encoded := []byte(raw)
		if len(raw) > 0 && raw[0] <= 0x7f {
			encoded, err = rlp.EncodeToBytes([]byte(raw))
			if err != nil {
				return nil, err
			}
		}
		if err = rlp.DecodeBytes(encoded, tx); err != nil {
			return nil, fmt.Errorf("RAW_ENVELOPE_%d: %w", i, err)
		}
		back, e := tx.MarshalBinary()
		if e != nil || !bytes.Equal(raw, back) {
			return nil, errors.New("NONCANONICAL_ORIGINAL_ENVELOPE")
		}
		var expected common.Hash
		if err = json.Unmarshal(body.Transactions[i], &expected); err != nil {
			var entry struct {
				Hash common.Hash `json:"hash"`
			}
			if err = json.Unmarshal(body.Transactions[i], &entry); err != nil {
				return nil, err
			}
			expected = entry.Hash
		}
		if tx.Hash() != expected {
			return nil, errors.New("ORDERED_TRANSACTION_IDENTITY_MISMATCH")
		}
		if tx.ChainId().Sign() != 0 && tx.ChainId().Cmp(cfg.ChainID) != 0 {
			return nil, errors.New("TRANSACTION_CHAIN_MISMATCH")
		}
		if _, e = core.TransactionToMessage(tx, signer, h.BaseFee, runCtx); e != nil {
			return nil, fmt.Errorf("NATIVE_MESSAGE_ADMISSION_%d: %w", i, e)
		}
		if i == 0 && tx.Type() != types.ArbitrumInternalTxType {
			return nil, errors.New("ORDERED_NITRO_SYSTEM_CONTEXT_REQUIRED")
		}
		txs[i] = tx
	}
	if types.DeriveSha(txs, trie.NewStackTrie(nil)) != h.TxHash {
		return nil, errors.New("TRANSACTIONS_ROOT_MISMATCH")
	}
	args, err := util.UnpackInternalTxDataStartBlock(txs[0].Data())
	if err != nil {
		return nil, errors.New("START_BLOCK_SYSTEM_INPUT_REQUIRED")
	}
	l2, ok := args["l2BlockNumber"].(uint64)
	if !ok || l2 != h.Number.Uint64() {
		return nil, errors.New("SYSTEM_L2_NUMBER_MISMATCH")
	}
	delta, ok := args["timePassed"].(uint64)
	if !ok || delta != h.Time-p.Time {
		return nil, errors.New("SYSTEM_TIME_CONTEXT_MISMATCH")
	}
	l1, ok := args["l1BlockNumber"].(uint64)
	if !ok || l1 != types.DeserializeHeaderExtraInformation(h).L1BlockNumber {
		return nil, errors.New("SYSTEM_L1_CONTEXT_MISMATCH")
	}
	encoded, err := json.Marshal(struct {
		Context Checkpoint
		Parent  json.RawMessage
		Block   json.RawMessage
		Raw     []hexutil.Bytes
		Config  hexutil.Bytes
	}{c, parentJSON, blockJSON, rawTxs, configRaw})
	if err != nil {
		return nil, err
	}
	digest := sha256.Sum256(append([]byte("rhook/external-canonical-block-inputs/0.1\n"), encoded...))
	return &Candidate{c, p, types.NewBlockWithHeader(h).WithBody(types.Body{Transactions: txs}), cfg, common.CopyBytes(configRaw), hex.EncodeToString(digest[:])}, nil
}
