package prestate

import (
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
	"math/big"
)

func CheckedCaseLPReplacement(current, expected, requested common.Hash) (common.Hash, error) {
	if current != expected {
		return common.Hash{}, errors.New("UNEXPECTED_OLD_WORD")
	}
	if current[10] != 0 || current[11] != 100 {
		return common.Hash{}, errors.New("UNEXPECTED_LP_VALUE")
	}
	if requested[10] != 0 || requested[11] > 99 {
		return common.Hash{}, errors.New("CASE_LP_RANGE")
	}
	want := current
	want[10] = requested[10]
	want[11] = requested[11]
	if want != requested {
		return common.Hash{}, errors.New("EXTRA_INITIAL_STORAGE_BITS_CHANGED")
	}
	return want, nil
}
func ValidateCaseLPIntervention(i LPIntervention, c Checkpoint) error {
	if i.Checkpoint != c || i.Pool != hookrPoolID || i.Account != hookrRules || i.Slot != hookrConfigSlot || i.Mask != hookrLPMask {
		return errors.New("EXACT_LP_INTERVENTION_IDENTITY_REQUIRED")
	}
	_, e := CheckedCaseLPReplacement(i.ExpectedOldWord, i.ExpectedOldWord, i.NewWord)
	return e
}
func RunHookrPlanned(c *Candidate, b *Bridge, i *LPIntervention, observation EconomicObservationPlan) (*CalibrationResult, error) {
	return runObservedBlock(c, b, observation, func() (*CalibrationResult, error) {
		if i == nil {
			return RunCanonical(c, b)
		}
		if e := ValidateCaseLPIntervention(*i, c.checkpoint); e != nil {
			return nil, b.stop("LP_INTERVENTION_REJECTED", e)
		}
		return runNativeBlock(c, b, func(b *Bridge) (*LPWriteRecord, error) { return applyCaseLPOverlay(b, *i, hookrRulesCodeHash) })
	})
}

func applyCaseLPOverlay(b *Bridge, i LPIntervention, codeHash common.Hash) (*LPWriteRecord, error) {
	if e := ValidateCaseLPIntervention(i, b.checkpoint); e != nil {
		return nil, b.stop("LP_INTERVENTION_REJECTED", e)
	}
	if b.lpPatched {
		return nil, b.stop("LP_PATCH_ALREADY_APPLIED", nil)
	}
	s, e := b.State()
	if e != nil {
		return nil, e
	}
	if !s.Exist(i.Account) || s.GetCodeHash(i.Account) != codeHash || crypto.Keccak256Hash(s.GetCode(i.Account)) != codeHash {
		return nil, b.stop("LP_ACCOUNT_RUNTIME_NOT_AUTHENTICATED", nil)
	}
	current := s.GetState(i.Account, i.Slot)
	changed, e := CheckedCaseLPReplacement(current, i.ExpectedOldWord, i.NewWord)
	if e != nil || changed != i.NewWord {
		return nil, b.stop("LP_FULL_WORD_OR_REPLACEMENT_MISMATCH", e)
	}
	if e = s.Error(); e != nil {
		return nil, b.stop("LP_ORIGINAL_STATE_UNAVAILABLE", e)
	}
	beforeWitness, _ := b.WitnessSnapshot()
	// SetState is the sole semantic initial-state mutation. Reader provenance
	// remains b.checkpoint; no node/code preimage is replaced or synthesized.
	nonce, balance, originalCode := s.GetNonce(i.Account), new(big.Int).Set(s.GetBalance(i.Account).ToBig()), s.GetCodeHash(i.Account)
	s.SetState(i.Account, i.Slot, changed)
	// This is checkpoint state, not a dirty write made by the first arrival.
	// Geth's EIP-2200 original-value lookup ignores dirtyStorage. Finalise the
	// one overlay write before entering Nitro so both current and committed
	// slot semantics start at the hypothetical word, without altering the
	// original root-pinned witness or adding an administrative transaction.
	s.Finalise(true)
	b.lpPatched = true
	if s.GetState(i.Account, i.Slot) != i.NewWord || s.GetCommittedState(i.Account, i.Slot) != i.NewWord || s.GetNonce(i.Account) != nonce || s.GetBalance(i.Account).ToBig().Cmp(balance) != 0 || s.GetCodeHash(i.Account) != originalCode {
		return nil, b.stop("LP_OVERLAY_PRESERVATION_FAILURE", nil)
	}
	afterWitness, _ := b.WitnessSnapshot()
	if beforeWitness != afterWitness {
		return nil, b.stop("LP_PATCH_MUTATED_ORIGINAL_WITNESS", nil)
	}
	b.guard()
	return &LPWriteRecord{i, 1, true, beforeWitness, "HYPOTHETICAL_CHECKPOINT_BRANCH"}, nil
}
