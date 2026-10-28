package scenario

import (
	"bytes"
	"context"
	"errors"
	"math/big"
	"testing"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/types"
)

func TestDiagnosticObservesAndCopiesResultWithoutMutation(t *testing.T) {
	target := common.HexToAddress("0x1234")
	input := []byte{1, 2, 3, 4, 5}
	tx := types.NewTx(&types.LegacyTx{To: &target, Gas: 100000, Value: big.NewInt(7), Data: input})
	returned := bytes.Repeat([]byte{0xaa}, diagnosticReturnLimit+1)
	result := &core.ExecutionResult{UsedGas: 77, Err: errors.New("execution reverted"), ReturnData: returned}
	d := &diagnosticLog{}
	if e := d.capture(Baseline, tx, common.Address{}, result); e != nil {
		t.Fatal(e)
	}
	if len(result.ReturnData) != diagnosticReturnLimit+1 || tx.Value().Uint64() != 7 || result.Err.Error() != "execution reverted" {
		t.Fatal("observed object mutated")
	}
	row := d.Rows[0]
	if len(row.ReturnData) != diagnosticReturnLimit || !row.Truncated || row.ReturnDataSha256 != digest(returned) || row.Error != "execution reverted" || !bytes.Equal(row.Selector, []byte{1, 2, 3, 4}) {
		t.Fatal("diagnostic bounds/identity")
	}
	returned[0] = 0xff
	if row.ReturnData[0] != 0xaa {
		t.Fatal("alias retained")
	}
	if e := d.capture(Variant, tx, common.Address{}, result); e == nil {
		t.Fatal("variant diagnostic")
	}
	if e := d.capture(Baseline, tx, common.Address{}, result); e != nil {
		t.Fatal(e)
	}
	if e := d.capture(Baseline, tx, common.Address{}, result); e == nil {
		t.Fatal("third result")
	}
}
func TestDiagnosticFenceAdmitsOnlyOneProducer(t *testing.T) {
	fence := &workerFence{maximum: 1}
	if e := fence.Enter(context.Background(), Baseline); e != nil {
		t.Fatal(e)
	}
	for _, world := range []string{Variant, Baseline} {
		if fence.Enter(context.Background(), world) == nil {
			t.Fatal("extra diagnostic producer")
		}
	}
}
func TestDiagnosticReferenceCannotActivateDiscoveryOrAnotherInput(t *testing.T) {
	a := &Admission{input: &admitted{spec: Spec{Commitment: "reference"}}}
	valid := map[string]any{"diagnosticProfile": DiagnosticProfile, "diagnosticOf": "reference", "maximumProducerEntries": float64(1)}
	if e := enableDiagnostic(a, valid); e != nil {
		t.Fatal(e)
	}
	for _, change := range []map[string]any{{"diagnosticOf": "other"}, {"diagnosticProfile": "other"}, {"discoveryProfile": DiscoveryProfile}, {"maximumProducerEntries": float64(2)}} {
		b := map[string]any{}
		for k, v := range valid {
			b[k] = v
		}
		for k, v := range change {
			b[k] = v
		}
		if e := enableDiagnostic(a, b); e == nil {
			t.Fatal("unbound diagnostic accepted")
		}
	}
}
