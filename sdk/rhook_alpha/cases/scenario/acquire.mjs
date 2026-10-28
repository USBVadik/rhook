import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {headerHash} from '../../../engine/plan_native/ethereum.mjs';
import {writeNew} from '../witness/files.mjs';
import {ProofCollector} from '../witness/collector.mjs';
import {C,chunkSlots} from '../witness/material.mjs';
import {configProfile} from '../witness/profile.mjs';
import {buildSpec,profile,word,actor,intent,canonical} from './build.mjs';
import {addHistorySubject,addActionSubjects,FILTER_ADDRESS} from './system.mjs';
import {mergeHints,initialRuleKeys,groupSubjects,prefetch} from './prefetch.mjs';
import {addExecutorWindow,WINDOW} from './executor-window.mjs';
import {reserveFinalHeader} from './checkpoint-budget.mjs';
const catalogue=JSON.parse(fs.readFileSync(new URL('./prefetch.json',import.meta.url)));
const traceHints=JSON.parse(fs.readFileSync(new URL('./trace-hints.json',import.meta.url)));
export async function acquire(rawClient,value,engine,output,{discover}={}){
 const client=reserveFinalHeader(rawClient);
 intent(value);const began=Number(process.hrtime.bigint()/1000000n),save=(n,v)=>writeNew(path.join(output,n),Buffer.from(canonical(v)+'\n'));let collector=null,checkpoint=null,parent=null,error=null;
 async function each(items,fn){let index=0,failure=null;await Promise.all([0,1].map(async()=>{while(!failure&&index<items.length){const item=items[index++];try{await fn(item);}catch(e){failure??=e;client.stop(e);}}}));if(failure)throw failure;}
 try{
  assert.equal(await client.call('eth_chainId',[]),'0x1237','CHAIN_ID');parent=await client.call('eth_getBlockByNumber',['latest',false]);
  assert.equal(headerHash(parent),parent.hash,'CHECKPOINT_HEADER_HASH');checkpoint={chainId:4663,blockNumber:Number(BigInt(parent.number)),blockHash:parent.hash,stateRoot:parent.stateRoot};client.pinCheckpoint(checkpoint,parent.timestamp);save('CHECKPOINT.json',{checkpoint,parent});
  collector=new ProofCollector(checkpoint,client.call);
  const subjects=mergeHints(catalogue.subjects,traceHints,{chainId:checkpoint.chainId,poolId:value.poolId});
  addExecutorWindow(subjects,checkpoint,value.poolId);
  save('EXECUTOR_WINDOW_PLAN.json',{...WINDOW,checkpoint,coverage:'HINTS_ONLY_FRESH_AUTHENTICATION_REQUIRED'});
  const configKeys=[0,1,2,3].map(i=>word(BigInt(C.slot)+BigInt(i)));
  const original=await collector.proof(C.rules,initialRuleKeys(subjects,C.rules,configKeys));assert.equal(original.account.codeHash,C.rulesCode,'RULES_CODE_IDENTITY');
  const words=configKeys.map(key=>word(BigInt(original.resolutions.find(r=>r.key===key).value)));assert.deepEqual(words,profile.baselineConfigWords,'SUPPORTED_ORIGINAL_CONFIGURATION');
  // The start-block writes the current parent's history-ring position. Old
  // catalogue slots authenticate different blocks and cannot cover this read.
  const draft=await buildSpec(value,parent,checkpoint,[],[],'0x',words,engine);
  const filterKeysBefore=new Set(subjects.get(FILTER_ADDRESS)??[]);
  const history=addHistorySubject(subjects,checkpoint),filters=addActionSubjects(subjects,draft.actions);
  save('SYSTEM_DEPENDENCIES.json',{history,filters,source:'PINNED_ARBOS61_HISTORY_AND_TRANSACTION_FILTER',meaning:'Subject hints only; authenticate each proof at this checkpoint'});
  for(const address of [actor(),C.filtered,C.rules,C.root,C.arbos,...profile.manifest.contracts.filter(c=>['router','poolManager'].includes(c.role)).map(c=>c.address),profile.poolKey.currency1])if(!subjects.has(address))subjects.set(address,new Set());
  for(const slot of [C.version,C.length,C.gas,...chunkSlots(640)])subjects.get(C.arbos).add(slot);
  for(const slot of [profile.rootRecordSlot,word(BigInt(profile.rootRecordSlot)+1n),C.executorSlot,C.executorHashSlot])subjects.get(C.root).add(slot);
  const plan=groupSubjects(subjects,checkpoint);save('PREFETCH_PLAN.json',plan);
  await prefetch(collector,plan,each);
  const addedFilterKeys=new Set(filters.map(r=>r.slot).filter(k=>!filterKeysBefore.has(k)));
  let additionalStorageEntriesJsonBytes=0;
  for(const row of collector.proofs.filter(r=>r.address===FILTER_ADDRESS)){
   const old={...row.proof,storageProof:row.proof.storageProof.filter(r=>!addedFilterKeys.has(word(BigInt(r.key))))};
   additionalStorageEntriesJsonBytes+=Buffer.byteLength(JSON.stringify(row.proof))-Buffer.byteLength(JSON.stringify(old));
  }
  save('FILTER_PREFETCH_MEASUREMENTS.json',{addedSlots:[...addedFilterKeys],
   scheduledExtraGroupedRequests:Math.ceil(subjects.get(FILTER_ADDRESS).size/48)-Math.ceil(filterKeysBefore.size/48),
   observedFilterProofRequests:client.observations().filter(r=>r.method==='eth_getProof'&&r.params[0]===FILTER_ADDRESS).length,
   additionalStorageEntriesJsonBytes,meaning:'Measured JSON bytes of added storage entries in retained authenticated proofs; excludes headers and any counterfactual provider compression'});
  const arb=await collector.proof(C.arbos,[C.version,C.length]);assert.equal(arb.resolutions[0].value,'61','ARBOS_PROFILE');const length=Number(arb.resolutions[1].value);const chunks=await collector.proof(C.arbos,chunkSlots(length));
  const config=Buffer.concat(chunks.resolutions.map((r,i)=>Buffer.from(BigInt(r.value).toString(16).padStart(64,'0'),'hex').subarray(32-Math.min(32,length-i*32))));
  assert.deepEqual(configProfile(JSON.parse(config)),[],'CHAIN_CONFIG_PROFILE');
  const absence=await collector.proof(actor(),[]);assert.equal(absence.account.status,'ABSENT','PUBLIC_SIMULATION_ACTOR_MUST_BE_ABSENT');
  await each([...subjects.keys()],a=>collector.code(a));
  if(discover){
   const provisional=await buildSpec(value,parent,checkpoint,[...collector.nodes.values()],[...collector.codes.values()],'0x'+config.toString('hex'),words,engine);
   await discover(provisional,collector);
  }
  const again=await client.finalHeader(parent.number);assert.equal(headerHash(again),parent.hash,'CHECKPOINT_REORG_OR_HEADER_MISMATCH');
  const spec=await buildSpec(value,parent,checkpoint,[...collector.nodes.values()],[...collector.codes.values()],'0x'+config.toString('hex'),words,engine);save('SCENARIO.json',spec);
  return {status:'AUTHENTICATED_SCENARIO_CAPTURED',scenarioCommitment:spec.scenarioCommitment,checkpoint,originalLpBps:100,variantLpBps:value.lpBps,poolId:profile.poolId,coverage:'ORIGINAL_ROOT_PREFETCH_ONLY_EXECUTION_CLOSURE_UNKNOWN',nativeExecutions:discover?null:0,nativeExecutionAccounting:discover?'DISCOVERY_WORKER_COMPLETION_REQUIRED':'NONE_READ_ONLY'};
 }catch(e){error=e;client.stop(e);throw e;}finally{
  if(collector)save('CHECKPOINT_STATE.json',{schema:'rhook/authenticated-scenario-state/0.1',checkpoint,parent,nodes:[...collector.nodes.values()],codes:[...collector.codes.values()],proofs:collector.proofs,projections:collector.projections,counts:collector.counts,coverage:'UNKNOWN_UNTIL_FRESH_OFFLINE_EXECUTION'});
  if(error?.missingDependency)save('MISSING_DEPENDENCY.json',error.missingDependency);
  save('FINAL_HEADER_RESERVATION.json',client.reservation());
  save('ACQUISITION_TIMING.json',{beganMonotonicMs:began,endedMonotonicMs:Number(process.hrtime.bigint()/1000000n),checkpoint,requests:client.observations(),budget:client.stats()});
 }
}
