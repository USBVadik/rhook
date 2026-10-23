package prestate

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/consensus"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/core/vm"
	"github.com/ethereum/go-ethereum/params"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/offchainlabs/nitro/arbos"
	"github.com/offchainlabs/nitro/arbos/arbosState"
	"github.com/offchainlabs/nitro/arbos/arbostypes"
	"github.com/offchainlabs/nitro/arbos/util"
	_ "github.com/offchainlabs/nitro/gethhook"
)

type capturingEngine struct {
	arbos.Engine
	final *types.Header
}

func (e *capturingEngine) Finalize(c consensus.ChainHeaderReader, h *types.Header, s vm.StateDB, body *types.Body) {
	e.Engine.Finalize(c, h, s, body)
	e.final = types.CopyHeader(h)
}

type nativeChain struct {
	config *params.ChainConfig
	parent *types.Header
	engine *capturingEngine
	bridge *Bridge
}

func (c *nativeChain) Config() *params.ChainConfig  { return c.config }
func (c *nativeChain) Engine() consensus.Engine     { return c.engine }
func (c *nativeChain) CurrentHeader() *types.Header { return types.CopyHeader(c.parent) }
func (c *nativeChain) GetHeader(hash common.Hash, number uint64) *types.Header {
	if hash != c.parent.Hash() || number != c.parent.Number.Uint64() {
		panic(c.bridge.stop("MISSING_ORIGINAL_HEADER", fmt.Errorf("%d %s", number, hash)))
	}
	return types.CopyHeader(c.parent)
}
func (c *nativeChain) GetHeaderByNumber(n uint64) *types.Header {
	return c.GetHeader(c.parent.Hash(), n)
}
func (c *nativeChain) GetHeaderByHash(h common.Hash) *types.Header {
	return c.GetHeader(h, c.parent.Number.Uint64())
}

type CalibrationResult struct {
	InputCommitment   string                     `json:"inputCommitment"`
	StateRoot         common.Hash                `json:"stateRoot"`
	ReceiptsRoot      common.Hash                `json:"receiptsRoot"`
	GasUsed           uint64                     `json:"gasUsed"`
	Transactions      int                        `json:"transactions"`
	WitnessCommitment string                     `json:"witnessCommitment"`
	Matched           bool                       `json:"matched"`
	BlockHash         common.Hash                `json:"blockHash"`
	ProducedHeader    *types.Header              `json:"producedHeader"`
	Receipts          types.Receipts             `json:"receipts"`
	World             string                     `json:"world"`
	Patch             *LPWriteRecord             `json:"patch,omitempty"`
	Observation       *NativeEconomicObservation `json:"observation,omitempty"`
}

type exactSequencingHooks struct {
	*arbos.NoopSequencingHooks
	failure error
}

func (h *exactSequencingHooks) TxFailed(err error) {
	if h.failure == nil {
		h.failure = err
	}
}

// RunCanonical is a single invocation, never a retry loop. Calling it for real
// history requires separate founder authorization; there is no automatic CLI.
func RunCanonical(c *Candidate, b *Bridge) (*CalibrationResult, error) {
	return runNativeBlock(c, b, nil)
}

// runNativeBlock retains one original checkpoint and one full native block call.
// A non-nil intervention changes only the initial live write overlay.
func runNativeBlock(c *Candidate, b *Bridge, intervention func(*Bridge) (*LPWriteRecord, error)) (out *CalibrationResult, err error) {
	if c == nil || b == nil || c.checkpoint != b.checkpoint {
		return nil, errors.New("CANDIDATE_CHECKPOINT_MISMATCH")
	}
	if b.executionStarted {
		return nil, b.stop("NATIVE_INSTANCE_ALREADY_CONSUMED", nil)
	}
	b.executionStarted = true
	err = b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		var patch *LPWriteRecord
		world := "ACTUAL"
		if intervention != nil {
			world = "BRANCH"
			patch, e = intervention(b)
			if e != nil {
				return e
			}
		}
		if b.observation != nil {
			b.observation.Before = observeState(s, b.observation.Plan)
		}
		arb, e := arbosState.OpenSystemArbosState(s, nil, true)
		if e != nil {
			return b.stop("NITRO_SYSTEM_CONTEXT_UNAVAILABLE", e)
		}
		raw, e := arb.ChainConfig()
		if e != nil {
			return b.stop("CHAIN_CONFIG_UNAVAILABLE", e)
		}
		cfg, e := ValidateConfig(raw, arb.ArbOSVersion())
		if e != nil {
			return b.stop("AUTHENTICATED_CHAIN_CONFIG_REJECTED", e)
		}
		if !bytes.Equal(raw, c.configRaw) {
			return b.stop("CHAIN_CONFIG_INPUT_BINDING_MISMATCH", nil)
		}
		h := c.block.Header()
		engine := &capturingEngine{}
		chain := &nativeChain{cfg, c.parent, engine, b}
		original := c.block.Transactions()
		start, e := util.UnpackInternalTxDataStartBlock(original[0].Data())
		if e != nil {
			return b.stop("START_BLOCK_CONTEXT_UNAVAILABLE", e)
		}
		l1BaseFee, ok := start["l1BaseFee"].(*big.Int)
		if !ok {
			return b.stop("START_BLOCK_BASE_FEE_UNAVAILABLE", nil)
		}
		l1Number, ok := start["l1BlockNumber"].(uint64)
		if !ok {
			return b.stop("START_BLOCK_L1_NUMBER_UNAVAILABLE", nil)
		}
		// Reconstruct only the fields consumed by this pinned producer. Timestamp
		// is the observed clamped L2 time, not a claim to recover the raw inbox message.
		l1Header := &arbostypes.L1IncomingMessageHeader{Poster: h.Coinbase, BlockNumber: l1Number, Timestamp: h.Time, L1BaseFee: l1BaseFee}
		var supplied types.Transactions
		for _, tx := range original[1:] {
			if tx.Type() != types.ArbitrumRetryTxType {
				supplied = append(supplied, tx)
			}
		}
		hooks := &exactSequencingHooks{NoopSequencingHooks: arbos.NewNoopSequencingHooks(supplied)}
		produced, outputState, receipts, e := arbos.ProduceBlockAdvanced(l1Header, binary.BigEndian.Uint64(h.Nonce[:]), c.parent, s, chain, hooks, false, core.NewMessageReplayContext(), false, nil)
		if e != nil {
			return b.stop("NATIVE_BLOCK_PROCESSOR_FAILURE", e)
		}
		if hooks.failure != nil {
			return b.stop("ORIGINAL_TRANSACTION_FAILED_NATIVE_ADMISSION", hooks.failure)
		}
		if b.observation != nil {
			b.observation.After = observeState(s, b.observation.Plan)
		}
		if outputState != s {
			return b.stop("UNEXPECTED_NATIVE_STATE_REPLACEMENT", nil)
		}
		if len(produced.Transactions()) != len(original) {
			return b.stop("GENERATED_TRANSACTION_SEQUENCE_MISMATCH", nil)
		}
		for i, tx := range produced.Transactions() {
			got, err := tx.MarshalBinary()
			if err != nil {
				return b.stop("GENERATED_ENVELOPE_ENCODING", err)
			}
			want, err := original[i].MarshalBinary()
			if err != nil || !bytes.Equal(got, want) {
				return b.stop("GENERATED_TRANSACTION_SEQUENCE_MISMATCH", err)
			}
		}
		if e = s.Error(); e != nil {
			return b.stop("NATIVE_STATE_ERROR", e)
		}
		b.guard()
		computed, e := b.Commit(h.Number.Uint64())
		if e != nil {
			return e
		}
		rr := types.DeriveSha(receipts, trie.NewStackTrie(nil))
		expected := c.block.Header()
		if computed != produced.Root() {
			return b.stop("FINALIZATION_COMMIT_MISMATCH", nil)
		}
		commitment, _, e := b.Seal()
		if e != nil {
			return e
		}
		out = &CalibrationResult{InputCommitment: c.InputCommitment(), StateRoot: computed,
			ReceiptsRoot: rr, GasUsed: produced.GasUsed(), Transactions: len(produced.Transactions()),
			WitnessCommitment: commitment, Matched: computed == expected.Root && rr == expected.ReceiptHash && produced.Hash() == expected.Hash(),
			BlockHash: produced.Hash(), ProducedHeader: produced.Header(), Receipts: receipts, World: world, Patch: patch, Observation: b.observation}
		if intervention == nil && !out.Matched {
			return b.stop("CANONICAL_ROOT_OR_GAS_MISMATCH", nil)
		}
		return nil
	})
	return out, err
}

var _ state.Database = (*strictDB)(nil)
