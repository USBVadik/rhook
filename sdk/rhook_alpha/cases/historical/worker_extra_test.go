package main

import (
 "errors"
 "testing"
 "github.com/ethereum/go-ethereum/common"
 prestate "local/rhook-robinhood"
)
type closeFailure struct{*fakeWorld}
func(w *closeFailure)Close()error{return errors.New("exact-close-failure")}
func TestHistoricalCleanupFailureClosesBranch(t *testing.T){
 p:=syntheticPlan();w:=&closeFailure{&fakeWorld{result:goodActual(p)}};n:=0
 c:=pair{plan:p,dir:t.TempDir(),factory:func()(world,error){n++;return w,nil}}
 out,e:=c.run();if e!=nil||n!=1||out.Counts.Branch!=0||out.Terminal!="INTERRUPTED_UNVERIFIED"{t.Fatalf("cleanup bypass %+v %v",out,e)}
}
func TestHistoricalDerivedRootAndWitnessEvidenceAreRequired(t *testing.T){
 for _,bad:=range []string{"initial-root","original-root","witness"}{t.Run(bad,func(t *testing.T){
 p:=syntheticPlan();p.Witness="witness";p.Checkpoint.StateRoot=common.Hash{7}
 a:=&fakeWorld{result:goodActual(p)}
 b:=&fakeWorld{result:&prestate.HistoricalDynamicResult{CalibrationResult:&prestate.CalibrationResult{World:"BRANCH",Transactions:p.Transactions,InputCommitment:p.Input},Patch:&prestate.HistoricalDynamicOverlay{Intervention:p.Intervention,SemanticInitialWrites:2,OriginalWitnessUnchanged:true,OriginalWitnessCommitment:p.Witness,OriginalRoot:p.Checkpoint.StateRoot,InitialRoot:common.Hash{9}}}}
 switch bad{case "initial-root":b.result.Patch.InitialRoot=common.Hash{};case "original-root":b.result.Patch.OriginalRoot=common.Hash{};case "witness":b.result.Patch.OriginalWitnessCommitment="wrong"}
 n:=0;c:=pair{plan:p,dir:t.TempDir(),factory:func()(world,error){n++;if n==1{return a,nil};return b,nil}}
 out,e:=c.run();if e!=nil||out.Terminal!="BRANCH_STOP"{t.Fatalf("incomplete typed evidence accepted %+v %v",out,e)}
 })}
}
