package prestate

import (
	"errors"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/trie"
)

var hookrRoot = common.HexToAddress("0x89c9fb50d1f03192230ffb1c279bb6e7d3fe6acc")
var hookrManager = common.HexToAddress("0x8366a39cc670b4001a1121b8f6a443a643e40951")
var hookrRouter = common.HexToAddress("0xc2bc9a3fe6c4ce8c2f7eb4655b0869b01d8c93c9")
var rhookToken = common.HexToAddress("0x3c022d43a9f826cd206c2ba60bc753d8b36185c4")
var swapTopic = eventTopic("Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)")
var routerTopic = eventTopic("SwapExecuted(bytes32,address,address,uint256,uint256)")
var feeTopic = eventTopic("HookFee(bytes32,address,uint256,uint256,uint256)")
var allocatedTopic = eventTopic("FeesAllocated(bytes32,address,uint256,uint256,uint256,address,uint256)")
var erc20TransferTopic = eventTopic("Transfer(address,address,uint256)")
var erc6909TransferTopic = eventTopic("Transfer(address,address,address,uint256,uint256)")

func eventTopic(s string) common.Hash { return crypto.Keccak256Hash([]byte(s)) }

// SettlementObservation is inspection data, not a qualified economic Claim.
// Missing monetary or state observations are never serialized as zero.
type SettlementObservation struct {
	Status             string         `json:"status"`
	Cause              string         `json:"cause,omitempty"`
	Assurance          string         `json:"assurance"`
	World              string         `json:"world"`
	Subject            common.Hash    `json:"subject"`
	NativeOrdinal      int            `json:"nativeOrdinal"`
	Lifecycle          string         `json:"lifecycle"`
	Pool               common.Hash    `json:"pool"`
	Quote              common.Address `json:"quote"`
	Token              common.Address `json:"token"`
	Payer              common.Address `json:"payer"`
	Recipient          common.Address `json:"recipient"`
	GrossInput         *string        `json:"grossInput"`
	PoolInput          *string        `json:"poolInput"`
	DeliveredOutput    *string        `json:"deliveredOutput"`
	HookEarned         *string        `json:"hookEarned"`
	Refund             *string        `json:"refund"`
	ProtocolAllocation *string        `json:"protocolAllocation"`
	RoyaltyAllocation  *string        `json:"royaltyAllocation"`
	AdvisoryAllocation *string        `json:"advisoryAllocation"`
	TotalPoolFeePips   *uint64        `json:"totalPoolFeePips"`
	GasUsed            uint64         `json:"gasUsed"`
	// Rate decomposition and realized component money need native quote/settle
	// preimages and authenticated state; a receipt total cannot supply them.
	ComponentAmountsStatus string                 `json:"componentAmountsStatus"`
	StateChangesStatus     string                 `json:"stateChangesStatus"`
	RealizedLPProfitStatus string                 `json:"realizedLPProfitStatus"`
	NativeQuote            *QuoteObservation      `json:"nativeQuote,omitempty"`
	Recapture              []RecaptureObservation `json:"recapture"`
}

func decimal(x *big.Int) *string { s := x.String(); return &s }
func add(xs ...*big.Int) *big.Int {
	r := new(big.Int)
	for _, x := range xs {
		r.Add(r, x)
	}
	return r
}
func abiWords(l *types.Log, topics, words int) error {
	if len(l.Topics) != topics || len(l.Data) != 32*words || l.Removed {
		return errors.New("EVENT_LAYOUT_OR_REMOVAL")
	}
	return nil
}
func abiUint(l *types.Log, n int) *big.Int { return new(big.Int).SetBytes(l.Data[n*32 : (n+1)*32]) }
func abiAddress(h common.Hash) (common.Address, error) {
	for _, x := range h[:12] {
		if x != 0 {
			return common.Address{}, errors.New("NONCANONICAL_ABI_ADDRESS")
		}
	}
	return common.BytesToAddress(h[12:]), nil
}
func signedABI(l *types.Log, n, width int) (*big.Int, error) {
	x := abiUint(l, n)
	negative := x.Bit(width-1) != 0
	want := uint(0)
	if negative {
		want = 1
	}
	for bit := width; bit < 256; bit++ {
		if x.Bit(bit) != want {
			return nil, errors.New("NONCANONICAL_SIGN_EXTENSION")
		}
	}
	if negative {
		x.Sub(x, new(big.Int).Lsh(big.NewInt(1), 256))
	}
	return x, nil
}

// ProjectHookrSettlement requires receipts returned by the full native runner.
// It recomputes their trie root and keeps subject identity when lifecycle flips.
func ProjectHookrSettlement(c *Candidate, native *CalibrationResult, index int) SettlementObservation {
	o := SettlementObservation{Status: "UNRESOLVED", Assurance: "UNRESOLVED", Lifecycle: "UNRESOLVED", Pool: hookrPoolID, Token: rhookToken, ComponentAmountsStatus: "UNRESOLVED_MISSING_QUOTE_SETTLEMENT_PREIMAGES", StateChangesStatus: "UNRESOLVED_NO_NATIVE_STATE_OBSERVATIONS", RealizedLPProfitStatus: "OUT_OF_SCOPE"}
	fail := func(s string) SettlementObservation { o.Cause = s; return o }
	if c == nil || native == nil || index < 1 || index >= len(c.block.Transactions()) {
		return fail("SUBJECT_OR_NATIVE_RESULT_MISSING")
	}
	o.World = native.World
	o.NativeOrdinal = index
	tx := c.block.Transactions()[index]
	o.Subject = tx.Hash()
	if native.InputCommitment != c.InputCommitment() || native.Transactions != len(c.block.Transactions()) || len(native.Receipts) != native.Transactions || native.ProducedHeader == nil {
		return fail("NATIVE_CONTEXT_INCOMPLETE")
	}
	if native.ProducedHeader.Hash() != native.BlockHash || native.ProducedHeader.Root != native.StateRoot || native.ProducedHeader.ReceiptHash != native.ReceiptsRoot || types.DeriveSha(native.Receipts, trie.NewStackTrie(nil)) != native.ReceiptsRoot {
		return fail("RECEIPT_HEADER_ROOT_BINDING")
	}
	if native.World == "ACTUAL" {
		if !native.Matched || native.BlockHash != c.block.Hash() {
			return fail("ACTUAL_NOT_CANONICALLY_CALIBRATED")
		}
	} else if native.World == "BRANCH" {
		if native.Patch == nil || ValidateLPIntervention(native.Patch.Intervention, c.checkpoint) != nil || !native.Patch.OriginalWitnessUnchanged || native.Patch.SemanticInitialWrites != 1 {
			return fail("BRANCH_INTERVENTION_BINDING")
		}
	} else {
		return fail("WORLD_UNSUPPORTED")
	}
	receipt := native.Receipts[index]
	o.GasUsed = receipt.GasUsed
	if receipt.TxHash != tx.Hash() || int(receipt.TransactionIndex) != index {
		return fail("RECEIPT_SUBJECT_IDENTITY")
	}
	if receipt.Status == types.ReceiptStatusFailed {
		if len(receipt.Logs) != 0 {
			return fail("REVERT_CONTAINS_COMMITTED_LOGS")
		}
		o.Status = "NOT_APPLICABLE"
		o.Lifecycle = "REVERT"
		o.ComponentAmountsStatus = "NOT_APPLICABLE"
		return o
	}
	if receipt.Status != types.ReceiptStatusSuccessful {
		return fail("UNSUPPORTED_RECEIPT_STATUS")
	}
	o.Lifecycle = "SUCCESS"
	var captureError error
	o.Recapture, captureError = projectRecapture(receipt.Logs)
	if captureError != nil {
		return fail("RECAPTURE_EVENT_UNRESOLVED")
	}

	if tx.To() == nil || *tx.To() != hookrRouter {
		return fail("UNSUPPORTED_DIRECT_ROUTER_SUBJECT")
	}
	// One exact route; recapture legs/multihop emitting additional target swaps
	// are not silently summed into the primary trade.
	var swap, route, fee, allocated, delivery, mint *types.Log
	choose := func(dst **types.Log, l *types.Log) bool {
		if *dst != nil {
			return false
		}
		*dst = l
		return true
	}
	for _, l := range receipt.Logs {
		if l == nil || len(l.Topics) == 0 {
			return fail("MALFORMED_NATIVE_LOG")
		}
		if l.TxHash != tx.Hash() || l.TxIndex != uint(index) || l.Removed {
			return fail("LOG_SUBJECT_IDENTITY")
		}
		if l.Address == rhookToken && l.Topics[0] == erc20TransferTopic {
			if abiWords(l, 3, 1) != nil {
				return fail("TOKEN_TRANSFER_LAYOUT")
			}
			from, e := abiAddress(l.Topics[1])
			if e != nil {
				return fail("TOKEN_TRANSFER_ADDRESS")
			}
			if from == hookrManager && !choose(&delivery, l) {
				return fail("AMBIGUOUS_DELIVERY")
			}
		}
		if l.Address == hookrManager && l.Topics[0] == erc6909TransferTopic {
			if abiWords(l, 4, 2) != nil {
				return fail("ERC6909_INDEXED_LAYOUT")
			}
			from, e := abiAddress(l.Topics[1])
			if e != nil {
				return fail("ERC6909_ADDRESS")
			}
			to, e := abiAddress(l.Topics[2])
			if e != nil {
				return fail("ERC6909_ADDRESS")
			}
			if from == (common.Address{}) && to == hookrRules && l.Topics[3] == (common.Hash{}) {
				if !choose(&mint, l) {
					return fail("AMBIGUOUS_RULES_CLAIM_MINT")
				}
			}
		}
		if len(l.Topics) < 2 || l.Topics[1] != hookrPoolID {
			continue
		}
		switch {
		case l.Address == hookrManager && l.Topics[0] == swapTopic:
			if !choose(&swap, l) {
				return fail("MULTIPLE_TARGET_POOL_SWAPS")
			}
		case l.Address == hookrRouter && l.Topics[0] == routerTopic:
			if !choose(&route, l) {
				return fail("MULTIPLE_ROUTER_SETTLEMENTS")
			}
		case l.Address == hookrRoot && l.Topics[0] == feeTopic:
			if !choose(&fee, l) {
				return fail("MULTIPLE_HOOK_FEES")
			}
		case l.Address == hookrRules && l.Topics[0] == allocatedTopic:
			if !choose(&allocated, l) {
				return fail("MULTIPLE_ALLOCATIONS")
			}
		}
	}
	if swap == nil || route == nil || fee == nil || allocated == nil || delivery == nil {
		return fail("REQUIRED_SETTLEMENT_OBSERVATION_MISSING")
	}
	if abiWords(swap, 3, 6) != nil || abiWords(route, 4, 2) != nil || abiWords(fee, 3, 3) != nil || abiWords(allocated, 3, 5) != nil || abiWords(delivery, 3, 1) != nil {
		return fail("SETTLEMENT_ABI_LAYOUT")
	}
	payer, e := abiAddress(route.Topics[2])
	if e != nil {
		return fail("PAYER_ABI")
	}
	recipient, e := abiAddress(route.Topics[3])
	if e != nil {
		return fail("RECIPIENT_ABI")
	}
	sender, e := abiAddress(swap.Topics[2])
	if e != nil || sender != hookrRouter {
		return fail("SWAP_SENDER")
	}
	deliveredTo, e := abiAddress(delivery.Topics[2])
	if e != nil || deliveredTo != recipient {
		return fail("DELIVERY_RECIPIENT")
	}
	if fee.Topics[2] != (common.Hash{}) || allocated.Topics[2] != (common.Hash{}) {
		return fail("UNSUPPORTED_QUOTE_CURRENCY")
	}
	amount0, e := signedABI(swap, 0, 128)
	if e != nil || amount0.Sign() >= 0 {
		return fail("NOT_ETH_TO_RHOOK_BUY")
	}
	amount1, e := signedABI(swap, 1, 128)
	if e != nil || amount1.Sign() <= 0 {
		return fail("NOT_POSITIVE_RHOOK_OUTPUT")
	}
	if abiUint(swap, 2).BitLen() > 160 || abiUint(swap, 3).BitLen() > 128 || abiUint(swap, 5).BitLen() > 24 {
		return fail("POOL_EVENT_INTEGER_WIDTH")
	}
	if _, e = signedABI(swap, 4, 24); e != nil {
		return fail("POOL_TICK_WIDTH")
	}
	gross, output := abiUint(route, 0), abiUint(route, 1)
	earned, refund, burned := abiUint(fee, 0), abiUint(fee, 1), abiUint(fee, 2)
	protocol, royalty, allocatedRefund, advisory := abiUint(allocated, 0), abiUint(allocated, 1), abiUint(allocated, 2), abiUint(allocated, 4)
	if _, e = abiAddress(common.BytesToHash(allocated.Data[96:128])); e != nil {
		return fail("ADVISORY_RECIPIENT_ABI")
	}
	poolIn := new(big.Int).Neg(amount0)
	if tx.Value().Cmp(gross) != 0 || output.Cmp(amount1) != 0 || output.Cmp(abiUint(delivery, 0)) != 0 || burned.Sign() != 0 || refund.Cmp(allocatedRefund) != 0 || add(poolIn, earned, refund).Cmp(gross) != 0 || add(protocol, royalty, advisory).Cmp(earned) != 0 {
		return fail("SETTLEMENT_RECONCILIATION")
	}
	if add(earned, refund).Sign() > 0 {
		if mint == nil || abiUint(mint, 1).Cmp(add(earned, refund)) != 0 {
			return fail("RULES_LIABILITY_CLAIM_MINT_MISSING_OR_MISMATCH")
		}
		caller, e := abiAddress(common.BytesToHash(mint.Data[:32]))
		if e != nil || caller != hookrRoot {
			return fail("CLAIM_MINT_CALLER")
		}
	} else if mint != nil && abiUint(mint, 1).Sign() != 0 {
		return fail("UNEXPECTED_RULES_CLAIM_MINT")
	}
	o.Status = "OBSERVED_SETTLEMENT_ONLY"
	o.Payer = payer
	o.Recipient = recipient
	o.GrossInput = decimal(gross)
	o.PoolInput = decimal(poolIn)
	o.DeliveredOutput = decimal(output)
	o.HookEarned = decimal(earned)
	o.Refund = decimal(refund)
	o.ProtocolAllocation = decimal(protocol)
	o.RoyaltyAllocation = decimal(royalty)
	o.AdvisoryAllocation = decimal(advisory)
	rate := abiUint(swap, 5).Uint64()
	o.TotalPoolFeePips = &rate
	if native.Observation != nil && native.Observation.Complete && native.Observation.Plan.Subject == o.Subject && native.Observation.Plan.NativeOrdinal == index {
		o.StateChangesStatus = "OBSERVED_BLOCK_BOUNDARY_KEYS_ONLY"
		q, cause := projectQuotePreimages(native.Observation, o)
		if cause != "" {
			o.Status = "UNRESOLVED"
			o.Cause = cause
			return o
		}
		o.NativeQuote = q
		o.ComponentAmountsStatus = "UNRESOLVED_MONETARY_COMPONENT_ATTRIBUTION_NOT_ADMITTED"
	}
	return o
}

// RateParts is source-derived integer arithmetic, not observed settlement or
// evidence of money paid to LPs. Its units intentionally remain separate.
type RateParts struct{ LPRewardPips, LPAssociatedProtocolPips, RoyaltyPips uint64 }

func BuyLPParts(lpBps, shareBps, royaltyBps uint64) (RateParts, error) {
	if lpBps > 1000 || shareBps > 5000 || royaltyBps > 1000 || (royaltyBps != 0 && lpBps == 0) {
		return RateParts{}, errors.New("UNSUPPORTED_RATE_CONFIG")
	}
	slice := (lpBps*shareBps + 99) / 100
	net := lpBps*100 - slice
	royalty := net * royaltyBps / 10000
	return RateParts{net - royalty, slice, royalty}, nil
}
