package scenario

import (
	"math/big"
	"os"
	"strings"
	"testing"

	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/offchainlabs/nitro/arbos/arbosState"
)

func TestGasCapacityStopsBeforeExecution(t *testing.T) {
	for _, tc := range []struct {
		tx, block, header uint64
		accept            bool
	}{
		{32000000, 32000000, 32000000, true},
		{10000000, 10000000, 10000000, true},
		{9999999, 32000000, 32000000, false},
		{32000000, 9999999, 32000000, false},
		{32000000, 32000000, 9999999, false},
		{0, 32000000, 32000000, false},
	} {
		if err := validateGasCapacity([]Action{{Gas: 10000000}}, tc.header, tc.tx, tc.block); (err == nil) != tc.accept {
			t.Fatalf("%+v: %v", tc, err)
		}
	}
}

// Authentication only: no producer, EVM, source or network is used.
func TestSavedScenarioGasBudgetAndSignedMapping(t *testing.T) {
	path := os.Getenv("RHOOK_GAS_SCENARIO_REGRESSION")
	if path == "" {
		t.Skip("private saved-root fixture not shipped with source")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	key, err := crypto.ToECDSA(crypto.Keccak256([]byte("RHOOK BUILD04 PUBLIC SIMULATION SIGNER; NEVER FUND OR BROADCAST")))
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name             string
		declared, signed uint64
		want             string
	}{
		{"retained", 5000000, 5000000, ""},
		{"lane-reserve", 10000000, 10000000, "FILTER_OR_ADMITTED"},
		{"unreviewed", 6000000, 6000000, "ACTION_CONTRACT"},
		{"above-bound", 10000001, 10000001, "ACTION_CONTRACT"},
		{"mismatch", 10000000, 5000000, "ACTION_TRANSACTION_MAPPING"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			s, err := Parse(raw)
			if err != nil {
				t.Fatal(err)
			}
			a := &s.Actions[0]
			var tx types.Transaction
			if err = tx.UnmarshalBinary(a.Raw); err != nil {
				t.Fatal(err)
			}
			txNew, err := types.SignTx(types.NewTx(&types.LegacyTx{Nonce: tx.Nonce(), Gas: tc.signed, GasPrice: tx.GasPrice(), To: tx.To(), Value: tx.Value(), Data: tx.Data()}), types.LatestSignerForChainID(big.NewInt(4663)), key)
			if err != nil {
				t.Fatal(err)
			}
			a.Raw, err = txNew.MarshalBinary()
			if err != nil {
				t.Fatal(err)
			}
			a.Gas = tc.declared
			a.ID = ActionID(*a)
			updated, err := Canonical(Commit(s.Body))
			if err != nil {
				t.Fatal(err)
			}
			accepted, err := Admit(append(updated, '\n'))
			if tc.want == "FILTER_OR_ADMITTED" {
				if err != nil && !strings.Contains(err.Error(), "TRANSACTION_FILTER_PRECONDITION") {
					t.Fatal(err)
				}
			} else if tc.want == "" {
				if err != nil {
					t.Fatal(err)
				}
				bridge, err := openBridge(accepted.input)
				if err != nil {
					t.Fatal(err)
				}
				defer bridge.Close()
				err = bridge.Protect(func() error {
					state, err := bridge.State()
					if err != nil {
						return err
					}
					arb, err := arbosState.OpenSystemArbosState(state, nil, true)
					if err != nil {
						return err
					}
					perTx, err := arb.L2PricingState().PerTxGasLimit()
					if err != nil {
						return err
					}
					perBlock, err := arb.L2PricingState().PerBlockGasLimit()
					if err != nil {
						return err
					}
					t.Logf("authenticated gas capacity: perTx=%d perBlock=%d parentHeader=%d", perTx, perBlock, accepted.input.parent.GasLimit)
					if perTx < 10000000 || perBlock < 10000000 || accepted.input.parent.GasLimit < 10000000 {
						t.Error("10m candidate exceeds authenticated chain gas capacity")
					}
					return state.Error()
				})
				if err != nil {
					t.Fatal(err)
				}
			} else if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("want %s, got %v", tc.want, err)
			}
		})
	}
}
