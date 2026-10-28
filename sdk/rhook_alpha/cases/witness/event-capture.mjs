import assert from 'node:assert/strict';
import {headerHash} from '../../../engine/plan_native/ethereum.mjs';
import {authenticatePoolEvent} from './events.mjs';
import {checkHeaders} from './material.mjs';
import {validateNotification,WATCH_LIMITS} from './watch.mjs';
export function checkFreeAccount(value,now=Date.now()){
  assert(value?.schema==='rhook/alchemy-free-assertions/0.1'&&value.freePlan===true&&value.paidUsageDisabled===true&&value.chainId===4663&&typeof value.websocketEntitled==='boolean','CONFIRMED_FREE_WSS_ACCOUNT_REQUIRED');
  assert(Number.isSafeInteger(value.remainingCU)&&value.remainingCU>=(value.websocketEntitled?WATCH_LIMITS.estimatedFreeCU:0),'FREE_CU_RESERVE');
  assert(Number.isSafeInteger(value.observedUnixMs)&&value.observedUnixMs<=now&&now-value.observedUnixMs<=600000,'FRESH_ACCOUNT_OBSERVATION_REQUIRED');
  return {freePlan:true,paidUsageDisabled:true,chainId:4663,websocketEntitled:value.websocketEntitled,remainingCU:value.remainingCU,observedUnixMs:value.observedUnixMs,sessionEstimatedCUBudget:value.websocketEntitled?WATCH_LIMITS.estimatedFreeCU:0};
}
export async function authenticateNotification(client,found,{now=()=>Number(process.hrtime.bigint()/1000000n)}={}){
  const log=validateNotification(found.notification);assert(log,'SUPPORTED_EVENT_REQUIRED');
  const block=await client.call('eth_getBlockByHash',[log.blockHash,true]);assert.equal(headerHash(block),log.blockHash,'NOTIFICATION_BLOCK_HASH');assert.equal(block.number,log.blockNumber,'NOTIFICATION_BLOCK_NUMBER');
  const parent=await client.call('eth_getBlockByHash',[block.parentHash,false]);const pinnedAt=now();
  const checkpoint={chainId:4663,blockNumber:Number(BigInt(block.number))-1,blockHash:parent.hash,stateRoot:parent.stateRoot};
  checkHeaders({checkpoint,parent,block});
  const receipts=await client.call('eth_getBlockReceipts',[block.hash]);
  const selected=authenticatePoolEvent(block,receipts,log);assert(selected,'NOTIFICATION_EVENT_NOT_IN_RECEIPTS');
  return {...selected,observedBlock:block,observedParent:parent,observedUnixMs:Date.now(),parentPinnedMonotonicMs:pinnedAt,
    eventReceivedMonotonicMs:found.eventReceivedMonotonicMs,eventReceivedUnixMs:found.eventReceivedUnixMs,discoveryMode:found.mode,checkpoint,
    latency:{eventToParentPinMs:pinnedAt-found.eventReceivedMonotonicMs,eventToReceiptAuthenticationMs:now()-found.eventReceivedMonotonicMs}};
}
