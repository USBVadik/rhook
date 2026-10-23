package prestate

import (
	"math/big"
	"testing"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/core/vm"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/rlp"
	"github.com/holiman/uint256"
)

func setFixtureCode(t *testing.T, f *fixture, a common.Address, code []byte) {
	t.Helper()
	f.code[a] = code
	account := types.StateAccount{Nonce: 1, Balance: uint256.NewInt(100), Root: f.storage[a].Hash(), CodeHash: crypto.Keccak256(code)}
	raw, _ := rlp.EncodeToBytes(&account)
	if e := f.accounts.Update(crypto.Keccak256(a[:]), raw); e != nil {
		t.Fatal(e)
	}
	f.checkpoint.StateRoot = f.accounts.Hash()
}
func callFixture(t *testing.T, b *Bridge, address common.Address) error {
	t.Helper()
	return b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		cfg, e := ValidateConfig(configBytes(t), 61)
		if e != nil {
			return e
		}
		evm := vm.NewEVM(vm.BlockContext{CanTransfer: core.CanTransfer, Transfer: core.Transfer, GetHash: func(uint64) common.Hash { return common.Hash{} }, GasLimit: 1000000, BlockNumber: big.NewInt(124), Time: 101, Difficulty: big.NewInt(1), BaseFee: big.NewInt(0), ArbOSVersion: 61}, s, cfg, vm.Config{})
		_, _, _, e = evm.Call(addrA, address, nil, 500000, uint256.NewInt(0))
		if e != nil {
			return e
		}
		return s.Error()
	})
}
func TestNativeEVMExecutesHydratedStorageRead(t *testing.T) {
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	if e := callFixture(t, b, addrA); e != nil {
		t.Fatal(e)
	}
	if f.calls < 2 {
		t.Fatal("real native EVM did not hydrate")
	}
}
func TestHostFailureCannotBecomeCaughtEVMRevert(t *testing.T) {
	for _, missing := range []bool{false, true} {
		f := makeFixture(t)
		parent := common.FromHex("0x600060006000600060007322222222222222222222222222222222222222226207a120f15000")
		setFixtureCode(t, f, addrA, parent)
		setFixtureCode(t, f, addrB, common.FromHex("0x60005460006000fd"))
		b := fixtureBridge(t, f)
		if e := b.Protect(func() error {
			s, e := b.State()
			if e != nil {
				return e
			}
			s.GetCode(addrA)
			s.GetCode(addrB)
			return nil
		}); e != nil {
			t.Fatal(e)
		}
		f.fail = missing
		e := callFixture(t, b, addrA)
		if missing && !IsHostStop(e) {
			t.Fatalf("host failure became EVM result: %v", e)
		}
		if !missing && e != nil {
			t.Fatalf("normal child revert should be caught by parent: %v", e)
		}
	}
}
func TestMissingCodeFailsAtNativeEVM(t *testing.T) {
	f := makeFixture(t)
	b := fixtureBridge(t, f)
	if e := b.Protect(func() error {
		s, e := b.State()
		if e != nil {
			return e
		}
		s.GetBalance(addrA)
		return nil
	}); e != nil {
		t.Fatal(e)
	}
	f.code[addrA] = []byte{0x00}
	e := callFixture(t, b, addrA)
	if !IsHostStop(e) {
		t.Fatalf("wrong/missing code accepted %v", e)
	}
}
