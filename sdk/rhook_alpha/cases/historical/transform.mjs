// Exact existing-leaf replacement. No insertion/deletion, EVM or transport.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {canonical,commitment,keccak256,fromRlp,toRlp} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {authenticateProof,merkleValue} from '../../../engine/adapters/hookr-case/proof.mjs';
import {proofPath} from '../witness/trie.mjs';
export const PROFILE='nitro-hookr-historical-dynamic-fee-off/0.1';
export const DOMAIN='rhook/hookr-historical-dynamic-fee-off/0.1';
export const profile=JSON.parse(fs.readFileSync(new URL('./profile.json',import.meta.url)));
export function validateTransform(i){
 const body={schema:DOMAIN+'/transform',checkpoint:profile.checkpoint,pool:profile.pool,rootCodeHash:profile.rootCodeHash,rulesCodeHash:profile.rulesCodeHash,writes:profile.writes};
 assert.deepEqual(i,{...body,interventionCommitment:commitment(DOMAIN+'/transform',body)},'EXACT_HISTORICAL_TRANSFORM');
}
export function validatePlan(p){
 const body={schema:DOMAIN+'/transform',checkpoint:profile.checkpoint,pool:profile.pool,rootCodeHash:profile.rootCodeHash,rulesCodeHash:profile.rulesCodeHash,writes:profile.writes};
 const intervention={...body,interventionCommitment:commitment(DOMAIN+'/transform',body)};
 assert.deepEqual(p,{schema:DOMAIN+'/plan',packageSha256:profile.packageSha256,inputCommitment:profile.inputCommitment,witnessCommitment:profile.witnessCommitment,
  checkpoint:profile.checkpoint,...profile.target,arrivals:profile.arrivals,transactions:7,subject:profile.subject,sender:profile.sender,router:profile.router,
  observation:profile.observation,intervention,rulesRuntimeHash:profile.rulesCodeHash},'EXACT_HISTORICAL_PLAN');
}
function read(root,key,nodes){return merkleValue(root,key,proofPath(root,key,nodes)).value;}
export function authenticateTransform(i,checkpoint,nodes,codes){
 validateTransform(i);assert.deepEqual(checkpoint,profile.checkpoint);
 for(const [n,w]of i.writes.entries()){
  const raw=read(checkpoint.stateRoot,keccak256(w.address),nodes);assert(raw!==null,'TARGET_ACCOUNT_ABSENT');
  const a=fromRlp(raw,'hex');assert.equal(toRlp(a),raw);assert.equal(a.length,4);
  const hash=n===0?i.rulesCodeHash:i.rootCodeHash;assert.equal(a[3],hash);assert.equal(keccak256(codes.get(hash)),hash);
  const v=read(a[2],keccak256(w.slot),nodes);assert.notEqual(v,null,'TARGET_WORD_ABSENT');
  const word=fromRlp(v,'hex');assert.equal(toRlp(word),v);assert(!word.startsWith('0x00'),'NON_CANONICAL_WORD');
  assert.equal(BigInt(word),BigInt(w.before));
 }
}
function replaceExisting(root,key,value,nodes){
 const path=[...key.slice(2)].map(c=>parseInt(c,16));
 function update(ref,at){
  const raw=Array.isArray(ref)?toRlp(ref):ref.length===66?nodes.get(ref):ref;
  assert(raw,'MISSING_UPDATE_NODE:'+ref);const node=fromRlp(raw,'hex');assert.equal(toRlp(node),raw);
  if(node.length===17){assert(at<path.length);node[path[at]]=update(node[path[at]],at+1);}
  else{
   assert.equal(node.length,2);const cp=[...node[0].slice(2)].map(c=>parseInt(c,16));const flag=cp.shift();assert(flag<=3);
   if(!(flag&1))assert.equal(cp.shift(),0);
   assert.deepEqual(cp,path.slice(at,at+cp.length),'EXISTING_PATH_ONLY');at+=cp.length;
   if(flag&2){assert.equal(at,path.length);node[1]=value;}
   else node[1]=update(node[1],at);
  }
  const encoded=toRlp(node),h=keccak256(encoded);nodes.set(h,encoded);return (encoded.length-2)/2<32?node:h;
 }
 const ref=update(root,0);return Array.isArray(ref)?keccak256(toRlp(ref)):ref;
}
export function deriveOverlayRoot(pkg,plan){
 const i=plan.intervention;validateTransform(i);
 const nodes=new Map(pkg.state.map(n=>[keccak256(n),n])),codes=new Map(pkg.codes.map(n=>[keccak256(n),n]));
 for(const p of pkg.proofs){const v=authenticateProof(pkg.checkpoint.stateRoot,p.address,p.slots??[],{...p.proof,storageProof:p.proof.storageProof??[]});for(const [h,vv]of v.nodes)nodes.set(h,vv);}
 authenticateTransform(i,pkg.checkpoint,nodes,codes);
 let root=pkg.checkpoint.stateRoot;
 for(const w of i.writes){
  const a=fromRlp(read(root,keccak256(w.address),nodes),'hex');
  const n=BigInt(w.after);assert(n>0n);const after='0x'+n.toString(16).padStart(Math.ceil(n.toString(16).length/2)*2,'0');
  a[2]=replaceExisting(a[2],keccak256(w.slot),toRlp(after),nodes);
  root=replaceExisting(root,keccak256(w.address),toRlp(a),nodes);
 }
 assert.notEqual(root,pkg.checkpoint.stateRoot);return root;
}
