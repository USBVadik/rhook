package scenario

// Profile Descriptor 0.1 (SDK 0.6, offline).
//
// One interpreter for reviewed hook profiles described as data
// (rhook/hook-profile-descriptor/0.1). The descriptor carries what overlay.go,
// spec.go and profile.json fix in code for SDK 0.4: chain and engine, contract
// identities, pool, storage targets with slot derivations, named bit fields,
// the authenticated original words, typed intervention kinds (parameters,
// original-state predicates, assignments, result invariants, conflicts), the
// action, setup, measures and declared witness reads.
//
// It holds no expressions, scripts, opcodes or code: predicates are a closed
// vocabulary (compare, productBound). A descriptor SHA-256 identifies it; whether
// it may be used is the separate review record in descriptors/CATALOGUE.json.
// Only embedded RHOOK-internal descriptors are loadable. G4A wires it into the
// worker as the linked profile nitro-hook-profile-overlay/0.1 (see profile.go);
// legacy runtimes accept only their own schemas. Mirror: rhook_alpha/profile_descriptor.py.
import (
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"regexp"
	"sort"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
)

const DescriptorSchema = "rhook/hook-profile-descriptor/0.1"
const DescriptorCatalogueSchema = "rhook/hook-profile-catalogue/0.1"
const ProfileDomain = "rhook/hookr-profile-overlay/0.1"
const ProfileOriginKind = "AUTHENTICATED_CHECKPOINT_PROFILE_OVERLAY"
const ProfileRuntimeProfile = "nitro-hook-profile-overlay/0.1"
const descriptorMaxSafe = 1<<53 - 1
const descriptorMaxBytes = 1 << 20

//go:embed descriptors/hookr-1.json
var hookr1DescriptorRaw []byte

//go:embed descriptors/CATALOGUE.json
var descriptorCatalogueRaw []byte

var embeddedDescriptors = map[string][]byte{"hookr-1.json": hookr1DescriptorRaw}

var (
	reProfileID  = regexp.MustCompile(`^[a-z][a-z0-9-]{0,47}$`)
	reName       = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_]{0,47}$`)
	reKind       = regexp.MustCompile(`^[A-Z][A-Z0-9_]{0,47}$`)
	reSha        = regexp.MustCompile(`^[0-9a-f]{64}$`)
	reDecimal    = regexp.MustCompile(`^(0|[1-9][0-9]{0,77})$`)
	reUnit       = regexp.MustCompile(`^[a-z][a-z0-9]{0,15}$`)
	reSource     = regexp.MustCompile(`^[A-Za-z0-9_.:/@+-]{1,120}$`)
	reNamespace  = regexp.MustCompile(`^[a-z][a-z0-9.]{0,63}$`)
	reHintPath   = regexp.MustCompile(`^[a-z_][a-z0-9_./-]{0,159}$`)
	reParamValue = regexp.MustCompile(`^(0|[1-9][0-9]{0,15})$`)
	reFileName   = regexp.MustCompile(`^[a-z0-9-]+\.json$`)
)

type DOperand struct {
	Const *string `json:"const,omitempty"`
	Field *string `json:"field,omitempty"`
	Param *string `json:"param,omitempty"`
}
type DCompare struct {
	Left  DOperand `json:"left"`
	Op    string   `json:"op"`
	Right DOperand `json:"right"`
}
type DFactor struct {
	ConstMinusSquare []string `json:"constMinusSquare,omitempty"`
	Diff             []string `json:"diff,omitempty"`
	Field            *string  `json:"field,omitempty"`
	Square           *string  `json:"square,omitempty"`
}
type DProductBound struct {
	Bound   string    `json:"bound"`
	Factors []DFactor `json:"factors"`
	Op      string    `json:"op"`
}
type DPredicate struct {
	Compare      *DCompare      `json:"compare,omitempty"`
	ProductBound *DProductBound `json:"productBound,omitempty"`
}
type DAssign struct {
	Field string   `json:"field"`
	Value DOperand `json:"value"`
}
type DParam struct {
	Max    *uint64  `json:"max,omitempty"`
	Min    *uint64  `json:"min,omitempty"`
	Name   string   `json:"name"`
	Type   string   `json:"type"`
	Values []string `json:"values,omitempty"`
}
type DKind struct {
	Assign        []DAssign    `json:"assign"`
	ConflictsWith []string     `json:"conflictsWith"`
	Ensures       []DPredicate `json:"ensures"`
	Kind          string       `json:"kind"`
	Parameters    []DParam     `json:"parameters"`
	Requires      []DPredicate `json:"requires"`
}
type DContract struct {
	Address         common.Address `json:"address"`
	Name            string         `json:"name"`
	ReleaseRole     *string        `json:"releaseRole,omitempty"`
	Requirement     string         `json:"requirement"`
	RuntimeCodeHash *common.Hash   `json:"runtimeCodeHash,omitempty"`
}
type DSlotDerivation struct {
	FieldOffset *uint64 `json:"fieldOffset,omitempty"`
	Kind        string  `json:"kind"`
	Namespace   *string `json:"namespace,omitempty"`
}
type DTarget struct {
	Contract       string          `json:"contract"`
	Name           string          `json:"name"`
	Slot           common.Hash     `json:"slot"`
	SlotDerivation DSlotDerivation `json:"slotDerivation"`
	Words          uint64          `json:"words"`
}
type DField struct {
	Name            string `json:"name"`
	Offset          uint64 `json:"offset"`
	SemanticsSource string `json:"semanticsSource"`
	Target          string `json:"target"`
	Type            string `json:"type"`
	Unit            string `json:"unit"`
	Width           uint64 `json:"width"`
	Word            uint64 `json:"word"`
}
type DOriginalWord struct {
	Target string      `json:"target"`
	Value  common.Hash `json:"value"`
	Word   uint64      `json:"word"`
}
type DOriginalState struct {
	Policy string          `json:"policy"`
	Words  []DOriginalWord `json:"words"`
}
type DChain struct {
	ArbosVersion      uint64 `json:"arbosVersion"`
	ChainConfigSha256 string `json:"chainConfigSha256"`
	ChainID           uint64 `json:"chainId"`
	EngineFamily      string `json:"engineFamily"`
}
type DRelease struct {
	Manifest           json.RawMessage `json:"manifest"`
	ManifestCommitment string          `json:"manifestCommitment"`
}
type DPool struct {
	Currency0     common.Address `json:"currency0"`
	Currency1     common.Address `json:"currency1"`
	Fee           uint64         `json:"fee"`
	HooksContract string         `json:"hooksContract"`
	PoolID        common.Hash    `json:"poolId"`
	TickSpacing   int64          `json:"tickSpacing"`
}
type DAction struct {
	Abi                    json.RawMessage   `json:"abi"`
	AmountInWei            string            `json:"amountInWei"`
	Campaigns              []json.RawMessage `json:"campaigns"`
	Count                  uint64            `json:"count"`
	Engagement             common.Address    `json:"engagement"`
	Function               string            `json:"function"`
	Gas                    []uint64          `json:"gas"`
	MinimumOutputBaseUnits string            `json:"minimumOutputBaseUnits"`
	Router                 string            `json:"router"`
	SqrtPriceLimitX96      string            `json:"sqrtPriceLimitX96"`
	TransactionType        string            `json:"transactionType"`
	Type                   string            `json:"type"`
	ZeroForOne             bool              `json:"zeroForOne"`
}
type DActor struct {
	Kind string `json:"kind"`
	Seed string `json:"seed"`
}
type DSetup struct {
	Actor                  DActor `json:"actor"`
	FundingWei             string `json:"fundingWei"`
	Nonce                  uint64 `json:"nonce"`
	RequireOriginalAbsence bool   `json:"requireOriginalAbsence"`
}
type DMeasure struct {
	Emitter *string      `json:"emitter,omitempty"`
	Name    string       `json:"name"`
	Party   *string      `json:"party,omitempty"`
	Source  string       `json:"source"`
	Topic0  *common.Hash `json:"topic0,omitempty"`
	Topic1  *string      `json:"topic1,omitempty"`
	Word    *uint64      `json:"word,omitempty"`
}
type DHint struct {
	Path   string `json:"path"`
	Sha256 string `json:"sha256"`
}
type DWitness struct {
	ReadHints      []DHint `json:"readHints"`
	SystemSubjects string  `json:"systemSubjects"`
	TargetWords    string  `json:"targetWords"`
}
type DSource struct {
	Kind   string `json:"kind"`
	Name   string `json:"name"`
	Ref    string `json:"ref"`
	Sha256 string `json:"sha256"`
}
type DDerivation struct {
	Method  string `json:"method"`
	Result  string `json:"result"`
	Subject string `json:"subject"`
}
type DProvenance struct {
	ContractSources string        `json:"contractSources"`
	Derivations     []DDerivation `json:"derivations"`
	Sources         []DSource     `json:"sources"`
}
type Descriptor struct {
	Action              DAction        `json:"action"`
	Chain               DChain         `json:"chain"`
	ConfigurationTarget string         `json:"configurationTarget"`
	Contracts           []DContract    `json:"contracts"`
	Fields              []DField       `json:"fields"`
	Interventions       []DKind        `json:"interventions"`
	Measures            []DMeasure     `json:"measures"`
	OriginalState       DOriginalState `json:"originalState"`
	Pool                DPool          `json:"pool"`
	ProfileID           string         `json:"profileId"`
	Provenance          DProvenance    `json:"provenance"`
	Release             DRelease       `json:"release"`
	Revision            uint64         `json:"revision"`
	Schema              string         `json:"schema"`
	Setup               DSetup         `json:"setup"`
	Targets             []DTarget      `json:"targets"`
	Witness             DWitness       `json:"witness"`

	raw       []byte
	targets   map[string]*DTarget
	fields    map[string]*DField
	kinds     map[string]*DKind
	contracts map[string]*DContract
	// reviewKinds: the catalogue's per-kind review status, set only by loadAcceptedFrom.
	reviewKinds map[string]string
}

func dfail(code string) error { return errors.New(code) }

func asciiOnly(raw []byte) bool {
	for _, c := range raw {
		if c >= 0x80 {
			return false
		}
	}
	return true
}

func jsonDepthOK(raw []byte) bool {
	depth, quoted, escape := 0, false, false
	for _, c := range raw {
		if quoted {
			if escape {
				escape = false
			} else if c == '\\' {
				escape = true
			} else if c == '"' {
				quoted = false
			}
		} else if c == '"' {
			quoted = true
		} else if c == '{' || c == '[' {
			depth++
			if depth > 64 {
				return false
			}
		} else if c == '}' || c == ']' {
			depth--
		}
	}
	return true
}

// strictDecode decodes exactly one JSON value with unknown fields refused.
func strictDecode(raw []byte, v any) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if e := d.Decode(v); e != nil {
		return e
	}
	var tail any
	if d.Decode(&tail) != io.EOF {
		return errors.New("JSON_TRAILING")
	}
	return nil
}

// noDuplicateKeys walks the token stream; a repeated key in one object is refused.
func noDuplicateKeys(raw []byte) bool {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	type frame struct {
		object bool
		keys   map[string]bool
		key    bool
	}
	var stack []*frame
	for {
		t, e := d.Token()
		if e == io.EOF {
			return true
		}
		if e != nil {
			return false
		}
		var top *frame
		if len(stack) > 0 {
			top = stack[len(stack)-1]
		}
		switch v := t.(type) {
		case json.Delim:
			if v == '{' || v == '[' {
				if top != nil && top.object {
					top.key = true
				}
				stack = append(stack, &frame{object: v == '{', keys: map[string]bool{}, key: true})
			} else {
				stack = stack[:len(stack)-1]
			}
		default:
			if top != nil && top.object {
				if top.key {
					s, ok := v.(string)
					if !ok || top.keys[s] {
						return false
					}
					top.keys[s] = true
					top.key = false
				} else {
					top.key = true
				}
			}
		}
	}
}

// ParseDescriptor: canonical ASCII bytes -> validated descriptor. Encoding first, then shape, then semantics.
func ParseDescriptor(raw []byte) (*Descriptor, error) {
	if len(raw) == 0 || len(raw) > descriptorMaxBytes || !asciiOnly(raw) || !jsonDepthOK(raw) || !noDuplicateKeys(raw) {
		return nil, dfail("DESCRIPTOR_ENCODING")
	}
	var generic any
	g := json.NewDecoder(bytes.NewReader(raw))
	g.UseNumber()
	if g.Decode(&generic) != nil {
		return nil, dfail("DESCRIPTOR_ENCODING")
	}
	c, e := Canonical(generic)
	if e != nil || !bytes.Equal(append(c, '\n'), raw) {
		return nil, dfail("DESCRIPTOR_ENCODING")
	}
	d := &Descriptor{}
	if strictDecode(raw, d) != nil {
		return nil, dfail("DESCRIPTOR_SCHEMA")
	}
	again, e := Canonical(d)
	if e != nil || !bytes.Equal(append(again, '\n'), raw) {
		return nil, dfail("DESCRIPTOR_SCHEMA")
	}
	d.raw = append([]byte(nil), raw...)
	if e = validateDescriptor(d); e != nil {
		return nil, e
	}
	return d, nil
}

func (d *Descriptor) Sha256() string { return digest(d.raw) }

func erc7201(namespace string) *big.Int {
	inner := new(big.Int).Sub(new(big.Int).SetBytes(crypto.Keccak256([]byte(namespace))), big.NewInt(1))
	out := new(big.Int).SetBytes(crypto.Keccak256(common.LeftPadBytes(inner.Bytes(), 32)))
	return out.AndNot(out, big.NewInt(0xff))
}

func word256(v *big.Int) []byte { return common.LeftPadBytes(v.Bytes(), 32) }

func descriptorPoolID(p DPool, hooks common.Address) common.Hash {
	tick := big.NewInt(p.TickSpacing)
	if tick.Sign() < 0 {
		tick.Add(tick, new(big.Int).Lsh(big.NewInt(1), 256))
	}
	var b []byte
	b = append(b, common.LeftPadBytes(p.Currency0[:], 32)...)
	b = append(b, common.LeftPadBytes(p.Currency1[:], 32)...)
	b = append(b, word256(new(big.Int).SetUint64(p.Fee))...)
	b = append(b, word256(tick)...)
	b = append(b, common.LeftPadBytes(hooks[:], 32)...)
	return crypto.Keccak256Hash(b)
}

func deriveDescriptorSlot(sd DSlotDerivation, pool common.Hash) (common.Hash, error) {
	if sd.Kind != "ERC7201_MAPPING_POOL_ID" || sd.Namespace == nil || sd.FieldOffset == nil {
		return common.Hash{}, dfail("DESCRIPTOR_SLOT_DERIVATION")
	}
	mapped := new(big.Int).SetBytes(crypto.Keccak256(pool[:], word256(erc7201(*sd.Namespace))))
	mapped.Add(mapped, new(big.Int).SetUint64(*sd.FieldOffset))
	mapped.Mod(mapped, new(big.Int).Lsh(big.NewInt(1), 256))
	return common.BigToHash(mapped), nil
}

func decimalOK(s string) bool { return reDecimal.MatchString(s) }

func validateOperand(o DOperand, d *Descriptor, params map[string]string) error {
	n := 0
	for _, p := range []*string{o.Const, o.Field, o.Param} {
		if p != nil {
			n++
		}
	}
	if n != 1 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	switch {
	case o.Const != nil:
		if !decimalOK(*o.Const) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
	case o.Field != nil:
		if d.fields[*o.Field] == nil {
			return dfail("DESCRIPTOR_PREDICATE")
		}
	default:
		if params[*o.Param] != "uint" {
			return dfail("DESCRIPTOR_PREDICATE")
		}
	}
	return nil
}

func validatePredicate(p DPredicate, d *Descriptor, params map[string]string) error {
	if (p.Compare == nil) == (p.ProductBound == nil) {
		return dfail("DESCRIPTOR_PREDICATE")
	}
	if c := p.Compare; c != nil {
		switch c.Op {
		case "eq", "ne", "lt", "le", "gt", "ge":
		default:
			return dfail("DESCRIPTOR_PREDICATE")
		}
		if e := validateOperand(c.Left, d, params); e != nil {
			return e
		}
		return validateOperand(c.Right, d, params)
	}
	b := p.ProductBound
	if b.Op != "lt" && b.Op != "le" {
		return dfail("DESCRIPTOR_PREDICATE")
	}
	if !decimalOK(b.Bound) {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	if b.Factors == nil || len(b.Factors) == 0 || len(b.Factors) > 4 {
		return dfail("DESCRIPTOR_PREDICATE")
	}
	for _, f := range b.Factors {
		n := 0
		if f.Field != nil {
			n++
		}
		if f.Square != nil {
			n++
		}
		if f.Diff != nil {
			n++
		}
		if f.ConstMinusSquare != nil {
			n++
		}
		if n != 1 {
			return dfail("DESCRIPTOR_PREDICATE")
		}
		switch {
		case f.Field != nil:
			if d.fields[*f.Field] == nil {
				return dfail("DESCRIPTOR_PREDICATE")
			}
		case f.Square != nil:
			if d.fields[*f.Square] == nil {
				return dfail("DESCRIPTOR_PREDICATE")
			}
		case f.Diff != nil:
			if len(f.Diff) != 2 || d.fields[f.Diff[0]] == nil || d.fields[f.Diff[1]] == nil {
				return dfail("DESCRIPTOR_PREDICATE")
			}
		default:
			if len(f.ConstMinusSquare) != 2 || !decimalOK(f.ConstMinusSquare[0]) || d.fields[f.ConstMinusSquare[1]] == nil {
				return dfail("DESCRIPTOR_PREDICATE")
			}
		}
	}
	return nil
}

func validateDescriptor(d *Descriptor) error {
	if d.Schema != DescriptorSchema {
		return dfail("DESCRIPTOR_VERSION")
	}
	if !reProfileID.MatchString(d.ProfileID) || d.Revision < 1 || d.Revision > descriptorMaxSafe {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	c := d.Chain
	if c.ChainID < 1 || c.ChainID > descriptorMaxSafe || c.ArbosVersion < 1 || c.ArbosVersion > descriptorMaxSafe || !reSha.MatchString(c.ChainConfigSha256) {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	if c.EngineFamily != "NITRO" {
		return dfail("DESCRIPTOR_CHAIN")
	}
	var manifest struct {
		Contracts []struct {
			Role        string      `json:"role"`
			Address     string      `json:"address"`
			RuntimeHash common.Hash `json:"runtimeHash"`
		} `json:"contracts"`
	}
	if len(d.Release.Manifest) == 0 || d.Release.Manifest[0] != '{' || json.Unmarshal(d.Release.Manifest, &manifest) != nil || manifest.Contracts == nil {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	if !reSha.MatchString(d.Release.ManifestCommitment) {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	if hashValue(Domain+"/release", d.Release.Manifest) != d.Release.ManifestCommitment {
		return dfail("DESCRIPTOR_RELEASE")
	}
	if d.Contracts == nil || len(d.Contracts) == 0 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	d.contracts = map[string]*DContract{}
	addresses := map[common.Address]bool{}
	for i := range d.Contracts {
		k := &d.Contracts[i]
		switch k.Requirement {
		case "CODE_HASH_EQUALS":
			if k.ReleaseRole == nil || k.RuntimeCodeHash == nil {
				return dfail("DESCRIPTOR_SCHEMA")
			}
			if *k.RuntimeCodeHash == (common.Hash{}) {
				return dfail("DESCRIPTOR_CONTRACT")
			}
			found := false
			for _, m := range manifest.Contracts {
				if m.Role == *k.ReleaseRole && m.Address == k.Address.Hex()[:2]+lowerHex(k.Address[:]) && m.RuntimeHash == *k.RuntimeCodeHash {
					found = true
				}
			}
			if !found {
				return dfail("DESCRIPTOR_CONTRACT")
			}
		case "CODE_PRESENT":
			if k.ReleaseRole != nil || k.RuntimeCodeHash != nil {
				return dfail("DESCRIPTOR_SCHEMA")
			}
		default:
			return dfail("DESCRIPTOR_CONTRACT")
		}
		if !reName.MatchString(k.Name) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		if d.contracts[k.Name] != nil || k.Address == (common.Address{}) {
			return dfail("DESCRIPTOR_CONTRACT")
		}
		d.contracts[k.Name] = k
		addresses[k.Address] = true
	}
	if len(addresses) != len(d.contracts) {
		return dfail("DESCRIPTOR_CONTRACT")
	}
	p := d.Pool
	if p.Fee > 1<<24-1 || p.TickSpacing < -(1<<23) || p.TickSpacing >= 1<<23 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	hooks := d.contracts[p.HooksContract]
	if hooks == nil || hooks.Requirement != "CODE_HASH_EQUALS" {
		return dfail("DESCRIPTOR_CONTRACT")
	}
	if descriptorPoolID(p, hooks.Address) != p.PoolID {
		return dfail("DESCRIPTOR_POOL_ID")
	}
	if d.Targets == nil || len(d.Targets) == 0 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	d.targets = map[string]*DTarget{}
	type slotKey struct {
		a common.Address
		s common.Hash
	}
	slots := map[slotKey]bool{}
	limit := new(big.Int).Lsh(big.NewInt(1), 256)
	for i := range d.Targets {
		t := &d.Targets[i]
		if !reName.MatchString(t.Name) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		if d.targets[t.Name] != nil {
			return dfail("DESCRIPTOR_TARGET")
		}
		k := d.contracts[t.Contract]
		if k == nil || k.Requirement != "CODE_HASH_EQUALS" {
			return dfail("DESCRIPTOR_TARGET")
		}
		if t.Words < 1 || t.Words > 8 {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		sd := t.SlotDerivation
		switch sd.Kind {
		case "ERC7201_MAPPING_POOL_ID":
			if sd.Namespace == nil || sd.FieldOffset == nil {
				return dfail("DESCRIPTOR_SCHEMA")
			}
			if !reNamespace.MatchString(*sd.Namespace) || *sd.FieldOffset > 255 {
				return dfail("DESCRIPTOR_SCHEMA")
			}
			got, e := deriveDescriptorSlot(sd, p.PoolID)
			if e != nil || got != t.Slot {
				return dfail("DESCRIPTOR_SLOT_DERIVATION")
			}
		case "FIXED":
			if sd.Namespace != nil || sd.FieldOffset != nil {
				return dfail("DESCRIPTOR_SCHEMA")
			}
		default:
			return dfail("DESCRIPTOR_SLOT_DERIVATION")
		}
		if new(big.Int).Add(t.Slot.Big(), new(big.Int).SetUint64(t.Words)).Cmp(limit) > 0 {
			return dfail("DESCRIPTOR_TARGET")
		}
		d.targets[t.Name] = t
	}
	for _, t := range d.Targets {
		for i := uint64(0); i < t.Words; i++ {
			k := slotKey{d.contracts[t.Contract].Address, wordAt(t.Slot, int(i))}
			if slots[k] {
				return dfail("DESCRIPTOR_TARGET")
			}
			slots[k] = true
		}
	}
	if d.targets[d.ConfigurationTarget] == nil {
		return dfail("DESCRIPTOR_TARGET")
	}
	if d.Fields == nil || len(d.Fields) == 0 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	d.fields = map[string]*DField{}
	type wordKey struct {
		t string
		w uint64
	}
	occupied := map[wordKey]*big.Int{}
	for i := range d.Fields {
		f := &d.Fields[i]
		if !reName.MatchString(f.Name) || !reUnit.MatchString(f.Unit) || !reSource.MatchString(f.SemanticsSource) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		if d.fields[f.Name] != nil || d.targets[f.Target] == nil {
			return dfail("DESCRIPTOR_FIELD_LAYOUT")
		}
		if f.Type != "uint" && f.Type != "flag" && f.Type != "address" {
			return dfail("DESCRIPTOR_FIELD_LAYOUT")
		}
		if f.Word > 7 || f.Offset > 255 || f.Width > 256 {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		if f.Word >= d.targets[f.Target].Words || f.Width < 1 || f.Offset+f.Width > 256 ||
			(f.Type == "flag" && f.Width != 1) || (f.Type == "address" && f.Width != 160) {
			return dfail("DESCRIPTOR_FIELD_LAYOUT")
		}
		m := fieldMask(f)
		k := wordKey{f.Target, f.Word}
		if occupied[k] == nil {
			occupied[k] = new(big.Int)
		}
		if new(big.Int).And(occupied[k], m).Sign() != 0 {
			return dfail("DESCRIPTOR_FIELD_LAYOUT")
		}
		occupied[k].Or(occupied[k], m)
		d.fields[f.Name] = f
	}
	o := d.OriginalState
	if o.Policy != "EXACT_WORDS" {
		return dfail("DESCRIPTOR_ORIGINAL_STATE")
	}
	if o.Words == nil || len(o.Words) == 0 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	seen := map[wordKey]bool{}
	for _, w := range o.Words {
		if d.targets[w.Target] == nil {
			return dfail("DESCRIPTOR_ORIGINAL_STATE")
		}
		if w.Word > 7 {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		k := wordKey{w.Target, w.Word}
		if w.Word >= d.targets[w.Target].Words || seen[k] {
			return dfail("DESCRIPTOR_ORIGINAL_STATE")
		}
		seen[k] = true
	}
	total := 0
	for _, t := range d.Targets {
		total += int(t.Words)
	}
	if len(seen) != total {
		return dfail("DESCRIPTOR_ORIGINAL_STATE")
	}
	if d.Interventions == nil || len(d.Interventions) == 0 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	d.kinds = map[string]*DKind{}
	var names []string
	for i := range d.Interventions {
		k := &d.Interventions[i]
		if !reKind.MatchString(k.Kind) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		if d.kinds[k.Kind] != nil {
			return dfail("DESCRIPTOR_KIND")
		}
		names = append(names, k.Kind)
		if k.Parameters == nil || len(k.Parameters) == 0 || k.Requires == nil || k.Ensures == nil || k.Assign == nil || k.ConflictsWith == nil {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		params := map[string]string{}
		for _, prm := range k.Parameters {
			switch prm.Type {
			case "uint":
				if prm.Min == nil || prm.Max == nil || prm.Values != nil {
					return dfail("DESCRIPTOR_SCHEMA")
				}
				if *prm.Min > descriptorMaxSafe || *prm.Max > descriptorMaxSafe {
					return dfail("DESCRIPTOR_SCHEMA")
				}
				if *prm.Min > *prm.Max {
					return dfail("DESCRIPTOR_KIND")
				}
			case "enum":
				if prm.Min != nil || prm.Max != nil || prm.Values == nil {
					return dfail("DESCRIPTOR_SCHEMA")
				}
				if len(prm.Values) == 0 {
					return dfail("DESCRIPTOR_SCHEMA")
				}
				uniq := map[string]bool{}
				for _, v := range prm.Values {
					if !reKind.MatchString(v) || uniq[v] {
						return dfail("DESCRIPTOR_KIND")
					}
					uniq[v] = true
				}
			default:
				return dfail("DESCRIPTOR_KIND")
			}
			if !reName.MatchString(prm.Name) {
				return dfail("DESCRIPTOR_SCHEMA")
			}
			if params[prm.Name] != "" {
				return dfail("DESCRIPTOR_KIND")
			}
			params[prm.Name] = prm.Type
		}
		for _, pr := range k.Requires {
			if e := validatePredicate(pr, d, params); e != nil {
				return e
			}
		}
		for _, pr := range k.Ensures {
			if e := validatePredicate(pr, d, params); e != nil {
				return e
			}
		}
		if len(k.Assign) == 0 {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		assigned := map[string]bool{}
		for _, a := range k.Assign {
			f := d.fields[a.Field]
			if f == nil || assigned[a.Field] || f.Type == "address" {
				return dfail("DESCRIPTOR_KIND")
			}
			assigned[a.Field] = true
			if e := validateOperand(a.Value, d, params); e != nil {
				return e
			}
		}
		for _, c2 := range k.ConflictsWith {
			if c2 == k.Kind {
				return dfail("DESCRIPTOR_KIND")
			}
		}
		d.kinds[k.Kind] = k
	}
	if !sort.StringsAreSorted(names) {
		return dfail("DESCRIPTOR_KIND")
	}
	for _, k := range d.kinds {
		for i, c2 := range k.ConflictsWith {
			other := d.kinds[c2]
			if other == nil || (i > 0 && k.ConflictsWith[i-1] >= c2) {
				return dfail("DESCRIPTOR_KIND")
			}
			symmetric := false
			for _, back := range other.ConflictsWith {
				if back == k.Kind {
					symmetric = true
				}
			}
			if !symmetric {
				return dfail("DESCRIPTOR_KIND")
			}
		}
	}
	a := d.Action
	if a.Count > descriptorMaxSafe {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	if a.Type != "HOOKR_ROUTER_EXACT_INPUT_BUY_V1" || a.TransactionType != "LEGACY" || a.Function != "swap" || a.Count != 1 || !a.ZeroForOne || a.Campaigns == nil || len(a.Campaigns) != 0 {
		return dfail("DESCRIPTOR_ACTION")
	}
	if r := d.contracts[a.Router]; r == nil || r.Requirement != "CODE_HASH_EQUALS" {
		return dfail("DESCRIPTOR_ACTION")
	}
	var abiRows []json.RawMessage
	if json.Unmarshal(a.Abi, &abiRows) != nil || len(abiRows) == 0 {
		return dfail("DESCRIPTOR_ACTION")
	}
	if !decimalOK(a.AmountInWei) || !decimalOK(a.MinimumOutputBaseUnits) || !decimalOK(a.SqrtPriceLimitX96) || a.Gas == nil || len(a.Gas) == 0 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	for i, gas := range a.Gas {
		if gas == 0 || gas > descriptorMaxSafe || (i > 0 && a.Gas[i-1] >= gas) {
			return dfail("DESCRIPTOR_ACTION")
		}
	}
	s := d.Setup
	if s.Actor.Kind != "PUBLIC_SIMULATION_SIGNER_V1" || s.Actor.Seed == "" {
		return dfail("DESCRIPTOR_SETUP")
	}
	if !decimalOK(s.FundingWei) || s.Nonce > descriptorMaxSafe {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	if s.Nonce != 0 || !s.RequireOriginalAbsence {
		return dfail("DESCRIPTOR_SETUP")
	}
	if d.Measures == nil || len(d.Measures) == 0 {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	measureNames := map[string]bool{}
	for _, m := range d.Measures {
		var event, transfer bool
		switch m.Source {
		case "SUBJECT_RECEIPT_GAS_USED", "SUBJECT_RECEIPT_STATUS", "WORLD_ACTOR_BALANCE_AFTER":
		case "EVENT_DATA_WORD":
			event = true
		case "ERC20_TRANSFER_NET":
			transfer = true
		default:
			return dfail("DESCRIPTOR_MEASURE")
		}
		if (m.Emitter != nil) != (event || transfer) || (m.Topic0 != nil) != (event || transfer) || (m.Topic1 != nil) != event ||
			(m.Word != nil) != event || (m.Party != nil) != transfer {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		if !reName.MatchString(m.Name) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		if measureNames[m.Name] {
			return dfail("DESCRIPTOR_MEASURE")
		}
		measureNames[m.Name] = true
		if m.Emitter != nil && d.contracts[*m.Emitter] == nil {
			return dfail("DESCRIPTOR_MEASURE")
		}
		if m.Topic1 != nil && *m.Topic1 != "POOL_ID" {
			return dfail("DESCRIPTOR_MEASURE")
		}
		if m.Word != nil && *m.Word > 31 {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		if m.Party != nil && *m.Party != "ACTOR" {
			return dfail("DESCRIPTOR_MEASURE")
		}
	}
	w := d.Witness
	if w.SystemSubjects != "NITRO_ARBOS61_SCENARIO_SYSTEM_V1" || w.TargetWords != "ALL_DECLARED_TARGET_WORDS" {
		return dfail("DESCRIPTOR_WITNESS")
	}
	if w.ReadHints == nil {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	for _, h := range w.ReadHints {
		if !reHintPath.MatchString(h.Path) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
		for _, part := range bytes.Split([]byte(h.Path), []byte("/")) {
			if string(part) == ".." {
				return dfail("DESCRIPTOR_WITNESS")
			}
		}
		if !reSha.MatchString(h.Sha256) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
	}
	pv := d.Provenance
	if pv.Sources == nil || len(pv.Sources) == 0 || pv.Derivations == nil {
		return dfail("DESCRIPTOR_SCHEMA")
	}
	for _, src := range pv.Sources {
		if !reSha.MatchString(src.Sha256) {
			return dfail("DESCRIPTOR_SCHEMA")
		}
	}
	return nil
}

func lowerHex(b []byte) string {
	const digits = "0123456789abcdef"
	out := make([]byte, 2*len(b))
	for i, c := range b {
		out[2*i], out[2*i+1] = digits[c>>4], digits[c&15]
	}
	return string(out)
}

func fieldOnes(f *DField) *big.Int {
	return new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), uint(f.Width)), big.NewInt(1))
}
func fieldMask(f *DField) *big.Int { return new(big.Int).Lsh(fieldOnes(f), uint(f.Offset)) }

// ----- catalogue ---------------------------------------------------------------------------------------

type descriptorReview struct {
	Admits            []string `json:"admits"`
	Author            string   `json:"author"`
	IndependentReview string   `json:"independentReview"`
	NativeExecution   string   `json:"nativeExecution"`
	Status            string   `json:"status"`
}
type descriptorEntry struct {
	DescriptorFile   string            `json:"descriptorFile"`
	DescriptorSha256 string            `json:"descriptorSha256"`
	Kinds            map[string]string `json:"kinds"`
	ProfileID        string            `json:"profileId"`
	Review           descriptorReview  `json:"review"`
	Revision         uint64            `json:"revision"`
}
type descriptorCatalogue struct {
	Entries []descriptorEntry `json:"entries"`
	Schema  string            `json:"schema"`
}

// LoadAcceptedDescriptor is the only workflow loader: an embedded catalogue entry, its exact descriptor bytes
// and a review status admitting the purpose. No caller-supplied descriptor file is ever loaded.
func LoadAcceptedDescriptor(profileID, purpose string) (*Descriptor, error) {
	return loadAcceptedFrom(descriptorCatalogueRaw, embeddedDescriptors, profileID, purpose)
}

func loadAcceptedFrom(catalogue []byte, files map[string][]byte, profileID, purpose string) (*Descriptor, error) {
	if purpose != "OFFLINE_PREPARATION" && purpose != "NATIVE_EXECUTION" {
		return nil, dfail("PROFILE_REVIEW_INSUFFICIENT")
	}
	var c descriptorCatalogue
	if strictDecode(catalogue, &c) != nil || c.Schema != DescriptorCatalogueSchema {
		return nil, dfail("PROFILE_CATALOGUE")
	}
	var match []descriptorEntry
	for _, e := range c.Entries {
		if e.ProfileID == profileID {
			match = append(match, e)
		}
	}
	if len(match) != 1 {
		return nil, dfail("PROFILE_NOT_IN_CATALOGUE")
	}
	e := match[0]
	raw, ok := files[e.DescriptorFile]
	if !reFileName.MatchString(e.DescriptorFile) || !ok {
		return nil, dfail("PROFILE_CATALOGUE")
	}
	if digest(raw) != e.DescriptorSha256 {
		return nil, dfail("PROFILE_DESCRIPTOR_HASH")
	}
	d, err := ParseDescriptor(raw)
	if err != nil {
		return nil, err
	}
	if d.ProfileID != profileID || d.Revision != e.Revision {
		return nil, dfail("PROFILE_CATALOGUE")
	}
	admitted := false
	for _, a := range e.Review.Admits {
		if a == purpose {
			admitted = true
		}
	}
	if !admitted {
		return nil, dfail("PROFILE_REVIEW_INSUFFICIENT")
	}
	if len(e.Kinds) != len(d.kinds) {
		return nil, dfail("PROFILE_CATALOGUE")
	}
	d.reviewKinds = map[string]string{}
	for k, status := range e.Kinds {
		if d.kinds[k] == nil || kindReviewPurposes[status] == nil {
			return nil, dfail("PROFILE_CATALOGUE")
		}
		d.reviewKinds[k] = status
	}
	return d, nil
}

// kindReviewPurposes is the closed vocabulary of per-kind review statuses and the purposes each admits. A kind
// admits a purpose only if its status lists it; the descriptor-level review must admit the purpose as well.
var kindReviewPurposes = map[string][]string{
	"LEGACY_EQUIVALENT_SDK04":       {"OFFLINE_PREPARATION", "NATIVE_EXECUTION"},
	"OFFLINE_PROBE_BIND_RULES_ONLY": {"OFFLINE_PREPARATION"},
}

func kindReviewAdmits(status, purpose string) bool {
	for _, p := range kindReviewPurposes[status] {
		if p == purpose {
			return true
		}
	}
	return false
}

// ----- interpretation ------------------------------------------------------------------------------------

type ProfileIntervention struct {
	Kind       string                     `json:"kind"`
	Parameters map[string]json.RawMessage `json:"parameters"`
}
type ProfileWrite struct {
	Address common.Address `json:"address"`
	After   common.Hash    `json:"after"`
	Before  common.Hash    `json:"before"`
	Slot    common.Hash    `json:"slot"`
	Target  string         `json:"target"`
	Word    uint64         `json:"word"`
}

// Originals holds every authenticated word of every target, by target name.
type Originals map[string][]*big.Int

type ProfileComposition struct {
	Interventions []ProfileIntervention
	Writes        []ProfileWrite
	Words         map[string][]common.Hash
	Baseline      map[string]*big.Int
	Variant       map[string]*big.Int
}

// DecodeProfileInterventions decodes a caller list; anything but [{kind, parameters}] is a shape error.
func DecodeProfileInterventions(raw []byte) ([]ProfileIntervention, error) {
	var items []ProfileIntervention
	if strictDecode(raw, &items) != nil {
		return nil, dfail("PROFILE_INTERVENTION_SHAPE")
	}
	for _, i := range items {
		if i.Parameters == nil || i.Kind == "" {
			return nil, dfail("PROFILE_INTERVENTION_SHAPE")
		}
	}
	return items, nil
}

func (d *Descriptor) OriginalsFromDescriptor() Originals {
	out := Originals{}
	for _, t := range d.Targets {
		out[t.Name] = make([]*big.Int, t.Words)
	}
	for _, w := range d.OriginalState.Words {
		out[w.Target][w.Word] = w.Value.Big()
	}
	return out
}

func getField(words Originals, f *DField) *big.Int {
	return new(big.Int).And(new(big.Int).Rsh(words[f.Target][f.Word], uint(f.Offset)), fieldOnes(f))
}

func (d *Descriptor) decodeAll(words Originals) map[string]*big.Int {
	out := map[string]*big.Int{}
	for name, f := range d.fields {
		out[name] = getField(words, f)
	}
	return out
}

func operandValue(o DOperand, words Originals, d *Descriptor, params map[string]*big.Int) *big.Int {
	switch {
	case o.Const != nil:
		v, _ := new(big.Int).SetString(*o.Const, 10)
		return v
	case o.Field != nil:
		return getField(words, d.fields[*o.Field])
	default:
		return params[*o.Param]
	}
}

func predicateHolds(p DPredicate, words Originals, d *Descriptor, params map[string]*big.Int) (bool, error) {
	if c := p.Compare; c != nil {
		r := operandValue(c.Left, words, d, params).Cmp(operandValue(c.Right, words, d, params))
		switch c.Op {
		case "eq":
			return r == 0, nil
		case "ne":
			return r != 0, nil
		case "lt":
			return r < 0, nil
		case "le":
			return r <= 0, nil
		case "gt":
			return r > 0, nil
		default:
			return r >= 0, nil
		}
	}
	b := p.ProductBound
	product := big.NewInt(1)
	for _, f := range b.Factors {
		var v *big.Int
		switch {
		case f.Field != nil:
			v = getField(words, d.fields[*f.Field])
		case f.Square != nil:
			x := getField(words, d.fields[*f.Square])
			v = new(big.Int).Mul(x, x)
		case f.Diff != nil:
			v = new(big.Int).Sub(getField(words, d.fields[f.Diff[0]]), getField(words, d.fields[f.Diff[1]]))
		default:
			c, _ := new(big.Int).SetString(f.ConstMinusSquare[0], 10)
			x := getField(words, d.fields[f.ConstMinusSquare[1]])
			v = new(big.Int).Sub(c, new(big.Int).Mul(x, x))
		}
		if v.Sign() < 0 {
			return false, dfail("PROFILE_NEGATIVE_FACTOR")
		}
		product.Mul(product, v)
	}
	bound, _ := new(big.Int).SetString(b.Bound, 10)
	if b.Op == "lt" {
		return product.Cmp(bound) < 0, nil
	}
	return product.Cmp(bound) <= 0, nil
}

// canonicalProfileInterventions validates the set and returns it sorted by kind, with typed parameter values.
func (d *Descriptor) canonicalProfileInterventions(items []ProfileIntervention) ([]ProfileIntervention, []map[string]*big.Int, error) {
	if len(items) < 1 || len(items) > len(d.kinds) {
		return nil, nil, dfail("PROFILE_INTERVENTION_COUNT")
	}
	for _, i := range items {
		if i.Parameters == nil {
			return nil, nil, dfail("PROFILE_INTERVENTION_SHAPE")
		}
		if d.kinds[i.Kind] == nil {
			return nil, nil, dfail("PROFILE_UNKNOWN_INTERVENTION")
		}
	}
	present := map[string]bool{}
	for _, i := range items {
		if present[i.Kind] {
			return nil, nil, dfail("PROFILE_DUPLICATE_KIND")
		}
		present[i.Kind] = true
	}
	for _, i := range items {
		for _, c := range d.kinds[i.Kind].ConflictsWith {
			if present[c] {
				return nil, nil, dfail("PROFILE_KIND_CONFLICT")
			}
		}
	}
	out := append([]ProfileIntervention{}, items...)
	sort.SliceStable(out, func(a, b int) bool { return out[a].Kind < out[b].Kind })
	values := make([]map[string]*big.Int, len(out))
	for n, i := range out {
		k := d.kinds[i.Kind]
		if len(i.Parameters) != len(k.Parameters) {
			return nil, nil, dfail("PROFILE_PARAMETER")
		}
		values[n] = map[string]*big.Int{}
		for _, prm := range k.Parameters {
			raw, ok := i.Parameters[prm.Name]
			if !ok {
				return nil, nil, dfail("PROFILE_PARAMETER")
			}
			if prm.Type == "uint" {
				if !reParamValue.Match(raw) {
					return nil, nil, dfail("PROFILE_PARAMETER")
				}
				v, _ := new(big.Int).SetString(string(raw), 10)
				if v.Cmp(new(big.Int).SetUint64(*prm.Min)) < 0 || v.Cmp(new(big.Int).SetUint64(*prm.Max)) > 0 {
					return nil, nil, dfail("PROFILE_PARAMETER")
				}
				values[n][prm.Name] = v
				continue
			}
			var s string
			if strictDecode(raw, &s) != nil {
				return nil, nil, dfail("PROFILE_PARAMETER")
			}
			ok = false
			for _, allowed := range prm.Values {
				if allowed == s {
					ok = true
				}
			}
			if !ok {
				return nil, nil, dfail("PROFILE_PARAMETER")
			}
		}
	}
	return out, values, nil
}

// ComposeProfile applies typed interventions to authenticated original words. The order of checks is the
// Python mirror's: originals, exact words, the set, then per kind requires and assignments, then ensures,
// unrelated bits, read-back and writes.
func (d *Descriptor) ComposeProfile(items []ProfileIntervention, originals Originals) (ProfileComposition, error) {
	var out ProfileComposition
	limit := new(big.Int).Lsh(big.NewInt(1), 256)
	if len(originals) != len(d.targets) {
		return out, dfail("PROFILE_ORIGINAL_STATE_UNAVAILABLE")
	}
	for name, t := range d.targets {
		row, ok := originals[name]
		if !ok || uint64(len(row)) != t.Words {
			return out, dfail("PROFILE_ORIGINAL_STATE_UNAVAILABLE")
		}
		for _, v := range row {
			if v == nil || v.Sign() < 0 || v.Cmp(limit) >= 0 {
				return out, dfail("PROFILE_ORIGINAL_STATE_UNAVAILABLE")
			}
		}
	}
	for _, w := range d.OriginalState.Words {
		if originals[w.Target][w.Word].Cmp(w.Value.Big()) != 0 {
			return out, dfail("PROFILE_ORIGINAL_WORD")
		}
	}
	canon, values, e := d.canonicalProfileInterventions(items)
	if e != nil {
		return out, e
	}
	original, result, used := Originals{}, Originals{}, Originals{}
	for name, row := range originals {
		original[name] = make([]*big.Int, len(row))
		result[name] = make([]*big.Int, len(row))
		used[name] = make([]*big.Int, len(row))
		for i, v := range row {
			original[name][i] = new(big.Int).Set(v)
			result[name][i] = new(big.Int).Set(v)
			used[name][i] = new(big.Int)
		}
	}
	type applied struct {
		f *DField
		v *big.Int
	}
	var done []applied
	for n, item := range canon {
		k := d.kinds[item.Kind]
		for _, pr := range k.Requires {
			ok, e := predicateHolds(pr, original, d, values[n])
			if e != nil {
				return out, e
			}
			if !ok {
				return out, dfail("PROFILE_ORIGINAL_PRECONDITION")
			}
		}
		for _, a := range k.Assign {
			f := d.fields[a.Field]
			v := operandValue(a.Value, original, d, values[n])
			if v.Sign() < 0 || v.Cmp(fieldOnes(f)) > 0 {
				return out, dfail("PROFILE_VALUE_WIDTH")
			}
			m := fieldMask(f)
			u := used[f.Target][f.Word]
			if new(big.Int).And(u, m).Sign() != 0 {
				return out, dfail("PROFILE_MASK_CONFLICT")
			}
			u.Or(u, m)
			w := result[f.Target][f.Word]
			w.AndNot(w, m)
			w.Or(w, new(big.Int).Lsh(v, uint(f.Offset)))
			done = append(done, applied{f, v})
		}
	}
	for n, item := range canon {
		for _, pr := range d.kinds[item.Kind].Ensures {
			ok, e := predicateHolds(pr, result, d, values[n])
			if e != nil {
				return out, e
			}
			if !ok {
				return out, dfail("PROFILE_INVARIANT")
			}
		}
	}
	for _, t := range d.Targets {
		for i := range result[t.Name] {
			if new(big.Int).AndNot(new(big.Int).Xor(result[t.Name][i], original[t.Name][i]), used[t.Name][i]).Sign() != 0 {
				return out, dfail("PROFILE_NON_TARGET_BITS")
			}
		}
	}
	for _, a := range done {
		if getField(result, a.f).Cmp(a.v) != 0 {
			return out, dfail("PROFILE_FIELD_VALUE")
		}
	}
	out.Words = map[string][]common.Hash{}
	for _, t := range d.Targets {
		address := d.contracts[t.Contract].Address
		for i := uint64(0); i < t.Words; i++ {
			out.Words[t.Name] = append(out.Words[t.Name], common.BigToHash(result[t.Name][i]))
			if used[t.Name][i].Sign() == 0 {
				continue
			}
			if result[t.Name][i].Cmp(original[t.Name][i]) == 0 {
				return out, dfail("PROFILE_NO_EFFECT")
			}
			out.Writes = append(out.Writes, ProfileWrite{Address: address, After: common.BigToHash(result[t.Name][i]), Before: common.BigToHash(original[t.Name][i]),
				Slot: wordAt(t.Slot, int(i)), Target: t.Name, Word: i})
		}
	}
	out.Interventions = canon
	out.Baseline, out.Variant = d.decodeAll(original), d.decodeAll(result)
	return out, nil
}

// profileState is what authentication reads from a witness-backed StateDB.
type profileState interface {
	Exist(common.Address) bool
	GetCodeHash(common.Address) common.Hash
	GetCode(common.Address) []byte
	GetState(common.Address, common.Hash) common.Hash
	Error() error
}

// AuthenticateProfile checks every declared contract identity and reads every target word, checking the
// state's error after each read: a missing witness node is UNAVAILABLE, never zero.
func (d *Descriptor) AuthenticateProfile(st profileState) (Originals, error) {
	for _, c := range d.Contracts {
		exists := st.Exist(c.Address)
		hash := st.GetCodeHash(c.Address)
		code := st.GetCode(c.Address)
		if st.Error() != nil {
			return nil, dfail("PROFILE_ORIGINAL_STATE_UNAVAILABLE")
		}
		if c.Requirement == "CODE_HASH_EQUALS" {
			if !exists || hash != *c.RuntimeCodeHash || crypto.Keccak256Hash(code) != *c.RuntimeCodeHash {
				return nil, dfail("PROFILE_CODE_IDENTITY")
			}
		} else if !exists || len(code) == 0 {
			return nil, dfail("PROFILE_TOKEN_CODE_REQUIRED")
		}
	}
	out := Originals{}
	for _, t := range d.Targets {
		address := d.contracts[t.Contract].Address
		for i := uint64(0); i < t.Words; i++ {
			v := st.GetState(address, wordAt(t.Slot, int(i)))
			if st.Error() != nil {
				return nil, dfail("PROFILE_ORIGINAL_STATE_UNAVAILABLE")
			}
			out[t.Name] = append(out[t.Name], v.Big())
		}
	}
	return out, nil
}

// CheckProfileWrites is the envelope check of a supplied write list: declared target words only.
func (d *Descriptor) CheckProfileWrites(writes []ProfileWrite) error {
	for _, w := range writes {
		t := d.targets[w.Target]
		if t == nil || w.Word >= t.Words || d.contracts[t.Contract].Address != w.Address || wordAt(t.Slot, int(w.Word)) != w.Slot {
			return dfail("PROFILE_WRITE_TARGET")
		}
	}
	return nil
}

// ApplyProfileWrites authenticates every original word before any write and writes only in the variant
// world. overlayState exposes storage only: code, balance and nonce cannot be changed through it.
func (d *Descriptor) ApplyProfileWrites(st overlayState, writes []ProfileWrite, label string) ([]ProfileWrite, error) {
	if label != Baseline && label != Variant {
		return nil, dfail("PROFILE_WORLD")
	}
	if e := d.CheckProfileWrites(writes); e != nil {
		return nil, e
	}
	for _, w := range writes {
		if st.GetState(w.Address, w.Slot) != w.Before {
			return nil, dfail("PROFILE_ORIGINAL_WORD_CHANGED")
		}
	}
	rows := append([]ProfileWrite{}, writes...)
	for i, w := range rows {
		if label == Variant {
			st.SetState(w.Address, w.Slot, w.After)
		} else {
			rows[i].After = w.Before
		}
	}
	return rows, nil
}

// legacyProfile derives the SDK 0.4 profile this descriptor reproduces (G1).
func (d *Descriptor) legacyProfile() profile {
	var p profile
	p.Kind = "AUTHENTICATED_CHECKPOINT_SCENARIO"
	p.Manifest = append(json.RawMessage(nil), d.Release.Manifest...)
	p.Pool = d.Pool.PoolID
	p.PoolKey.Currency0, p.PoolKey.Currency1 = d.Pool.Currency0, d.Pool.Currency1
	p.PoolKey.Hooks = d.contracts[d.Pool.HooksContract].Address
	p.PoolKey.Fee, p.PoolKey.TickSpacing = d.Pool.Fee, d.Pool.TickSpacing
	p.RootSlot, p.ConfigSlot = d.targets["rootRecord"].Slot, d.targets["rulesConfig"].Slot
	o := d.OriginalsFromDescriptor()
	for _, w := range o["rulesConfig"] {
		p.BaselineWords = append(p.BaselineWords, common.BigToHash(w))
	}
	p.RootCaps = common.BigToHash(o["rootRecord"][1])
	p.BaseLpFee = getField(o, d.fields["rootBaseLpFeePips"]).Uint64()
	p.SwapABI = append(json.RawMessage(nil), d.Action.Abi...)
	p.Pins = map[common.Address]common.Hash{}
	for _, c := range d.Contracts {
		if c.Requirement == "CODE_HASH_EQUALS" {
			p.Pins[c.Address] = *c.RuntimeCodeHash
		}
	}
	p.Rules, p.Router = d.contracts["rules"].Address, d.contracts["router"].Address
	return p
}

// exactWord is the reviewed original of one target word (EXACT_WORDS).
func (d *Descriptor) exactWord(target string, word uint64) common.Hash {
	for _, w := range d.OriginalState.Words {
		if w.Target == target && w.Word == word {
			return w.Value
		}
	}
	return common.Hash{}
}

// ----- prepared-input binding (rhook/hookr-profile-overlay/0.1) ----------------------------------------------

type ProfileDescriptorRef struct {
	ProfileID string `json:"profileId"`
	Revision  uint64 `json:"revision"`
	Sha256    string `json:"sha256"`
}
type ProfileOverlay struct {
	CodeHashes    map[string]common.Hash `json:"codeHashes"`
	Commitment    string                 `json:"interventionCommitment,omitempty"`
	Descriptor    ProfileDescriptorRef   `json:"descriptor"`
	Interventions []ProfileIntervention  `json:"interventions"`
	OriginalRoot  common.Hash            `json:"originalStateRoot"`
	Pool          common.Hash            `json:"poolId"`
	Schema        string                 `json:"schema"`
	Writes        []ProfileWrite         `json:"writes"`
}

// ParseProfileSpec decodes a canonical profile-overlay input through the shared strict Parse. Codes follow the
// Python mirror: a commitment or domain failure is PROFILE_SPEC_COMMITMENT, any other parse failure
// PROFILE_SPEC_ENCODING.
func ParseProfileSpec(raw []byte) (Spec, error) {
	s, e := Parse(raw)
	if e != nil {
		if e.Error() == "SCENARIO_DOMAIN_OR_COMMITMENT" {
			return s, dfail("PROFILE_SPEC_COMMITMENT")
		}
		return s, dfail("PROFILE_SPEC_ENCODING")
	}
	if s.Schema != ProfileDomain {
		return s, dfail("PROFILE_SPEC_COMMITMENT")
	}
	if s.Intervention != nil || s.Overlay != nil || s.ProfileOverlay == nil {
		return s, dfail("PROFILE_SPEC_BINDING")
	}
	return s, nil
}

func (d *Descriptor) profileTransform(b Body, canon []ProfileIntervention, c ProfileComposition) ProfileOverlay {
	hashes := map[string]common.Hash{}
	for _, k := range d.Contracts {
		if k.Requirement == "CODE_HASH_EQUALS" {
			hashes[k.Name] = *k.RuntimeCodeHash
		}
	}
	writes := c.Writes
	if writes == nil {
		writes = []ProfileWrite{}
	}
	o := ProfileOverlay{CodeHashes: hashes, Descriptor: ProfileDescriptorRef{d.ProfileID, d.Revision, d.Sha256()}, Interventions: canon,
		OriginalRoot: b.Checkpoint.StateRoot, Pool: d.Pool.PoolID, Schema: ProfileDomain + "/transform", Writes: writes}
	o.Commitment = hashValue(ProfileDomain+"/transform", o)
	return o
}

func (d *Descriptor) profileCapsule(b Body, canon []ProfileIntervention) string {
	intent := map[string]any{"schema": ProfileDomain + "/intent", "poolId": b.Pool, "interventions": canon,
		"profile": map[string]any{"profileId": d.ProfileID, "sha256": d.Sha256()}}
	return hashValue(ProfileDomain+"/checkpoint", map[string]any{"checkpoint": b.Checkpoint, "intent": intent})
}

func canonicalEqual(a, b any) bool {
	x, e1 := Canonical(a)
	y, e2 := Canonical(b)
	return e1 == nil && e2 == nil && bytes.Equal(x, y)
}

// ValidateProfileSpec mirrors profile_descriptor.validate_spec: descriptor binding, canonical order, derived
// writes, configuration words, origin, then pool, chain and release.
func (d *Descriptor) ValidateProfileSpec(s Spec) (ProfileComposition, error) {
	var none ProfileComposition
	o := s.ProfileOverlay
	if o == nil || s.Schema != ProfileDomain || s.Intervention != nil || s.Overlay != nil {
		return none, dfail("PROFILE_SPEC_BINDING")
	}
	if o.Descriptor != (ProfileDescriptorRef{d.ProfileID, d.Revision, d.Sha256()}) {
		return none, dfail("PROFILE_SPEC_BINDING")
	}
	canon, _, e := d.canonicalProfileInterventions(o.Interventions)
	if e != nil {
		return none, e
	}
	if !canonicalEqual(canon, o.Interventions) {
		return none, dfail("PROFILE_CANONICAL_ORDER")
	}
	c, e := d.ComposeProfile(canon, d.OriginalsFromDescriptor())
	if e != nil {
		return none, e
	}
	body := s.Body
	body.ProfileOverlay = nil
	if !canonicalEqual(d.profileTransform(body, canon, c), *o) {
		return none, dfail("PROFILE_SPEC_DERIVED_WRITES")
	}
	var baseline []common.Hash
	for _, w := range d.OriginalState.Words {
		if w.Target == d.ConfigurationTarget {
			baseline = append(baseline, w.Value)
		}
	}
	if !canonicalEqual(s.Configs, Configurations{Baseline: baseline, Variant: c.Words[d.ConfigurationTarget]}) {
		return none, dfail("PROFILE_SPEC_VARIANT_WORD")
	}
	if s.Origin.Kind != ProfileOriginKind || s.Origin.Capsule != d.profileCapsule(body, canon) {
		return none, dfail("PROFILE_SPEC_ORIGIN")
	}
	if s.Pool != d.Pool.PoolID || s.Checkpoint.ChainID != d.Chain.ChainID || s.Release != d.Release.ManifestCommitment {
		return none, dfail("PROFILE_SPEC_BINDING")
	}
	return c, nil
}
