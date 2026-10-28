import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;assert(lib);
const load=p=>import(pathToFileURL(path.join(lib,p)));
const {ExecutorWindow,addExecutorWindow,WINDOW}=await load('rhook_alpha/cases/scenario/executor-window.mjs');
const {ProofCollector}=await load('rhook_alpha/cases/witness/collector.mjs');
const {serveDiscovery,DISCOVERY}=await load('rhook_alpha/cases/scenario/discovery.mjs');
const {toRlp,keccak256,EMPTY_ROOT}=await load('engine/adapters/hookr-case/primitives.mjs');
const key=n=>'0x'+n.toString(16).padStart(64,'0');
const raw=toRlp(['0x20'+keccak256(WINDOW.address).slice(2),toRlp(['0x01','0x',EMPTY_ROOT,WINDOW.codeHash])]);
const cp={chainId:4663,blockNumber:3,blockHash:key(2n),stateRoot:keccak256(raw)};
function proof(keys){return {address:WINDOW.address,nonce:'0x1',balance:'0x0',storageHash:EMPTY_ROOT,codeHash:WINDOW.codeHash,accountProof:[raw],storageProof:keys.map(key=>({key,value:'0x0',proof:[]}))};}
async function fixture(){
 const c=new ProofCollector(cp,async(_m,p)=>proof(p[1]));const subjects=new Map();addExecutorWindow(subjects,cp,WINDOW.poolId);
 const keys=[...subjects.get(WINDOW.address)];assert.equal(keys.length,27);await c.proof(WINDOW.address,keys);
 return {c,w:new ExecutorWindow(c)};
}

test('initial27-key window is exact, bounded and authenticates absence',async()=>{
 const {c,w}=await fixture();assert.equal(w.snapshot().initialWindowKeys,27);
 assert.equal(c.project(WINDOW.address,[WINDOW.start,WINDOW.end]).verified.resolutions.every(r=>r.status==='ABSENT'),true);
 assert.throws(()=>addExecutorWindow(new Map(),{...cp,chainId:1},WINDOW.poolId));
 assert.throws(()=>addExecutorWindow(new Map(),cp,key(9n)));
});

test('already proven absence does not trigger speculative pages',async()=>{
 const {c,w}=await fixture();
 await w.fetch(c,WINDOW.address,[key(BigInt(WINDOW.end)+33n)]);
 assert.equal(w.snapshot().pages,0);assert.equal(w.snapshot().additionalKeys,0);
 assert.equal(w.snapshot().totalWindowKeysUpperBound,27);
});

test('root mismatch and rejected fetch preserve accepted page state',async()=>{
 const {c,w}=await fixture();c.checkpoint={...cp,stateRoot:key(9n)};
 await assert.rejects(w.fetch(c,WINDOW.address,[key(BigInt(WINDOW.end)+33n)]),/CHECKPOINT_DRIFT/);
 c.checkpoint=cp;c.proof=async()=>{throw Error('MALFORMED_PROOF')};
 await assert.rejects(w.fetch(c,WINDOW.address,[key(BigInt(WINDOW.end)+33n)]),/MALFORMED_PROOF/);
 assert.equal(w.snapshot().pages,0);assert.equal(w.snapshot().additionalKeys,0);assert.equal(w.snapshot().events.at(-1).status,'REJECTED');
});

test('unverified initial keys or changed executor identity cannot activate the window',async()=>{
 const {c}=await fixture();const project=c.project.bind(c);c.project=()=>null;
 assert.throws(()=>new ExecutorWindow(c),/INITIAL_WINDOW_UNAUTHENTICATED/);
 c.project=(a,k)=>{const r=project(a,k);if(r)r.verified.account.codeHash=key(7n);return r;};
 assert.throws(()=>new ExecutorWindow(c),/EXECUTOR_RUNTIME_CHANGED/);
});

test('incomplete initial multi-key replies cannot activate a verified window',async()=>{
 const c=new ProofCollector(cp,async(_m,p)=>({...proof(p[1]),storageProof:proof(p[1]).storageProof.slice(1)}));
 const subjects=new Map();addExecutorWindow(subjects,cp,WINDOW.poolId);
 await assert.rejects(c.proof(WINDOW.address,[...subjects.get(WINDOW.address)]));
 assert.equal(c.nodes.size,0);assert.throws(()=>new ExecutorWindow(c),/INITIAL_WINDOW_UNAUTHENTICATED/);
});

test('real broker returns only the requested proof after bounded read-ahead',async()=>{
 const {c,w,adjacent}=await hiddenNonadjacentFixture(),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'rhc-win-'));
 const socket=path.join(tmp,'b.sock'),ready=path.join(tmp,'ready'),abort=new AbortController();
 const active=serveDiscovery(socket,c,{stats:()=>({remainingMs:3000,requests:0,responseBytes:0}),stop(){}},ready,{signal:abort.signal,storageWindow:w});
 active.catch(()=>{});
 const send=q=>new Promise((resolve,reject)=>{const connection=net.connect(socket),chunks=[];connection.on('error',reject);connection.on('connect',()=>connection.write(JSON.stringify(q)+'\n'));connection.on('data',x=>chunks.push(x));connection.on('end',()=>{try{resolve(JSON.parse(Buffer.concat(chunks)))}catch(e){reject(e)}});});
 try{
  for(let i=0;i<100&&!fs.existsSync(ready);i++)await new Promise(r=>setTimeout(r,5));
  const slot=adjacent;
  const r=await send({schema:DISCOVERY,id:1,checkpoint:c.checkpoint,world:'SCENARIO_BASELINE',phase:'unit',kind:'eth_getProof',address:WINDOW.address,slots:[slot]});
  assert.equal(r.result.storageProof.length,1);assert.equal(r.result.storageProof[0].key,slot);assert.equal(w.snapshot().pages,1);
  await send({schema:DISCOVERY,id:2,checkpoint:c.checkpoint,world:'CONTROL',phase:'unit',kind:'finish',completed:true});await active;
 }finally{abort.abort();await Promise.allSettled([active]);fs.rmSync(tmp,{recursive:true,force:true});}
});

// A synthetic branch hidden behind a prefix that none of the initial keys
// reaches. The nonadjacent read therefore needs a new authenticated trie node.
async function hiddenNonadjacentFixture(malformed=false){
 const adjacent=key(BigInt(WINDOW.end)+33n),hashed=keccak256(adjacent).slice(2),prefix=hashed.slice(0,8);
 const leaf=toRlp(['0x3'+hashed.slice(9),toRlp('0x01')]);
 const other=toRlp(['0x3'+hashed.slice(9),toRlp('0x02')]);
 const branch=Array(17).fill('0x'),n=parseInt(hashed[8],16);
 branch[n]=keccak256(leaf);branch[(n+1)%16]=keccak256(other);
 const branchRaw=toRlp(branch),storage=toRlp(['0x00'+prefix,keccak256(branchRaw)]);
 const account=toRlp(['0x20'+keccak256(WINDOW.address).slice(2),toRlp(['0x01','0x',keccak256(storage),WINDOW.codeHash])]);
 const checkpoint={...cp,stateRoot:keccak256(account)},calls=[];
 const c=new ProofCollector(checkpoint,async(_m,params)=>{
  calls.push(params[1]);const storageProof=params[1].map(k=>{
   assert.equal(k,adjacent,'ONLY_UNRESOLVED_PATH_FETCHED');
   return {key:k,value:'0x1',proof:[storage,branchRaw,leaf]};
  });
  return {address:WINDOW.address,nonce:'0x1',balance:'0x0',storageHash:keccak256(storage),codeHash:WINDOW.codeHash,
   accountProof:[account],storageProof:malformed?[]:storageProof};
 },{checkpoint,nodes:{[keccak256(account)]:account,[keccak256(storage)]:storage},codes:{}});
 const subjects=new Map();addExecutorWindow(subjects,checkpoint,WINDOW.poolId);
 for(const k of subjects.get(WINDOW.address))assert.notEqual(keccak256(k).slice(2,10),prefix);
 await c.proof(WINDOW.address,[...subjects.get(WINDOW.address)]);
 return {c,w:new ExecutorWindow(c),calls,adjacent};
}

test('nonadjacent read authenticates missing branch while preserving cached absences',async()=>{
 const {c,w,calls,adjacent}=await hiddenNonadjacentFixture(),scheduled=[],original=c.proof.bind(c);
 c.proof=async(a,keys)=>{scheduled.push(keys);return original(a,keys);};
 const result=await w.fetch(c,WINDOW.address,[adjacent]);
 assert.deepEqual(calls,[[adjacent]]);assert.equal(w.snapshot().events[0].pageKeys.length,8);
 assert.equal(result.storageProof.length,1);assert.equal(result.storageProof[0].value,'0x1');
 assert.equal(w.snapshot().pages,1);assert.equal(w.snapshot().additionalKeys,1);assert.equal(w.snapshot().events[0].status,'AUTHENTICATED');
 for(const k of w.snapshot().events[0].pageKeys)if(k!==adjacent)assert.equal(c.project(WINDOW.address,[k]).verified.resolutions[0].status,'ABSENT');
});

test('malformed nonadjacent multiproof closes read without advancing verified bounds',async()=>{
 const {c,w,adjacent}=await hiddenNonadjacentFixture(true),before=w.snapshot();
 await assert.rejects(w.fetch(c,WINDOW.address,[adjacent]));
 assert.equal(w.snapshot().totalWindowKeysUpperBound,before.totalWindowKeysUpperBound);assert.equal(w.snapshot().pages,0);
 assert.equal(w.snapshot().events[0].status,'REJECTED');assert.equal(c.project(WINDOW.address,[adjacent]),null);
});
