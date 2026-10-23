package prestate

import (
	"encoding/json"
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
)

// Extra scope guard for the selected ETH/RHOOK candidate, after generic proof
// admission. These are the exact previously authenticated Root/executor pins.
func CheckHookrBindings(raw []byte) error {
	var p BlockPackage
	if e := json.Unmarshal(raw, &p); e != nil {
		return e
	}
	root := common.HexToAddress("0x89c9fb50d1f03192230ffb1c279bb6e7d3fe6acc")
	executor := common.HexToAddress("0x4b4c16681401454140a9dbca55e5c186bbe8d728")
	hash := common.HexToHash("0xa454566f248677718ca1c6ed8df59e23bc6dc4b9f787a1c9bd687912d4ef508f")
	slot8 := common.HexToHash("0xdc5740eeafc78ca4488605782bceeee21ea0cec0908c37bbb90fb77c45910411")
	slot9 := common.HexToHash("0xdc5740eeafc78ca4488605782bceeee21ea0cec0908c37bbb90fb77c45910412")
	rootOK, executorOK, codeOK := false, false, false
	for _, capture := range p.Proofs {
		if capture.Address != root && capture.Address != executor {
			continue
		}
		if _, e := verifyProof(p.Checkpoint.StateRoot, capture.Address, capture.Slots, capture.Proof); e != nil {
			return e
		}
		proof := capture.Proof
		if capture.Address == executor {
			executorOK = proof.CodeHash == hash
		} else {
			if proof.CodeHash != common.HexToHash("0xd336de325837e60a74cea11d87b5ebd1cc8961911f611f38de0508d23b6e779f") {
				return errors.New("HOOKR_ROOT_CODE_CHANGED")
			}
			a, h := false, false
			for _, sp := range proof.StorageProof {
				if sp.Key == slot8 {
					a = common.BigToAddress(sp.Value.ToInt()) == executor
				}
				if sp.Key == slot9 {
					h = common.BigToHash(sp.Value.ToInt()) == hash
				}
			}
			rootOK = a && h
		}
	}
	for _, code := range p.Codes {
		if crypto.Keccak256Hash(code) == hash {
			codeOK = true
		}
	}
	if !rootOK || !executorOK || !codeOK {
		return errors.New("HOOKR_EXECUTOR_PIN_NOT_AUTHENTICATED")
	}
	return nil
}
