// Reserve one shared RPC slot for the required final pinned-header check.
import assert from 'node:assert/strict';
export function reserveFinalHeader(raw){
 let ordinaryIssued=0,finalIssued=0,checkpoint=null;
 const reservation=()=>({maximumTotalRequests:64,reservedFinalHeaderRequests:1,maximumOrdinaryRequests:63,
  ordinaryIssued,finalIssued,finalHeaderUsed:finalIssued===1});
 return {...raw,
  call:async(method,params)=>{
   assert.equal(finalIssued,0,'ACQUISITION_ALREADY_FINALIZED');
   assert(ordinaryIssued<63,'RPC_BUDGET_RESERVED_FINAL_HEADER');
   // Count issuance before awaiting the raw client's asynchronous dispatch gate.
   ordinaryIssued++;return raw.call(method,params);
  },
  pinCheckpoint:(cp,...rest)=>{
   if(checkpoint)assert.deepEqual(checkpoint,cp,'RESERVATION_CHECKPOINT_DRIFT');
   else checkpoint=Object.freeze(structuredClone(cp));
   return raw.pinCheckpoint(cp,...rest);
  },
  finalHeader:async number=>{
   assert(checkpoint,'PINNED_CHECKPOINT_REQUIRED');assert.equal(finalIssued,0,'FINAL_HEADER_ALREADY_ISSUED');
   assert.equal(Number(BigInt(number)),checkpoint.blockNumber,'FINAL_HEADER_SELECTOR');
   assert(raw.stats().inFlight===0&&raw.stats().requests<=63,'FINAL_HEADER_PENDING_OR_BUDGET_DRIFT');
   finalIssued=1;return raw.call('eth_getBlockByNumber',[number,false]);
  },reservation};
}
