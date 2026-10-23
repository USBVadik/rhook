package prestate

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/crypto"
)

// OfflineCalibration is the small command adapter to the unchanged native
// library. No transport is constructed and no new state can be acquired.
type OfflineCalibration struct {
	Candidate *Candidate
	Bridge    *Bridge
	Inventory *Inventory
	ConfigSHA string
	TxHashes  []common.Hash
}

func PrepareOfflineCalibration(raw []byte, inputPin, witnessPin string) (*OfflineCalibration, error) {
	c, inv, err := AdmitPackage(raw)
	if err != nil {
		return nil, err
	}
	if inv.InputCommitment != inputPin || inv.WitnessCommitment != witnessPin {
		return nil, errors.New("ADMITTED_COMMITMENT_MISMATCH")
	}
	if err := CheckHookrBindings(raw); err != nil {
		return nil, err
	}
	var p BlockPackage
	if err := json.Unmarshal(raw, &p); err != nil {
		return nil, err
	}
	nodes, codes := map[common.Hash]hexutil.Bytes{}, map[common.Hash]hexutil.Bytes{}
	for _, n := range p.State {
		nodes[crypto.Keccak256Hash(n)] = n
	}
	for _, code := range p.Codes {
		codes[crypto.Keccak256Hash(code)] = code
	}
	for _, capture := range p.Proofs {
		used, err := verifyProof(p.Checkpoint.StateRoot, capture.Address, capture.Slots, capture.Proof)
		if err != nil {
			return nil, err
		}
		for h, n := range used {
			nodes[h] = n
		}
	}
	// The one attempted missing-state lookup may be recorded, but the nil source
	// always stops it without a socket/RPC. CPU/wall bounds belong to the launcher.
	b, err := NewBridge(p.Checkpoint, Budget{MaxRequests: 1, MaxBytes: 32 << 20,
		MaxResponseBytes: 8 << 20, ExpiresAt: time.Now().Add(120 * time.Second)}, nil)
	if err != nil {
		return nil, err
	}
	if err = b.LoadWitness(p.Checkpoint, nodes, codes); err != nil {
		b.Close()
		return nil, err
	}
	configHash := sha256.Sum256(c.configRaw)
	prepared := &OfflineCalibration{Candidate: c, Bridge: b, Inventory: inv, ConfigSHA: hex.EncodeToString(configHash[:])}
	for _, tx := range c.block.Transactions() {
		prepared.TxHashes = append(prepared.TxHashes, tx.Hash())
	}
	return prepared, nil
}

func (p *OfflineCalibration) Attempts() []Attempt {
	return append([]Attempt(nil), p.Bridge.attempts...)
}

// ClassifyCalibrationError does not infer a transaction-level EVM REVERT.
func ClassifyCalibrationError(err error) (string, string) {
	if err == nil {
		return "CANONICAL_ACTUAL_ROOTS_MATCH", ""
	}
	var host *HostStop
	if !errors.As(err, &host) {
		return "RUNTIME_OR_RESOURCE_STOP", "UNCLASSIFIED_NATIVE_ERROR"
	}
	switch host.Code {
	case "CANONICAL_ROOT_OR_GAS_MISMATCH", "FINALIZATION_COMMIT_MISMATCH",
		"GENERATED_TRANSACTION_SEQUENCE_MISMATCH", "GENERATED_ENVELOPE_ENCODING":
		return "CANONICAL_EXECUTION_MISMATCH", host.Code
	case "PROOF_SOURCE_UNAVAILABLE", "CODE_SOURCE_UNAVAILABLE", "ACCOUNT_PREIMAGE_UNAVAILABLE",
		"STORAGE_PREIMAGE_UNAVAILABLE", "TRIE_UPDATE_PREIMAGE_UNAVAILABLE",
		"MISSING_ORIGINAL_HEADER", "NITRO_SYSTEM_CONTEXT_UNAVAILABLE", "CHAIN_CONFIG_UNAVAILABLE":
		return "HOST_STOP_MISSING_STATE", host.Code
	default:
		if strings.Contains(host.Code, "BUDGET") || strings.Contains(host.Code, "EXPIRED") {
			return "RUNTIME_OR_RESOURCE_STOP", host.Code
		}
		return "RUNTIME_OR_RESOURCE_STOP", host.Code
	}
}
