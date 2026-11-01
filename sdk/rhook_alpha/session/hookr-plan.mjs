// Hookr scenario profile: static original-state dependencies derived offline from one SCENARIO.json.
// Mirrors the prefetch subject set that scenario/acquire.mjs assembles before live acquisition, using the
// same exported helpers and catalogues, so a session can check which of those reads its seed answers.
// It authenticates the parent header against the checkpoint hash on the way (addSendMerkleSubjects).
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {C,chunkSlots} from '../cases/witness/material.mjs';
import {profile,word} from '../cases/scenario/build.mjs';
import {addHistorySubject,addActionSubjects} from '../cases/scenario/system.mjs';
import {mergeHints,initialRuleKeys,groupSubjects,addSendMerkleSubjects} from '../cases/scenario/prefetch.mjs';
import {addExecutorWindow} from '../cases/scenario/executor-window.mjs';

const read=name=>JSON.parse(fs.readFileSync(new URL(`../cases/scenario/${name}`,import.meta.url)));
const catalogue=read('prefetch.json'),traceHints=read('trace-hints.json');
export const CONFIG_KEYS=Object.freeze([0,1,2,3].map(i=>word(BigInt(C.slot)+BigInt(i))));

export function hookrStaticPlan(spec){
 const checkpoint=spec.checkpoint,parent=spec.parent;
 assert.equal(spec.poolId,profile.poolId,'UNSUPPORTED_POOL');
 const subjects=mergeHints(catalogue.subjects,traceHints,{chainId:checkpoint.chainId,poolId:spec.poolId});
 addExecutorWindow(subjects,checkpoint,spec.poolId);
 const rulesKeys=initialRuleKeys(subjects,C.rules,[...CONFIG_KEYS]);
 const history=addHistorySubject(subjects,checkpoint),filters=addActionSubjects(subjects,spec.actions);
 const actor=spec.commonSetup.actor;
 for(const address of [actor,C.filtered,C.rules,C.root,C.arbos,...profile.manifest.contracts.filter(c=>['router','poolManager'].includes(c.role)).map(c=>c.address),profile.poolKey.currency1])
  if(!subjects.has(address))subjects.set(address,new Set());
 for(const key of [C.version,C.length,C.gas,...chunkSlots(640)])subjects.get(C.arbos).add(key);
 for(const key of [profile.rootRecordSlot,word(BigInt(profile.rootRecordSlot)+1n),C.executorSlot,C.executorHashSlot])subjects.get(C.root).add(key);
 const sendMerkle=addSendMerkleSubjects(subjects,parent,checkpoint);
 const plan=groupSubjects(subjects,checkpoint);
 const configBytes=(spec.chainConfig.length-2)/2;
 // acquire.mjs reads code for every subject address once; the first group of each address carries it.
 const seen=new Set(),dependencies=[{address:C.rules,slots:rulesKeys,code:true,source:'RULES_CONFIGURATION'}];
 seen.add(C.rules);
 for(const g of plan.groups){dependencies.push({address:g.address,slots:g.slots,code:!seen.has(g.address),source:'PREFETCH_PLAN'});seen.add(g.address);}
 dependencies.push({address:C.arbos,slots:chunkSlots(configBytes),code:false,source:'ARBOS_CHAIN_CONFIG'});
 return {schema:'rhook/hookr-static-dependencies/0.1',checkpoint:structuredClone(checkpoint),prefetchPlan:plan,dependencies,
  actor,history,filters:filters.map(f=>f.slot),sendMerkleLevels:sendMerkle.partialLevels,
  variantIndependent:true,
  meaning:'Static reads before live acquisition for this profile. LP Rewards variants change only a replacement word, so these reads do not depend on the selected lpBps; dynamic reads do.'};
}
