package scenario

import (
	"errors"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/types"
)

const DiagnosticProfile = "rhook/scenario-result-diagnostic/0.1"
const diagnosticReturnLimit = 16384

// Observes the producer's existing result hook. It never calls StateDB or
// changes the result, transaction, environment, gas accounting or filter answer.
type diagnosticLog struct {
	Profile  string             `json:"profile"`
	Scope    string             `json:"scope"`
	Scenario string             `json:"scenarioCommitment"`
	Rows     []diagnosticResult `json:"results"`
}
type diagnosticResult struct {
	World            string          `json:"world"`
	TransactionHash  common.Hash     `json:"transactionHash"`
	TransactionType  uint8           `json:"transactionType"`
	Sender           common.Address  `json:"sender"`
	Recipient        *common.Address `json:"recipient"`
	Selector         hexutil.Bytes   `json:"selector"`
	Value            string          `json:"valueWei"`
	UsedGas          uint64          `json:"executionResultUsedGas"`
	Error            string          `json:"vmError,omitempty"`
	ReturnData       hexutil.Bytes   `json:"returnData"`
	ReturnDataBytes  int             `json:"returnDataBytes"`
	ReturnDataSha256 string          `json:"returnDataSha256"`
	Truncated        bool            `json:"truncated"`
}

func (d *diagnosticLog) capture(world string, tx *types.Transaction, sender common.Address, result *core.ExecutionResult) error {
	if world != Baseline || tx == nil || result == nil || len(d.Rows) >= 2 {
		return errors.New("DIAGNOSTIC_SCOPE_OR_RESULT_LIMIT")
	}
	input := tx.Data()
	if len(input) > 4 {
		input = input[:4]
	}
	data := result.ReturnData
	length := len(data)
	if length > diagnosticReturnLimit {
		data = data[:diagnosticReturnLimit]
	}
	row := diagnosticResult{World: world, TransactionHash: tx.Hash(), TransactionType: tx.Type(), Sender: sender, Recipient: tx.To(), Selector: common.CopyBytes(input), Value: tx.Value().String(), UsedGas: result.UsedGas, ReturnData: common.CopyBytes(data), ReturnDataBytes: length, ReturnDataSha256: digest(result.ReturnData), Truncated: length > diagnosticReturnLimit}
	if result.Err != nil {
		row.Error = result.Err.Error()
		if len(row.Error) > 400 {
			row.Error = row.Error[:400]
		}
	}
	d.Rows = append(d.Rows, row)
	return nil
}
func enableDiagnostic(a *Admission, b map[string]any) error {
	if a == nil || a.input == nil || b["diagnosticProfile"] != DiagnosticProfile || b["discoveryProfile"] != nil || b["diagnosticOf"] != a.input.spec.Commitment || b["maximumProducerEntries"] != float64(1) {
		return errors.New("EXACT_DIAGNOSTIC_BINDING_REQUIRED")
	}
	a.input.diagnostic = &diagnosticLog{Profile: DiagnosticProfile, Scope: "TOP_LEVEL_NITRO_POST_TX_RESULT_NO_INTERNAL_CALL_TRACE", Scenario: a.input.spec.Commitment, Rows: []diagnosticResult{}}
	return nil
}
