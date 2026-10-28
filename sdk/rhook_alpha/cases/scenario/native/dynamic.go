package scenario

// Explicit versioned Dynamic Fee relation. It does not broaden the LP mask.
import (
	"errors"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/state"
	"github.com/ethereum/go-ethereum/core/tracing"
	"github.com/holiman/uint256"
	prestate "local/rhook-robinhood"
	"math/big"
)

const DynamicDomain = "rhook/hookr-dynamic-fee-off/0.1"
const DynamicKind = "AUTHENTICATED_CHECKPOINT_DYNAMIC_FEE_OFF"
const DynamicRuntimeProfile = "nitro-hookr-dynamic-fee-off/0.1"

// LinkedProfile is fixed when linking a derivative, not caller-configurable.
var LinkedProfile = RuntimeProfile
var dynamicRootOn = common.HexToHash("0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942")
var dynamicRootOff = common.HexToHash("0x020101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942")

type StorageWrite struct {
	Address common.Address `json:"address"`
	Slot    common.Hash    `json:"slot"`
	Before  common.Hash    `json:"before"`
	After   common.Hash    `json:"after"`
}
type DynamicFeeOff struct {
	Schema       string         `json:"schema"`
	OriginalRoot common.Hash    `json:"originalStateRoot"`
	Pool         common.Hash    `json:"poolId"`
	RootCode     common.Hash    `json:"rootCodeHash"`
	RulesCode    common.Hash    `json:"rulesCodeHash"`
	Plan         string         `json:"planCommitment"`
	Writes       []StorageWrite `json:"writes"`
	Commitment   string         `json:"interventionCommitment,omitempty"`
}

func dynamicTransformID(d DynamicFeeOff) string {
	d.Commitment = ""
	return hashValue(DynamicDomain+"/transform", d)
}
func dynamicConfigOff(old common.Hash, base uint64) common.Hash {
	mask := new(big.Int).Or(new(big.Int).Lsh(big.NewInt(0xffffff), 40), new(big.Int).Lsh(big.NewInt(65535), 128))
	n := new(big.Int).AndNot(old.Big(), mask)
	n.Or(n, new(big.Int).Lsh(new(big.Int).SetUint64(base), 40))
	return common.BigToHash(n)
}
func dynamicCapsule(s Spec) string {
	return hashValue(DynamicDomain+"/checkpoint", map[string]any{"checkpoint": s.Checkpoint, "intent": map[string]any{"schema": DynamicDomain + "/intent", "poolId": s.Pool, "dynamicFee": "OFF", "lpBps": 100}})
}

func validateDynamic(s Spec, p profile) error {
	d := s.Intervention
	if s.Origin.Kind != DynamicKind || s.Origin.Capsule != dynamicCapsule(s) || s.Schema != DynamicDomain || d == nil || d.Schema != DynamicDomain+"/transform" || d.Commitment != dynamicTransformID(*d) || !pin(d.Plan) || d.OriginalRoot != s.Checkpoint.StateRoot || d.Pool != p.Pool || d.RootCode != p.Pins[p.PoolKey.Hooks] || d.RulesCode != p.Pins[rulesAddress] || len(d.Writes) != 2 || len(s.Configs.Baseline) != 4 || len(s.Configs.Variant) != 4 {
		return errors.New("DYNAMIC_INTERVENTION_BINDING")
	}
	for i := range s.Configs.Baseline {
		if s.Configs.Baseline[i] != p.BaselineWords[i] {
			return errors.New("DYNAMIC_ORIGINAL_CONFIG")
		}
	}
	want := dynamicConfigOff(p.BaselineWords[0], p.BaseLpFee)
	if s.Configs.Variant[0] != want {
		return errors.New("DYNAMIC_CONFIG_OFF_ONLY")
	}
	for i := 1; i < 4; i++ {
		if s.Configs.Variant[i] != s.Configs.Baseline[i] {
			return errors.New("DYNAMIC_UNRELATED_CONFIG")
		}
	}
	expected := []StorageWrite{{rulesAddress, p.ConfigSlot, p.BaselineWords[0], want}, {p.PoolKey.Hooks, p.RootSlot, dynamicRootOn, dynamicRootOff}}
	for i, w := range expected {
		if d.Writes[i] != w {
			return errors.New("DYNAMIC_EXACT_TWO_WRITES_REQUIRED")
		}
	}
	return nil
}
func validateRuntimeSpec(s Spec, runtime string) error {
	if (runtime == RuntimeProfile && s.Schema == Domain && s.Intervention == nil) || (runtime == DynamicRuntimeProfile && s.Schema == DynamicDomain && s.Intervention != nil) {
		return nil
	}
	return errors.New("SCENARIO_RUNTIME_DOMAIN")
}
func dynamicProfile() profile                     { p := officialProfile(); p.Kind = DynamicKind; return p }
func AdmitDynamic(raw []byte) (*Admission, error) { return admit(raw, dynamicProfile()) }
func admitRuntime(raw []byte) (*Admission, error) {
	s, e := Parse(raw)
	if e != nil {
		return nil, e
	}
	if e = validateRuntimeSpec(s, LinkedProfile); e != nil {
		return nil, e
	}
	if LinkedProfile == DynamicRuntimeProfile {
		return AdmitDynamic(raw)
	}
	return Admit(raw)
}

type overlayState interface {
	GetState(common.Address, common.Hash) common.Hash
	SetState(common.Address, common.Hash, common.Hash) common.Hash
}

func configurationOverlay(st overlayState, s Spec, p profile, label string) ([]StorageWrite, error) {
	if label != Baseline && label != Variant {
		return nil, errors.New("SCENARIO_WORLD_REQUIRED")
	}
	if s.Schema == DynamicDomain {
		if e := validateDynamic(s, p); e != nil {
			return nil, e
		}
		rows := append([]StorageWrite{}, s.Intervention.Writes...)
		// Authenticate the complete pair before any write. A second-field mismatch
		// cannot leave a partially applied first write.
		for _, w := range rows {
			if st.GetState(w.Address, w.Slot) != w.Before {
				return nil, errors.New("DYNAMIC_ORIGINAL_WORD_CHANGED")
			}
		}
		for i, w := range rows {
			if label == Variant {
				st.SetState(w.Address, w.Slot, w.After)
			} else {
				rows[i].After = w.Before
			}
		}
		return rows, nil
	}
	if s.Schema != Domain || s.Intervention != nil {
		return nil, errors.New("SCENARIO_RUNTIME_DOMAIN")
	}
	if st.GetState(rulesAddress, p.ConfigSlot) != s.Configs.Baseline[0] {
		return nil, errors.New("ORIGINAL_CONFIG_CHANGED")
	}
	if label == Variant {
		st.SetState(rulesAddress, p.ConfigSlot, s.Configs.Variant[0])
	}
	return nil, nil
}
func initializeWorld(b *prestate.Bridge, x *admitted, label string) (*state.StateDB, Overlay, *big.Int, error) {
	var out Overlay
	x.phase = "COMMON_SETUP"
	st, e := b.State()
	if e != nil {
		return nil, out, nil, e
	}
	actor := x.spec.Setup.Actor
	if st.Exist(actor) {
		return nil, out, nil, errors.New("ACTOR_ORIGINAL_ABSENCE_REQUIRED")
	}
	funding, e := decimal(x.spec.Setup.Funding)
	if e != nil {
		return nil, out, nil, e
	}
	st.CreateAccount(actor)
	st.SetBalance(actor, uint256.MustFromBig(funding), tracing.BalanceChangeUnspecified)
	st.SetNonce(actor, 0, tracing.NonceChangeUnspecified)
	commonRoot, e := prestate.CommitScenarioSetup(b, x.spec.Checkpoint, funding)
	if e != nil {
		return nil, out, nil, e
	}
	st, e = b.State()
	if e != nil {
		return nil, out, nil, e
	}
	x.phase = "CONFIGURATION_OVERLAY"
	rows, e := configurationOverlay(st, x.spec, x.profile, label)
	if e != nil {
		return nil, out, nil, e
	}
	initial := st.IntermediateRoot(true)
	if e = st.Error(); e != nil {
		return nil, out, nil, e
	}
	words := x.spec.Configs.Baseline
	if label == Variant {
		words = x.spec.Configs.Variant
	}
	out = Overlay{Common: x.spec.Setup, CommonRoot: commonRoot, InitialRoot: initial, Account: rulesAddress, Slot: x.profile.ConfigSlot, Before: x.spec.Configs.Baseline[0], After: words[0], Writes: rows}
	if x.spec.Intervention != nil {
		out.Intervention = x.spec.Intervention.Commitment
	}
	return st, out, funding, nil
}

// Pure StateDB/trie setup reconstruction; never invokes Nitro's producer.
func deriveDynamicOverlay(x *admitted, label string) (out Overlay, err error) {
	if x.spec.Schema != DynamicDomain || x.discovery != nil {
		return out, errors.New("DYNAMIC_OFFLINE_REQUIRED")
	}
	b, e := openBridge(x)
	if e != nil {
		return out, e
	}
	defer func() { err = errors.Join(err, prestate.CloseScenarioBridge(b)) }()
	err = b.Protect(func() error { _, overlay, _, e := initializeWorld(b, x, label); out = overlay; return e })
	return
}
