import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
const installed=process.env.RHOOK_TEST_INSTALLED_LIB;assert(installed);
const {PageOnMiss,planPage,policy,EXECUTOR,CODE_HASH}=await import(new URL('file://'+installed+'/rhook_alpha/cases/scenario/page-on-miss.mjs'));
const lib=process.env.RHOOK_TEST_INSTALLED_LIB+'/';assert(process.env.RHOOK_TEST_INSTALLED_LIB);
const {ProofCollector}=await import(lib+'rhook_alpha/cases/witness/collector.mjs');
const {rpcClient}=await import(lib+'rhook_alpha/cases/witness/rpc.mjs');
const {toRlp,keccak256}=await import(lib+'engine/adapters/hookr-case/primitives.mjs');
const key=n=>'0x'+n.toString(16).padStart(64,'0');
const missing=BigInt('0x290decd9548b62a8d60345a988386fc84ba6bc95484008f6362f93160ef3e62b');
function fixture(transform=x=>x){
 const target=key(missing),storage=toRlp(['0x20'+keccak256(target).slice(2),toRlp('0x01')]);
 const account=toRlp(['0x20'+keccak256(EXECUTOR).slice(2),toRlp(['0x01','0x',keccak256(storage),CODE_HASH])]);
 const cp={chainId:4663,blockNumber:1,blockHash:key(99n),stateRoot:keccak256(account)},calls=[];
 const reply=keys=>({address:EXECUTOR,nonce:'0x1',balance:'0x0',codeHash:CODE_HASH,storageHash:keccak256(storage),accountProof:[account],storageProof:keys.map(k=>({key:k,value:k===target?'0x1':'0x0',proof:[storage]}))});
 const seed={checkpoint:cp,nodes:{[keccak256(account)]:account},codes:{}};
 const c=new ProofCollector(cp,async(_m,p)=>{calls.push(p);return transform(reply(p[1]));},seed);
 return {c,cp,calls,reply,seed,storage};
}
for(const size of [8])test(`page${size}: nonadjacent actual miss, whole page authenticated and exact response`,async()=>{
 const {c,calls}=fixture(),p=new PageOnMiss(c,policy(size));const r=await p.fetch(c,EXECUTOR,[key(missing)]);
 assert.equal(calls.length,1);assert.equal(calls[0][1].length,size);assert.deepEqual(calls[0][2],{blockHash:c.checkpoint.blockHash,requireCanonical:true});
 assert.equal(r.storageProof.length,1);assert.equal(r.storageProof[0].value,'0x1');assert.equal(p.snapshot().additionalKeys,size);
 const event=p.snapshot().events[0];assert.equal(c.project(EXECUTOR,event.pageKeys).verified.resolutions.filter(v=>v.status==='ABSENT').length,size-1);
});
test('fixed policy, page/key limits and out-of-family extremes',()=>{
 const state={pages:0,added:new Set()},p=policy();
 assert.throws(()=>policy(16));assert.throws(()=>policy(32));assert.throws(()=>policy(8,'whole-account-control'));
 for(const k of [0n,(1n<<256n)-1n])assert.equal(planPage(p,state,EXECUTOR,[key(k)],()=>false).pageKeys.length,0);
 assert.throws(()=>planPage(p,state,EXECUTOR,['0x1'],()=>false));assert.throws(()=>planPage(p,state,EXECUTOR,[key(1n),key(1n)],()=>false));
 assert.equal(planPage(p,{pages:4,added:new Set()},EXECUTOR,[key(missing)],()=>false).pageKeys.length,0);
 assert.equal(planPage(p,{pages:1,added:new Set(Array.from({length:32},(_,i)=>key(BigInt(i))))},EXECUTOR,[key(missing)],()=>false).pageKeys.length,0);
});
test('cached reads, unrelated account and nonfamily mappings do not consume pages',async()=>{
 const {c}=fixture(),p=new PageOnMiss(c,policy(8));await p.fetch(c,EXECUTOR,[key(missing)]);const n=p.snapshot().pages;
 await p.fetch(c,EXECUTOR,[key(missing)]);assert.equal(p.snapshot().pages,n);
 const state={pages:0,added:new Set()};assert.equal(planPage(policy(8),state,EXECUTOR,[key(1n)],()=>false).reason,'OUTSIDE_OBSERVED_FAMILY');
 assert.equal(planPage(policy(8),state,'0x'+'22'.repeat(20),[key(missing)],()=>false).pageKeys.length,0);
});
for(const [name,alter] of [['missing storage entry',r=>({...r,storageProof:r.storageProof.slice(1)})],['false absent value',r=>({...r,storageProof:r.storageProof.map(v=>({...v,value:'0x0'}))})],['wrong storage node',r=>({...r,storageProof:r.storageProof.map(v=>({...v,proof:['0xc0']}))})]])test(`${name}: no page accepted`,async()=>{
 const {c}=fixture(alter),p=new PageOnMiss(c,policy(8));await assert.rejects(p.fetch(c,EXECUTOR,[key(missing)]));assert.equal(p.snapshot().pages,0);assert.equal(p.snapshot().additionalKeys,0);assert.equal(p.snapshot().events[0].status,'REJECTED');
});
test('checkpoint and runtime changes fail before request',async()=>{
 const {c}=fixture(),p=new PageOnMiss(c,policy(8));c.checkpoint={...c.checkpoint,stateRoot:key(3n)};await assert.rejects(p.fetch(c,EXECUTOR,[key(missing)]),/CHECKPOINT_DRIFT/);
 const f=fixture(),old=f.c.project.bind(f.c);f.c.project=(a,k)=>{const v=old(a,k);if(v)v.verified.account.codeHash=key(7n);return v;};assert.throws(()=>new PageOnMiss(f.c,policy(8)),/RUNTIME_CHANGED/);
});
test('shared RPC request cap stops page fetch without acceptance or retry',async()=>{
 const f=fixture(),dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhc-page-budget-'));let now=0,sends=0;
 const client=rpcClient(dir,{limits:{requests:1,wallMs:30000,requestMs:3000,gapMs:125,bytes:8<<20,body:2<<20,header:8192},now:()=>now,sleep:async ms=>{now+=ms;},transport:{close(){},async send(body){sends++;const q=JSON.parse(body);return {body:Buffer.from(JSON.stringify({jsonrpc:'2.0',id:q.id,result:f.reply(q.params[1])})),headers:Buffer.from('HTTP/1.1 200 OK\r\n\r\n'),status:200};}}});
 try{
  const c=new ProofCollector(f.cp,client.call,f.seed),p=new PageOnMiss(c,policy(8));await p.fetch(c,EXECUTOR,[key(missing)]);c.nodes.delete(keccak256(f.storage));
  await assert.rejects(p.fetch(c,EXECUTOR,[key(missing+16n)]),/RPC_BUDGET/);assert.equal(sends,1);assert.equal(p.snapshot().pages,1);assert.equal(client.stats().requests,1);
 }finally{await client.close();fs.rmSync(dir,{recursive:true,force:true});}
});
test('overlapping fetches rejected; first request completes with no extra worker subjects',async()=>{
 const {c,reply}=fixture();let unblock;const gate=new Promise(r=>{unblock=r;});c.call=async(_m,params)=>{await gate;return reply(params[1]);};
 const p=new PageOnMiss(c,policy(8)),first=p.fetch(c,EXECUTOR,[key(missing)]);await assert.rejects(p.fetch(c,EXECUTOR,[key(missing+1n)]),/SERIALIZED/);unblock();
 const r=await first;assert.equal(r.storageProof.length,1);assert.equal(p.snapshot().events.length,1);
});

test('caller cannot widen fixed read-ahead bounds',()=>{
 const {c}=fixture();assert.throws(()=>new PageOnMiss(c,{...policy(8),maximumAdditionalKeys:1024}),/FIXED_READ_AHEAD_BOUNDS/);
});
for(const failure of ['bytes','time'])test(`shared RPC ${failure} guard rejects before any page is accepted`,async()=>{
 const f=fixture(),dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhc-page-guard-'));let now=0,sends=0;
 const limits={requests:64,wallMs:30000,requestMs:3000,gapMs:125,bytes:failure==='bytes'?100:8<<20,body:2<<20,header:failure==='bytes'?64:8192};
 const client=rpcClient(dir,{limits,now:()=>now,sleep:async ms=>{now+=ms;},transport:{close(){},async send(body){sends++;const q=JSON.parse(body);return {body:Buffer.from(JSON.stringify({jsonrpc:'2.0',id:q.id,result:f.reply(q.params[1])})),headers:Buffer.alloc(0),status:200};}}});
 try{
  const c=new ProofCollector(f.cp,client.call,f.seed),p=new PageOnMiss(c,policy(8));if(failure==='time')now=30001;
  await assert.rejects(p.fetch(c,EXECUTOR,[key(missing)]),failure==='time'?/ACQUISITION_DEADLINE/:/TRANSPORT_RESPONSE_RESERVATION/);
  assert.equal(p.snapshot().pages,0);assert.equal(p.snapshot().additionalKeys,0);assert.equal(sends,failure==='time'?0:1);
 }finally{await client.close();fs.rmSync(dir,{recursive:true,force:true});}
});


test('accepted policy is copied and frozen independently of caller object',()=>{
 const {c}=fixture(),supplied={...policy(8)},p=new PageOnMiss(c,supplied);supplied.maximumAdditionalKeys=1000;
 assert.equal(p.snapshot().policy.maximumAdditionalKeys,32);assert(Object.isFrozen(p.policy));assert(Object.isFrozen(p.checkpoint));
});

test('cancellation during first page leaves no authenticated page or new trie material',async()=>{
 const f=fixture();let entered,cancel;
 const called=new Promise(resolve=>{entered=resolve;});
 f.c.call=async()=>{entered();return new Promise((_resolve,reject)=>{cancel=()=>reject(new Error('DISCOVERY_INTERRUPTED'));});};
 const before=[...f.c.nodes.keys()],p=new PageOnMiss(f.c,policy());
 const request=p.fetch(f.c,EXECUTOR,[key(missing)]);
 await called;
 const planned=p.snapshot().events[0];
 assert.equal(planned.start,key(missing&~7n));assert.equal(planned.end,key((missing&~7n)+7n));
 assert.equal(planned.start.slice(-4),'e628');assert.equal(planned.end.slice(-4),'e62f');
 cancel();await assert.rejects(request,/DISCOVERY_INTERRUPTED/);
 assert.deepEqual([...f.c.nodes.keys()],before);assert.equal(f.c.proofs.length,0);
 assert.equal(p.snapshot().pages,0);assert.equal(p.snapshot().additionalKeys,0);assert.equal(p.active,false);
 assert.equal(p.snapshot().events[0].status,'REJECTED');
});

test('a proof from another original root cannot commit a page',async()=>{
 const f=fixture(r=>({...r,nonce:'0x2',accountProof:[toRlp(['0x20'+keccak256(EXECUTOR).slice(2),toRlp(['0x02','0x',r.storageHash,CODE_HASH])])]}));
 const before=[...f.c.nodes.keys()],p=new PageOnMiss(f.c,policy());
 await assert.rejects(p.fetch(f.c,EXECUTOR,[key(missing)]));
 assert.deepEqual([...f.c.nodes.keys()],before);assert.equal(f.c.proofs.length,0);assert.equal(p.snapshot().pages,0);
});

test('completed local page is reusable without another fetch and keeps independent collectors original',async()=>{
 const first=fixture(),second=fixture(),page=new PageOnMiss(first.c,policy());
 const result=await page.fetch(first.c,EXECUTOR,[key(missing)]);
 assert.equal(result.storageProof.length,1);assert.equal(first.calls.length,1);
 const snapshot=page.snapshot();assert.equal(snapshot.events[0].start.slice(-4),'e628');
 assert.equal(snapshot.events[0].end.slice(-4),'e62f');assert.equal(snapshot.pages,1);
 const all=first.c.project(EXECUTOR,snapshot.events[0].pageKeys);assert(all);
 assert.equal(all.verified.resolutions.length,8);
 assert.equal(second.c.project(EXECUTOR,[key(missing)]),null);
 await page.fetch(first.c,EXECUTOR,[key(missing+1n)]);assert.equal(first.calls.length,1);
 assert.equal(second.c.nodes.size,1); // The Go Bridge regression separately checks writable LP overlays.
});
