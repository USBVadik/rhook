package scenario

// Parameterized Config Overlay Engine (SDK 0.4).
//
// A fixed, source-defined registry of typed interventions is composed into masked
// writes on the authenticated original Rules config word and Root record. The
// engine never accepts arbitrary storage writes: every target, field, mask, value
// range and original-state precondition is part of this reviewed source. The
// prepared input carries the canonical intervention set and the derived writes;
// the worker recomputes the writes and accepts the input only when they match.
import (
	"errors"
	"math/big"
	"sort"

	"github.com/ethereum/go-ethereum/common"
	prestate "local/rhook-robinhood"
)

const OverlayDomain = "rhook/hookr-config-overlay/0.1"
const OverlayKind = "AUTHENTICATED_CHECKPOINT_CONFIG_OVERLAY"
const OverlayRuntimeProfile = "nitro-hookr-config-overlay/0.1"
const InterventionDynamicFee = "DYNAMIC_FEE"
const InterventionLpRewards = "LP_REWARDS_BPS"

// TypedIntervention is one descriptor. Exactly the parameter of its kind is set.
type TypedIntervention struct {
	Kind       string  `json:"kind"`
	LpBps      *uint64 `json:"lpBps,omitempty"`
	DynamicFee string  `json:"dynamicFee,omitempty"`
}
type ConfigOverlay struct {
	Schema        string              `json:"schema"`
	OriginalRoot  common.Hash         `json:"originalStateRoot"`
	Pool          common.Hash         `json:"poolId"`
	RootCode      common.Hash         `json:"rootCodeHash"`
	RulesCode     common.Hash         `json:"rulesCodeHash"`
	Plan          string              `json:"planCommitment"`
	Interventions []TypedIntervention `json:"interventions"`
	Writes        []StorageWrite      `json:"writes"`
	Commitment    string              `json:"interventionCommitment,omitempty"`
}

const (
	targetRules = 0
	targetRoot  = 1
)

type overlayField struct {
	Name   string
	Target int
	Shift  uint
	Width  uint
}

func (f overlayField) ones() *big.Int {
	return new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), f.Width), big.NewInt(1))
}
func (f overlayField) mask() *big.Int { return new(big.Int).Lsh(f.ones(), f.Shift) }
func (f overlayField) get(w *big.Int) uint64 {
	return new(big.Int).And(new(big.Int).Rsh(w, f.Shift), f.ones()).Uint64()
}

// Field layout of the pinned Hookr generation (profile.json configSlot / rootRecordSlot).
var (
	fieldMaxFee      = overlayField{"maxFeePips", targetRules, 40, 24}
	fieldSensitivity = overlayField{"sensitivity", targetRules, 128, 16}
	fieldLpBps       = overlayField{"lpBps", targetRules, 160, 16}
	fieldMode        = overlayField{"mode", targetRoot, 248, 8}
)

type assignment struct {
	Field    overlayField
	Original func(uint64) bool
	Value    uint64
}
type interventionRule func(TypedIntervention, profile) ([]assignment, error)

var overlayRegistry = map[string]interventionRule{
	InterventionLpRewards: func(t TypedIntervention, p profile) ([]assignment, error) {
		if t.LpBps == nil || t.DynamicFee != "" || *t.LpBps > 99 {
			return nil, errors.New("CONFIG_OVERLAY_LP_PARAMETER")
		}
		return []assignment{{fieldLpBps, func(v uint64) bool { return v == 100 }, *t.LpBps}}, nil
	},
	InterventionDynamicFee: func(t TypedIntervention, p profile) ([]assignment, error) {
		if t.LpBps != nil || t.DynamicFee != "OFF" {
			return nil, errors.New("CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER")
		}
		base := p.BaseLpFee
		return []assignment{
			{fieldMaxFee, func(v uint64) bool { return v > base }, base},
			{fieldSensitivity, func(v uint64) bool { return v > 0 }, 0},
			{fieldMode, func(v uint64) bool { return v == 3 }, 2},
		}, nil
	},
}

type composedOverlay struct {
	Rules, Root common.Hash
	Writes      []StorageWrite
}

// canonicalInterventions returns the set sorted by kind; duplicates are a conflict.
func canonicalInterventions(items []TypedIntervention) ([]TypedIntervention, error) {
	out := append([]TypedIntervention{}, items...)
	sort.SliceStable(out, func(i, j int) bool { return out[i].Kind < out[j].Kind })
	for i := 1; i < len(out); i++ {
		if out[i].Kind == out[i-1].Kind {
			return nil, errors.New("CONFIG_OVERLAY_DUPLICATE_KIND")
		}
	}
	return out, nil
}

// composeOverlay applies the typed interventions to the original words. The result
// does not depend on the order of compatible descriptors: their masks are disjoint
// and each assignment only replaces bits under its own mask.
func composeOverlay(registry map[string]interventionRule, items []TypedIntervention, p profile, rules0, root0 common.Hash) (composedOverlay, error) {
	var out composedOverlay
	if len(items) == 0 || len(items) > len(registry) {
		return out, errors.New("CONFIG_OVERLAY_INTERVENTION_COUNT")
	}
	if _, e := canonicalInterventions(items); e != nil {
		return out, e
	}
	original := [2]*big.Int{rules0.Big(), root0.Big()}
	words := [2]*big.Int{rules0.Big(), root0.Big()}
	used := [2]*big.Int{new(big.Int), new(big.Int)}
	var applied []assignment
	for _, t := range items {
		rule, ok := registry[t.Kind]
		if !ok {
			return out, errors.New("CONFIG_OVERLAY_UNKNOWN_INTERVENTION")
		}
		rows, e := rule(t, p)
		if e != nil {
			return out, e
		}
		for _, a := range rows {
			if (a.Field.Target != targetRules && a.Field.Target != targetRoot) || a.Field.Width == 0 || a.Field.Shift+a.Field.Width > 256 || a.Original == nil {
				return out, errors.New("CONFIG_OVERLAY_FIELD_LAYOUT")
			}
			m := a.Field.mask()
			if new(big.Int).And(used[a.Field.Target], m).Sign() != 0 {
				return out, errors.New("CONFIG_OVERLAY_MASK_CONFLICT")
			}
			used[a.Field.Target].Or(used[a.Field.Target], m)
			if !a.Original(a.Field.get(original[a.Field.Target])) {
				return out, errors.New("CONFIG_OVERLAY_ORIGINAL_PRECONDITION")
			}
			if new(big.Int).SetUint64(a.Value).Cmp(a.Field.ones()) > 0 {
				return out, errors.New("CONFIG_OVERLAY_VALUE_WIDTH")
			}
			w := words[a.Field.Target]
			w.AndNot(w, m)
			w.Or(w, new(big.Int).Lsh(new(big.Int).SetUint64(a.Value), a.Field.Shift))
			applied = append(applied, a)
		}
	}
	for i := range words {
		if new(big.Int).AndNot(new(big.Int).Xor(words[i], original[i]), used[i]).Sign() != 0 {
			return out, errors.New("CONFIG_OVERLAY_NON_TARGET_BITS")
		}
	}
	for _, a := range applied {
		if a.Field.get(words[a.Field.Target]) != a.Value {
			return out, errors.New("CONFIG_OVERLAY_FIELD_VALUE")
		}
	}
	out.Rules, out.Root = common.BigToHash(words[targetRules]), common.BigToHash(words[targetRoot])
	targets := [2]StorageWrite{{rulesAddress, p.ConfigSlot, rules0, out.Rules}, {p.PoolKey.Hooks, p.RootSlot, root0, out.Root}}
	for i, w := range targets {
		if used[i].Sign() == 0 {
			continue
		}
		if w.After == w.Before {
			return out, errors.New("CONFIG_OVERLAY_NO_EFFECT")
		}
		out.Writes = append(out.Writes, w)
	}
	return out, nil
}

func overlayTransformID(o ConfigOverlay) string {
	o.Commitment = ""
	return hashValue(OverlayDomain+"/transform", o)
}

// overlayIntent names the resulting settings and the exact canonical set.
func overlayIntent(pool common.Hash, items []TypedIntervention) map[string]any {
	lp, dynamic := uint64(100), "ON"
	for _, t := range items {
		if t.Kind == InterventionLpRewards && t.LpBps != nil {
			lp = *t.LpBps
		}
		if t.Kind == InterventionDynamicFee {
			dynamic = t.DynamicFee
		}
	}
	return map[string]any{"schema": OverlayDomain + "/intent", "poolId": pool, "lpBps": lp, "dynamicFee": dynamic, "interventions": items}
}
func overlayCapsule(s Spec) string {
	return hashValue(OverlayDomain+"/checkpoint", map[string]any{"checkpoint": s.Checkpoint, "intent": overlayIntent(s.Pool, s.Overlay.Interventions)})
}
func overlayProfile() profile                     { p := officialProfile(); p.Kind = OverlayKind; return p }
func AdmitOverlay(raw []byte) (*Admission, error) { return admit(raw, overlayProfile()) }

func validateOverlay(s Spec, p profile) (composedOverlay, error) {
	var none composedOverlay
	o := s.Overlay
	if s.Schema != OverlayDomain || s.Intervention != nil || o == nil || o.Schema != OverlayDomain+"/transform" || o.Commitment != overlayTransformID(*o) || !pin(o.Plan) ||
		o.OriginalRoot != s.Checkpoint.StateRoot || o.Pool != p.Pool || s.Pool != p.Pool || o.RootCode != p.Pins[p.PoolKey.Hooks] || o.RulesCode != p.Pins[rulesAddress] ||
		len(p.BaselineWords) != 4 || len(s.Configs.Baseline) != 4 || len(s.Configs.Variant) != 4 {
		return none, errors.New("CONFIG_OVERLAY_BINDING")
	}
	sorted, e := canonicalInterventions(o.Interventions)
	if e != nil {
		return none, e
	}
	a, e1 := Canonical(sorted)
	b, e2 := Canonical(o.Interventions)
	if e1 != nil || e2 != nil || string(a) != string(b) {
		return none, errors.New("CONFIG_OVERLAY_CANONICAL_ORDER")
	}
	if s.Origin.Kind != OverlayKind || s.Origin.Capsule != overlayCapsule(s) {
		return none, errors.New("CONFIG_OVERLAY_ORIGIN")
	}
	for i := range s.Configs.Baseline {
		if s.Configs.Baseline[i] != p.BaselineWords[i] {
			return none, errors.New("CONFIG_OVERLAY_ORIGINAL_CONFIG")
		}
	}
	c, e := composeOverlay(overlayRegistry, o.Interventions, p, p.BaselineWords[0], dynamicRootOn)
	if e != nil {
		return none, e
	}
	if s.Configs.Variant[0] != c.Rules {
		return none, errors.New("CONFIG_OVERLAY_VARIANT_WORD")
	}
	for i := 1; i < 4; i++ {
		if s.Configs.Variant[i] != s.Configs.Baseline[i] {
			return none, errors.New("CONFIG_OVERLAY_UNRELATED_CONFIG")
		}
	}
	if len(o.Writes) != len(c.Writes) {
		return none, errors.New("CONFIG_OVERLAY_DERIVED_WRITES")
	}
	for i := range c.Writes {
		if o.Writes[i] != c.Writes[i] {
			return none, errors.New("CONFIG_OVERLAY_DERIVED_WRITES")
		}
	}
	return c, nil
}

// applyCheckedWrites authenticates every original word before any write, so a
// mismatch on a later target cannot leave a partially applied overlay.
func applyCheckedWrites(st overlayState, writes []StorageWrite, label, code string) ([]StorageWrite, error) {
	rows := append([]StorageWrite{}, writes...)
	for _, w := range rows {
		if st.GetState(w.Address, w.Slot) != w.Before {
			return nil, errors.New(code)
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

// OverlayFields are the decoded target fields of one world, read back from its StateDB.
type OverlayFields struct {
	LpBps       uint64      `json:"lpBps"`
	MaxFeePips  uint64      `json:"maxFeePips"`
	Sensitivity uint64      `json:"sensitivity"`
	Mode        uint64      `json:"rootMode"`
	RulesWord   common.Hash `json:"rulesConfigWord"`
	RootWord    common.Hash `json:"rootRecordWord"`
}

func decodeOverlayFields(rules, root common.Hash) OverlayFields {
	r, o := rules.Big(), root.Big()
	return OverlayFields{fieldLpBps.get(r), fieldMaxFee.get(r), fieldSensitivity.get(r), fieldMode.get(o), rules, root}
}

// deriveWorldOverlay reconstructs one world's initial state (common setup plus
// overlay) on the witness-backed StateDB and reads both targets back. It never
// invokes Nitro's producer.
func deriveWorldOverlay(x *admitted, label string) (out Overlay, fields OverlayFields, err error) {
	if (x.spec.Schema != DynamicDomain && x.spec.Schema != OverlayDomain && x.spec.Schema != ProfileDomain) || x.discovery != nil {
		return out, fields, errors.New("TYPED_OVERLAY_OFFLINE_REQUIRED")
	}
	b, e := openBridge(x)
	if e != nil {
		return out, fields, e
	}
	defer func() { err = errors.Join(err, prestate.CloseScenarioBridge(b)) }()
	err = b.Protect(func() error {
		st, overlay, _, e := initializeWorld(b, x, label)
		if e != nil {
			return e
		}
		out = overlay
		fields = decodeOverlayFields(st.GetState(x.profile.Rules, x.profile.ConfigSlot), st.GetState(x.profile.PoolKey.Hooks, x.profile.RootSlot))
		return st.Error()
	})
	return
}
func deriveConfigOverlay(x *admitted, label string) (Overlay, OverlayFields, error) {
	if x.spec.Schema != OverlayDomain {
		return Overlay{}, OverlayFields{}, errors.New("CONFIG_OVERLAY_OFFLINE_REQUIRED")
	}
	return deriveWorldOverlay(x, label)
}
