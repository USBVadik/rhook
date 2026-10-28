// Bounded original-root pages for one supported executor and observed key family.
import assert from 'node:assert/strict';
export const EXECUTOR='0x4b4c16681401454140a9dbca55e5c186bbe8d728';
export const CODE_HASH='0xa454566f248677718ca1c6ed8df59e23bc6dc4b9f787a1c9bd687912d4ef508f';
export const OBSERVED_FAMILY='0x290decd9548b62a8d60345a988386fc84ba6bc95484008f6362f93160ef3';
const word=n=>'0x'+n.toString(16).padStart(64,'0');
const addr=a=>{assert(/^0x[0-9a-fA-F]{40}$/.test(a),'ADDRESS');return a.toLowerCase();};
const key=k=>{assert(/^0x[0-9a-fA-F]{64}$/.test(k),'STORAGE_KEY');return k.toLowerCase();};
export function policy(pageSize=8,scope='observed-family'){
 assert.equal(pageSize,8,'PAGE_SIZE');assert.equal(scope,'observed-family','SCOPE');
 return Object.freeze({pageSize,scope,maximumAdditionalKeys:32,maximumPages:4,keysPerProof:48});
}
// Pure scheduling only. A plan is not proof of any value or of its existence.
export function planPage(p,state,address,requested,isKnown){
 const a=addr(address),keys=requested.map(key);assert(keys.length<=48&&new Set(keys).size===keys.length,'REQUEST_KEYS');
 const base={address:a,requested:keys,fetchKeys:keys,pageKeys:[],extraKeys:[],addedKeys:[],reason:'EXACT_ONLY'};
 if(a!==EXECUTOR)return base;
 const missing=keys.filter(k=>!isKnown(k));if(!missing.length)return {...base,reason:'ALREADY_AUTHENTICATED'};
 const eligible=missing.find(k=>k.startsWith(OBSERVED_FAMILY));
 if(!eligible)return {...base,reason:'OUTSIDE_OBSERVED_FAMILY'};
 const first=BigInt(eligible)&~BigInt(p.pageSize-1),last=first+BigInt(p.pageSize-1);
 const pageKeys=Array.from({length:p.pageSize},(_,i)=>word(first+BigInt(i)));
 const addedKeys=pageKeys.filter(k=>!isKnown(k)&&!state.added.has(k));
 if(state.pages>=p.maximumPages||state.added.size+addedKeys.length>p.maximumAdditionalKeys)return {...base,reason:'READ_AHEAD_BUDGET_EXACT_ONLY'};
 const extraKeys=pageKeys.filter(k=>!isKnown(k)&&!keys.includes(k));
 return {...base,fetchKeys:[...new Set([...keys,...extraKeys])],pageKeys,extraKeys,addedKeys,reason:'PAGE_ON_ACTUAL_MISS',start:word(first),end:word(last)};
}

// The serialized broker is the intended owner. Concurrent fetches are rejected.
export class PageOnMiss{
 constructor(collector,p){
  assert.deepEqual(p,policy(p.pageSize,p.scope),'FIXED_READ_AHEAD_BOUNDS');
  assert.equal(collector.checkpoint.chainId,4663,'CHAIN');
  const a=collector.project(EXECUTOR,[]);assert(a,'EXECUTOR_ACCOUNT_UNAUTHENTICATED');assert.equal(a.verified.account.codeHash,CODE_HASH,'EXECUTOR_RUNTIME_CHANGED');
  this.checkpoint=Object.freeze(structuredClone(collector.checkpoint));this.policy=policy(p.pageSize,p.scope);this.state={pages:0,added:new Set()};this.events=[];this.active=false;
 }
 async fetch(collector,address,requested){
  assert(!this.active,'SERIALIZED_FETCH_REQUIRED');assert.deepEqual(collector.checkpoint,this.checkpoint,'CHECKPOINT_DRIFT');
  const a=addr(address),p=planPage(this.policy,this.state,a,requested,k=>collector.project(a,[k])!==null),event={...p,status:'PLANNED'};
  this.active=true;this.events.push(event);
  try{
   for(let i=0;i<p.fetchKeys.length;i+=48)await collector.proof(a,p.fetchKeys.slice(i,i+48));
   if(!p.fetchKeys.length)await collector.proof(a,[]);
   if(p.pageKeys.length)assert(collector.project(a,p.pageKeys),'ENTIRE_PAGE_AUTHENTICATION_REQUIRED');
   const result=collector.project(a,p.requested);assert(result,'REQUEST_PROJECTION');
   if(p.pageKeys.length){this.state.pages++;for(const k of p.addedKeys)this.state.added.add(k);}
   event.status='AUTHENTICATED';return result.proof;
  }catch(e){event.status='REJECTED';event.cause=String(e.message).slice(0,400);throw e;}
  finally{this.active=false;}
 }
 snapshot(){return {checkpoint:this.checkpoint,policy:this.policy,pages:this.state.pages,additionalKeys:this.state.added.size,events:structuredClone(this.events),completeWitness:false};}
}
