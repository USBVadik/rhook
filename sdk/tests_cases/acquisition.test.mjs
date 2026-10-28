// Synthetic protocol/availability tests, never canonical EVM execution.
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;
assert(lib,'RHOOK_TEST_INSTALLED_LIB required');
const load=name=>import(pathToFileURL(path.join(lib,name)));
const {rawFromRpc}=await load('rhook_alpha/cases/witness/transactions.mjs');
const {ProofCollector}=await load('rhook_alpha/cases/witness/collector.mjs');
const {qualifyRoot}=await load('rhook_alpha/cases/witness/qualify.mjs');
const {selectRecent,captureBlock}=await load('rhook_alpha/cases/witness/capture.mjs');
const {headerHash}=await load('engine/plan_native/ethereum.mjs');
const {C}=await load('rhook_alpha/cases/witness/material.mjs');
const fs=await import('node:fs'),os=await import('node:os');
const {toRlp,keccak256,EMPTY_ROOT,EMPTY_CODE}=await load('engine/adapters/hookr-case/primitives.mjs');
const address='0x'+'11'.repeat(20),slot='0x'+'22'.repeat(32),code='0x6000';
function fixture(){
 const account=toRlp(['0x01','0x',EMPTY_ROOT,keccak256(code)]),leaf=toRlp(['0x20'+keccak256(address).slice(2),account]);
 const cp={chainId:4663,blockNumber:10,blockHash:'0x'+'33'.repeat(32),stateRoot:keccak256(leaf)};
 const proof={address,accountProof:[leaf],nonce:'0x1',balance:'0x0',storageHash:EMPTY_ROOT,codeHash:keccak256(code),storageProof:[]};return {cp,proof};
}
test('signed type2 bytes are reconstructed and checked against their hash',()=>{
 const tx={type:'0x2',chainId:'0x1237',nonce:'0x0',maxPriorityFeePerGas:'0x0',maxFeePerGas:'0x2',gas:'0x5208',to:address,value:'0x1',input:'0x',accessList:[],yParity:'0x0',r:'0x1',s:'0x2'};
 const raw='0x02'+toRlp(['0x1237','0x','0x','0x02','0x5208',address,'0x01','0x',[],'0x','0x01','0x02']).slice(2);
 tx.hash=keccak256(raw);assert.equal(rawFromRpc(tx),raw);assert.throws(()=>rawFromRpc({...tx,value:'0x2'}),/RAW_HASH/);
});
test('Nitro internal envelope uses the retained two-field encoding',()=>{
 const raw='0x6a'+toRlp(['0x1237','0x0102']).slice(2);
 assert.equal(rawFromRpc({type:'0x6a',chainId:'0x1237',input:'0x0102',hash:keccak256(raw)}),raw);
});
test('unsupported types stop instead of silently substituting an envelope',()=>{
 assert.throws(()=>rawFromRpc({type:'0x4'}),/UNSUPPORTED_TRANSACTION_TYPE/);
});
test('cached account and proven-zero storage need no repeated proof RPC',async()=>{
 const {cp,proof}=fixture();let calls=0;
 const c=new ProofCollector(cp,async(method,params)=>{calls++;assert.equal(method,'eth_getProof');assert.deepEqual(params[2],{blockHash:cp.blockHash,requireCanonical:true});return proof;});
 await c.proof(address,[]);const v=await c.proof(address,[slot]);assert.equal(v.resolutions[0].value,'0');assert.equal(calls,1);assert(c.projections.length>0);
});
test('code bytes are cached only after account binding and hash validation',async()=>{
 const {cp,proof}=fixture();let requests=0;
 const c=new ProofCollector(cp,async method=>{requests++;return method==='eth_getProof'?proof:code;});
 await c.proof(address,[]);assert.equal(await c.code(address),code);assert.equal(await c.code(address),code);assert.equal(requests,2);
});
test('wrong-root seed and poisoned code bytes are rejected',async()=>{
 const {cp,proof}=fixture();assert.throws(()=>new ProofCollector(cp,async()=>{}, {checkpoint:{...cp,blockNumber:9},nodes:{},codes:{}}),/CHECKPOINT/);
 const c=new ProofCollector(cp,async method=>method==='eth_getProof'?proof:'0x6001');await c.proof(address,[]);await assert.rejects(c.code(address),/CODE_HASH/);
});
test('constructor pins a copy of the checkpoint',async()=>{
 const {cp,proof}=fixture();const wanted=cp.blockHash;let observed;
 const c=new ProofCollector(cp,async(_m,p)=>{observed=p[2].blockHash;return proof;});cp.blockHash='0x'+'44'.repeat(32);
 await c.proof(address,[]);assert.equal(observed,wanted);
});
test('partly cached grouped storage requests only its unresolved slots',async()=>{
 const a=slot;let b='0x'+'44'.repeat(32);while(keccak256(a)[2]===keccak256(b)[2])b='0x'+(BigInt(b)+1n).toString(16).padStart(64,'0');
 const leaf=(key,value)=>toRlp(['0x3'+keccak256(key).slice(3),toRlp(value)]);
 const one=leaf(a,'0x01'),two=leaf(b,'0x02'),branch=Array(17).fill('0x');branch[parseInt(keccak256(a)[2],16)]=keccak256(one);branch[parseInt(keccak256(b)[2],16)]=keccak256(two);
 const storage=toRlp(branch),account=toRlp(['0x01','0x',keccak256(storage),EMPTY_CODE]),root=toRlp(['0x20'+keccak256(address).slice(2),account]);
 const cp={chainId:4663,blockNumber:10,blockHash:'0x'+'33'.repeat(32),stateRoot:keccak256(root)},requests=[];
 const c=new ProofCollector(cp,async(_m,params)=>{
  requests.push(params[1]);return {address,nonce:'0x1',balance:'0x0',codeHash:EMPTY_CODE,storageHash:keccak256(storage),accountProof:[root],
   storageProof:params[1].map(key=>({key,value:key===a?'0x1':'0x2',proof:[storage,key===a?one:two]}))};
 });
 await c.proof(address,[a]);const v=await c.proof(address,[a,b]);assert.deepEqual(requests,[[a],[b]]);assert.deepEqual(v.resolutions.map(x=>x.value),['1','2']);
});
function header(number,root){
 const h={parentHash:'0x'+'00'.repeat(32),sha3Uncles:'0x'+'11'.repeat(32),miner:'0x'+'00'.repeat(20),stateRoot:root,transactionsRoot:EMPTY_ROOT,
  receiptsRoot:EMPTY_ROOT,logsBloom:'0x'+'00'.repeat(256),difficulty:'0x1',number:'0x'+number.toString(16),gasLimit:'0x989680',gasUsed:'0x0',timestamp:'0x1',
  extraData:'0x'+'00'.repeat(32),mixHash:'0x'+'00'.repeat(32),nonce:'0x'+'00'.repeat(8),baseFeePerGas:'0x1'};h.hash=headerHash(h);return h;
}
async function qualifiedFixture(fail=false){
 const leaf=toRlp(['0x20'+keccak256(C.rules).slice(2),toRlp(['0x01','0x',EMPTY_ROOT,EMPTY_CODE])]),root=keccak256(leaf),calls=[];
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhook-fresh-test-'));let headers=0;
 const client={observations:()=>calls,call:async(method,params)=>{
  const offset=calls.length*100;calls.push({method,params,transportStartedOffsetMs:offset,responseCompleteOffsetMs:offset+20,transportStartedUnixMs:1000000+offset});
  if(method==='eth_chainId')return '0x1237';if(method==='eth_getBlockByNumber')return header(2000+headers++,root);
  if(fail)throw Error('historical state '+root+' is not available');
  return {address:C.rules,nonce:'0x1',balance:'0x0',codeHash:EMPTY_CODE,storageHash:EMPTY_ROOT,accountProof:[leaf],storageProof:[{key:C.slot,value:'0x0',proof:[]}]};
 }};
 try{return {result:await qualifyRoot(client,dir),calls};}finally{fs.rmSync(dir,{recursive:true,force:true});}
}
test('fresh-root qualification authenticates a proof and reports observation age',async()=>{
 const {result:r,calls}=await qualifiedFixture();assert.equal(r.status,'FRESH_ROOT_PROOF_AUTHENTICATED');assert.equal(calls.length,4);
 assert.equal(r.ageSinceCheckpointObservedMs,80);assert.equal(r.headAfterProof.distanceFromCheckpoint,1);assert.equal(r.eligibleHookrCaseSelected,false);assert.equal(r.nativeExecutions,0);
});
test('fresh-root failure preserves its classification without reselecting or retrying',async()=>{
 const {result:r,calls}=await qualifiedFixture(true);assert.equal(r.status,'FRESHLY_OBSERVED_ROOT_UNAVAILABLE');assert.equal(r.proofAuthenticated,false);assert.equal(calls.length,3);
});
test('no pool events means no candidate, with exactly one bounded log search',async()=>{
 const calls=[];await assert.rejects(selectRecent({call:async(method)=>{calls.push(method);return method==='eth_getLogs'?[]:header(2000,EMPTY_ROOT);}}),/NO_SUPPORTED_POOL_EVENT/);
 assert.deepEqual(calls,['eth_getBlockByNumber','eth_getLogs']);
});
test('a changed selected event block is rejected before proof acquisition',async()=>{
 const block={...header(2000,EMPTY_ROOT),transactions:[{hash:'0x'+'11'.repeat(32)},{hash:'0x'+'22'.repeat(32)}]};
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhook-event-test-'));let calls=0;
 try{await assert.rejects(captureBlock({call:async()=>++calls===1?'0x1237':block},2000,dir,{selection:{blockNumber:2000,blockHash:'0x'+'99'.repeat(32),subjectIndex:1,transactionHash:block.transactions[1].hash}}),/EVENT_BLOCK_HASH_CHANGED/);assert.equal(calls,2);}
 finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('overlapping reads of one proven code hash share one fetch',async()=>{
 const {cp,proof}=fixture();let codeReads=0,release;
 const c=new ProofCollector(cp,async method=>method==='eth_getProof'?proof:(codeReads++,await new Promise(r=>{release=r;})));
 await c.proof(address,[]);const one=c.code(address),two=c.code(address);assert.equal(codeReads,1);release(code);
 assert.deepEqual(await Promise.all([one,two]),[code,code]);assert.equal(c.counts.networkCodes,1);
});
test('expired checkpoint proofs and missing code preserve their exact dependency identities',async()=>{
 const {cp,proof}=fixture();
 const c=new ProofCollector(cp,async method=>{if(method==='eth_getProof')return proof;throw Error('CODE_UNAVAILABLE');});
 await c.proof(address,[]);await assert.rejects(c.code(address),e=>e.missingDependency.kind==='CODE'&&e.missingDependency.address===address&&e.missingDependency.codeHash===keccak256(code)&&e.missingDependency.checkpoint.blockHash===cp.blockHash);
 const d=new ProofCollector(cp,async()=>{throw Error('historical state unavailable');});
 await assert.rejects(d.proof(address,[slot]),e=>e.missingDependency.kind==='ACCOUNT_OR_STORAGE_PROOF'&&e.missingDependency.address===address&&e.missingDependency.slots[0]===slot&&e.missingDependency.checkpoint.stateRoot===cp.stateRoot);
});
