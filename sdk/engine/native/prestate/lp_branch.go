package prestate

import (
	"errors"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
)

var hookrPoolID = common.HexToHash("0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780")
var hookrRules = common.HexToAddress("0x4a71c270b1520f94064268102aebd744b0de7942")
var hookrRulesCodeHash = common.HexToHash("0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b")
var hookrConfigSlot = common.HexToHash("0x1ad7756ae873b72ee7b85d116a86b7b2c5244640095753f73687752bed4705aa")
var hookrLPMask = common.HexToHash("0x00000000000000000000ffff0000000000000000000000000000000000000000")

// LPIntervention is instantiated from admitted original-root data and committed
// before native entry. The full word, not a getter's lp field, must be equal.
type LPIntervention struct {
	Checkpoint      Checkpoint     `json:"checkpoint"`
	Pool            common.Hash    `json:"pool"`
	Account         common.Address `json:"account"`
	Slot            common.Hash    `json:"slot"`
	Mask            common.Hash    `json:"mask"`
	ExpectedOldWord common.Hash    `json:"expectedOldWord"`
	NewWord         common.Hash    `json:"newWord"`
}

type LPWriteRecord struct {
	Intervention              LPIntervention `json:"intervention"`
	SemanticInitialWrites     int            `json:"semanticInitialWrites"`
	OriginalWitnessUnchanged  bool           `json:"originalWitnessUnchanged"`
	OriginalWitnessCommitment string         `json:"originalWitnessCommitment"`
	// This is an overlay on the original parent. It is not a canonical parent,
	// an administrative transaction, or an authorization by Root.policyHash.
	World string `json:"world"`
}

// CheckedLPReplacement is the prior tested guard, using complete 32-byte words.
func CheckedLPReplacement(current, expected common.Hash) (common.Hash, error) {
	if current != expected {
		return common.Hash{}, errors.New("UNEXPECTED_OLD_WORD")
	}
	if current[10] != 0 || current[11] != 100 {
		return common.Hash{}, errors.New("UNEXPECTED_LP_VALUE")
	}
	result := current
	result[10], result[11] = 0, 0
	return result, nil
}

func ValidateLPIntervention(i LPIntervention, c Checkpoint) error {
	if i.Checkpoint != c || i.Pool != hookrPoolID || i.Account != hookrRules || i.Slot != hookrConfigSlot || i.Mask != hookrLPMask {
		return errors.New("EXACT_LP_INTERVENTION_IDENTITY_REQUIRED")
	}
	expected, err := CheckedLPReplacement(i.ExpectedOldWord, i.ExpectedOldWord)
	if err != nil {
		return err
	}
	if expected != i.NewWord {
		return errors.New("EXTRA_INITIAL_STORAGE_BITS_CHANGED")
	}
	return nil
}

// No method turns this record into an admitted economic Claim or assurance.
func RunHookrBranch(c *Candidate, b *Bridge, i LPIntervention) (*CalibrationResult, error) {
	if c == nil || b == nil {
		return nil, errors.New("MISSING_CANDIDATE_OR_BRIDGE")
	}
	if e := ValidateLPIntervention(i, c.checkpoint); e != nil {
		return nil, b.stop("LP_INTERVENTION_REJECTED", e)
	}
	return runNativeBlock(c, b, func(b *Bridge) (*LPWriteRecord, error) {
		return applyLPOverlay(b, i, hookrRulesCodeHash)
	})
}

func applyLPOverlay(b *Bridge, i LPIntervention, codeHash common.Hash) (*LPWriteRecord, error) {
	if e := ValidateLPIntervention(i, b.checkpoint); e != nil {
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
	changed, e := CheckedLPReplacement(current, i.ExpectedOldWord)
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
