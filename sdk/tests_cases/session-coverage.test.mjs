// Counterfactual Session static coverage: synthetic hash-linked tries only, never chain or EVM evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;
assert(lib,'RHOOK_TEST_INSTALLED_LIB required');
const load=name=>import(pathToFileURL(path.join(lib,name)));
const {coverage,seedFrom,offlineCollector}=await load('rhook_alpha/session/coverage.mjs');
const {hookrStaticPlan}=await load('rhook_alpha/session/hookr-plan.mjs');
const {C}=await load('rhook_alpha/cases/witness/material.mjs');
const {toRlp,keccak256}=await load('engine/adapters/hookr-case/primitives.mjs');
const fixture=await import(pathToFileURL(path.join(path.dirname(fileURLToPath(import.meta.url)),'session-fixture.mjs')));
const {syntheticScenarioParts,buildTrie,word,RULES_CODE,CONFIG_KEYS}=fixture;
const profile=JSON.parse(fs.readFileSync(path.join(lib,'rhook_alpha/cases/scenario/native/profile.json')));
const OTHER='0x'+'12'.repeat(20),ACTOR='0xd2480fd61af9bc73b8c73e8fdcabceb6f21ea8ff';
const rules=(slots=CONFIG_KEYS,code=true)=>({address:C.rules,slots,code});
const stopCode=async(promise,code)=>assert.rejects(promise,e=>e.code===code);

test('a same-root seed answers declared reads without any network request',async()=>{
 const p=syntheticScenarioParts();
 const r=await coverage(p.checkpoint,p.inventory,[rules(),{address:OTHER,slots:['0x01'],code:true},{address:ACTOR,slots:[]}]);
 assert.equal(r.status,'STATIC_DEPENDENCIES_COVERED');
 assert.deepEqual([r.networkRequestsPerformed,r.networkRequestsRefused,r.nativeExecutions],[0,0,0]);
 assert.equal(r.reuse.cachedProofs,3);assert.equal(r.dynamicClosure,'UNKNOWN');
 assert.deepEqual(r.dependencies.map(d=>[d.account,d.code]),[['PRESENT','PRESENT'],['PROVEN_ABSENT','PROVEN_EMPTY'],['PROVEN_ABSENT','NOT_REQUESTED']]);
});

test('a seed for another checkpoint, a poisoned node and a poisoned code preimage are rejected',()=>{
 const p=syntheticScenarioParts();const {seed}=seedFrom(p.checkpoint,p.inventory);
 assert.throws(()=>offlineCollector({...p.checkpoint,blockNumber:p.checkpoint.blockNumber-1},seed),e=>e.code==='CACHE_CHECKPOINT');
 assert.throws(()=>offlineCollector({...p.checkpoint,stateRoot:'0x'+'ab'.repeat(32)},seed),e=>e.code==='CACHE_CHECKPOINT');
 const [id,raw]=Object.entries(seed.nodes)[0];
 const poisonedNode={...seed,nodes:{...seed.nodes,[id]:raw.slice(0,-2)+(raw.endsWith('00')?'01':'00')}};
 assert.throws(()=>offlineCollector(p.checkpoint,poisonedNode),e=>['CACHE_NODE_HASH','SEED_PREIMAGE_INVALID'].includes(e.code));
 const poisonedCode={...seed,codes:{[keccak256(RULES_CODE)]:'0x6001'}};
 assert.throws(()=>offlineCollector(p.checkpoint,poisonedCode),e=>e.code==='CACHE_CODE_HASH');
});

test('an inventory preimage that is not a trie node stops instead of being ignored',async()=>{
 const p=syntheticScenarioParts();
 await stopCode(coverage(p.checkpoint,{...p.inventory,nodes:[...p.inventory.nodes,'0x01']},[rules()]),'SEED_PREIMAGE_INVALID');
 await stopCode(coverage(p.checkpoint,{...p.inventory,nodes:['nothex']},[rules()]),'SEED_PREIMAGE_ENCODING');
});

test('a missing account path is UNKNOWN with its missing node, while a proven absence stays distinct',async()=>{
 const p=syntheticScenarioParts({unknownSibling:true});
 const r=await coverage(p.checkpoint,p.inventory,[rules(),{address:OTHER,slots:['0x01'],code:true}]);
 assert.equal(r.status,'STATIC_DEPENDENCIES_MISSING');
 const other=r.dependencies[1];
 if(other.account==='UNKNOWN'){
  assert.equal(other.missingNodeHash,p.missingNodeHash);assert.deepEqual(other.storage.map(s=>s.status),['UNKNOWN']);assert.equal(other.code,'UNKNOWN');
 }else assert.equal(other.account,'PROVEN_ABSENT');
 assert(r.networkRequestsRefused>0);assert.equal(r.networkRequestsPerformed,0);
 const complete=await coverage(syntheticScenarioParts().checkpoint,syntheticScenarioParts().inventory,[{address:OTHER,slots:[]}]);
 assert.equal(complete.dependencies[0].account,'PROVEN_ABSENT');
});

test('a missing storage path is UNKNOWN, not zero, and missing code is not empty code',async()=>{
 const nodes=[];
 // Storage root: a branch whose other children are unknown hashes.
 const known=toRlp([ '0x3'+keccak256(CONFIG_KEYS[0]).slice(3),toRlp('0x05')]);nodes.push(known);
 const branch=Array(17).fill('0x'),first=parseInt(keccak256(CONFIG_KEYS[0])[2],16),hidden=keccak256('0x01');
 for(let i=0;i<16;i++)branch[i]=i===first?keccak256(known):hidden;
 const storage=toRlp(branch);nodes.push(storage);
 const account=toRlp(['0x01','0x',keccak256(storage),keccak256(RULES_CODE)]);
 const stateRoot=buildTrie([{key:keccak256(C.rules),value:account}],nodes);
 const cp={chainId:4663,blockNumber:1,blockHash:'0x'+'33'.repeat(32),stateRoot};
 const other=CONFIG_KEYS.find(k=>parseInt(keccak256(k)[2],16)!==first);
 const r=await coverage(cp,{nodes,codes:[]},[rules([CONFIG_KEYS[0],other],true)]);
 const row=r.dependencies[0];
 assert.equal(row.account,'PRESENT');
 assert.deepEqual(row.storage.map(s=>s.status),['PRESENT','UNKNOWN']);assert.equal(row.storage[1].missingNodeHash,hidden);
 assert.equal(row.code,'MISSING_PREIMAGE');assert.equal(row.codeHash,keccak256(RULES_CODE));
 assert.equal(r.status,'STATIC_DEPENDENCIES_MISSING');
});

test('duplicate preimages are deduplicated and counted, not grown',async()=>{
 const p=syntheticScenarioParts();
 const r=await coverage(p.checkpoint,{nodes:[...p.inventory.nodes,...p.inventory.nodes,...p.inventory.nodes],codes:[RULES_CODE,RULES_CODE]},[rules()]);
 assert.equal(r.seed.distinctNodes,p.inventory.nodes.length);assert.equal(r.seed.duplicateNodes,2*p.inventory.nodes.length);
 assert.equal(r.seed.distinctCodes,1);assert.equal(r.seed.duplicateCodes,1);
});

test('initial reads passing never declares trie-update closure',async()=>{
 const p=syntheticScenarioParts();
 const r=await coverage(p.checkpoint,p.inventory,[rules()]);
 assert.equal(r.status,'STATIC_DEPENDENCIES_COVERED');assert.equal(r.dynamicClosure,'UNKNOWN');
 assert.equal(r.trieUpdateAudit.completeness,'NOT_INFERRED_FROM_NODE_COUNT_OR_PARTIAL_FRONTIER');
});

test('dependency lists are bounded',async()=>{
 const p=syntheticScenarioParts();
 await stopCode(coverage(p.checkpoint,p.inventory,Array.from({length:129},()=>rules())),'DEPENDENCY_LIMIT');
 await stopCode(coverage(p.checkpoint,p.inventory,[rules(Array.from({length:49},(_,i)=>word(i)))]),'DEPENDENCY_SHAPE');
});

test('the Hookr static plan authenticates the parent header and depends only on the scenario',()=>{
 const p=syntheticScenarioParts();
 const spec={checkpoint:p.checkpoint,parent:p.parent,poolId:profile.poolId,actions:[{signedTransaction:'0xdead'}],
  commonSetup:{actor:ACTOR},chainConfig:'0x'+'00'.repeat(64)};
 const plan=hookrStaticPlan(spec);
 assert.equal(plan.variantIndependent,true);assert.equal(plan.dependencies[0].address,C.rules);
 for(const k of CONFIG_KEYS)assert(plan.dependencies[0].slots.includes(k));
 assert.deepEqual(hookrStaticPlan(structuredClone(spec)),plan);
 assert.throws(()=>hookrStaticPlan({...spec,parent:{...p.parent,extraData:'0x'+'00'.repeat(32)}}),/SEND_MERKLE_HEADER/);
 assert.throws(()=>hookrStaticPlan({...spec,poolId:'0x'+'00'.repeat(32)}),/UNSUPPORTED_POOL/);
});

test('the Hookr coverage helper reads stdin and reports the authenticated original configuration',()=>{
 const p=syntheticScenarioParts();
 const spec={checkpoint:p.checkpoint,parent:p.parent,poolId:profile.poolId,actions:[{signedTransaction:'0xdead'}],
  commonSetup:{actor:ACTOR},chainConfig:'0x'+'00'.repeat(64),inventory:p.inventory,configurations:{baseline:profile.baselineConfigWords}};
 const helper=path.join(lib,'rhook_alpha/session/hookr-coverage-main.mjs');
 const out=JSON.parse(execFileSync(process.execPath,[helper],{input:JSON.stringify(spec)}));
 assert.equal(out.status,'STATIC_DEPENDENCIES_COVERED');assert.equal(out.profile.originalConfiguration,'AUTHENTICATED_EQUALS_BASELINE');
 assert.equal(out.profile.simulationActor,'PROVEN_ABSENT');
 const changed=JSON.parse(execFileSync(process.execPath,[helper],{input:JSON.stringify({...spec,configurations:{baseline:[word(1),...profile.baselineConfigWords.slice(1)]}})}));
 assert.equal(changed.profile.originalConfiguration,'AUTHENTICATED_DIFFERS_FROM_BASELINE');
 const bad=JSON.parse(execFileSync(process.execPath,[helper],{input:'{"a":1,"a":2}'}));
 assert.deepEqual([bad.status,bad.code],['STOP','SOURCE_JSON_INVALID']);
});

// Optional parity check against the accepted on-demand run's retained capture (not in Git).
const REAL=process.env.RHOOK_SESSION_REAL_CAPTURE;
test('static plan equals the recorded prefetch plan of the accepted run',{skip:!REAL&&'RHOOK_SESSION_REAL_CAPTURE not set'},()=>{
 const spec=JSON.parse(fs.readFileSync(path.join(REAL,'SCENARIO.json')));
 const plan=hookrStaticPlan(spec);
 assert.deepEqual(plan.prefetchPlan.groups,JSON.parse(fs.readFileSync(path.join(REAL,'PREFETCH_PLAN.json'))).groups);
 const out=JSON.parse(execFileSync(process.execPath,[path.join(lib,'rhook_alpha/session/hookr-coverage-main.mjs')],{input:fs.readFileSync(path.join(REAL,'SCENARIO.json'))}));
 assert.equal(out.status,'STATIC_DEPENDENCIES_COVERED');assert.equal(out.networkRequestsPerformed,0);
});
