// Offline descriptor target authentication only. No transport, EVM or authority API.
// Input on stdin: {"spec": <prepared scenario input>, "descriptor": <parsed reviewed descriptor>}. For every
// declared contract it authenticates the account from the checkpoint state root (code hash, code preimage present
// and non-empty), and for every declared target every word, through the witness trie nodes only. A missing node
// stops; nothing is read as zero unless the trie proves the leaf absent.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {keccak256,fromRlp,toRlp,hex,hash,EMPTY_CODE} from '../engine/adapters/hookr-case/primitives.mjs';
import {makeNodes,lookup} from './cases/witness/trie.mjs';
const word=n=>'0x'+n.toString(16).padStart(64,'0');
function stop(code,details){throw Object.assign(Error(code),{code,details});}
export function authenticateProfileTargets(spec,descriptor){
 assert(spec&&spec.inventory&&Array.isArray(spec.inventory.nodes)&&spec.inventory.nodes.length<=4096,'INVENTORY_LIMIT');
 assert(Array.isArray(spec.inventory.codes)&&spec.inventory.codes.length<=256,'INVENTORY_LIMIT');
 assert(descriptor&&Array.isArray(descriptor.contracts)&&Array.isArray(descriptor.targets)&&descriptor.contracts.length<=16&&descriptor.targets.length<=16,'DESCRIPTOR_SHAPE');
 for(const value of spec.inventory.nodes)assert(hex(value).length<=8194,'NODE_TOO_LARGE');
 const nodes=makeNodes(spec.inventory.nodes);
 const codes=new Map();
 for(const value of spec.inventory.codes){const raw=hex(value);assert(raw.length<=196610,'CODE_TOO_LARGE');codes.set(keccak256(raw),raw);}
 function read(root,key,subject){
  hash(root);const result=lookup(root,key,nodes);
  if(result.status==='UNKNOWN')stop('MISSING_TRIE_NODE',{...subject,nodeHash:result.missingNodeHash,trieRoot:root,prefix:result.prefix});
  return result.value;
 }
 const out={schema:'rhook/profile-target-state/0.1',checkpoint:structuredClone(spec.checkpoint),contracts:{},targets:{}};
 const storageRoots={};
 for(const c of descriptor.contracts){
  const raw=read(spec.checkpoint.stateRoot,keccak256(c.address),{contract:c.name,address:c.address,key:null});
  if(raw===null)stop('CONTRACT_ACCOUNT_ABSENT',{contract:c.name,address:c.address});
  const a=fromRlp(raw,'hex');assert(Array.isArray(a)&&a.length===4,'ACCOUNT_RLP');assert.equal(toRlp(a),raw,'NON_CANONICAL_ACCOUNT_RLP');
  for(const v of a.slice(0,2))assert(typeof v==='string'&&(v==='0x'||!v.startsWith('0x00'))&&v.length<=66,'ACCOUNT_INTEGER');hash(a[2]);hash(a[3]);
  if(c.requirement==='CODE_HASH_EQUALS'&&a[3]!==c.runtimeCodeHash)stop('CONTRACT_CODE_IDENTITY',{contract:c.name,address:c.address,expected:c.runtimeCodeHash,actual:a[3]});
  if(a[3]===EMPTY_CODE)stop('CONTRACT_CODE_REQUIRED',{contract:c.name,address:c.address});
  if(!codes.has(a[3]))stop('CODE_PREIMAGE_MISSING',{contract:c.name,address:c.address,codeHash:a[3]});
  storageRoots[c.name]=a[2];
  out.contracts[c.name]={address:c.address,codeHash:a[3],codeBytes:(codes.get(a[3]).length-2)/2,requirement:c.requirement};
 }
 for(const t of descriptor.targets){
  const root=storageRoots[t.contract];if(root===undefined)stop('TARGET_CONTRACT_UNKNOWN',{target:t.name});
  assert(Number.isInteger(t.words)&&t.words>=1&&t.words<=8,'TARGET_WORDS');
  const words=[];
  for(let i=0;i<t.words;i++){
   const key=word(BigInt(t.slot)+BigInt(i));
   const raw=read(root,keccak256(key),{target:t.name,word:i,key});
   let n=0n;
   if(raw!==null){const v=fromRlp(raw,'hex');assert.equal(toRlp(v),raw,'NON_CANONICAL_STORAGE_RLP');assert(typeof v==='string'&&v!=='0x'&&!v.startsWith('0x00')&&v.length<=66,'STORAGE_INTEGER');n=BigInt(v);}
   words.push(word(n));
  }
  out.targets[t.name]=words;
 }
 return out;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===fs.realpathSync(process.argv[1])){
 try{
  const chunks=[];let size=0;
  for await(const c of process.stdin){size+=c.length;assert(size<=16<<20,'INPUT_LIMIT');chunks.push(c);}
  const input=JSON.parse(Buffer.concat(chunks).toString('utf8'));
  process.stdout.write(JSON.stringify(authenticateProfileTargets(input.spec,input.descriptor))+'\n');
 }catch(error){process.stdout.write(JSON.stringify({status:'PROFILE_TARGET_AUTHENTICATION_STOP',causeCode:error.code&&/^[A-Z_]+$/.test(error.code)?error.code:'INVALID_TARGET_PROOF',details:error.details||{reason:error.message.slice(0,200)}})+'\n');process.exitCode=1;}
}
