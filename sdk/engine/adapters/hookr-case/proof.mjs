import assert from 'node:assert/strict';
import {hex,hash,address,slot,quantity,keccak256,fromRlp,toRlp,EMPTY_ROOT,EMPTY_CODE} from './primitives.mjs';
const nibs=x=>[...x.slice(2)].map(c=>parseInt(c,16));
export function merkleValue(root,key,proof){
 hash(root);hex(key,32);assert(Array.isArray(proof)&&proof.length<=128,'INVALID_PROOF');
 const supplied=new Map();
 for(const value of proof){const raw=hex(value),id=keccak256(raw);assert((raw.length-2)/2<=4096,'NODE_TOO_LARGE');if(supplied.has(id))assert.equal(supplied.get(id),raw,'HASH_COLLISION');supplied.set(id,raw);}
 if(root===EMPTY_ROOT){assert.equal(supplied.size,0,'UNRELATED_EMPTY_TRIE_PROOF');return {value:null,path:[],nodes:new Map()};}
 let ref=root,at=0;const path=nibs(key),used=new Map(),ids=[];
 const result=value=>{assert.equal(used.size,supplied.size,'UNREFERENCED_PROOF_NODE');return {value,path:ids,nodes:used};};
 for(let step=0;step<129;step++){
  let node;
  if(Array.isArray(ref))node=ref;
  else{
   if(ref==='0x')return result(null);
   const encoded=ref.length===66?supplied.get(ref):ref;
   assert(encoded,'MISSING_PROOF_NODE');
   if(ref.length!==66)assert((encoded.length-2)/2<32,'INVALID_INLINE_REFERENCE');
   node=fromRlp(encoded,'hex');assert.equal(toRlp(node),encoded,'NON_CANONICAL_RLP');
   if(ref.length===66){used.set(ref,encoded);ids.push(ref);}
  }
  assert(Array.isArray(node),'INVALID_TRIE_NODE');
  if(node.length===17){
   if(at===path.length){assert(typeof node[16]==='string');return result(node[16]==='0x'?null:node[16]);}
   ref=node[path[at++]];continue;
  }
  assert.equal(node.length,2,'INVALID_TRIE_ARITY');assert(typeof node[0]==='string');
  const cp=nibs(node[0]),flag=cp.shift();assert(flag>=0&&flag<=3,'INVALID_COMPACT_FLAG');
  if(!(flag&1))assert.equal(cp.shift(),0,'INVALID_COMPACT_PADDING');
  assert(at+cp.length<=path.length,'TRIE_PATH_OVERFLOW');
  if(cp.some((n,i)=>n!==path[at+i]))return result(null);
  at+=cp.length;
  if(flag&2){assert(typeof node[1]==='string');return result(at===path.length?node[1]:null);}
  assert(cp.length>0,'EMPTY_TRIE_EXTENSION');ref=node[1];
 }
 throw Error('TRIE_PATH_LIMIT');
}
function rlpInteger(raw){
 hex(raw);assert(raw==='0x'||!raw.startsWith('0x00'),'NON_CANONICAL_INTEGER');assert((raw.length-2)/2<=32,'INTEGER_TOO_LARGE');return raw==='0x'?0n:BigInt(raw);
}
export function authenticateAccount(root,subject,proof){
 subject=address(subject);assert.equal(address(proof.address),subject,'ACCOUNT_SUBJECT_MISMATCH');
 const verified=merkleValue(root,keccak256(subject),proof.accountProof);
 let account;
 if(verified.value===null)account={address:subject,status:'ABSENT',nonce:'0',balance:'0',storageRoot:EMPTY_ROOT,codeHash:EMPTY_CODE,path:verified.path};
 else{
  const fields=fromRlp(verified.value,'hex');assert(Array.isArray(fields)&&fields.length===4,'INVALID_ACCOUNT_RLP');assert.equal(toRlp(fields),verified.value);
  account={address:subject,status:'PRESENT',nonce:rlpInteger(fields[0]).toString(),balance:rlpInteger(fields[1]).toString(),storageRoot:hash(fields[2]),codeHash:hash(fields[3]),path:verified.path};
 }
 assert.equal(quantity(proof.nonce).toString(),account.nonce,'NONCE_METADATA_MISMATCH');assert.equal(quantity(proof.balance).toString(),account.balance,'BALANCE_METADATA_MISMATCH');
 if(account.status==='PRESENT'){assert.equal(hash(proof.storageHash),account.storageRoot,'STORAGE_ROOT_METADATA_MISMATCH');assert.equal(hash(proof.codeHash),account.codeHash,'CODE_HASH_METADATA_MISMATCH');}
 else{assert([EMPTY_ROOT,'0x'+'00'.repeat(32)].includes(hash(proof.storageHash)));assert([EMPTY_CODE,'0x'+'00'.repeat(32)].includes(hash(proof.codeHash)));}
 return {account,nodes:verified.nodes};
}
export function authenticateStorage(account,key,proof){
 key=slot(key);assert.equal(slot(proof.key),key,'STORAGE_SUBJECT_MISMATCH');
 const verified=merkleValue(account.storageRoot,keccak256(key),proof.proof);
 let value=0n;
 if(verified.value!==null){const decoded=fromRlp(verified.value,'hex');assert(typeof decoded==='string');assert.equal(toRlp(decoded),verified.value);value=rlpInteger(decoded);assert(value>0n,'NON_CANONICAL_ZERO_STORAGE');}
 assert.equal(quantity(proof.value),value,'STORAGE_VALUE_METADATA_MISMATCH');
 return {resolution:{address:account.address,key,status:verified.value===null?'ABSENT':'PRESENT',value:value.toString(),path:verified.path},nodes:verified.nodes};
}
export function authenticateProof(root,subject,keys,proof){
 assert(Array.isArray(keys)&&keys.length<=48,'PROOF_SUBJECT_LIMIT');keys=keys.map(slot);assert.equal(new Set(keys).size,keys.length,'DUPLICATE_STORAGE_SUBJECT');
 const {account,nodes}=authenticateAccount(root,subject,proof);assert(Array.isArray(proof.storageProof)&&proof.storageProof.length===keys.length,'STORAGE_SUBJECT_SET_MISMATCH');
 const resolutions=[];
 for(let i=0;i<keys.length;i++){const result=authenticateStorage(account,keys[i],proof.storageProof[i]);resolutions.push(result.resolution);for(const [id,raw]of result.nodes){if(nodes.has(id))assert.equal(nodes.get(id),raw);nodes.set(id,raw);}}
 return {account,resolutions,nodes};
}
