package prestate

// This file is linked into the retained prestate package, not the SDK control plane.
import (
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
	"math/big"
)

func ValidateCapsuleLP(i LPIntervention, c Checkpoint, code common.Hash) error {
	if i.Checkpoint != c || i.Pool != hookrPoolID || i.Account != hookrRules || i.Slot != hookrConfigSlot || i.Mask != hookrLPMask || code != hookrRulesCodeHash {
		return errors.New("UNSUPPORTED_HOOKR_RULE_BINDING")
	}
	old, next := i.ExpectedOldWord, i.NewWord
	if (uint(old[10])<<8|uint(old[11])) > 10000 || next[10] != 0 || next[11] > 99 {
		return errors.New("LP_VALUE_RANGE")
	}
	old[10] = next[10]
	old[11] = next[11]
	if old != next {
		return errors.New("EXTRA_INITIAL_STORAGE_BITS_CHANGED")
	}
	return nil
}
func CheckCapsuleLP(b *Bridge, i LPIntervention, code common.Hash) error {
	if e := ValidateCapsuleLP(i, b.checkpoint, code); e != nil {
		return e
	}
	s, e := b.State()
	if e != nil {
		return e
	}
	if !s.Exist(i.Account) || s.GetCodeHash(i.Account) != code || crypto.Keccak256Hash(s.GetCode(i.Account)) != code {
		return b.stop("LP_ACCOUNT_RUNTIME_NOT_AUTHENTICATED", nil)
	}
	if s.GetState(i.Account, i.Slot) != i.ExpectedOldWord {
		return b.stop("UNEXPECTED_OLD_WORD", nil)
	}
	return s.Error()
}
func RunCapsuleLP(c *Candidate, b *Bridge, i *LPIntervention, o EconomicObservationPlan, code common.Hash) (*CalibrationResult, error) {
	return runObservedBlock(c, b, o, func() (*CalibrationResult, error) {
		if i == nil {
			return RunCanonical(c, b)
		}
		return runNativeBlock(c, b, func(b *Bridge) (*LPWriteRecord, error) {
			if e := CheckCapsuleLP(b, *i, code); e != nil {
				return nil, e
			}
			if b.lpPatched {
				return nil, b.stop("LP_PATCH_ALREADY_APPLIED", nil)
			}
			s, e := b.State()
			if e != nil {
				return nil, e
			}
			before, _ := b.WitnessSnapshot()
			nonce, balance, originalCode := s.GetNonce(i.Account), new(big.Int).Set(s.GetBalance(i.Account).ToBig()), s.GetCodeHash(i.Account)
			s.SetState(i.Account, i.Slot, i.NewWord)
			s.Finalise(true)
			b.lpPatched = true
			if s.GetState(i.Account, i.Slot) != i.NewWord || s.GetCommittedState(i.Account, i.Slot) != i.NewWord || s.GetNonce(i.Account) != nonce || s.GetBalance(i.Account).ToBig().Cmp(balance) != 0 || s.GetCodeHash(i.Account) != originalCode {
				return nil, b.stop("LP_OVERLAY_PRESERVATION_FAILURE", nil)
			}
			after, _ := b.WitnessSnapshot()
			if before != after {
				return nil, b.stop("LP_PATCH_MUTATED_ORIGINAL_WITNESS", nil)
			}
			b.guard()
			return &LPWriteRecord{*i, 1, true, before, "HYPOTHETICAL_CHECKPOINT_BRANCH"}, nil
		})
	})
}
