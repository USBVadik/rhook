package main

import (
 "errors"
 "fmt"
 "math/big"
 "testing"
 "github.com/ethereum/go-ethereum/common"
 "github.com/ethereum/go-ethereum/core"
 "github.com/ethereum/go-ethereum/core/types"
 "github.com/ethereum/go-ethereum/core/vm"
)
func TestInvalidationClassifierRejectsExecutionAndUnchangedLookingErrors(t *testing.T){
 tx:=types.NewTx(&types.DynamicFeeTx{ChainID:big.NewInt(4663)})
 zero:=common.Hash{};changed:=common.HexToHash("0x01")
 cases:=[]struct{name string;err error;post common.Hash;gasAfter,usedAfter uint64;entries,ops int;accept bool}{
  {"native nonce before execution",fmt.Errorf("wrapped: %w",core.ErrNonceTooHigh),zero,100,0,0,0,true},
  {"native balance before execution",core.ErrInsufficientFunds,zero,100,0,0,0,true},
  {"unknown unchanged error",errors.New("native failure"),zero,100,0,0,0,false},
  {"lookalike error text",errors.New(core.ErrNonceTooHigh.Error()),zero,100,0,0,0,false},
  {"EVM revert",vm.ErrExecutionReverted,zero,100,0,0,0,false},
  {"post-purchase intrinsic failure",core.ErrIntrinsicGas,zero,100,0,0,0,false},
  {"state changed",core.ErrNonceTooHigh,changed,100,0,0,0,false},
  {"gas pool changed",core.ErrNonceTooHigh,zero,99,0,0,0,false},
  {"cumulative gas changed",core.ErrNonceTooHigh,zero,100,1,0,0,false},
  {"EVM entered",core.ErrNonceTooHigh,zero,100,0,1,0,false},
  {"opcode executed",core.ErrNonceTooHigh,zero,100,0,0,1,false},
 }
 for _,c:=range cases{t.Run(c.name,func(t *testing.T){accepted:=false;func(){defer func(){_ = recover()}();label:=qualifyInvalidation(c.err,tx,zero,c.post,100,c.gasAfter,0,c.usedAfter,c.entries,c.ops);accepted=label!=""}();if accepted!=c.accept{t.Fatalf("accepted=%v want=%v",accepted,c.accept)}})}
}
