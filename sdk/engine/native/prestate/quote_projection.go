package prestate

import (
	"bytes"
	"github.com/ethereum/go-ethereum/common"
	"math/big"
)

const swapContextABI = "(bytes32,address,address,address,address,address,bool,bool,bool,bool,int256,uint160,uint24)"

var beforeSwapSelector = eventTopic("beforeSwap(" + swapContextABI + ")")
var simulatedSelector = eventTopic("quoteSimulatedSwap(" + swapContextABI + ",(uint160,int24,uint160,int24))")
var settlementSelector = eventTopic("settleSwap(" + swapContextABI + ",(uint256,uint256,uint256,uint256,uint256,uint256,uint256,address))")

type QuoteObservation struct {
	ConfigWord        common.Hash `json:"configWordAtQuote"`
	LPBps             uint64      `json:"lpBps"`
	BaseLPFeePips     uint64      `json:"baseLPFeePips"`
	LPRewardPips      uint64      `json:"lpRuleRewardPipsOfPoolInput"`
	LPProtocolPips    uint64      `json:"lpAssociatedProtocolPipsOfGrossQuote"`
	QuotedLPSurcharge uint64      `json:"quotedTotalLPSurchargePips"`
	QuotedQuoteTake   uint64      `json:"quotedTotalQuoteTakePips"`
	QuoteBasis        string      `json:"quoteBasis"`
	ActualQuote       string      `json:"actualQuote"`
	RulesFee          string      `json:"rulesFee"`
	Meaning           string      `json:"meaning"`
}

func field(w common.Hash, offset, width uint) uint64 {
	x := new(big.Int).Rsh(w.Big(), offset)
	mask := new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), width), big.NewInt(1))
	return x.And(x, mask).Uint64()
}
func callWord(c NativeCallObservation, n int) *big.Int {
	return new(big.Int).SetBytes(c.Input[4+n*32 : 4+(n+1)*32])
}
func callAddress(c NativeCallObservation, n int) (common.Address, bool) {
	a, e := abiAddress(common.BytesToHash(c.Input[4+n*32 : 4+(n+1)*32]))
	return a, e == nil
}

func projectQuotePreimages(obs *NativeEconomicObservation, o SettlementObservation) (*QuoteObservation, string) {
	var quote, settle *NativeCallObservation
	for n := range obs.Calls {
		c := &obs.Calls[n]
		if c.Kind != 0xf1 || c.From != hookrRoot || c.To != hookrRules || c.Reverted || c.AncestorReverted || len(c.Input) < 4+13*32 || common.BytesToHash(c.Input[4:36]) != hookrPoolID {
			continue
		}
		sender, ok := callAddress(*c, 1)
		if !ok || sender != hookrRouter {
			continue
		}
		payer, ok := callAddress(*c, 2)
		if !ok || payer != o.Payer {
			continue
		}
		beneficiary, ok := callAddress(*c, 3)
		if !ok || beneficiary != o.Recipient {
			continue
		}
		switch {
		case bytes.Equal(c.Input[:4], simulatedSelector[:4]) || bytes.Equal(c.Input[:4], beforeSwapSelector[:4]):
			expected := 4 + 13*32
			if bytes.Equal(c.Input[:4], simulatedSelector[:4]) {
				expected += 4 * 32
			}
			if len(c.Input) != expected || len(c.Output) != 3*32 || quote != nil {
				return nil, "AMBIGUOUS_OR_MALFORMED_NATIVE_QUOTE"
			}
			quote = c
		case bytes.Equal(c.Input[:4], settlementSelector[:4]):
			if len(c.Input) != 4+21*32 || len(c.Output) != 32 || settle != nil {
				return nil, "AMBIGUOUS_OR_MALFORMED_NATIVE_SETTLEMENT"
			}
			settle = c
		}
	}
	if quote == nil || settle == nil || quote.RulesWordAtEntry == nil || settle.RulesWordAtEntry == nil {
		return nil, "NATIVE_QUOTE_SETTLEMENT_PREIMAGES_MISSING"
	}
	if !bytes.Equal(quote.Input[4:4+13*32], settle.Input[4:4+13*32]) || *quote.RulesWordAtEntry != *settle.RulesWordAtEntry {
		return nil, "QUOTE_SETTLEMENT_CONTEXT_CHANGED"
	}
	subject, ok := callAddress(*quote, 4)
	if !ok || subject != rhookToken {
		return nil, "QUOTE_SUBJECT_CURRENCY"
	}
	currency, ok := callAddress(*quote, 5)
	if !ok || currency != (common.Address{}) {
		return nil, "QUOTE_CURRENCY"
	}
	for _, n := range []int{6, 7, 8, 9} {
		if callWord(*quote, n).Cmp(big.NewInt(1)) != 0 {
			return nil, "UNSUPPORTED_QUOTE_AUTH_DIRECTION_OR_EXACTNESS"
		}
	}
	base := callWord(*quote, 12)
	if !base.IsUint64() || base.Uint64() != 3000 {
		return nil, "BASE_LP_FEE_CHANGED"
	}
	w := *quote.RulesWordAtEntry
	lp, share, royalty := field(w, 160, 16), field(w, 208, 16), field(w, 192, 16)
	// Narrow first case: no guard/snipe/burn/pot/royalty. All untouched words,
	// including recapture config and Root.policy, retain their native state.
	if field(w, 0, 40) != 0 || field(w, 64, 24) != 0 || field(w, 144, 16) != 0 || field(w, 176, 16) != 0 || royalty != 0 || share != 2000 {
		return nil, "UNSUPPORTED_QUOTE_RULE_SHAPE"
	}
	expectedLP := uint64(100)
	if o.World == "BRANCH" {
		expectedLP = 0
	}
	if lp != expectedLP {
		return nil, "SELECTED_SWAP_LP_VALUE_CHANGED_AFTER_CHECKPOINT"
	}
	parts, e := BuyLPParts(lp, share, royalty)
	if e != nil {
		return nil, "LP_RATE_MODEL_REJECTED"
	}
	surcharge := new(big.Int).SetBytes(quote.Output[:32])
	take := new(big.Int).SetBytes(quote.Output[32:64])
	burn := new(big.Int).SetBytes(quote.Output[64:96])
	if surcharge.BitLen() > 24 || take.BitLen() > 24 || burn.Sign() != 0 || surcharge.Uint64()+3000 != *o.TotalPoolFeePips || surcharge.Uint64() < parts.LPRewardPips || take.Uint64() < parts.LPAssociatedProtocolPips {
		return nil, "NATIVE_QUOTE_RATE_RECONCILIATION"
	}
	want := []*string{o.PoolInput, o.DeliveredOutput, o.GrossInput}
	for n, v := range want {
		x, ok := new(big.Int).SetString(*v, 10)
		if !ok || callWord(*settle, 13+n).Cmp(x) != 0 {
			return nil, "NATIVE_SETTLEMENT_BASE_RECONCILIATION"
		}
	}
	requested := callWord(*quote, 10)
	if requested.Bit(255) != 1 {
		return nil, "NOT_NEGATIVE_EXACT_INPUT"
	}
	requested.Sub(new(big.Int).Lsh(big.NewInt(1), 256), requested)
	gross, _ := new(big.Int).SetString(*o.GrossInput, 10)
	if requested.Cmp(gross) != 0 || callWord(*quote, 11).BitLen() > 160 {
		return nil, "UNSUPPORTED_PARTIAL_FILL_OR_PRICE_LIMIT_ENCODING"
	}
	expectedRulesFee := new(big.Int).Div(new(big.Int).Mul(callWord(*settle, 15), take), big.NewInt(1000000))
	if expectedRulesFee.Cmp(callWord(*settle, 16)) != 0 || callWord(*settle, 17).Sign() != 0 || callWord(*settle, 18).Sign() != 0 {
		return nil, "RULES_FEE_ROUNDING_OR_NONZERO_ADVICE_REFUND_UNSUPPORTED"
	}
	if take.Cmp(big.NewInt(1000000)) >= 0 {
		return nil, "QUOTE_TAKE_RATE_OUT_OF_BOUNDS"
	}
	expectedBasis := new(big.Int).Div(new(big.Int).Mul(callWord(*settle, 13), big.NewInt(1000000)), new(big.Int).Sub(big.NewInt(1000000), take))
	if expectedBasis.Cmp(gross) > 0 {
		expectedBasis.Set(gross)
	}
	if expectedBasis.Cmp(callWord(*settle, 15)) != 0 {
		return nil, "ROOT_QUOTE_BASIS_ROUNDING"
	}
	dynamic := new(big.Int).Sub(add(surcharge, take), new(big.Int).SetUint64(parts.LPRewardPips+parts.LPAssociatedProtocolPips))
	if dynamic.Sign() < 0 || dynamic.BitLen() > 24 {
		return nil, "DYNAMIC_RATE_COMPONENT_RECONCILIATION"
	}
	dynamicProtocol := new(big.Int).Div(new(big.Int).Mul(dynamic, new(big.Int).SetUint64(share)), big.NewInt(10000))
	if add(new(big.Int).SetUint64(parts.LPAssociatedProtocolPips), dynamicProtocol).Cmp(take) != 0 {
		return nil, "DYNAMIC_PROTOCOL_RATE_ROUNDING"
	}
	credited := new(big.Int).SetBytes(settle.Output)
	if callWord(*settle, 19).Sign() != 0 {
		return nil, "UNSUPPORTED_SUBJECT_BURN"
	}
	if credited.Cmp(add(callWord(*settle, 16), callWord(*settle, 17), callWord(*settle, 18))) != 0 {
		return nil, "NATIVE_SETTLEMENT_CREDIT_RECONCILIATION"
	}
	earned, _ := new(big.Int).SetString(*o.HookEarned, 10)
	refund, _ := new(big.Int).SetString(*o.Refund, 10)
	if earned.Cmp(add(callWord(*settle, 16), callWord(*settle, 17))) != 0 || refund.Cmp(callWord(*settle, 18)) != 0 {
		return nil, "NATIVE_SETTLEMENT_EVENT_RECONCILIATION"
	}
	return &QuoteObservation{w, lp, 3000, parts.LPRewardPips, parts.LPAssociatedProtocolPips, surcharge.Uint64(), take.Uint64(), callWord(*settle, 15).String(), callWord(*settle, 13).String(), callWord(*settle, 16).String(), "Native call observations and source-derived rate components. Monetary component attribution and realized LP profit are not established; no qualified profile is issued."}, ""
}
