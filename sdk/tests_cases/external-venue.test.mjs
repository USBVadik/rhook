// Synthetic original-root authentication, not historical fixture completion or EVM execution.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;assert(lib);
const load=p=>import(pathToFileURL(path.join(lib,p)));
const {mergeHints,groupSubjects,prefetch}=await load('rhook_alpha/cases/scenario/prefetch.mjs');
const {ProofCollector}=await load('rhook_alpha/cases/witness/collector.mjs');
const {toRlp,keccak256}=await load('engine/adapters/hookr-case/primitives.mjs');
const hints=JSON.parse(fs.readFileSync(path.join(lib,'rhook_alpha/cases/scenario/trace-hints.json')));
const address='0xd8b750f564321ce68b4b3d8498616da96fad798d';
const row=hints.subjects.find(r=>r.address===address);assert(row);
const key=n=>'0x'+BigInt.asUintN(256,BigInt(n)).toString(16).padStart(64,'0');
const mapping=(n,slot)=>keccak256(key(n)+key(slot).slice(2));
const next=mapping(16,6),each=async(rows,fn)=>{for(const row of rows)await fn(row);};

test('external venue retains the derived core and batches recorded identities without mapping scans',()=>{
 const ticks=mapping(117480,5),expected=[key(0),key(4),...Array.from({length:10},(_,i)=>mapping(i+7,6)),
  ...[0n,1n,2n,3n].map(n=>key(BigInt(ticks)+n))].sort();
 assert(expected.every(k=>row.slots.includes(k)));assert(row.slots.length<=48);assert.equal(new Set(row.slots).size,row.slots.length);assert.deepEqual(Object.keys(row).sort(),['address','slots']);
 const subjects=mergeHints([],hints,{chainId:4663,poolId:hints.poolId});
 const plan=groupSubjects(subjects,{chainId:4663,blockNumber:1,blockHash:key(1),stateRoot:key(2)});
 const groups=plan.groups.filter(g=>g.address===address);
 assert.equal(groups.length,1);assert.deepEqual(groups[0].slots,row.slots);assert(plan.groups.every(g=>g.slots.length<=48));assert(plan.slotCount<=512);
 assert.equal(plan.coverage,'HINTS_ONLY_AUTHENTICATION_AND_CLOSURE_REQUIRED');
});

function fixture(value){
 const storage=toRlp(['0x20'+keccak256(next).slice(2),toRlp('0x'+value.toString(16).padStart(2,'0'))]);
 const code='0x6000',account=toRlp(['0x20'+keccak256(address).slice(2),
  toRlp(['0x01','0x',keccak256(storage),keccak256(code)])]);
 const checkpoint={chainId:4663,blockNumber:value,blockHash:key(value),stateRoot:keccak256(account)};
 const proof=keys=>({address,nonce:'0x1',balance:'0x0',storageHash:keccak256(storage),codeHash:keccak256(code),accountProof:[account],
  storageProof:keys.map(k=>({key:k,value:k===next?'0x'+value.toString(16):'0x0',proof:[storage]}))});
 return {checkpoint,proof,code};
}

test('all recorded venue hints get fresh authenticated values and code at each distinct synthetic root',async()=>{
 for(const value of [7,9]){
  const f=fixture(value),calls=[];
  const c=new ProofCollector(f.checkpoint,async(method,params)=>{
   calls.push({method,params});assert.deepEqual(params.at(-1),{blockHash:f.checkpoint.blockHash,requireCanonical:true});
   return method==='eth_getProof'?f.proof(params[1]):f.code;
  });
  await prefetch(c,groupSubjects(new Map([[address,new Set(row.slots)]]),f.checkpoint),each);
  assert.equal(await c.code(address),f.code);
  for(const slot of row.slots)await c.proof(address,[slot]);
  assert.deepEqual(calls.map(q=>q.method),['eth_getProof','eth_getCode']);
  assert.equal(c.project(address,[next]).verified.resolutions[0].value,String(value));
  assert.equal(c.project(address,[key(0)]).verified.resolutions[0].status,'ABSENT');
 }
});

test('missing last subject or wrong-root grouped replies fail before cache adoption',async()=>{
 const f=fixture(7),wrong=fixture(9);
 for(const reply of [keys=>({...f.proof(keys),storageProof:f.proof(keys).storageProof.filter(p=>p.key!==next)}),keys=>wrong.proof(keys)]){
  const c=new ProofCollector(f.checkpoint,async(_m,params)=>reply(params[1]));
  await assert.rejects(prefetch(c,groupSubjects(new Map([[address,new Set(row.slots)]]),f.checkpoint),each));
  assert.equal(c.nodes.size,0);assert.equal(c.proofs.length,0);assert.equal(c.project(address,[next]),null);
 }
});
