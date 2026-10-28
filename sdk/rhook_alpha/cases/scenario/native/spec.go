// Package scenario implements an offline two-world controller, separate from
// historical calibration. It is not an execution launcher or authority issuer.
package scenario

import (
	"bytes"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"regexp"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/common/hexutil"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	prestate "local/rhook-robinhood"
)

const Domain = "rhook/hookr-scenario/0.1"
const Baseline = "SCENARIO_BASELINE"
const Variant = "SCENARIO_VARIANT"

// This SDK profile promises one declared buy by the public simulation identity.
// Broader retained R&D scenarios are not implicitly authorized by that plan.
func validateOnDemandShape(s Spec) error {
	key, e := crypto.ToECDSA(crypto.Keccak256([]byte("RHOOK BUILD04 PUBLIC SIMULATION SIGNER; NEVER FUND OR BROADCAST")))
	if e != nil || len(s.Actions) != 1 || s.Setup.Actor != crypto.PubkeyToAddress(key.PublicKey) {
		return errors.New("ON_DEMAND_SINGLE_BUY_AND_PUBLIC_ACTOR_REQUIRED")
	}
	return nil
}

//go:embed profile.json
var profileJSON []byte

type Identity struct {
	Source string `json:"sourceSha256"`
	Binary string `json:"binarySha256"`
	Policy string `json:"policySha256"`
}
type Limits struct {
	Wall     uint64 `json:"nativeWallSeconds"`
	CPU      uint64 `json:"nativeCPUSeconds"`
	RSS      uint64 `json:"workerRSSBytes"`
	Stage    uint64 `json:"stageWallSeconds"`
	Workflow uint64 `json:"workflowWallSeconds"`
	Output   uint64 `json:"outputBytes"`
	RPC      uint64 `json:"rpc"`
	Worlds   uint64 `json:"worlds"`
}

var policy = Limits{120, 120, 1 << 30, 140, 180, 64 << 20, 0, 2}

type Inventory struct {
	Nodes []hexutil.Bytes `json:"nodes"`
	Codes []hexutil.Bytes `json:"codes"`
}
type Origin struct {
	Kind    string `json:"kind"`
	Capsule string `json:"capsuleId"`
}
type Setup struct {
	Actor         common.Address `json:"actor"`
	Funding       string         `json:"fundingWei"`
	Nonce         uint64         `json:"nonce"`
	RequireAbsent bool           `json:"requireOriginalAbsence"`
}
type Configurations struct {
	Baseline []common.Hash `json:"baseline"`
	Variant  []common.Hash `json:"variant"`
}
type Environment struct {
	Number    uint64         `json:"l2BlockNumber"`
	Time      uint64         `json:"l2Timestamp"`
	L1Number  uint64         `json:"l1BlockNumber"`
	L1BaseFee string         `json:"syntheticL1BaseFeeWei"`
	Poster    common.Address `json:"poster"`
	Delayed   uint64         `json:"delayedMessagesRead"`
}
type Action struct {
	ID         string        `json:"id,omitempty"`
	Nonce      uint64        `json:"nonce"`
	Gas        uint64        `json:"gas"`
	GasPrice   string        `json:"gasPriceWei"`
	Amount     string        `json:"amountInWei"`
	Minimum    string        `json:"minimumOutputBaseUnits"`
	PriceLimit string        `json:"sqrtPriceLimitX96"`
	Deadline   uint64        `json:"deadline"`
	Raw        hexutil.Bytes `json:"signedTransaction"`
}
type Body struct {
	Intervention *DynamicFeeOff      `json:"intervention,omitempty"`
	Schema       string              `json:"schema"`
	Origin       Origin              `json:"origin"`
	Checkpoint   prestate.Checkpoint `json:"checkpoint"`
	Parent       json.RawMessage     `json:"parent"`
	ChainConfig  hexutil.Bytes       `json:"chainConfig"`
	Inventory    Inventory           `json:"inventory"`
	Release      string              `json:"releaseManifestSha256"`
	Pool         common.Hash         `json:"poolId"`
	Configs      Configurations      `json:"configurations"`
	Setup        Setup               `json:"commonSetup"`
	Actions      []Action            `json:"actions"`
	Environment  Environment         `json:"environment"`
	Engine       Identity            `json:"engine"`
	Limits       Limits              `json:"limits"`
}
type Spec struct {
	Body
	Commitment string `json:"scenarioCommitment"`
}

// Canonical sorts object keys, retains integer precision and never depends on locale.
func Canonical(v any) ([]byte, error) {
	raw, e := json.Marshal(v)
	if e != nil {
		return nil, e
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	var value any
	if e = d.Decode(&value); e != nil {
		return nil, e
	}
	var out bytes.Buffer
	encoder := json.NewEncoder(&out)
	encoder.SetEscapeHTML(false)
	if e = encoder.Encode(value); e != nil {
		return nil, e
	}
	return bytes.TrimSuffix(out.Bytes(), []byte{'\n'}), nil
}
func digest(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func hashValue(domain string, v any) string {
	raw, e := Canonical(v)
	if e != nil {
		panic(e)
	}
	return digest(append([]byte(domain+"\n"), raw...))
}
func Commit(b Body) Spec       { return Spec{b, hashValue(b.Schema, b)} }
func ActionID(a Action) string { a.ID = ""; return hashValue(Domain+"/action", a) }
func decimal(s string) (*big.Int, error) {
	if !regexp.MustCompile(`^(0|[1-9][0-9]{0,77})$`).MatchString(s) {
		return nil, errors.New("DECIMAL_REQUIRED")
	}
	v, ok := new(big.Int).SetString(s, 10)
	if !ok || v.BitLen() > 256 {
		return nil, errors.New("UINT256_REQUIRED")
	}
	return v, nil
}
func pin(s string) bool {
	return regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(s) && s != string(bytes.Repeat([]byte{'0'}, 64))
}

func Parse(raw []byte) (Spec, error) {
	var s Spec
	if len(raw) > 48<<20 {
		return s, errors.New("SPEC_SIZE")
	}
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
				return s, errors.New("JSON_DEPTH")
			}
		} else if c == '}' || c == ']' {
			depth--
		}
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if e := d.Decode(&s); e != nil {
		return s, e
	}
	var tail any
	if d.Decode(&tail) != io.EOF {
		return s, errors.New("JSON_TRAILING")
	}
	c, e := Canonical(s)
	if e != nil {
		return s, e
	}
	if !bytes.Equal(raw, append(c, '\n')) {
		return s, errors.New("CANONICAL_SPEC_REQUIRED")
	}
	if (s.Schema != Domain && s.Schema != DynamicDomain) || (s.Schema == Domain && s.Intervention != nil) || (s.Schema == DynamicDomain && s.Intervention == nil) || s.Commitment != hashValue(s.Schema, s.Body) {
		return s, errors.New("SCENARIO_DOMAIN_OR_COMMITMENT")
	}
	return s, nil
}

type profile struct {
	Kind     string
	Manifest json.RawMessage `json:"manifest"`
	Pool     common.Hash     `json:"poolId"`
	PoolKey  struct {
		Currency0, Currency1, Hooks common.Address
		Fee                         uint64
		TickSpacing                 int64
	} `json:"poolKey"`
	RootSlot      common.Hash     `json:"rootRecordSlot"`
	ConfigSlot    common.Hash     `json:"configSlot"`
	BaselineWords []common.Hash   `json:"baselineConfigWords"`
	RootCaps      common.Hash     `json:"rootCapsWord"`
	BaseLpFee     uint64          `json:"baseLpFeePips"`
	SwapABI       json.RawMessage `json:"swapAbi"`
	Pins          map[common.Address]common.Hash
}

func officialProfile() profile {
	var p profile
	if e := json.Unmarshal(profileJSON, &p); e != nil {
		panic(e)
	}
	var manifest struct {
		Contracts []struct {
			Role        string
			Address     common.Address
			RuntimeHash common.Hash
		}
	}
	if e := json.Unmarshal(p.Manifest, &manifest); e != nil {
		panic(e)
	}
	p.Kind = "AUTHENTICATED_CHECKPOINT_SCENARIO"
	p.Pins = map[common.Address]common.Hash{}
	for _, c := range manifest.Contracts {
		if c.Role == "root" || c.Role == "router" || c.Role == "poolManager" || c.Address == rulesAddress {
			p.Pins[c.Address] = c.RuntimeHash
		}
	}
	// Other releases' Rules entries are not execution targets for this profile.
	for a := range p.Pins {
		if a != p.PoolKey.Hooks && a != rulesAddress && a != routerAddress && a != managerAddress {
			delete(p.Pins, a)
		}
	}
	return p
}

var rulesAddress = common.HexToAddress("0x4a71c270b1520f94064268102aebd744b0de7942")
var routerAddress = common.HexToAddress("0xc2bc9a3fe6c4ce8c2f7eb4655b0869b01d8c93c9")
var managerAddress = common.HexToAddress("0x8366a39cc670b4001a1121b8f6a443a643e40951")
var lpMask = new(big.Int).Lsh(big.NewInt(65535), 160)

func wordAt(first common.Hash, n int) common.Hash {
	return common.BigToHash(new(big.Int).Add(first.Big(), big.NewInt(int64(n))))
}

type admitted struct {
	spec         Spec
	parent       *types.Header
	configRaw    []byte
	profile      profile
	nodes, codes map[common.Hash]hexutil.Bytes
	world, phase string
	producerGate NativeGate
	discovery    *discoverySource
	diagnostic   *diagnosticLog
}
