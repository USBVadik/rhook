package prestate

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"math/big"
	"time"
)

type SelectedHookrTrade struct {
	Hash      common.Hash    `json:"hash"`
	Ordinal   int            `json:"nativeOrdinal"`
	Payer     common.Address `json:"payer"`
	Recipient common.Address `json:"recipient"`
}
type HookrPair struct {
	Subject                 *SelectedHookrTrade      `json:"subject,omitempty"`
	Intervention            *LPIntervention          `json:"intervention,omitempty"`
	Plan                    *EconomicObservationPlan `json:"observationPlan,omitempty"`
	Branch                  *CalibrationResult       `json:"branch,omitempty"`
	BranchAttempts          int                      `json:"branchAttempts"`
	ActualEconomics         *SettlementObservation   `json:"actualEconomics,omitempty"`
	BranchEconomics         *SettlementObservation   `json:"branchEconomics,omitempty"`
	BranchWitnessCommitment string                   `json:"branchWitnessCommitment,omitempty"`
	HeterogeneousAgreement  string                   `json:"heterogeneousAgreement"`
	EconomicAssurance       string                   `json:"economicAssurance"`
}

func selectHookrTrade(ctx context.Context, rpc *RPCSource, raw []byte, h *types.Header) (*SelectedHookrTrade, string, error) {
	var logs []*types.Log
	e := rpc.call(ctx, "eth_getLogs", []any{map[string]any{"blockHash": h.Hash(), "address": []common.Address{hookrManager, hookrRouter}, "topics": []any{[]common.Hash{swapTopic, routerTopic}, hookrPoolID}}}, &logs)
	if e != nil {
		return nil, "", e
	}
	return selectHookrTradeLogs(raw, h, logs, false)
}

func selectHookrTradeLogs(raw []byte, h *types.Header, logs []*types.Log, exactInput bool) (*SelectedHookrTrade, string, error) {
	var body struct {
		Transactions []struct {
			Hash  common.Hash     `json:"hash"`
			To    *common.Address `json:"to"`
			Type  *hexutil.Uint64 `json:"type"`
			Input hexutil.Bytes   `json:"input"`
			Value *hexutil.Big    `json:"value"`
		} `json:"transactions"`
	}
	if json.Unmarshal(raw, &body) != nil {
		return nil, "", errors.New("HOOKR_BLOCK_BODY_ENCODING")
	}
	var selected *SelectedHookrTrade
	for _, l := range logs {
		if l == nil || l.BlockHash != h.Hash() || l.BlockNumber != h.Number.Uint64() || l.Removed || len(l.Topics) < 2 || l.Topics[1] != hookrPoolID {
			return nil, "", errors.New("HOOKR_LOG_BLOCK_IDENTITY")
		}
		if l.Address != hookrManager || l.Topics[0] != swapTopic {
			continue
		}
		if abiWords(l, 3, 6) != nil {
			return nil, "", errors.New("HOOKR_SWAP_LOG_ENCODING")
		}
		sender, err := abiAddress(l.Topics[2])
		if err != nil {
			return nil, "", err
		}
		if sender != hookrRouter {
			continue
		}
		a, err := signedABI(l, 0, 128)
		if err != nil {
			return nil, "", err
		}
		b, err := signedABI(l, 1, 128)
		if err != nil {
			return nil, "", err
		}
		if a.Sign() >= 0 || b.Sign() <= 0 {
			continue
		}
		if l.TxIndex == 0 || int(l.TxIndex) >= len(body.Transactions) {
			return nil, "", errors.New("HOOKR_SWAP_INPUT_ORDINAL")
		}
		tx := body.Transactions[l.TxIndex]
		if tx.Hash != l.TxHash {
			return nil, "", errors.New("HOOKR_SWAP_TX_IDENTITY")
		}
		if tx.To == nil || *tx.To != hookrRouter || tx.Type == nil || *tx.Type > 2 {
			continue
		}
		if exactInput && !eligibleRouterInput(tx.Input, tx.Value) {
			continue
		}
		if selected == nil || int(l.TxIndex) < selected.Ordinal {
			selected = &SelectedHookrTrade{Hash: l.TxHash, Ordinal: int(l.TxIndex)}
		}
	}
	if selected == nil {
		return nil, "NO_ELIGIBLE_DIRECT_ETH_RHOOK_BUY", nil
	}
	count := 0
	for _, l := range logs {
		if l.TxHash == selected.Hash && l.Address == hookrRouter && l.Topics[0] == routerTopic {
			if abiWords(l, 4, 2) != nil || abiUint(l, 0).Sign() <= 0 || abiUint(l, 1).Sign() <= 0 {
				return nil, "", errors.New("HOOKR_ROUTE_LOG_ENCODING")
			}
			count++
			var err error
			selected.Payer, err = abiAddress(l.Topics[2])
			if err != nil {
				return nil, "", err
			}
			selected.Recipient, err = abiAddress(l.Topics[3])
			if err != nil {
				return nil, "", err
			}
		}
	}
	if count != 1 {
		return nil, "", errors.New("HOOKR_PRIMARY_ROUTE_AMBIGUOUS")
	}
	return selected, "ELIGIBLE", nil
}

func plus(h common.Hash, n int64) common.Hash {
	return common.BigToHash(new(big.Int).Add(h.Big(), big.NewInt(n)))
}

func captureHookrDependencies(ctx context.Context, rpc *RPCSource, p *BlockPackage, subject *SelectedHookrTrade) (*LPIntervention, *EconomicObservationPlan, error) {
	if subject == nil {
		return nil, nil, errors.New("HOOKR_SUBJECT_REQUIRED")
	}
	rootBase := plus(common.HexToHash("0xdc5740eeafc78ca4488605782bceeee21ea0cec0908c37bbb90fb77c45910411"), -8)
	rootSlots := []common.Hash{}
	for i := int64(0); i < 11; i++ {
		rootSlots = append(rootSlots, plus(rootBase, i))
	}
	namespace := common.HexToHash("0x762913e4bc0f59f7b08c82f07586fa48932548ab5fab99e6db0b09765b4ff900")
	// State.recapture is mapping slot 5. Observe its two packed config words
	// and the following word as an explicit extra boundary observation.
	recaptureBase := crypto.Keccak256Hash(hookrPoolID[:], plus(namespace, 5).Bytes())
	rulesSlots := []common.Hash{plus(hookrConfigSlot, -1), hookrConfigSlot, plus(hookrConfigSlot, 1), plus(hookrConfigSlot, 2), plus(hookrConfigSlot, 3), plus(hookrConfigSlot, 4), plus(recaptureBase, 0), plus(recaptureBase, 1), plus(recaptureBase, 2)}
	executor := common.HexToAddress("0x4b4c16681401454140a9dbca55e5c186bbe8d728")
	captures := []struct {
		a     common.Address
		slots []common.Hash
	}{{hookrRules, rulesSlots}, {hookrRoot, rootSlots}, {executor, nil}, {hookrManager, nil}, {hookrRouter, nil}, {rhookToken, nil}}
	var word common.Hash
	rootWords := map[common.Hash]common.Hash{}
	rulesWords := map[common.Hash]common.Hash{}
	for _, x := range captures {
		proof, e := rpc.GetProof(ctx, p.Checkpoint, x.a, x.slots)
		if e != nil {
			return nil, nil, e
		}
		if _, e = verifyProof(p.Checkpoint.StateRoot, x.a, x.slots, proof); e != nil {
			return nil, nil, e
		}
		if proof.CodeHash == types.EmptyCodeHash {
			return nil, nil, errors.New("HOOKR_ROLE_CODE_ABSENT")
		}
		if x.a == hookrRules {
			if proof.CodeHash != hookrRulesCodeHash {
				return nil, nil, errors.New("HOOKR_RULES_CODE_CHANGED")
			}
			for _, v := range proof.StorageProof {
				if v.Key == hookrConfigSlot {
					word = common.BigToHash(v.Value.ToInt())
				}
			}
		}
		if x.a == hookrRoot {
			for _, v := range proof.StorageProof {
				rootWords[v.Key] = common.BigToHash(v.Value.ToInt())
			}
		}
		if x.a == hookrRules {
			for _, v := range proof.StorageProof {
				rulesWords[v.Key] = common.BigToHash(v.Value.ToInt())
			}
		}
		p.Proofs = append(p.Proofs, CapturedProof{x.a, x.slots, proof})
		present := false
		for _, code := range p.Codes {
			if crypto.Keccak256Hash(code) == proof.CodeHash {
				present = true
			}
		}
		if !present {
			code, e := rpc.GetCode(ctx, p.Checkpoint, x.a)
			if e != nil {
				return nil, nil, e
			}
			if crypto.Keccak256Hash(code) != proof.CodeHash {
				return nil, nil, errors.New("HOOKR_CODE_PREIMAGE_HASH")
			}
			p.Codes = append(p.Codes, code)
		}
	}
	raw, e := json.Marshal(p)
	if e != nil {
		return nil, nil, e
	}
	if e = CheckHookrBindings(raw); e != nil {
		return nil, nil, e
	}
	rootWord := rootWords[rootBase]
	boundWord := rulesWords[plus(hookrConfigSlot, -1)]
	if common.BigToAddress(rootWord.Big()) != hookrRules || field(rootWord, 160, 24) != 3000 || field(rootWord, 232, 8) != 1 || field(rootWord, 240, 8) != 1 || field(boundWord, 0, 24) != 3000 || field(boundWord, 40, 8) != 1 || field(boundWord, 48, 8) != 1 || field(boundWord, 56, 8)&3 != 0 {
		return nil, nil, errors.New("ROOT_RULES_BOUND_CONTEXT_OUTSIDE_FROZEN_SHAPE")
	}
	changed, e := CheckedLPReplacement(word, word)
	if e != nil {
		return nil, nil, e
	}
	if field(word, 0, 40) != 0 || field(word, 64, 24) != 0 || field(word, 144, 16) != 0 || field(word, 176, 16) != 0 || field(word, 192, 16) != 0 || field(word, 208, 16) != 2000 || field(word, 40, 24) != 11500 {
		return nil, nil, errors.New("ORIGINAL_HOOKR_CONFIG_OUTSIDE_FROZEN_SHAPE")
	}
	request := &LPIntervention{p.Checkpoint, hookrPoolID, hookrRules, hookrConfigSlot, hookrLPMask, word, changed}
	plan := &EconomicObservationPlan{Subject: subject.Hash, NativeOrdinal: subject.Ordinal, Accounts: []common.Address{hookrRules, hookrRoot, hookrManager, hookrRouter, subject.Payer, subject.Recipient}}
	for _, slot := range rulesSlots {
		plan.Storage = append(plan.Storage, WatchedStorage{hookrRules, slot})
	}
	for _, slot := range rootSlots {
		plan.Storage = append(plan.Storage, WatchedStorage{hookrRoot, slot})
	}
	return request, plan, nil
}

func completeHookrPair(ctx context.Context, rpc *RPCSource, write WriteEvidence, emit EmitEvent, raw []byte, out *ProspectiveResult) (terminal string, err error) {
	pair := out.Hookr
	if ctx.Err() != nil {
		return "RUNTIME_OR_RESOURCE_STOP", errors.New("OPERATION_DEADLINE_BEFORE_BRANCH")
	}
	var a SettlementObservation
	// A separate bridge is constructed from the original package, never ACTUAL's
	// final state. Both bridge sources share one RPCSource and its total budget.
	branch, e := NewLiveCalibration(raw, rpc, minTime(time.Now().Add(120*time.Second), rpc.deadline))
	if e != nil {
		return "HOST_STOP_MISSING_STATE", e
	}
	defer branch.Bridge.Close()
	a = ProjectHookrSettlement(branch.Candidate, out.Native, pair.Subject.Ordinal)
	pair.ActualEconomics = &a
	if a.Status != "OBSERVED_SETTLEMENT_ONLY" || a.NativeQuote == nil {
		return "ECONOMIC_PROJECTION_UNRESOLVED", errors.New("ACTUAL_ECONOMIC_OBSERVATION_INCOMPLETE:" + a.Cause)
	}
	if e = EmitJSON(write, "ACTUAL_ECONOMICS.json", a); e != nil {
		return "RUNTIME_OR_RESOURCE_STOP", e
	}
	if e = EmitJSON(write, "BRANCH_PRECOMMIT.json", map[string]any{"originalInputCommitment": out.Inventory.InputCommitment, "parentCheckpoint": out.Inventory.Checkpoint, "intervention": pair.Intervention, "observationPlan": pair.Plan}); e != nil {
		return "RUNTIME_OR_RESOURCE_STOP", e
	}
	if e = emit("BRANCH_REPLAY_ENTERED", map[string]any{"originalInputCommitment": out.Inventory.InputCommitment, "intervention": pair.Intervention}); e != nil {
		return "RUNTIME_OR_RESOURCE_STOP", e
	}
	out.NativeAttempts++
	pair.BranchAttempts = 1
	pair.Branch, e = RunHookrObserved(branch.Candidate, branch.Bridge, pair.Intervention, *pair.Plan)
	if branch.Bridge.observation != nil {
		if save := EmitJSON(write, "BRANCH_OBSERVATION.json", branch.Bridge.observation); save != nil {
			return "RUNTIME_OR_RESOURCE_STOP", save
		}
	}
	commitment, witness := branch.Bridge.WitnessSnapshot()
	pair.BranchWitnessCommitment = commitment
	if save := write("BRANCH_FINAL_WITNESS.json", witness); save != nil {
		return "RUNTIME_OR_RESOURCE_STOP", save
	}
	if pair.Branch != nil {
		if save := EmitJSON(write, "BRANCH_RESULT.json", pair.Branch); save != nil {
			return "RUNTIME_OR_RESOURCE_STOP", save
		}
	}
	if e != nil {
		terminal, _ = ClassifyCalibrationError(e)
		return terminal, e
	}
	b := ProjectHookrSettlement(branch.Candidate, pair.Branch, pair.Subject.Ordinal)
	pair.BranchEconomics = &b
	if e = EmitJSON(write, "BRANCH_ECONOMICS.json", b); e != nil {
		return "RUNTIME_OR_RESOURCE_STOP", e
	}
	if (b.Status != "OBSERVED_SETTLEMENT_ONLY" || b.NativeQuote == nil) && b.Status != "NOT_APPLICABLE" {
		return "ECONOMIC_PROJECTION_UNRESOLVED", errors.New("BRANCH_ECONOMIC_OBSERVATION_INCOMPLETE:" + b.Cause)
	}
	return "GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED", nil
}
