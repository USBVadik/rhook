package prestate

import (
 "encoding/json"
 "os"
 "testing"
 "github.com/ethereum/go-ethereum/common"
 "github.com/ethereum/go-ethereum/core/state"
)

func TestHistoricalExactRelation(t *testing.T){
 i:=historicalExpected();i.Commitment=HistoricalTransformCommitment(i)
 if e:=ValidateHistoricalDynamic(i,i.Checkpoint,i.RulesCode);e!=nil{t.Fatal(e)}
 for _,change:=range []string{"root","code","lp","lane","extra","missing","reversed","commitment"}{t.Run(change,func(t *testing.T){
  raw,_:=json.Marshal(i);var v HistoricalDynamicOff;_ = json.Unmarshal(raw,&v)
  switch change{
  case "root":v.Checkpoint.StateRoot=common.Hash{1}
  case "code":v.RootCode=common.Hash{1}
  case "lp":v.Writes[0].After[11]=49
  case "lane":v.Writes[1].After[0]=0
  case "extra":v.Writes=append(v.Writes,v.Writes[0])
  case "missing":v.Writes=v.Writes[:1]
  case "reversed":v.Writes[0],v.Writes[1]=v.Writes[1],v.Writes[0]
  case "commitment":v.Commitment="wrong"
  }
  if change!="commitment"{v.Commitment=HistoricalTransformCommitment(v)}
  if ValidateHistoricalDynamic(v,i.Checkpoint,i.RulesCode)==nil{t.Fatal("extra or inconsistent relation admitted")}
 })}
}

// Original saved state is authenticated and patched in memory only. No call to
// RunHistoricalDynamic, RunCanonical, ProduceBlock or an EVM occurs in this test.
func TestHistoricalOverlayAdmissionAndInitialRootOnly(t *testing.T){
 file:=os.Getenv("RHOOK_HISTORICAL_TEST_PACKAGE");if file==""{t.Skip("explicit retained fixture required")}
 raw,e:=os.ReadFile(file);if e!=nil{t.Fatal(e)}
 p,e:=PrepareOfflineCalibration(raw,HistoricalInput,HistoricalWitness);if e!=nil{t.Fatal(e)}
 defer CloseHistoricalBridge(p.Bridge)
 i:=historicalExpected();i.Commitment=HistoricalTransformCommitment(i)
 if e=p.Bridge.Protect(func()error{return CheckHistoricalDynamic(p.Bridge,i,i.RulesCode)});e!=nil{t.Fatal(e)}
 var overlay *HistoricalDynamicOverlay
 if e=p.Bridge.Protect(func()error{var e error;overlay,e=applyHistoricalDynamic(p.Bridge,i);return e});e!=nil{t.Fatal(e)}
 if overlay.InitialRoot==(common.Hash{})||overlay.InitialRoot==i.Checkpoint.StateRoot||overlay.SemanticInitialWrites!=2||!overlay.OriginalWitnessUnchanged||overlay.OriginalWitnessCommitment!=HistoricalWitness{t.Fatalf("bad overlay: %+v",overlay)}
 t.Logf("OFFLINE_DERIVED_INITIAL_ROOT=%s; EVM_INVOCATIONS=0",overlay.InitialRoot)
}

func TestHistoricalSecondWordMismatchIsAtomic(t *testing.T){
 file:=os.Getenv("RHOOK_HISTORICAL_TEST_PACKAGE");if file==""{t.Skip("explicit retained fixture required")}
 raw,e:=os.ReadFile(file);if e!=nil{t.Fatal(e)}
 p,e:=PrepareOfflineCalibration(raw,HistoricalInput,HistoricalWitness);if e!=nil{t.Fatal(e)};defer CloseHistoricalBridge(p.Bridge)
 i:=historicalExpected();i.Commitment=HistoricalTransformCommitment(i)
 var s *state.StateDB
 e=p.Bridge.Protect(func()error{
  var e error;s,e=p.Bridge.State();if e!=nil{return e};s.SetState(i.Writes[1].Address,i.Writes[1].Slot,common.Hash{})
  _,e=applyHistoricalDynamic(p.Bridge,i)
  if e!=nil{return e}
  return nil
 });if e==nil{t.Fatal("inconsistent second word accepted")}
 if s.GetState(i.Writes[0].Address,i.Writes[0].Slot)!=i.Writes[0].Before{t.Fatal("first word changed before complete authentication")}
}
