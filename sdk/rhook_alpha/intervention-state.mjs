// Offline target-field authentication only. No transport, EVM or authority API.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {keccak256,fromRlp,toRlp,hex,hash} from '../engine/adapters/hookr-case/primitives.mjs';
import {makeNodes,lookup} from './cases/witness/trie.mjs';
const word=n=>'0x'+n.toString(16).padStart(64,'0');
function stop(code,details){throw Object.assign(Error(code),{code,details});}
export function authenticateTargetState(spec,profile){
 assert(spec&&spec.inventory&&Array.isArray(spec.inventory.nodes)&&spec.inventory.nodes.length<=4096,'INVENTORY_LIMIT');
 assert(Array.isArray(spec.inventory.codes)&&spec.inventory.codes.length<=256,'INVENTORY_LIMIT');
 for(const value of spec.inventory.nodes)assert(hex(value).length<=8194,'NODE_TOO_LARGE');
 const nodes=makeNodes(spec.inventory.nodes);
 const codes=new Map();
 for(const value of spec.inventory.codes){const raw=hex(value);assert(raw.length<=196610,'CODE_TOO_LARGE');codes.set(keccak256(raw),raw);}
 function read(root,key,subject){
  hash(root);const result=lookup(root,key,nodes);
  if(result.status==='UNKNOWN')stop('MISSING_TRIE_NODE',{...subject,nodeHash:result.missingNodeHash,trieRoot:root,prefix:result.prefix});
  return result.value;
 }
 const out={schema:'rhook/intervention-target-state/0.1',checkpoint:structuredClone(spec.checkpoint),accounts:{}};
 for(const role of ['root','rules']){
  // Release manifests contain several Rules modules. This profile's primary
  // entry is the module bound in its baseline Root record, not the last role.
  const c=profile.manifest.contracts.find(c=>c.role===role);assert(c,'PROFILE_CONTRACT');
  const raw=read(spec.checkpoint.stateRoot,keccak256(c.address),{role,address:c.address,key:null});
  if(raw===null)stop('CONTRACT_ACCOUNT_ABSENT',{role,address:c.address});
  const a=fromRlp(raw,'hex');assert(Array.isArray(a)&&a.length===4,'ACCOUNT_RLP');assert.equal(toRlp(a),raw,'NON_CANONICAL_ACCOUNT_RLP');
  for(const v of a.slice(0,2))assert(typeof v==='string'&&(v==='0x'||!v.startsWith('0x00'))&&v.length<=66,'ACCOUNT_INTEGER');hash(a[2]);hash(a[3]);
  if(a[3]!==c.runtimeHash)stop('CONTRACT_CODE_IDENTITY',{role,address:c.address,expected:c.runtimeHash,actual:a[3]});
  if(!codes.has(a[3]))stop('CODE_PREIMAGE_MISSING',{role,address:c.address,codeHash:a[3]});
  const account={address:c.address,codeHash:a[3],storage:{}};
  const keys=role==='root'?[profile.rootRecordSlot]:profile.baselineConfigWords.map((_,i)=>word(BigInt(profile.configSlot)+BigInt(i)));
  for(const key of keys){
   const raw=read(a[2],keccak256(key),{role,address:c.address,key});
   let n=0n;
   if(raw!==null){const v=fromRlp(raw,'hex');assert.equal(toRlp(v),raw,'NON_CANONICAL_STORAGE_RLP');assert(typeof v==='string'&&v!=='0x'&&!v.startsWith('0x00')&&v.length<=66,'STORAGE_INTEGER');n=BigInt(v);}
   account.storage[key]=word(n);
  }
  out.accounts[role]=account;
 }
 return out;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===fs.realpathSync(process.argv[1])){
 try{
  const chunks=[];let size=0;
  for await(const c of process.stdin){size+=c.length;assert(size<=8<<20,'INPUT_LIMIT');chunks.push(c);}
  const spec=JSON.parse(Buffer.concat(chunks).toString('utf8'));
  const profile=JSON.parse(fs.readFileSync(new URL('./cases/scenario/native/profile.json',import.meta.url),'utf8'));
  process.stdout.write(JSON.stringify(authenticateTargetState(spec,profile))+'\n');
 }catch(error){process.stdout.write(JSON.stringify({status:'INTERVENTION_AUTHENTICATION_STOP',causeCode:error.code&&/^[A-Z_]+$/.test(error.code)?error.code:'INVALID_TARGET_PROOF',details:error.details||{reason:error.message.slice(0,200)}})+'\n');process.exitCode=1;}
}
