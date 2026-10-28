// Trace slots are acquisition hints. Values always come from fresh root-bound proofs.
import assert from 'node:assert/strict';
import {address,hash} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {HISTORY_ADDRESS,FILTER_ADDRESS} from './system.mjs';

export function mergeHints(base,hints,{chainId,poolId}){
 assert.equal(hints.schema,'rhook/scenario-trace-hints/0.1');
 assert.equal(hints.chainId,chainId,'PREFETCH_CHAIN');assert.equal(hints.poolId,poolId,'PREFETCH_POOL');
 assert.deepEqual(Object.keys(hints).sort(),['schema','chainId','poolId','source','subjects'].sort(),'PREFETCH_HINT_FIELDS');
 assert(Array.isArray(base)&&Array.isArray(hints.subjects)&&base.length+hints.subjects.length<=64,'PREFETCH_ACCOUNT_LIMIT');
 const subjects=new Map();let total=0;
 for(const [rows,trace] of [[base,false],[hints.subjects,true]])for(const row of rows){
  assert.deepEqual(Object.keys(row).sort(),['address','slots'],'PREFETCH_VALUES_FORBIDDEN');
  const a=address(row.address);assert(Array.isArray(row.slots)&&row.slots.length<=512,'PREFETCH_SLOT_LIMIT');
  if(trace)assert(![HISTORY_ADDRESS,FILTER_ADDRESS].includes(a),'SYSTEM_HINT_MUST_BE_DERIVED');
  if(!subjects.has(a))subjects.set(a,new Set());
  const keys=subjects.get(a);for(const raw of row.slots){const key=hash(raw);if(!keys.has(key)){keys.add(key);assert(++total<=512,'PREFETCH_SLOT_LIMIT');}}
 }
 return subjects;
}

export function initialRuleKeys(subjects,rules,mandatory){
 const first=[...new Set(mandatory.map(hash))];assert(first.length<=48,'RULES_BATCH_LIMIT');
 for(const key of [...(subjects.get(address(rules))??[])].sort())if(!first.includes(key)&&first.length<48)first.push(key);
 return first;
}

export function groupSubjects(subjects,checkpoint){
 assert.equal(checkpoint.chainId,4663);hash(checkpoint.blockHash);hash(checkpoint.stateRoot);
 const groups=[];let slotCount=0;
 for(const [raw,values] of subjects){
  const a=address(raw),keys=[...new Set([...values].map(hash))].sort();slotCount+=keys.length;
  assert(slotCount<=512,'PREFETCH_SLOT_LIMIT');
  if(!keys.length)groups.push({address:a,slots:[]});
  else for(let i=0;i<keys.length;i+=48)groups.push({address:a,slots:keys.slice(i,i+48)});
 }
 assert(groups.length<=64,'PREFETCH_BATCH_LIMIT');
 return {schema:'rhook/scenario-prefetch-plan/0.1',checkpoint:structuredClone(checkpoint),
  groups,accountCount:subjects.size,slotCount,proofBatches:groups.length,
  coverage:'HINTS_ONLY_AUTHENTICATION_AND_CLOSURE_REQUIRED'};
}

export async function prefetch(collector,plan,each){
 assert.deepEqual(plan.checkpoint,collector.checkpoint,'PREFETCH_CHECKPOINT');
 await each(plan.groups,({address,slots})=>collector.proof(address,slots));
}
