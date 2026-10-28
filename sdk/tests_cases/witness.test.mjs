// Run against the installed library with its pinned dependencies. Synthetic
// trie fixtures test availability/authentication, never canonical execution.
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;
assert(lib,'Set RHOOK_TEST_INSTALLED_LIB to the private test installation');
const load=name=>import(pathToFileURL(path.join(lib,name)));
const {dependency,chunkSlots,projectProof,mergeWitness,analyze}=await load('rhook_alpha/cases/witness/material.mjs');
const {makeNodes}=await load('rhook_alpha/cases/witness/trie.mjs');
const {keccak256,toRlp,EMPTY_ROOT,EMPTY_CODE}=await load('engine/adapters/hookr-case/primitives.mjs');
const {headerHash}=await load('engine/plan_native/ethereum.mjs');
const address='0x'+'11'.repeat(20),slot='0x'+'22'.repeat(32),other='0x'+'33'.repeat(20);
function fixture(storageRoot=EMPTY_ROOT){
  const account=toRlp(['0x01','0x',storageRoot,EMPTY_CODE]);
  const raw=toRlp(['0x20'+keccak256(address).slice(2),account]);
  return {cp:{stateRoot:keccak256(raw)},m:{nodes:makeNodes([raw]),codes:new Map()}};
}
function input(){
  const {cp,m}=fixture();
  const h={parentHash:'0x'+'00'.repeat(32),sha3Uncles:'0x'+'11'.repeat(32),miner:'0x'+'00'.repeat(20),stateRoot:cp.stateRoot,
    transactionsRoot:EMPTY_ROOT,receiptsRoot:EMPTY_ROOT,logsBloom:'0x'+'00'.repeat(256),difficulty:'0x1',number:'0xa',gasLimit:'0x989680',gasUsed:'0x0',
    timestamp:'0x1',extraData:'0x'+'00'.repeat(32),mixHash:'0x'+'00'.repeat(32),nonce:'0x'+'00'.repeat(8),baseFeePerGas:'0x1'};
  h.hash=headerHash(h);const block={...h,parentHash:h.hash,number:'0xb',transactions:[{hash:'0x'+'99'.repeat(32),type:'0x6a'}]};block.hash=headerHash(block);
  return {checkpoint:{chainId:4663,blockNumber:10,blockHash:h.hash,stateRoot:cp.stateRoot},parent:h,block,rawTransactions:[],proofs:[],state:[...m.nodes.values()],codes:[]};
}
test('account membership and authenticated absence remain distinct',()=>{
  const {cp,m}=fixture();assert.equal(dependency(cp,m,address).status,'PRESENT');assert.equal(dependency(cp,m,other).status,'PROVEN_ABSENT');
});
test('missing root is UNKNOWN with the exact node hash, not absence',()=>{
  const {cp,m}=fixture();m.nodes.clear();const r=dependency(cp,m,address);assert.equal(r.status,'MISSING');assert.equal(r.missingNodeHash,cp.stateRoot);
});
test('missing and absent account paths preserve the requested storage slot',()=>{
  const {cp,m}=fixture();
  assert.equal(dependency(cp,m,other,slot).slot,slot);
  m.nodes.clear();assert.equal(dependency(cp,m,address,slot).slot,slot);
});
test('empty storage is proven zero',()=>{
  const {cp,m}=fixture();const r=dependency(cp,m,address,slot);assert.equal(r.status,'PROVEN_ABSENT');assert.equal(r.value,'0');
});
test('missing storage frontier names its unavailable node',()=>{
  const missing='0x'+'44'.repeat(32),{cp,m}=fixture(missing);const r=dependency(cp,m,address,slot);assert.equal(r.status,'MISSING');assert.equal(r.missingNodeHash,missing);
});
test('authenticated storage value is read from the proof bytes',()=>{
  const raw=toRlp(['0x20'+keccak256(slot).slice(2),toRlp('0x32')]);
  const {cp,m}=fixture(keccak256(raw));m.nodes.set(keccak256(raw),raw);assert.equal(dependency(cp,m,address,slot).value,'50');
});
test('config chunks have a bounded exact declared length',()=>{
  assert.equal(chunkSlots(624).length,20);assert.equal(chunkSlots(1536).length,48);
  for(const value of [0,1537,-1,NaN,1.5])assert.throws(()=>chunkSlots(value));
});
test('malformed RLP and non-trie nodes fail closed',()=>{
  for(const node of ['0x','0xc0',toRlp(['0x','0x','0x'])])assert.throws(()=>makeNodes([node]));
});
test('derived account paths are genuine proofs, not acquisition records',async()=>{
  const {cp,m}=fixture();
  // projectProof also authenticates real headers/material; check its path
  // primitive separately here with the existing proof verifier.
  const {proofPath}=await load('rhook_alpha/cases/witness/trie.mjs');
  const {authenticateAccount}=await load('engine/adapters/hookr-case/proof.mjs');
  const proof={address,accountProof:proofPath(cp.stateRoot,keccak256(address),m.nodes),nonce:'0x1',balance:'0x0',storageHash:EMPTY_ROOT,codeHash:EMPTY_CODE};
  assert.equal(authenticateAccount(cp.stateRoot,address,proof).account.status,'PRESENT');
  assert.throws(()=>authenticateAccount(cp.stateRoot,address,{...proof,nonce:'0x2'}));
});
test('native-import projection is authenticated and carries no fake RPC record',()=>{
  const p=input(),v=projectProof(p,address,[]);assert.equal(v.address,address);assert.equal(v.proof.nonce,'0x1');assert(!Object.hasOwn(v,'request'));
});
test('external seed checkpoint cannot be substituted by its status label',()=>{
  const p=input();assert.throws(()=>mergeWitness(p,{format:'rhook/remote-witness-seed/0.1',checkpoint:{...p.checkpoint,stateRoot:EMPTY_ROOT},status:'AUTHENTICATED_SEED',nodes:{},codes:{}}),/WITNESS_CHECKPOINT/);
});
test('external preimages must match their declared hash',()=>{
  const p=input();assert.throws(()=>mergeWitness(p,{format:'rhook/remote-witness-seed/0.1',checkpoint:p.checkpoint,nodes:{['0x'+'01'.repeat(32)]:'0xc0'},codes:{}}),/PREIMAGE_HASH/);
});
test('header-only partial data is not called authenticated state or complete coverage',async()=>{
  const p={...input(),state:[]},r=await analyze(p);assert.equal(r.status,'HEADERS_ONLY_INCOMPLETE');assert.equal(r.authentication,'HEADERS_VERIFIED_STATE_NOT_AUTHENTICATED');
  assert.equal(r.completeForCase,false);assert.equal(r.inputCommitment,null);assert(r.missing.length>0);assert.equal(r.nativeExecutions,0);
});
test('Nitro filtering context names a missing original-root account before Go admission',async()=>{
 const p=input();p.state=[];const r=await analyze(p),address='0xa4b0500000000000000000000000000000000001';
 const row=r.missing.find(x=>x.address===address&&x.kind==='ACCOUNT');assert(row,'missing native context must not be JS-ready');
 assert.equal(row.reason,'ACCOUNT_PATH_MISSING');assert.equal(row.missingNodeHash,p.checkpoint.stateRoot);assert.equal(r.knownDependenciesPresent,false);
});
test('proven absence of Nitro filtering context stays distinct from a missing path',async()=>{
 const p=input(),r=await analyze(p),address='0xa4b0500000000000000000000000000000000001';
 const row=r.dependencies.find(x=>x.address===address&&x.kind==='ACCOUNT');assert(row);assert.equal(row.status,'PROVEN_ABSENT');assert(!r.missing.some(x=>x.address===address));
});
