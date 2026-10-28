import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {commitment} from '../engine/adapters/hookr-case/primitives.mjs';
import {profile,DOMAIN,PROFILE,validateTransform,validatePlan,deriveOverlayRoot} from '../rhook_alpha/cases/historical/transform.mjs';
import {authenticatePackage,verifyWorld} from '../rhook_alpha/cases/historical/block.mjs';
const body={schema:DOMAIN+'/transform',checkpoint:profile.checkpoint,pool:profile.pool,rootCodeHash:profile.rootCodeHash,rulesCodeHash:profile.rulesCodeHash,writes:profile.writes};
const i={...body,interventionCommitment:commitment(DOMAIN+'/transform',body)};
const plan={schema:DOMAIN+'/plan',packageSha256:profile.packageSha256,inputCommitment:profile.inputCommitment,witnessCommitment:profile.witnessCommitment,
 checkpoint:profile.checkpoint,...profile.target,arrivals:profile.arrivals,transactions:7,subject:profile.subject,sender:profile.sender,router:profile.router,
 observation:profile.observation,intervention:i,rulesRuntimeHash:profile.rulesCodeHash};
test('exact typed transform and plan accepted',()=>{validateTransform(i);validatePlan(plan)});
for(const field of ['checkpoint','rootCodeHash','writes','interventionCommitment'])test('reject altered '+field,()=>{
 const v=structuredClone(i);if(field==='writes')v.writes[1].after=v.writes[1].before;else v[field]='wrong';assert.throws(()=>validateTransform(v));
});
for(const field of ['schema','packageSha256','arrivals','subject','observation'])test('reject plan relabelling '+field,()=>{
 const v=structuredClone(plan);v[field]='wrong';assert.throws(()=>validatePlan(v));
});
test('LP/scenario world cannot be relabelled',()=>assert.throws(()=>verifyWorld({schema:'rhook/hookr-scenario/0.1',profile:PROFILE,error:''},'ACTUAL',plan,{})));
test('retained block authenticates and JS overlay matches the pinned prior Go OFF root',{skip:!process.env.RHOOK_HISTORICAL_TEST_PACKAGE},async()=>{
 const raw=fs.readFileSync(process.env.RHOOK_HISTORICAL_TEST_PACKAGE),pkg=await authenticatePackage(raw,plan);
 assert.equal(deriveOverlayRoot(pkg,plan),'0xbadb4e1079b311b518cd1c3583f1b956f27fb3d8de9fa63e74696bb99c2f17d8');
 const bad=structuredClone(pkg);bad.state=[];bad.proofs=[];assert.throws(()=>deriveOverlayRoot(bad,plan));
});
