// Offline structural/path audit. No EVM, network, or state mutation.
import assert from 'node:assert/strict';
import {keccak256,fromRlp,toRlp,EMPTY_ROOT,EMPTY_CODE} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {merkleValue,authenticateProof} from '../../../engine/adapters/hookr-case/proof.mjs';
export {keccak256,fromRlp,toRlp,EMPTY_ROOT,EMPTY_CODE};
const nibs=x=>[...x.slice(2)].map(c=>parseInt(c,16));
const hexPath=ns=>'0x'+ns.map(x=>x.toString(16)).join('');
function compact(raw){const ns=nibs(raw),f=ns.shift();assert(f>=0&&f<=3);if(!(f&1))assert.equal(ns.shift(),0);return {path:ns,leaf:!!(f&2)};}
export function makeNodes(values){
 const map=new Map();for(const raw of values){const decoded=fromRlp(raw,'hex');assert.equal(toRlp(decoded),raw);assert(Array.isArray(decoded)&&[2,17].includes(decoded.length));const h=keccak256(raw);if(map.has(h))assert.equal(map.get(h),raw);else map.set(h,raw);}return map;
}
export function proofPath(root,key,map){
 const path=nibs(key),used=[];let ref=root,at=0;
 for(let i=0;i<130;i++){
  if(ref==='0x'||ref===EMPTY_ROOT)return used;
  let node;
  if(Array.isArray(ref))node=ref;
  else{const raw=ref.length===66?map.get(ref):ref;if(raw===undefined){const e=Error('UNKNOWN');e.hash=ref;e.prefix=hexPath(path.slice(0,at));throw e;}if(ref.length===66)used.push(raw);node=fromRlp(raw,'hex');}
  if(node.length===17){if(at===path.length)return used;ref=node[path[at++]];continue;}
  assert.equal(node.length,2);const c=compact(node[0]);if(c.path.some((x,j)=>x!==path[at+j]))return used;at+=c.path.length;if(c.leaf)return used;ref=node[1];
 }
 throw Error('PATH_LIMIT');
}
export function lookup(root,key,map){
 try{const proof=proofPath(root,key,map),v=merkleValue(root,key,proof);return {status:v.value===null?'PROVEN_ABSENT':'PRESENT',value:v.value,proofNodes:proof.length};}
 catch(e){if(e.message==='UNKNOWN')return {status:'UNKNOWN',missingNodeHash:e.hash,prefix:e.prefix};throw e;}
}
function walk(root,map){
 const leaves=[],frontier=[],visited=new Set();let emptyEdges=0,steps=0;
 function rec(ref,path,proof,ancestors,depth){
  assert(++steps<=250000&&depth<130&&path.length<=64,'TRIE_BOUNDS');
  if(ref==='0x'||ref===EMPTY_ROOT){emptyEdges++;return;}
  let node,raw,id=null,p=proof;
  if(Array.isArray(ref)){node=ref;raw=toRlp(node);assert((raw.length-2)/2<32);}
  else{raw=ref.length===66?map.get(ref):ref;if(raw===undefined){frontier.push({hash:ref,prefix:hexPath(path)});return;}node=fromRlp(raw,'hex');if(ref.length===66){id=ref;visited.add(id);p=[...proof,raw];}else assert((raw.length-2)/2<32);}
  assert.equal(toRlp(node),raw);
  if(node.length===17){
   const live=node.slice(0,16).map((r,i)=>r==='0x'?null:i).filter(x=>x!==null);
   if(node[16]!=='0x'){assert.equal(path.length,64);leaves.push({keyHash:hexPath(path),value:node[16],proof:p,ancestors});}
   for(const i of live)rec(node[i],[...path,i],p,[...ancestors,{kind:'branch',id,node,chosen:i}],depth+1);
   emptyEdges+=16-live.length;return;
  }
  assert.equal(node.length,2);const c=compact(node[0]),full=[...path,...c.path];
  if(c.leaf){assert.equal(full.length,64,'HASHED_LEAF_LENGTH');leaves.push({keyHash:hexPath(full),value:node[1],proof:p,ancestors});}
  else{assert(c.path.length>0);rec(node[1],full,p,[...ancestors,{kind:'extension',id}],depth+1);}
 }
 rec(root,[],[],[],0);
 for(const l of leaves){const validated=merkleValue(root,l.keyHash,l.proof);assert.equal(validated.value,l.value);}
 return {leaves,frontier,visited,emptyEdges};
}
function deleteSibling(leaf,map){
 const b=leaf.ancestors.findLast(a=>a.kind==='branch');
 if(!b)return {status:'NO_EXTRA_NODE',reason:'single path deletion empties trie'};
 const remain=b.node.slice(0,16).map((ref,i)=>({ref,i})).filter(x=>x.i!==b.chosen&&x.ref!=='0x');
 if(b.node[16]!=='0x'||remain.length!==1)return {status:'NO_EXTRA_NODE',reason:'nearest branch does not need single-child collapse'};
 const ref=remain[0].ref;
 if(Array.isArray(ref)||ref.length!==66)return {status:'AVAILABLE',reason:'collapse child inline'};
 return map.has(ref)?{status:'AVAILABLE',requiredNodeHash:ref}:{status:'UNKNOWN',requiredNodeHash:ref,reason:'canonical collapse must inspect surviving child type/path'};
}
export function auditForest(root,nodes,codes){
 const accounts=walk(root,nodes),storages=[],boundCode=new Set(),missingCodes=new Set(),reached=new Set(accounts.visited),deletions=[];
 for(const l of accounts.leaves){
  const fields=fromRlp(l.value,'hex');assert(Array.isArray(fields)&&fields.length===4);assert.equal(toRlp(fields),l.value);
  for(const q of fields.slice(0,2))assert(q==='0x'||!q.startsWith('0x00'));
  assert.equal(fields[2].length,66);assert.equal(fields[3].length,66);
  if(fields[3]!==EMPTY_CODE)(codes.has(fields[3])?boundCode:missingCodes).add(fields[3]);
  const t=walk(fields[2],nodes);for(const n of t.visited)reached.add(n);
  for(const sl of t.leaves){const v=fromRlp(sl.value,'hex');assert(typeof v==='string'&&v!=='0x'&&!v.startsWith('0x00'));assert.equal(toRlp(v),sl.value);deletions.push({accountKeyHash:l.keyHash,storageRoot:fields[2],slotKeyHash:sl.keyHash,...deleteSibling(sl,nodes)});}
  storages.push({accountKeyHash:l.keyHash,nonce:fields[0]==='0x'?'0':BigInt(fields[0]).toString(),balance:fields[1]==='0x'?'0':BigInt(fields[1]).toString(),storageRoot:fields[2],codeHash:fields[3],codeCaptured:fields[3]===EMPTY_CODE||codes.has(fields[3]),knownStorageLeaves:t.leaves.length,unknownFrontier:t.frontier.length,emptyEdges:t.emptyEdges,frontier:t.frontier});
 }
 return {availableAccountLeaves:accounts.leaves.length,accountFrontier:accounts.frontier,provenEmptyAccountEdges:accounts.emptyEdges,accounts:storages,
  knownStorageLeaves:storages.reduce((n,x)=>n+x.knownStorageLeaves,0),unknownStorageFrontier:storages.reduce((n,x)=>n+x.unknownFrontier,0),rootReachableNodes:reached.size,unanchoredSuppliedNodes:[...nodes.keys()].filter(k=>!reached.has(k)),providedCodeHashes:[...codes.keys()],providedCodeHashesBoundToKnownAccounts:[...boundCode],missingCodeHashesAtKnownAccounts:[...missingCodes],leafDeletionRequirements:deletions,
  possibleDeletionSiblingGaps:deletions.filter(x=>x.status==='UNKNOWN'),
  completeness:'NOT_INFERRED_FROM_NODE_COUNT_OR_PARTIAL_FRONTIER'};
}
export function mergeProof(root,address,slots,proof,nodes){const v=authenticateProof(root,address,slots,proof);for(const [h,raw]of v.nodes){if(nodes.has(h))assert.equal(nodes.get(h),raw);else nodes.set(h,raw);}return v;}
