package prestate

import (
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"math/big"
	"testing"
)

func syntheticQuoteAndSettlement(t *testing.T) (*NativeEconomicObservation, SettlementObservation) {
	c, out := syntheticSettlement(t, func(r *types.Receipt) {
		r.Logs[0].Data = ints(-998000, 4000000, 1, 1, 1, 11000)
		r.Logs[1].Data = ints(2000, 0, 0, 0, 0)
		r.Logs[2].Data = encodedInts(new(big.Int).SetBytes(hookrRoot[:]), big.NewInt(2000))
		r.Logs[3].Data = ints(2000, 0, 0)
	})
	o := ProjectHookrSettlement(c, out, 1)
	if o.Status != "OBSERVED_SETTLEMENT_ONLY" {
		t.Fatal(o)
	}
	xs := []*big.Int{hookrPoolID.Big(), new(big.Int).SetBytes(hookrRouter[:]), new(big.Int).SetBytes(o.Payer[:]), new(big.Int).SetBytes(o.Recipient[:]), new(big.Int).SetBytes(rhookToken[:]), big.NewInt(0), big.NewInt(1), big.NewInt(1), big.NewInt(1), big.NewInt(1), big.NewInt(-1000000), big.NewInt(1), big.NewInt(3000)}
	w := new(big.Int).Lsh(big.NewInt(2000), 208)
	w.Or(w, new(big.Int).Lsh(big.NewInt(100), 160))
	w.Or(w, new(big.Int).Lsh(big.NewInt(11500), 40))
	word := common.BigToHash(w)
	quote := NativeCallObservation{From: hookrRoot, To: hookrRules, Kind: 0xf1, Input: append(common.CopyBytes(beforeSwapSelector[:4]), encodedInts(xs...)...), Output: ints(8000, 2000, 0), RulesWordAtEntry: &word}
	z := append([]*big.Int{}, xs...)
	for _, v := range []int64{998000, 4000000, 1000000, 2000, 0, 0, 0, 0} {
		z = append(z, big.NewInt(v))
	}
	settlement := NativeCallObservation{From: hookrRoot, To: hookrRules, Kind: 0xf1, Input: append(common.CopyBytes(settlementSelector[:4]), encodedInts(z...)...), Output: ints(2000), RulesWordAtEntry: &word}
	return &NativeEconomicObservation{Complete: true, Calls: []NativeCallObservation{quote, settlement}}, o
}

func TestNativeQuoteSettlementPreimagesAndIntegerReconciliation(t *testing.T) {
	obs, o := syntheticQuoteAndSettlement(t)
	q, cause := projectQuotePreimages(obs, o)
	if cause != "" || q.LPRewardPips != 8000 || q.LPProtocolPips != 2000 || q.RulesFee != "2000" {
		t.Fatal(q, cause)
	}
}

func TestQuotePreimageCannotComeFromRevertedOrMismatchedFrame(t *testing.T) {
	for _, kind := range []string{"reverted-parent", "config", "context", "rounding", "duplicate", "caller"} {
		t.Run(kind, func(t *testing.T) {
			obs, o := syntheticQuoteAndSettlement(t)
			switch kind {
			case "reverted-parent":
				obs.Calls[0].AncestorReverted = true
			case "config":
				w := *obs.Calls[1].RulesWordAtEntry
				w[31] ^= 1
				obs.Calls[1].RulesWordAtEntry = &w
			case "context":
				obs.Calls[1].Input[35] ^= 1
			case "rounding":
				obs.Calls[1].Input[4+17*32-1] ^= 1
			case "duplicate":
				obs.Calls = append(obs.Calls, obs.Calls[0])
			case "caller":
				obs.Calls[0].From = hookrRouter
			}
			if q, cause := projectQuotePreimages(obs, o); q != nil || cause == "" {
				t.Fatal("invalid preimage promoted", q, cause)
			}
		})
	}
}
