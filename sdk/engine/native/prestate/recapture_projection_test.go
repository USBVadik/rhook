package prestate

import (
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"testing"
)

func TestRecaptureFailureIsNotZeroProfitOrZeroPush(t *testing.T) {
	reason := make([]byte, 32)
	copy(reason, []byte{1, 2, 3, 4})
	l := &types.Log{Address: hookrRoot, Topics: []common.Hash{correctionFailedTopic, hookrPoolID, common.HexToHash("0x01"), {}}, Data: reason}
	o, e := projectRecapture([]*types.Log{l})
	if e != nil || len(o) != 1 || o[0].ReportedProfit != nil || o[0].Pushed != nil || o[0].Reason == nil {
		t.Fatal(o, e)
	}
	l.Topics[0] = correctionSucceededTopic
	l.Data = ints(7, 5, 0)
	o, e = projectRecapture([]*types.Log{l})
	if e != nil || *o[0].ReportedProfit != "7" || *o[0].Pushed != "5" {
		t.Fatal(o, e)
	}
	if _, e = projectRecapture([]*types.Log{l, l}); e == nil {
		t.Fatal("duplicate recapture phase accepted")
	}
}
