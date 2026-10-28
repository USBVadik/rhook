package scenario

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum/accounts/abi"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/params"
	"github.com/offchainlabs/nitro/arbos/arbosState"
	prestate "local/rhook-robinhood"
)

// Admission owns a deep copy; callers cannot change inputs after validation.
// Success means required initial reads passed, not that transitive closure is proven.
type Admission struct{ input *admitted }

func Admit(raw []byte) (*Admission, error) { return admit(raw, officialProfile()) }

func admit(raw []byte, p profile) (accepted *Admission, err error) {
	return admitOffline(raw, p)
}

func admitOffline(raw []byte, p profile) (accepted *Admission, err error) {
	return admitWithSource(raw, p, nil)
}

func admitWithSource(raw []byte, p profile, source *discoverySource) (accepted *Admission, err error) {
	s, e := Parse(raw)
	if e != nil {
		return nil, e
	}
	if e = validateOnDemandShape(s); e != nil {
		return nil, e
	}
	if (s.Schema == DynamicDomain) != (p.Kind == DynamicKind) || (s.Schema == DynamicDomain && source != nil) || s.Origin.Kind != p.Kind || !pin(s.Origin.Capsule) || s.Checkpoint.ChainID != 4663 || s.Pool != p.Pool ||
		s.Release != hashValue(Domain+"/release", json.RawMessage(p.Manifest)) ||
		!pin(s.Engine.Source) || !pin(s.Engine.Binary) || !pin(s.Engine.Policy) || s.Limits != policy {
		return nil, errors.New("PROFILE_IDENTITY")
	}
	var parent types.Header
	if e = json.Unmarshal(s.Parent, &parent); e != nil {
		return nil, e
	}
	if parent.Number == nil || !parent.Number.IsUint64() || parent.Number.Uint64() != s.Checkpoint.BlockNumber ||
		parent.Hash() != s.Checkpoint.BlockHash || parent.Root != s.Checkpoint.StateRoot || parent.Time == ^uint64(0) || parent.Number.Uint64() == ^uint64(0) {
		return nil, errors.New("CHECKPOINT_HEADER")
	}
	var extra map[string]json.RawMessage
	json.Unmarshal(s.Parent, &extra)
	if v := extra["hash"]; v != nil {
		var supplied common.Hash
		if json.Unmarshal(v, &supplied) != nil || supplied != parent.Hash() {
			return nil, errors.New("PARENT_HASH_METADATA")
		}
	}
	for _, k := range []string{"withdrawalsRoot", "blobGasUsed", "excessBlobGas", "parentBeaconBlockRoot", "requestsHash", "blockAccessListHash", "slotNumber"} {
		if v := extra[k]; v != nil && !bytes.Equal(v, []byte("null")) {
			return nil, errors.New("UNSUPPORTED_HEADER_EXTENSION")
		}
	}
	env := s.Environment
	hi := types.DeserializeHeaderExtraInformation(&parent)
	if v := extra["l1BlockNumber"]; v != nil {
		var supplied hexutil.Uint64
		if json.Unmarshal(v, &supplied) != nil || uint64(supplied) != hi.L1BlockNumber {
			return nil, errors.New("PARENT_L1_METADATA")
		}
	}
	if env.Time > (1<<53)-301 || env.Number >= 1<<53 || env.L1Number >= 1<<53 || env.Delayed >= 1<<53 || hi.ArbOSFormatVersion != 61 || env.Number != s.Checkpoint.BlockNumber+1 || env.Time != parent.Time+1 || env.L1Number != hi.L1BlockNumber ||
		env.Poster != parent.Coinbase || env.Delayed != binary.BigEndian.Uint64(parent.Nonce[:]) || env.L1BaseFee != "1000000000" {
		return nil, errors.New("SCENARIO_ENVIRONMENT")
	}
	if _, e = prestate.ValidateConfig(s.ChainConfig, 61); e != nil {
		return nil, e
	}
	if s.Setup.Actor == (common.Address{}) || !s.Setup.RequireAbsent || s.Setup.Nonce != 0 || s.Setup.Funding != "1000000000000000000" {
		return nil, errors.New("COMMON_SETUP")
	}
	if s.Schema == DynamicDomain {
		if e = validateDynamic(s, p); e != nil {
			return nil, e
		}
	} else {
		if len(s.Configs.Baseline) != 4 || len(s.Configs.Variant) != 4 {
			return nil, errors.New("CONFIG_WORD_COUNT")
		}
		for i, w := range s.Configs.Baseline {
			if len(p.BaselineWords) != 4 || w != p.BaselineWords[i] {
				return nil, errors.New("FIRST_PROFILE_CONFIG_REQUIRED")
			}
		}
		for i := 1; i < 4; i++ {
			if s.Configs.Baseline[i] != s.Configs.Variant[i] {
				return nil, errors.New("UNRELATED_CONFIG_WORD")
			}
		}
		old, next := s.Configs.Baseline[0].Big(), s.Configs.Variant[0].Big()
		xor := new(big.Int).Xor(old, next)
		if new(big.Int).AndNot(xor, lpMask).Sign() != 0 || new(big.Int).And(new(big.Int).Rsh(old, 160), big.NewInt(65535)).Uint64() != 100 {
			return nil, errors.New("LP_ONLY_INTERVENTION")
		}
		newLP := new(big.Int).And(new(big.Int).Rsh(next, 160), big.NewInt(65535)).Uint64()
		if newLP > 99 {
			return nil, errors.New("LP_PROFILE_RANGE")
		}
	}
	// Equal-config control is deliberate and remains a scenario, not a qualified Claim.
	if len(s.Actions) < 1 || len(s.Actions) > 2 {
		return nil, errors.New("ACTION_COUNT")
	}
	var spend big.Int
	for i, a := range s.Actions {
		// Retained 5m actions remain verifiable; new buys fund the lane with 10m.
		if a.ID != ActionID(a) || a.Nonce != uint64(i) || (a.Gas != 5000000 && a.Gas != 10000000) || a.Amount != "1000000000000000" || a.Minimum != "1" || a.PriceLimit != "4295128740" || a.Deadline != env.Time+300 {
			return nil, errors.New("ACTION_CONTRACT")
		}
		price, e := decimal(a.GasPrice)
		if e != nil || price.Sign() <= 0 || parent.BaseFee == nil || price.Cmp(new(big.Int).Mul(parent.BaseFee, big.NewInt(2))) < 0 {
			return nil, errors.New("GAS_PRICE")
		}
		spend.Add(&spend, new(big.Int).Add(new(big.Int).Mul(price, new(big.Int).SetUint64(a.Gas)), big.NewInt(1000000000000000)))
		expected, e := resolve(p, s.Setup.Actor, a)
		if e != nil {
			return nil, e
		}
		var tx types.Transaction
		if e = tx.UnmarshalBinary(a.Raw); e != nil {
			return nil, e
		}
		back, _ := tx.MarshalBinary()
		sender, e := types.Sender(types.LatestSignerForChainID(big.NewInt(4663)), &tx)
		if e != nil || sender != s.Setup.Actor || tx.Type() != types.LegacyTxType || tx.Nonce() != a.Nonce || tx.Gas() != a.Gas || tx.GasPrice().Cmp(price) != 0 ||
			tx.ChainId().Cmp(big.NewInt(4663)) != 0 || tx.To() == nil || *tx.To() != routerAddress || tx.Value().Cmp(big.NewInt(1000000000000000)) != 0 || !bytes.Equal(tx.Data(), expected) || !bytes.Equal(back, a.Raw) {
			return nil, errors.New("ACTION_TRANSACTION_MAPPING")
		}
	}
	funding, _ := decimal(s.Setup.Funding)
	if spend.Cmp(funding) > 0 {
		return nil, errors.New("INSUFFICIENT_DECLARED_FUNDING")
	}
	x := &admitted{spec: s, parent: &parent, configRaw: append([]byte(nil), s.ChainConfig...), profile: p, nodes: map[common.Hash]hexutil.Bytes{}, codes: map[common.Hash]hexutil.Bytes{}, discovery: source}
	x.world = "ADMISSION"
	x.phase = "INITIAL_AUTHENTICATION"
	var size int
	for i, rows := range [][]hexutil.Bytes{s.Inventory.Nodes, s.Inventory.Codes} {
		last := ""
		target := x.nodes
		if i == 1 {
			target = x.codes
		}
		for _, b := range rows {
			size += len(b)
			h := crypto.Keccak256Hash(b)
			if len(b) == 0 || len(b) > 98304 || size > 32<<20 || h.Hex() <= last {
				return nil, errors.New("INVENTORY_ORDER_OR_LIMIT")
			}
			last = h.Hex()
			target[h] = append([]byte(nil), b...)
		}
	}
	if _, ok := x.nodes[parent.Root]; !ok {
		return nil, errors.New("CHECKPOINT_ROOT_PREIMAGE_REQUIRED")
	}
	b, e := openBridge(x)
	if e != nil {
		return nil, e
	}
	defer func() {
		if e := prestate.CloseScenarioBridge(b); e != nil {
			accepted = nil
			err = errors.Join(err, e)
		}
	}()
	// Nitro's internal start-block overwrites this original-root history slot.
	// Authenticate its old path here, before any producer entry; a missing leaf
	// must never be inferred as zero or deferred until EVM execution.
	historySlot := common.BigToHash(new(big.Int).SetUint64(s.Checkpoint.BlockNumber % 393168))
	e = b.Protect(func() error {
		state, err := b.State()
		if err != nil {
			return err
		}
		if state.GetCodeHash(params.HistoryStorageAddress) != crypto.Keccak256Hash(params.HistoryStorageCodeArbitrum) || !bytes.Equal(state.GetCode(params.HistoryStorageAddress), params.HistoryStorageCodeArbitrum) {
			return errors.New("UNSUPPORTED_HISTORY_STORAGE_RUNTIME")
		}
		state.GetState(params.HistoryStorageAddress, historySlot)
		return state.Error()
	})
	if e != nil {
		return nil, fmt.Errorf("HISTORY_STORAGE_PRECONDITION address=%s slot=%s: %w", params.HistoryStorageAddress.Hex(), historySlot.Hex(), e)
	}
	for _, action := range s.Actions {
		var tx types.Transaction
		if e = tx.UnmarshalBinary(action.Raw); e != nil {
			return nil, e
		}
		key := transactionFilterSlot(tx.Hash())
		e = b.Protect(func() error {
			st, err := b.State()
			if err != nil {
				return err
			}
			st.GetState(types.FilteredTransactionsStateAddress, key)
			return st.Error()
		})
		if e != nil {
			return nil, fmt.Errorf("TRANSACTION_FILTER_PRECONDITION address=%s slot=%s: %w", types.FilteredTransactionsStateAddress.Hex(), key.Hex(), e)
		}
	}
	e = b.Protect(func() error {
		state, e := b.State()
		if e != nil {
			return e
		}
		for address, expected := range p.Pins {
			if !state.Exist(address) || state.GetCodeHash(address) != expected || crypto.Keccak256Hash(state.GetCode(address)) != expected {
				return errors.New("RELEASE_CODE_IDENTITY")
			}
		}
		if !state.Exist(p.PoolKey.Currency1) || len(state.GetCode(p.PoolKey.Currency1)) == 0 {
			return errors.New("TOKEN_CODE_REQUIRED")
		}
		if state.Exist(s.Setup.Actor) {
			return errors.New("ACTOR_ORIGINAL_ABSENCE_REQUIRED")
		}
		rootWord := state.GetState(p.PoolKey.Hooks, p.RootSlot).Big()
		if s.Schema == DynamicDomain && common.BigToHash(rootWord) != dynamicRootOn {
			return errors.New("DYNAMIC_ORIGINAL_ROOT_WORD")
		}
		if common.BigToAddress(rootWord) != rulesAddress || new(big.Int).And(new(big.Int).Rsh(rootWord, 232), big.NewInt(255)).Uint64() != 1 {
			return errors.New("STANDARD_POOL_BINDING")
		}
		baseFee := new(big.Int).And(new(big.Int).Rsh(rootWord, 160), big.NewInt(0xffffff)).Uint64()
		if baseFee != p.BaseLpFee || state.GetState(p.PoolKey.Hooks, wordAt(p.RootSlot, 1)) != p.RootCaps {
			return errors.New("FIRST_PROFILE_POOL_CAPS")
		}
		for i, w := range s.Configs.Baseline {
			if state.GetState(rulesAddress, wordAt(p.ConfigSlot, i)) != w {
				return errors.New("AUTHENTICATED_BASELINE_WORD")
			}
		}
		arb, e := arbosState.OpenSystemArbosState(state, nil, true)
		if e != nil {
			return e
		}
		cfg, e := arb.ChainConfig()
		if e != nil {
			return e
		}
		if !bytes.Equal(cfg, x.configRaw) || arb.ArbOSVersion() != 61 {
			return errors.New("AUTHENTICATED_ARBOS_CONFIG")
		}
		perTx, err := arb.L2PricingState().PerTxGasLimit()
		if err != nil {
			return err
		}
		perBlock, err := arb.L2PricingState().PerBlockGasLimit()
		if err != nil {
			return err
		}
		if err = validateGasCapacity(s.Actions, parent.GasLimit, perTx, perBlock); err != nil {
			return err
		}
		return state.Error()
	})
	if e != nil {
		return nil, e
	}
	return &Admission{x}, nil
}

func validateGasCapacity(actions []Action, header, perTx, perBlock uint64) error {
	for _, action := range actions {
		if action.Gas == 0 || action.Gas > perTx || action.Gas > perBlock || action.Gas > header {
			return fmt.Errorf("ACTION_CHAIN_GAS_CAPACITY gas=%d perTx=%d perBlock=%d header=%d", action.Gas, perTx, perBlock, header)
		}
	}
	return nil
}

func openBridge(x *admitted) (*prestate.Bridge, error) {
	var source prestate.Source
	requests := 1
	if x.discovery != nil {
		source = x.discovery.bind(x.world, func() string { return x.phase })
		requests = 128
	}
	b, e := prestate.NewBridge(x.spec.Checkpoint, prestate.Budget{MaxRequests: requests, MaxBytes: 32 << 20, MaxResponseBytes: 8 << 20, ExpiresAt: time.Now().Add(120 * time.Second), PerRequest: 3 * time.Second}, source)
	if e != nil {
		return nil, e
	}
	if e = b.LoadWitness(x.spec.Checkpoint, x.nodes, x.codes); e != nil {
		return nil, errors.Join(e, prestate.CloseScenarioBridge(b))
	}
	if x.discovery != nil {
		prestate.ObserveScenarioBridge(b, func(row prestate.ScenarioAccess) { x.discovery.record(x.world, x.phase, row) })
	}
	return b, nil
}

func transactionFilterSlot(txHash common.Hash) common.Hash {
	key := crypto.Keccak256Hash(txHash[:31])
	key[31] = txHash[31]
	return key
}

func resolve(p profile, actor common.Address, a Action) ([]byte, error) {
	ab, e := abi.JSON(strings.NewReader(string(p.SwapABI)))
	if e != nil {
		return nil, e
	}
	amount, e := decimal(a.Amount)
	if e != nil {
		return nil, e
	}
	minimum, e := decimal(a.Minimum)
	if e != nil {
		return nil, e
	}
	price, e := decimal(a.PriceLimit)
	if e != nil {
		return nil, e
	}
	type key struct {
		Currency0, Currency1 common.Address
		Fee, TickSpacing     *big.Int
		Hooks                common.Address
	}
	params := struct {
		Key                                             key
		ZeroForOne                                      bool
		AmountSpecified, AmountBound, SqrtPriceLimitX96 *big.Int
		Recipient                                       common.Address
		Deadline                                        *big.Int
	}{
		key{p.PoolKey.Currency0, p.PoolKey.Currency1, new(big.Int).SetUint64(p.PoolKey.Fee), big.NewInt(p.PoolKey.TickSpacing), p.PoolKey.Hooks},
		true, new(big.Int).Neg(amount), minimum, price, actor, new(big.Int).SetUint64(a.Deadline)}
	return ab.Pack("swap", params, common.Address{}, []*big.Int{})
}
