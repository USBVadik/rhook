import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;assert(lib);
const load=p=>import(pathToFileURL(path.join(lib,p)));
const {mergeHints,groupSubjects,initialRuleKeys,prefetch}=await load('rhook_alpha/cases/scenario/prefetch.mjs');
const {ProofCollector}=await load('rhook_alpha/cases/witness/collector.mjs');
const {rpcClient}=await load('rhook_alpha/cases/witness/rpc.mjs');
const {toRlp,keccak256,EMPTY_ROOT,EMPTY_CODE}=await load('engine/adapters/hookr-case/primitives.mjs');
const address='0x'+'11'.repeat(20),poolId='0x'+'22'.repeat(32),key=n=>'0x'+BigInt(n).toString(16).padStart(64,'0');
const raw=toRlp(['0x20'+keccak256(address).slice(2),toRlp(['0x01','0x',EMPTY_ROOT,EMPTY_CODE])]);
const cp={chainId:4663,blockNumber:7,blockHash:key(99),stateRoot:keccak256(raw)};
const hints=subjects=>({schema:'rhook/scenario-trace-hints/0.1',chainId:4663,poolId,source:{coverage:'PARTIAL'},subjects});
const each=async(rows,fn)=>{for(const row of rows)await fn(row)};
function proof(keys){return {address,nonce:'0x1',balance:'0x0',storageHash:EMPTY_ROOT,codeHash:EMPTY_CODE,accountProof:[raw],storageProof:keys.map(k=>({key:k,value:'0x0',proof:[]}))};}

test('trace identities deduplicate into bounded per-account batches without importing values',()=>{
 const base=[{address,slots:[key(0)]}],input=hints([{address,slots:Array.from({length:55},(_,i)=>key(i))}]);
 const subjects=mergeHints(base,input,{chainId:4663,poolId}),plan=groupSubjects(subjects,cp);
 assert.deepEqual(plan.groups.map(g=>g.slots.length),[48,7]);assert.equal(plan.slotCount,55);assert.equal(base[0].slots.length,1);
 assert.equal(plan.coverage,'HINTS_ONLY_AUTHENTICATION_AND_CLOSURE_REQUIRED');
 assert.deepEqual(initialRuleKeys(subjects,address,[key(54),key(53)]).slice(0,2),[key(54),key(53)]);
 for(const bad of [{...input,chainId:1},{...input,poolId:key(3)},hints([{address,slots:[key(1)],value:'old'}]),hints([{address,slots:['0x1']}])])assert.throws(()=>mergeHints(base,bad,{chainId:4663,poolId}));
});

test('prefetch authenticates every requested key and rejects another root before dispatch',async()=>{
 let calls=0;const c=new ProofCollector(cp,async(method,params)=>{calls++;assert.equal(method,'eth_getProof');assert.deepEqual(params[2],{blockHash:cp.blockHash,requireCanonical:true});return proof(params[1]);});
 const p=groupSubjects(new Map([[address,new Set([key(1),key(2)])]]),cp);
 await prefetch(c,p,each);assert.equal(calls,1);assert.equal(c.project(address,[key(1),key(2)]).verified.resolutions.length,2);
 assert.equal(c.nodes.size,1);await assert.rejects(prefetch(c,{...p,checkpoint:{...cp,stateRoot:key(4)}},each),/PREFETCH_CHECKPOINT/);assert.equal(calls,1);
});

test('partial batches, malformed proofs and provider errors never populate authenticated cache',async()=>{
 const plan=groupSubjects(new Map([[address,new Set([key(1),key(2)])]]),cp);
 for(const reply of [keys=>({...proof(keys),storageProof:proof(keys).storageProof.slice(1)}),keys=>({...proof(keys),accountProof:['0xc0']}),()=>{throw Error('RPC_ERROR: provider rejection')}]){
  const c=new ProofCollector(cp,async(_m,p)=>reply(p[1]));await assert.rejects(prefetch(c,plan,each));assert.equal(c.nodes.size,0);assert.equal(c.proofs.length,0);
 }
});

test('a grouped reply cannot bypass the existing byte budget',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhook-prefetch-budget-'));let sends=0;
 const client=rpcClient(dir,{limits:{requests:64,wallMs:30000,requestMs:1000,gapMs:0,bytes:100,body:100,header:1},transport:{send:async rawRequest=>{sends++;const q=JSON.parse(rawRequest);return {status:200,body:Buffer.from(JSON.stringify({jsonrpc:'2.0',id:q.id,result:proof(q.params[1])})),headers:Buffer.alloc(0)};},close(){}}});
 try{const c=new ProofCollector(cp,client.call);await assert.rejects(prefetch(c,groupSubjects(new Map([[address,new Set([key(1)])]]),cp),each),/RESERVATION|BUDGET/);assert.equal(c.nodes.size,0);assert.equal(sends,1);}finally{await client.close();fs.rmSync(dir,{recursive:true,force:true});}
});
