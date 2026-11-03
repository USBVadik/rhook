package scenario

// G4A: the descriptor-driven linked profile nitro-hook-profile-overlay/0.1.
//
// A profile-overlay input (rhook/hookr-profile-overlay/0.1) is admitted by the unchanged SDK 0.4 admission
// (admitWithSource) with a profile derived from an accepted descriptor, plus the descriptor's own
// authentication of every code-pinned contract and target word. The worker keeps fixed protections for what
// the 0.1 schema does not express as data: chain 4663 and ArbOS 61, the Hookr buy action and its ABI, the
// public simulation actor and funding, the Hookr Rules/Root shape. A descriptor outside them is refused
// (PROFILE_WORKER_BOUNDS) before any input is read. Native execution additionally needs a catalogue review
// that admits NATIVE_EXECUTION; the embedded hookr-1 review does not.
import (
	"errors"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	prestate "local/rhook-robinhood"
)

const ProfileKind = ProfileOriginKind

// The compiled bounds of this worker; identical to the legacy profile constants and admission literals.
const (
	boundChainID     = 4663
	boundArbOS       = 61
	boundSeed        = "RHOOK BUILD04 PUBLIC SIMULATION SIGNER; NEVER FUND OR BROADCAST"
	boundFunding     = "1000000000000000000"
	boundAmount      = "1000000000000000"
	boundMinimum     = "1"
	boundPriceLimit  = "4295128740"
	boundActionType  = "HOOKR_ROUTER_EXACT_INPUT_BUY_V1"
	boundSystemReads = "NITRO_ARBOS61_SCENARIO_SYSTEM_V1"
	// SHA-256 of the chain configuration bytes the SDK 0.4 runs admitted (authenticated against ArbOS state).
	boundChainConfig  = "dfa6de28a2dcf9fa3079d97c73401af7c7df0bc7222a6a3fe1e927d98104ffe0"
	purposeOffline    = "OFFLINE_PREPARATION"
	purposeNative     = "NATIVE_EXECUTION"
	errWorkerBounds   = "PROFILE_WORKER_BOUNDS"
	errOperationBound = "PROFILE_OPERATION_BINDING"
)

// validateProfileWorkerBounds refuses a descriptor that needs anything this compiled worker does not implement.
func validateProfileWorkerBounds(d *Descriptor) error {
	c := d.Chain
	if c.ChainID != boundChainID || c.ArbosVersion != boundArbOS || c.EngineFamily != "NITRO" || c.ChainConfigSha256 != boundChainConfig ||
		d.Witness.SystemSubjects != boundSystemReads {
		return dfail(errWorkerBounds)
	}
	for _, name := range []string{"poolManager", "root", "router", "rules"} {
		k := d.contracts[name]
		if k == nil || k.Requirement != "CODE_HASH_EQUALS" || k.ReleaseRole == nil || *k.ReleaseRole != name {
			return dfail(errWorkerBounds)
		}
	}
	token := 0
	for _, k := range d.Contracts {
		if k.Requirement == "CODE_PRESENT" {
			token++
			if k.Address != d.Pool.Currency1 {
				return dfail(errWorkerBounds)
			}
		}
	}
	if token != 1 || d.Pool.HooksContract != "root" || d.Pool.Currency0 != (common.Address{}) {
		return dfail(errWorkerBounds)
	}
	rules, root := d.targets["rulesConfig"], d.targets["rootRecord"]
	if len(d.Targets) != 2 || rules == nil || root == nil || rules.Contract != "rules" || rules.Words != 4 || root.Contract != "root" || root.Words != 2 ||
		d.ConfigurationTarget != "rulesConfig" || d.OriginalState.Policy != "EXACT_WORDS" {
		return dfail(errWorkerBounds)
	}
	// The whole Root word 0 layout: Rules address, base LP fee, bit 248 Dynamic Fee, bit 249 recapture, reserved.
	for name, want := range map[string][3]uint64{"rootRulesAddress": {0, 0, 160}, "rootBaseLpFeePips": {0, 160, 24},
		"rootDynamicFeeFlag": {0, 248, 1}, "rootRecaptureFlag": {0, 249, 1}, "rootFlagsReserved": {0, 250, 6}} {
		f := d.fields[name]
		if f == nil || f.Target != "rootRecord" || f.Word != want[0] || f.Offset != want[1] || f.Width != want[2] {
			return dfail(errWorkerBounds)
		}
	}
	// Every SDK 0.4 compiled precondition stays a compiled precondition: release manifest, pool and key, target
	// slots, code pins, Rules/Router, the authenticated original words and the original Root word. The descriptor
	// may add intervention kinds as data; it may not move what SDK 0.4 admission compared against constants.
	got, want := d.legacyProfile(), overlayProfile()
	if !canonicalEqual(got.Manifest, want.Manifest) || got.Pool != want.Pool || got.PoolKey != want.PoolKey ||
		got.RootSlot != want.RootSlot || got.ConfigSlot != want.ConfigSlot || got.RootCaps != want.RootCaps || got.BaseLpFee != want.BaseLpFee ||
		!canonicalEqual(got.BaselineWords, want.BaselineWords) || got.Rules != want.Rules || got.Router != want.Router || len(got.Pins) != len(want.Pins) ||
		d.exactWord("rootRecord", 0) != dynamicRootOn {
		return dfail(errWorkerBounds)
	}
	for k, v := range want.Pins {
		if got.Pins[k] != v {
			return dfail(errWorkerBounds)
		}
	}
	a := d.Action
	if a.Type != boundActionType || a.Router != "router" || a.Function != "swap" || a.AmountInWei != boundAmount || a.MinimumOutputBaseUnits != boundMinimum ||
		a.SqrtPriceLimitX96 != boundPriceLimit || !a.ZeroForOne || a.Engagement != (common.Address{}) || len(a.Campaigns) != 0 || a.TransactionType != "LEGACY" ||
		a.Count != 1 || len(a.Gas) != 2 || a.Gas[0] != 5000000 || a.Gas[1] != 10000000 || !canonicalEqual(a.Abi, officialProfile().SwapABI) {
		return dfail(errWorkerBounds)
	}
	s := d.Setup
	if s.Actor.Kind != "PUBLIC_SIMULATION_SIGNER_V1" || s.Actor.Seed != boundSeed || s.FundingWei != boundFunding || s.Nonce != 0 || !s.RequireOriginalAbsence {
		return dfail(errWorkerBounds)
	}
	return nil
}

// profileFromDescriptor derives the admission profile of a descriptor inside the worker bounds.
func profileFromDescriptor(d *Descriptor) (profile, error) {
	if e := validateProfileWorkerBounds(d); e != nil {
		return profile{}, e
	}
	p := d.legacyProfile()
	p.Kind = ProfileKind
	p.descriptor = d
	return p, nil
}

type descriptorLoader func(profileID, purpose string) (*Descriptor, error)

// profileForInput loads the descriptor the input names, under the purpose, and binds its SHA-256.
func profileForInput(raw []byte, purpose string, load descriptorLoader) (profile, error) {
	s, e := Parse(raw)
	if e != nil {
		return profile{}, e
	}
	if s.Schema != ProfileDomain || s.ProfileOverlay == nil {
		return profile{}, errors.New("SCENARIO_RUNTIME_DOMAIN")
	}
	d, e := load(s.ProfileOverlay.Descriptor.ProfileID, purpose)
	if e != nil {
		return profile{}, e
	}
	if d.Sha256() != s.ProfileOverlay.Descriptor.Sha256 {
		return profile{}, dfail("PROFILE_SPEC_BINDING")
	}
	// Each selected kind must itself be reviewed for the purpose, not only the descriptor.
	for _, item := range s.ProfileOverlay.Interventions {
		if !kindReviewAdmits(d.reviewKinds[item.Kind], purpose) {
			return profile{}, dfail("PROFILE_KIND_REVIEW_INSUFFICIENT")
		}
	}
	return profileFromDescriptor(d)
}

// AdmitProfile admits a profile-overlay input for a purpose under the embedded catalogue.
func AdmitProfile(raw []byte, purpose string) (*Admission, error) {
	return admitProfileWith(raw, purpose, LoadAcceptedDescriptor)
}

func admitProfileWith(raw []byte, purpose string, load descriptorLoader) (*Admission, error) {
	p, e := profileForInput(raw, purpose, load)
	if e != nil {
		return nil, e
	}
	a, e := admit(raw, p)
	if e != nil {
		return nil, e
	}
	a.input.purpose = purpose
	return a, nil
}

// deriveProfileOverlay reconstructs one world's initial state (common setup plus descriptor writes) on the
// witness-backed StateDB and reads every target word back. It never invokes Nitro's producer.
func deriveProfileOverlay(x *admitted, label string) (out Overlay, fields map[string]*big.Int, err error) {
	if x.spec.Schema != ProfileDomain || x.discovery != nil || x.profile.descriptor == nil {
		return out, nil, errors.New("PROFILE_OVERLAY_OFFLINE_REQUIRED")
	}
	d := x.profile.descriptor
	b, e := openBridge(x)
	if e != nil {
		return out, nil, e
	}
	defer func() { err = errors.Join(err, prestate.CloseScenarioBridge(b)) }()
	err = b.Protect(func() error {
		st, overlay, _, e := initializeWorld(b, x, label)
		if e != nil {
			return e
		}
		out = overlay
		words := Originals{}
		for _, t := range d.Targets {
			for i := uint64(0); i < t.Words; i++ {
				words[t.Name] = append(words[t.Name], st.GetState(d.contracts[t.Contract].Address, wordAt(t.Slot, int(i))).Big())
			}
		}
		fields = d.decodeAll(words)
		return st.Error()
	})
	return
}

// profileStateReport is the offline --profile-state command: admission for OFFLINE_PREPARATION, then the
// derived BASELINE and VARIANT overlays with all descriptor fields read back. No producer, no EVM.
func profileStateReport(raw []byte) (map[string]any, error) {
	if LinkedProfile != ProfileRuntimeProfile {
		return nil, errors.New("PROFILE_RUNTIME_REQUIRED")
	}
	return profileStateReportWith(raw, LoadAcceptedDescriptor)
}

func profileStateReportWith(raw []byte, load descriptorLoader) (map[string]any, error) {
	a, e := admitProfileWith(raw, purposeOffline, load)
	if e != nil {
		return nil, e
	}
	base, baseFields, e := deriveProfileOverlay(a.input, Baseline)
	if e != nil {
		return nil, e
	}
	variant, variantFields, e := deriveProfileOverlay(a.input, Variant)
	if e != nil {
		return nil, e
	}
	o := a.input.spec.ProfileOverlay
	return map[string]any{"status": "PROFILE_OVERLAY_STATE_AUTHENTICATED", "profile": ProfileRuntimeProfile, "scenarioCommitment": a.input.spec.Commitment,
		"descriptor": o.Descriptor, "interventionCommitment": o.Commitment, "interventions": o.Interventions, "baseline": base, "variant": variant,
		"fields": map[string]any{"baseline": baseFields, "variant": variantFields}, "nativeExecutions": 0, "EVMReexecution": false,
		"coverage": "TARGET_TRANSFORM_ONLY_NOT_EXECUTION_CLOSURE"}, nil
}

// profileOperationBinding: the one-shot operation of a profile worker must name the exact descriptor of its
// input. Other linked profiles must not carry a descriptor binding.
func profileOperationBinding(linked string, raw []byte, b map[string]any) error {
	ref, present := b["profileDescriptor"]
	if linked != ProfileRuntimeProfile {
		if present {
			return dfail(errOperationBound)
		}
		return nil
	}
	s, e := Parse(raw)
	if e != nil {
		return e
	}
	if !present || s.Schema != ProfileDomain || s.ProfileOverlay == nil || !canonicalEqual(ref, s.ProfileOverlay.Descriptor) {
		return dfail(errOperationBound)
	}
	return nil
}

func profileStorageWrites(rows []ProfileWrite) []StorageWrite {
	out := make([]StorageWrite, 0, len(rows))
	for _, w := range rows {
		out = append(out, StorageWrite{Address: w.Address, Slot: w.Slot, Before: w.Before, After: w.After})
	}
	return out
}
