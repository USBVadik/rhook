// Reads one authenticated Hookr SCENARIO.json on stdin and prints its static coverage as JSON.
// No network, no native process. The Python session has already checked the bytes against their pin.
import {coverage,CoverageStop} from './coverage.mjs';
import {hookrStaticPlan,CONFIG_KEYS} from './hookr-plan.mjs';
import {offlineCollector,seedFrom} from './coverage.mjs';
import {C} from '../cases/witness/material.mjs';
import {parseStrictEvidenceJson} from '../../engine/adapters/hookr-case/strict-json.mjs';

const MAX=8<<20;
const chunks=[];let size=0;
for await(const chunk of process.stdin){size+=chunk.length;if(size>MAX){process.stdout.write(JSON.stringify({status:'STOP',code:'SOURCE_TOO_LARGE'})+'\n');process.exit(0);}chunks.push(chunk);}
try{
 const spec=parseStrictEvidenceJson(Buffer.concat(chunks).toString('utf8'));
 let plan;
 try{plan=hookrStaticPlan(spec);}catch(error){throw new CoverageStop('STATIC_PLAN_UNAVAILABLE',String(error.message).split('\n')[0].slice(0,200));}
 const report=await coverage(spec.checkpoint,spec.inventory,plan.dependencies);
 // Profile semantics on top of the neutral report: the intervention's starting value and the actor.
 const {collector}=offlineCollector(spec.checkpoint,seedFrom(spec.checkpoint,spec.inventory).seed);
 const rules=collector.project(C.rules,[...CONFIG_KEYS]);
 const words=rules?rules.verified.resolutions.map(r=>'0x'+BigInt(r.value).toString(16).padStart(64,'0')):null;
 const actorRow=report.dependencies.find(r=>r.address===plan.actor);
 report.profile={
  id:'hookr-buy/0.1',
  parentHeader:'HEADER_HASH_RECOMPUTED_EQUALS_CHECKPOINT',
  originalConfiguration:words===null?'UNKNOWN':JSON.stringify(words)===JSON.stringify(spec.configurations.baseline)
   ?'AUTHENTICATED_EQUALS_BASELINE':'AUTHENTICATED_DIFFERS_FROM_BASELINE',
  simulationActor:actorRow?.account==='PROVEN_ABSENT'?'PROVEN_ABSENT':actorRow?.account==='PRESENT'?'PRESENT_NOT_ALLOWED':'UNKNOWN',
  prefetchPlan:{accountCount:plan.prefetchPlan.accountCount,slotCount:plan.prefetchPlan.slotCount,proofBatches:plan.prefetchPlan.proofBatches,
   groups:plan.prefetchPlan.groups},
  variantIndependent:plan.variantIndependent,
 };
 process.stdout.write(JSON.stringify(report)+'\n');
}catch(error){
 const code=error instanceof CoverageStop?error.code:error.code==='STRICT_JSON_SYNTAX'?'SOURCE_JSON_INVALID':'COVERAGE_STOP';
 process.stdout.write(JSON.stringify({status:'STOP',code,detail:String(error.message).split('\n')[0].slice(0,300)})+'\n');
}
