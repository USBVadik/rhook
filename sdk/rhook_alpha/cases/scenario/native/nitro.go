package scenario

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"math/big"

	"github.com/ethereum/go-ethereum/arbitrum_types"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/consensus"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/params"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/offchainlabs/nitro/arbos"
	"github.com/offchainlabs/nitro/arbos/arbosState"
	"github.com/offchainlabs/nitro/arbos/arbostypes"
	_ "github.com/offchainlabs/nitro/gethhook"
	prestate "local/rhook-robinhood"
)

type scenarioChain struct {
	cfg    *params.ChainConfig
	parent *types.Header
	engine arbos.Engine
}

func (c *scenarioChain) Config() *params.ChainConfig  { return c.cfg }
func (c *scenarioChain) Engine() consensus.Engine     { return &c.engine }
func (c *scenarioChain) CurrentHeader() *types.Header { return types.CopyHeader(c.parent) }
func (c *scenarioChain) GetHeader(hash common.Hash, n uint64) *types.Header {
	if hash != c.parent.Hash() || n != c.parent.Number.Uint64() {
		panic(&prestate.HostStop{Code: "MISSING_ORIGINAL_HEADER", Detail: fmt.Sprint(n)})
	}
	return types.CopyHeader(c.parent)
}
func (c *scenarioChain) GetHeaderByNumber(n uint64) *types.Header {
	return c.GetHeader(c.parent.Hash(), n)
}
func (c *scenarioChain) GetHeaderByHash(h common.Hash) *types.Header {
	return c.GetHeader(h, c.parent.Number.Uint64())
}

type sequencing struct {
	*arbos.NoopSequencingHooks
	failure    error
	phase      func(*types.Transaction)
	diagnostic func(*types.Transaction, common.Address, *core.ExecutionResult) error
}

func (h *sequencing) PostTxFilter(header *types.Header, db *state.StateDB, arb *arbosState.ArbosState, tx *types.Transaction, sender common.Address, dataGas uint64, result *core.ExecutionResult, position int) error {
	if h.diagnostic != nil {
		if e := h.diagnostic(tx, sender, result); e != nil {
			return e
		}
	}
	return h.NoopSequencingHooks.PostTxFilter(header, db, arb, tx, sender, dataGas, result, position)
}

func (h *sequencing) NextTxToSequence() (*types.Transaction, *arbitrum_types.ConditionalOptions, error) {
	tx, options, e := h.NoopSequencingHooks.NextTxToSequence()
	if h.phase != nil {
		h.phase(tx)
	}
	return tx, options, e
}

func (h *sequencing) TxFailed(e error) {
	if h.failure == nil {
		h.failure = e
	}
}

func runWorld(ctx context.Context, x *admitted, label string, entered func(), failed func(FailureDetail)) (out *WorldResult, closed bool, err error) {
	copy := *x
	x = &copy
	x.world = label
	x.phase = "COMMON_SETUP"
	b, e := openBridge(x)
	if e != nil {
		return nil, false, e
	}
	defer func() {
		e := prestate.CloseScenarioBridge(b)
		closed = e == nil
		err = errors.Join(err, e)
		if err != nil {
			f := FailureDetail{World: label, Cause: err.Error(), MissingLookups: prestate.ScenarioLookupAttempts(b)}
			var h *prestate.HostStop
			if errors.As(err, &h) {
				f.HostCode = h.Code
			}
			failed(f)
		}
	}()
	err = b.Protect(func() error {
		if e := ctx.Err(); e != nil {
			return e
		}
		s, overlay, funding, e := initializeWorld(b, x, label)
		if e != nil {
			return e
		}
		actor := x.spec.Setup.Actor
		cfg, e := prestate.ValidateConfig(x.configRaw, 61)
		if e != nil {
			return e
		}
		chain := &scenarioChain{cfg: cfg, parent: types.CopyHeader(x.parent)}
		txs := make(types.Transactions, len(x.spec.Actions))
		for i, a := range x.spec.Actions {
			tx := new(types.Transaction)
			if e = tx.UnmarshalBinary(a.Raw); e != nil {
				return e
			}
			txs[i] = tx
		}
		env := x.spec.Environment
		l1Base, _ := decimal(env.L1BaseFee)
		header := &arbostypes.L1IncomingMessageHeader{Poster: env.Poster, BlockNumber: env.L1Number, Timestamp: env.Time, L1BaseFee: l1Base}
		x.phase = "SYSTEM_START_BLOCK"
		hooks := &sequencing{NoopSequencingHooks: arbos.NewNoopSequencingHooks(txs), phase: func(tx *types.Transaction) {
			x.phase = "BLOCK_FINALIZATION"
			if tx != nil {
				for i, candidate := range txs {
					if candidate.Hash() == tx.Hash() {
						x.phase = x.spec.Actions[i].ID
						return
					}
				}
				x.phase = "UNMAPPED_TRANSACTION"
			}
		}}
		if x.diagnostic != nil {
			hooks.diagnostic = func(tx *types.Transaction, sender common.Address, result *core.ExecutionResult) error {
				return x.diagnostic.capture(label, tx, sender, result)
			}
		}
		if x.producerGate != nil {
			if e = x.producerGate.Enter(ctx, label); e != nil {
				return e
			}
		}
		entered()
		produced, output, receipts, e := arbos.ProduceBlockAdvanced(header, env.Delayed, chain.parent, s, chain, hooks, false, core.NewMessageReplayContext(), false, nil)
		if e != nil {
			return &prestate.HostStop{Code: "SCENARIO_PRODUCER_FAILURE", Detail: e.Error()}
		}
		if e = ctx.Err(); e != nil {
			return e
		}
		if hooks.failure != nil {
			return &prestate.HostStop{Code: "SYNTHETIC_TRANSACTION_ADMISSION", Detail: hooks.failure.Error()}
		}
		if output != s || produced == nil || produced.NumberU64() != env.Number || produced.Time() != env.Time {
			return errors.New("PRODUCED_ENVIRONMENT")
		}
		all := produced.Transactions()
		if len(all) != len(txs)+1 || len(receipts) != len(all) || all[0].Type() != types.ArbitrumInternalTxType {
			return errors.New("SYSTEM_ACTION_SEQUENCE")
		}
		// Reconstruct the system transaction from the declared environment and
		// producer-derived header. No real historical start-block input is reused.
		expectedSystem := types.NewTx(arbos.InternalTxStartBlock(big.NewInt(4663), l1Base, env.L1Number, produced.Header(), chain.parent))
		got, _ := all[0].MarshalBinary()
		want, _ := expectedSystem.MarshalBinary()
		if !bytes.Equal(got, want) {
			return errors.New("SYSTEM_TRANSACTION_MAPPING")
		}
		mapping := []ActionMapping{}
		for i, tx := range txs {
			got, _ := all[i+1].MarshalBinary()
			want, _ := tx.MarshalBinary()
			if !bytes.Equal(got, want) || receipts[i+1].TxHash != tx.Hash() {
				return errors.New("PRODUCED_ACTION_MAPPING")
			}
			mapping = append(mapping, ActionMapping{x.spec.Actions[i].ID, i + 1, tx.Hash()})
		}
		after := s.GetBalance(actor).ToBig().String()
		nonce := s.GetNonce(actor)
		if e = s.Error(); e != nil {
			return e
		}
		x.phase = "COMMIT"
		root, e := prestate.CommitScenarioState(b, env.Number)
		if e != nil {
			return e
		}
		rr := types.DeriveSha(receipts, trie.NewStackTrie(nil))
		if root != produced.Root() || rr != produced.ReceiptHash() {
			return errors.New("SCENARIO_INTERNAL_COMMITMENT_MISMATCH")
		}
		witness, _, e := b.Seal()
		if e != nil {
			return e
		}
		// Geth's JSON decoder requires logs to be an array, including for the
		// generated system receipt. Empty and nil logs have identical trie encoding.
		for _, r := range receipts {
			if r.Logs == nil {
				r.Logs = []*types.Log{}
			}
		}
		out = &WorldResult{World: label, Scenario: x.spec.Commitment,
			Overlay: overlay,
			Header:  produced.Header(), StateRoot: root, ReceiptsRoot: rr, SystemTransaction: all[0].Hash(), Actions: mapping, Receipts: receipts,
			ActorBalanceBefore: funding.String(), ActorBalanceAfter: after, ActorNonceAfter: nonce, Witness: witness,
			ObservedDeltas: "ACTOR_BALANCE_NONCE_AND_CONFIG_OVERLAY; FULL_RECEIPTS_LOGS; NOT_EXHAUSTIVE_STATE_DIFF"}
		return nil
	})
	return
}
