package prestate

import (
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
)

var correctionSucceededTopic = eventTopic("CorrectionSucceeded(bytes32,uint8,address,uint256,uint256,address)")
var correctionFailedTopic = eventTopic("CorrectionFailed(bytes32,uint8,address,bytes4)")
var laneCodeChangedTopic = eventTopic("LaneCodeChanged(bytes32,uint8)")

type RecaptureObservation struct {
	Phase          uint64          `json:"phase"`
	Status         string          `json:"status"`
	Trader         common.Address  `json:"trader"`
	ReportedProfit *string         `json:"reportedProfit"`
	Pushed         *string         `json:"pushed"`
	Currency       *common.Address `json:"currency"`
	Reason         *string         `json:"reason"`
	Meaning        string          `json:"meaning"`
}

func projectRecapture(logs []*types.Log) ([]RecaptureObservation, error) {
	out := []RecaptureObservation{}
	seen := map[uint64]bool{}
	for _, l := range logs {
		if l == nil || l.Address != hookrRoot || len(l.Topics) < 2 || l.Topics[1] != hookrPoolID {
			continue
		}
		if l.Topics[0] == laneCodeChangedTopic {
			return nil, errors.New("LANE_RUNTIME_CHANGED")
		}
		if l.Topics[0] != correctionSucceededTopic && l.Topics[0] != correctionFailedTopic {
			continue
		}
		if len(l.Topics) != 4 || l.Removed || l.Topics[2].Big().BitLen() > 8 {
			return nil, errors.New("RECAPTURE_ABI")
		}
		phase := l.Topics[2].Big().Uint64()
		if phase < 1 || phase > 2 || seen[phase] {
			return nil, errors.New("RECAPTURE_PHASE_AMBIGUOUS")
		}
		seen[phase] = true
		trader, e := abiAddress(l.Topics[3])
		if e != nil {
			return nil, e
		}
		o := RecaptureObservation{Phase: phase, Trader: trader, Meaning: "Committed native event. Reported profit is not independently proved realized LP profit; pushed is kept separate from the LP-rule fee components."}
		if l.Topics[0] == correctionSucceededTopic {
			if abiWords(l, 4, 3) != nil {
				return nil, errors.New("RECAPTURE_SUCCESS_ABI")
			}
			currency, e := abiAddress(common.BytesToHash(l.Data[64:96]))
			if e != nil {
				return nil, e
			}
			o.Status = "SUCCEEDED_EVENT_OBSERVED"
			o.ReportedProfit = decimal(abiUint(l, 0))
			o.Pushed = decimal(abiUint(l, 1))
			o.Currency = &currency
		} else {
			if abiWords(l, 4, 1) != nil {
				return nil, errors.New("RECAPTURE_FAILURE_ABI")
			}
			for _, b := range l.Data[4:] {
				if b != 0 {
					return nil, errors.New("RECAPTURE_REASON_ABI")
				}
			}
			reason := hexutil.Encode(l.Data[:4])
			o.Status = "FAILED_EVENT_OBSERVED"
			o.Reason = &reason
		}
		out = append(out, o)
	}
	return out, nil
}
