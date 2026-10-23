package prestate

import (
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/trie"
	"math/big"
	"testing"
)

func encodedInts(values ...*big.Int) []byte {
	out := []byte{}
	for _, x := range values {
		u := new(big.Int).Set(x)
		if u.Sign() < 0 {
			u.Add(u, new(big.Int).Lsh(big.NewInt(1), 256))
		}
		out = append(out, u.FillBytes(make([]byte, 32))...)
	}
	return out
}
func ints(ns ...int64) []byte {
	xs := make([]*big.Int, len(ns))
	for i, n := range ns {
		xs[i] = big.NewInt(n)
	}
	return encodedInts(xs...)
}
func topicAddress(a common.Address) common.Hash { return common.BytesToHash(a[:]) }

// Entirely fabricated receipts and header, for decoder/accounting development.
// No historical data or successful native result is claimed by this fixture.
func syntheticSettlement(t *testing.T, change func(*types.Receipt)) (*Candidate, *CalibrationResult) {
	t.Helper()
	payer := common.HexToAddress("0x1234")
	recipient := common.HexToAddress("0x5678")
	system := types.NewTx(&types.LegacyTx{Nonce: 1, Gas: 21000, GasPrice: big.NewInt(1)})
	user := types.NewTx(&types.LegacyTx{Nonce: 2, To: &hookrRouter, Gas: 200000, GasPrice: big.NewInt(1), Value: big.NewInt(1000000)})
	logs := []*types.Log{
		{Address: hookrManager, Topics: []common.Hash{swapTopic, hookrPoolID, topicAddress(hookrRouter)}, Data: ints(-990000, 4000000, 1, 1, 1, 11000)},
		{Address: hookrRules, Topics: []common.Hash{allocatedTopic, hookrPoolID, {}}, Data: ints(10000, 0, 0, 0, 0)},
		{Address: hookrManager, Topics: []common.Hash{erc6909TransferTopic, {}, topicAddress(hookrRules), {}}, Data: encodedInts(new(big.Int).SetBytes(hookrRoot[:]), big.NewInt(10000))},
		{Address: hookrRoot, Topics: []common.Hash{feeTopic, hookrPoolID, {}}, Data: ints(10000, 0, 0)},
		{Address: rhookToken, Topics: []common.Hash{erc20TransferTopic, topicAddress(hookrManager), topicAddress(recipient)}, Data: ints(4000000)},
		{Address: hookrRouter, Topics: []common.Hash{routerTopic, hookrPoolID, topicAddress(payer), topicAddress(recipient)}, Data: ints(1000000, 4000000)},
	}
	for i, l := range logs {
		l.TxHash = user.Hash()
		l.TxIndex = 1
		l.Index = uint(i)
	}
	receipt := &types.Receipt{Status: 1, TxHash: user.Hash(), TransactionIndex: 1, GasUsed: 50000, CumulativeGasUsed: 71000, Logs: logs}
	if change != nil {
		change(receipt)
	}
	receipts := types.Receipts{&types.Receipt{Status: 1, TxHash: system.Hash(), TransactionIndex: 0, GasUsed: 21000, CumulativeGasUsed: 21000}, receipt}
	h := &types.Header{Root: common.HexToHash("0x01"), ReceiptHash: types.DeriveSha(receipts, trie.NewStackTrie(nil)), Difficulty: big.NewInt(1), Number: big.NewInt(124)}
	block := types.NewBlockWithHeader(h).WithBody(types.Body{Transactions: types.Transactions{system, user}})
	c := &Candidate{block: block, inputCommitment: "SYNTHETIC_ONLY"}
	out := &CalibrationResult{InputCommitment: c.InputCommitment(), StateRoot: h.Root, ReceiptsRoot: h.ReceiptHash, Transactions: 2, Matched: true, BlockHash: block.Hash(), ProducedHeader: h, Receipts: receipts, World: "ACTUAL"}
	return c, out
}

func TestEconomicSettlementReconcilesBaseUnitsWithoutQualification(t *testing.T) {
	c, out := syntheticSettlement(t, nil)
	o := ProjectHookrSettlement(c, out, 1)
	if o.Status != "OBSERVED_SETTLEMENT_ONLY" || o.Assurance != "UNRESOLVED" || *o.GrossInput != "1000000" || *o.PoolInput != "990000" || *o.DeliveredOutput != "4000000" || *o.ProtocolAllocation != "10000" {
		t.Fatalf("projection incomplete: %+v", o)
	}
	if o.ComponentAmountsStatus != "UNRESOLVED_MISSING_QUOTE_SETTLEMENT_PREIMAGES" || o.RealizedLPProfitStatus != "OUT_OF_SCOPE" {
		t.Fatal("invented component money/profit")
	}
}

func TestEconomicExtractionRejectsAmbiguousAndMissingRecords(t *testing.T) {
	cases := []struct {
		name   string
		change func(*types.Receipt)
	}{
		{"duplicate-swap", func(r *types.Receipt) { r.Logs = append(r.Logs, r.Logs[0]) }},
		{"missing-hook-fee", func(r *types.Receipt) { r.Logs = append(r.Logs[:3], r.Logs[4:]...) }},
		{"wrong-delivery", func(r *types.Receipt) { r.Logs[4].Data = ints(4000001) }},
		{"wrong-subject", func(r *types.Receipt) { r.TxHash = common.HexToHash("0x99") }},
		{"wrong-claim-indexing", func(r *types.Receipt) { r.Logs[2].Topics = []common.Hash{erc6909TransferTopic, {}} }},
		{"wrong-quote", func(r *types.Receipt) { r.Logs[3].Topics[2] = common.HexToHash("0x01") }},
		{"wrong-allocation", func(r *types.Receipt) { r.Logs[1].Data = ints(9999, 0, 0, 0, 0) }},
		{"positive-amount0", func(r *types.Receipt) { r.Logs[0].Data = ints(990000, 4000000, 1, 1, 1, 11000) }},
		{"malformed-abi", func(r *types.Receipt) { r.Logs[0].Data = append(r.Logs[0].Data, 0) }},
		{"wrong-emitter", func(r *types.Receipt) { r.Logs[3].Address = common.HexToAddress("0x99") }},
	}
	for _, x := range cases {
		t.Run(x.name, func(t *testing.T) {
			c, out := syntheticSettlement(t, x.change)
			o := ProjectHookrSettlement(c, out, 1)
			if o.Status != "UNRESOLVED" || o.Cause == "" || o.GrossInput != nil {
				t.Fatalf("unsupported evidence became money: %+v", o)
			}
		})
	}
}

func TestEconomicReceiptTamperCannotReuseNativeRoot(t *testing.T) {
	c, out := syntheticSettlement(t, nil)
	out.Receipts[1].Logs[0].Data = ints(-990001, 4000000, 1, 1, 1, 11000)
	if o := ProjectHookrSettlement(c, out, 1); o.Status != "UNRESOLVED" || o.Cause != "RECEIPT_HEADER_ROOT_BINDING" {
		t.Fatalf("tamper accepted: %+v", o)
	}
}

func TestEconomicRevertHasNoInventedZeroSettlement(t *testing.T) {
	c, out := syntheticSettlement(t, func(r *types.Receipt) { r.Status = 0; r.Logs = nil })
	o := ProjectHookrSettlement(c, out, 1)
	if o.Status != "NOT_APPLICABLE" || o.Lifecycle != "REVERT" || o.GrossInput != nil || o.DeliveredOutput != nil {
		t.Fatal("REVERT confused with unknown or zero")
	}
}

func TestLPModelRatesHaveDistinctBasesAndSolidityRounding(t *testing.T) {
	p, e := BuyLPParts(100, 2000, 0)
	if e != nil || p.LPRewardPips != 8000 || p.LPAssociatedProtocolPips != 2000 {
		t.Fatal(p, e)
	}
	p, e = BuyLPParts(0, 2000, 0)
	if e != nil || p != (RateParts{}) {
		t.Fatal(p, e)
	}
	p, e = BuyLPParts(1, 1, 1000)
	if e != nil || p.LPAssociatedProtocolPips != 1 || p.RoyaltyPips != 9 || p.LPRewardPips != 90 {
		t.Fatal(p, e)
	}
	if _, e = BuyLPParts(0, 2000, 1); e == nil {
		t.Fatal("invalid zero-lp royalty accepted")
	}
}
