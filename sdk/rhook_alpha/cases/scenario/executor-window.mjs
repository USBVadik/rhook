// Preserve the original initial hints; extend by pages on genuine cache misses.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {hash} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {PageOnMiss,policy,EXECUTOR,CODE_HASH,OBSERVED_FAMILY} from './page-on-miss.mjs';
export const WINDOW=Object.freeze(JSON.parse(fs.readFileSync(new URL('./executor-window.json',import.meta.url))));
const word=n=>'0x'+n.toString(16).padStart(64,'0');
const initial=()=>Array.from({length:27},(_,i)=>word(BigInt(hash(WINDOW.start))+BigInt(i)));
assert.equal(initial().at(-1),WINDOW.end);assert.equal(WINDOW.address,EXECUTOR);assert.equal(WINDOW.codeHash,CODE_HASH);
assert.equal(WINDOW.observedFamilyPrefix,OBSERVED_FAMILY);assert.equal(WINDOW.pageSize,8);assert.equal(WINDOW.maximumPages,4);
assert.equal(WINDOW.maximumAdditionalKeys,32);assert.equal(WINDOW.maximumWindowKeys,59);assert.equal(WINDOW.maximumKeysPerProof,48);
export function addExecutorWindow(subjects,checkpoint,poolId){
 assert.equal(checkpoint.chainId,WINDOW.chainId,'EXECUTOR_WINDOW_CHAIN');assert.equal(poolId,WINDOW.poolId,'EXECUTOR_WINDOW_POOL');
 if(!subjects.has(WINDOW.address))subjects.set(WINDOW.address,new Set());
 for(const key of initial())subjects.get(WINDOW.address).add(key);
}
export class ExecutorWindow extends PageOnMiss{
 constructor(collector){
  assert(collector.project(WINDOW.address,initial()),'INITIAL_WINDOW_UNAUTHENTICATED');
  super(collector,policy());
 }
 snapshot(){return {...super.snapshot(),profile:WINDOW.schema,address:WINDOW.address,codeHash:WINDOW.codeHash,
  initialStart:WINDOW.start,initialEnd:WINDOW.end,initialWindowKeys:27,
  maximumTotalWindowKeys:59,totalWindowKeysUpperBound:27+this.state.added.size,
  coverage:'AUTHENTICATED_ORIGINAL_ROOT_PAGES_ONLY_NOT_COMPLETE_SCENARIO'};}
}
