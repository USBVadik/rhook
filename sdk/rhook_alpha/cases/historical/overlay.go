// Staged into the retained prestate package only for the historical derivative.
package prestate

import (
 "bytes"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "math/big"
 "github.com/ethereum/go-ethereum/common"
 "github.com/ethereum/go-ethereum/core/state"
 "github.com/ethereum/go-ethereum/crypto"
)

const HistoricalDynamicDomain = "rhook/hookr-historical-dynamic-fee-off/0.1"
const HistoricalPackageSHA = "b55ba3a6d70bd081148966f3b447135a098a26c18bae0c773f065beda807bda3"
const HistoricalInput = "d8e00b18493247235f25bc4d0804449b3918763909c25dd03353e3df6cf135b2"
const HistoricalWitness = "8cc51fe2215ec68af17e0735ee5fbe1e21c71e26de05a68ea85099373cede615"
type HistoricalWrite struct { Address common.Address `json:"address"`; Slot common.Hash `json:"slot"`; Before common.Hash `json:"before"`; After common.Hash `json:"after"` }
type HistoricalDynamicOff struct {
 Schema string `json:"schema"`
 Checkpoint Checkpoint `json:"checkpoint"`
 Pool common.Hash `json:"pool"`
 RootCode common.Hash `json:"rootCodeHash"`
 RulesCode common.Hash `json:"rulesCodeHash"`
 Writes []HistoricalWrite `json:"writes"`
 Commitment string `json:"interventionCommitment,omitempty"`
}
type HistoricalDynamicOverlay struct {
 Intervention HistoricalDynamicOff `json:"intervention"`
 SemanticInitialWrites int `json:"semanticInitialWrites"`
 OriginalWitnessUnchanged bool `json:"originalWitnessUnchanged"`
 OriginalWitnessCommitment string `json:"originalWitnessCommitment"`
 OriginalRoot common.Hash `json:"originalRoot"`
 InitialRoot common.Hash `json:"initialRoot"`
 World string `json:"world"`
}
type HistoricalDynamicResult struct {
 *CalibrationResult
 Patch *HistoricalDynamicOverlay `json:"dynamicFeeOverlay,omitempty"`
}

func HistoricalTransformCommitment(i HistoricalDynamicOff) string {
 i.Commitment=""
 // Re-encode a map so keys match the SDK's sorted canonical JSON. All integer
 // values are small checkpoint numbers; words and hashes are strings.
 raw,_:=json.Marshal(i);var value any;_ = json.Unmarshal(raw,&value);raw,_=json.Marshal(value)
 h:=sha256.Sum256(append([]byte(HistoricalDynamicDomain+"/transform\n"),raw...));return hex.EncodeToString(h[:])
}
func EqualHistoricalDynamic(a,b HistoricalDynamicOff) bool {
 x,_:=json.Marshal(a);y,_:=json.Marshal(b);return bytes.Equal(x,y)
}
func historicalExpected() HistoricalDynamicOff {
 root:=common.HexToAddress("0x89c9fb50d1f03192230ffb1c279bb6e7d3fe6acc")
 return HistoricalDynamicOff{Schema:HistoricalDynamicDomain+"/transform",Checkpoint:Checkpoint{ChainID:4663,BlockNumber:93251802,BlockHash:common.HexToHash("0x991db6ee40bd7056cfabff012763a1b75995979e5023dc010553dbc304c16016"),StateRoot:common.HexToHash("0x9c63ad5d9c6ba4fd19c301ea35264cec28dd1ad0e951a5f5578af8a32131baa6")},Pool:hookrPoolID,
 RootCode:common.HexToHash("0xd336de325837e60a74cea11d87b5ebd1cc8961911f611f38de0508d23b6e779f"),RulesCode:hookrRulesCodeHash,
 Writes:[]HistoricalWrite{
 {hookrRules,hookrConfigSlot,common.HexToHash("0x0000000007d0000000000064000000020000000000000000002cec0000000000"),common.HexToHash("0x0000000007d0000000000064000000000000000000000000000bb80000000000")},
 {root,common.HexToHash("0xdc5740eeafc78ca4488605782bceeee21ea0cec0908c37bbb90fb77c45910409"),common.HexToHash("0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942"),common.HexToHash("0x020101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942")}}}
}
func ValidateHistoricalDynamic(i HistoricalDynamicOff,c Checkpoint,code common.Hash) error {
 expected:=historicalExpected();expected.Commitment=HistoricalTransformCommitment(expected)
 if c!=expected.Checkpoint||code!=expected.RulesCode||!EqualHistoricalDynamic(i,expected){return errors.New("EXACT_HISTORICAL_DYNAMIC_OFF_RELATION_REQUIRED")}
 return nil
}
func CheckHistoricalDynamic(b *Bridge,i HistoricalDynamicOff,code common.Hash) error {
 if e:=ValidateHistoricalDynamic(i,b.checkpoint,code);e!=nil{return e}
 st,e:=b.State();if e!=nil{return e}
 for n,w:=range i.Writes {expected:=i.RulesCode;if n==1{expected=i.RootCode}
  if !st.Exist(w.Address)||st.GetCodeHash(w.Address)!=expected||crypto.Keccak256Hash(st.GetCode(w.Address))!=expected||st.GetState(w.Address,w.Slot)!=w.Before{return b.stop("DYNAMIC_ORIGINAL_ACCOUNT_CODE_WORD",nil)}
 }
 return st.Error()
}
// Read-only guard is performed for the complete pair before either SetState.
func applyHistoricalDynamic(b *Bridge,i HistoricalDynamicOff) (*HistoricalDynamicOverlay,error) {
 if e:=CheckHistoricalDynamic(b,i,i.RulesCode);e!=nil{return nil,e}
 if b.lpPatched{return nil,b.stop("INITIAL_OVERLAY_ALREADY_APPLIED",nil)}
 st,e:=b.State();if e!=nil{return nil,e};before,_:=b.WitnessSnapshot()
 type account struct{nonce uint64;balance *big.Int;code common.Hash}
 originals:=make([]account,2)
 for n,w:=range i.Writes{originals[n]=account{st.GetNonce(w.Address),new(big.Int).Set(st.GetBalance(w.Address).ToBig()),st.GetCodeHash(w.Address)}}
 for _,w:=range i.Writes{st.SetState(w.Address,w.Slot,w.After)}
 st.Finalise(true);b.lpPatched=true
 for n,w:=range i.Writes{a:=originals[n];if st.GetState(w.Address,w.Slot)!=w.After||st.GetCommittedState(w.Address,w.Slot)!=w.After||st.GetNonce(w.Address)!=a.nonce||st.GetBalance(w.Address).ToBig().Cmp(a.balance)!=0||st.GetCodeHash(w.Address)!=a.code{return nil,b.stop("DYNAMIC_OVERLAY_PRESERVATION",nil)}}
 initial:=st.IntermediateRoot(true)
 if e=st.Error();e!=nil{return nil,b.stop("TRIE_UPDATE_PREIMAGE_UNAVAILABLE",e)}
 after,_:=b.WitnessSnapshot();if before!=after{return nil,b.stop("DYNAMIC_ORIGINAL_WITNESS_CHANGED",nil)}
 if initial==i.Checkpoint.StateRoot{return nil,b.stop("DYNAMIC_DERIVED_ROOT_UNCHANGED",nil)}
 b.guard();return &HistoricalDynamicOverlay{i,2,true,before,i.Checkpoint.StateRoot,initial,"HYPOTHETICAL_CHECKPOINT_BRANCH"},nil
}
func RunHistoricalDynamic(c *Candidate,b *Bridge,i *HistoricalDynamicOff,o EconomicObservationPlan,code common.Hash) (*HistoricalDynamicResult,error) {
 var patch *HistoricalDynamicOverlay
 r,e:=runObservedBlock(c,b,o,func()(*CalibrationResult,error){
  if i==nil{return RunCanonical(c,b)}
  if e:=ValidateHistoricalDynamic(*i,c.checkpoint,code);e!=nil{return nil,e}
  return runNativeBlockWithOverlay(c,b,func(b *Bridge)error{var e error;patch,e=applyHistoricalDynamic(b,*i);return e})
 })
 if r==nil{return nil,e};return &HistoricalDynamicResult{r,patch},e
}
var ErrHistoricalBridgeCleanup = errors.New("HISTORICAL_BRIDGE_CLEANUP_UNCONFIRMED")
func CloseHistoricalBridge(b *Bridge) error{e:=errors.Join(b.tdb.Close(),b.disk.Close());if e!=nil{return errors.Join(ErrHistoricalBridgeCleanup,e)};return nil}

// state is imported for the compile-time API assertion, not EVM execution.
var _ interface{IntermediateRoot(bool) common.Hash}=(*state.StateDB)(nil)
