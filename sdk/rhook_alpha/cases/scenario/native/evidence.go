package scenario

import (
	"errors"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/trie"
	"github.com/offchainlabs/nitro/arbos"
)

// VerifyEvidence authenticates the official profile's required initial inputs
// and checks internal execution-record coherence. It does not rerun Nitro,
// establish transitive closure/consensus, or prove the engine ran honestly.
func VerifyEvidence(input, output []byte) error {
	return verifyEvidence(input, output, officialProfile())
}

func VerifyDynamicEvidence(input, output []byte) error {
	return verifyEvidence(input, output, dynamicProfile())
}

func verifyEvidence(input, output []byte, p profile) error {
	admitted, e := admit(input, p)
	if e != nil {
		return e
	}
	s := admitted.input.spec
	o, e := DecodeOutcome(output)
	if e != nil {
		return e
	}
	if o.Schema != s.Schema+"/evidence" || o.Scenario != s.Commitment || o.Profile != s.Origin.Kind || o.Status != "SCENARIO_EXECUTED_UNQUALIFIED" ||
		o.DiscoveryOnly || o.DiagnosticOnly || o.ProducerInvocations != 2 || !o.Cleanup || o.QualifiedClaims != 0 || o.ExternalDelivery != "HOLD" || len(o.Worlds) != 2 {
		return errors.New("SCENARIO_EVIDENCE_SCOPE")
	}
	var parent types.Header
	if e = parent.UnmarshalJSON(s.Parent); e != nil {
		return e
	}
	if parent.Number == nil || parent.Hash() != s.Checkpoint.BlockHash || parent.Root != s.Checkpoint.StateRoot || len(s.Configs.Baseline) != 4 || len(s.Actions) < 1 || len(s.Actions) > 2 {
		return errors.New("EVIDENCE_INPUT_SHAPE")
	}
	fee, e := decimal(s.Environment.L1BaseFee)
	if e != nil {
		return e
	}
	for i, w := range o.Worlds {
		label := Baseline
		words := s.Configs.Baseline
		if i == 1 {
			label = Variant
			words = s.Configs.Variant
		}
		if len(words) != 4 || w == nil || w.World != label || w.Scenario != s.Commitment || w.Header == nil {
			return errors.New("WORLD_EVIDENCE_IDENTITY")
		}
		if s.Schema == DynamicDomain {
			expected, e := deriveDynamicOverlay(admitted.input, label)
			if e != nil {
				return e
			}
			a, _ := Canonical(expected)
			b, _ := Canonical(w.Overlay)
			if string(a) != string(b) {
				return errors.New("DYNAMIC_DERIVED_OVERLAY_EVIDENCE")
			}
		} else if w.Overlay.Intervention != "" || len(w.Overlay.Writes) != 0 {
			return errors.New("LP_EVIDENCE_CANNOT_CARRY_DYNAMIC_OVERLAY")
		}
		h := w.Header
		if h.Number == nil || !h.Number.IsUint64() || h.Number.Uint64() != s.Environment.Number || h.Time != s.Environment.Time || h.ParentHash != s.Checkpoint.BlockHash || h.Root != w.StateRoot || h.ReceiptHash != w.ReceiptsRoot {
			return errors.New("SYNTHETIC_HEADER_COHERENCE")
		}
		if w.Overlay.Common != s.Setup || w.ActorBalanceBefore != s.Setup.Funding || w.Overlay.Before != s.Configs.Baseline[0] || w.Overlay.After != words[0] ||
			w.Overlay.Account != rulesAddress || w.Overlay.Slot != p.ConfigSlot {
			return errors.New("OVERLAY_EVIDENCE")
		}
		if w.Overlay.CommonRoot != o.Worlds[0].Overlay.CommonRoot || len(w.Receipts) != len(s.Actions)+1 || len(w.Actions) != len(s.Actions) || w.ActorNonceAfter != uint64(len(s.Actions)) {
			return errors.New("ACTION_RECEIPT_COUNT")
		}
		if w.Overlay.CommonRoot == (common.Hash{}) || w.Overlay.InitialRoot == (common.Hash{}) || !pin(w.Witness) || w.Witness != o.Worlds[0].Witness {
			return errors.New("INITIAL_ROOT_OR_WITNESS_COHERENCE")
		}
		if (i == 0 || s.Configs.Baseline[0] == words[0]) && w.Overlay.InitialRoot != w.Overlay.CommonRoot {
			return errors.New("UNPATCHED_INITIAL_ROOT")
		}
		if _, e = decimal(w.ActorBalanceAfter); e != nil {
			return e
		}
		system := types.NewTx(arbos.InternalTxStartBlock(big.NewInt(4663), fee, s.Environment.L1Number, h, &parent))
		if system.Hash() != w.SystemTransaction {
			return errors.New("SYSTEM_EVIDENCE_MAPPING")
		}
		txs := types.Transactions{system}
		for j, a := range s.Actions {
			tx := new(types.Transaction)
			if e = tx.UnmarshalBinary(a.Raw); e != nil {
				return e
			}
			txs = append(txs, tx)
			mapping := w.Actions[j]
			if mapping.ID != a.ID || mapping.Ordinal != j+1 || mapping.Hash != tx.Hash() {
				return errors.New("ACTION_EVIDENCE_MAPPING")
			}
		}
		var cumulative uint64
		var logIndex uint
		for j, r := range w.Receipts {
			if r == nil || r.TxHash != txs[j].Hash() || r.Status > 1 || r.Type != txs[j].Type() || len(r.PostState) != 0 {
				return errors.New("RECEIPT_IDENTITY")
			}
			if r.BlockHash != h.Hash() || r.BlockNumber == nil || r.BlockNumber.Cmp(h.Number) != 0 || r.TransactionIndex != uint(j) || r.CumulativeGasUsed < cumulative || r.GasUsed != r.CumulativeGasUsed-cumulative || r.GasUsedForL1 > r.GasUsed || r.ContractAddress != (common.Address{}) {
				return errors.New("RECEIPT_METADATA")
			}
			cumulative = r.CumulativeGasUsed
			for _, l := range r.Logs {
				if l == nil || l.Removed || l.BlockHash != h.Hash() || l.BlockNumber != h.Number.Uint64() || l.BlockTimestamp != h.Time || l.TxHash != txs[j].Hash() || l.TxIndex != uint(j) || l.Index != logIndex {
					return errors.New("LOG_METADATA")
				}
				logIndex++
			}
			if types.CreateBloom(r) != r.Bloom {
				return errors.New("RECEIPT_LOG_BLOOM")
			}
		}
		if types.MergeBloom(w.Receipts) != h.Bloom {
			return errors.New("HEADER_LOG_BLOOM")
		}
		if types.DeriveSha(txs, trie.NewStackTrie(nil)) != h.TxHash || types.DeriveSha(w.Receipts, trie.NewStackTrie(nil)) != w.ReceiptsRoot ||
			w.Receipts[len(w.Receipts)-1].CumulativeGasUsed != h.GasUsed {
			return errors.New("TRANSACTION_OR_RECEIPT_ROOT")
		}
	}
	return nil
}
