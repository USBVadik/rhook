// Offline coverage of declared original-state dependencies for one checkpoint.
// Profile-neutral: callers supply the checkpoint, the authenticated inventory and the dependency list.
// Reuses ProofCollector (seed validation, root-bound projection) and the trie helpers. It refuses
// every network request, so a dependency the seed cannot answer stays UNKNOWN, never zero or empty.
import assert from 'node:assert/strict';
import {ProofCollector} from '../cases/witness/collector.mjs';
import {auditForest,lookup,keccak256} from '../cases/witness/trie.mjs';
import {EMPTY_CODE,hex,hash,slot} from '../../engine/adapters/hookr-case/primitives.mjs';

export const COVERAGE_SCHEMA='rhook/session-static-coverage/0.1';
export const LIMITS=Object.freeze({dependencies:128,slots:48,nodes:8192,codes:8192});

class CoverageStop extends Error{constructor(code,detail){super(`${code}: ${detail}`);this.code=code;}}
const stop=(ok,code,detail)=>{if(!ok)throw new CoverageStop(code,detail);};

// Hash-keyed, deduplicated seed for ProofCollector. A preimage is identified only by its own Keccak.
export function seedFrom(checkpoint,inventory){
 stop(inventory&&Array.isArray(inventory.nodes)&&Array.isArray(inventory.codes),'SEED_INVENTORY','nodes and codes arrays required');
 const nodes=new Map(),codes=new Map();let duplicateNodes=0,duplicateCodes=0;
 for(const [list,map,kind] of [[inventory.nodes,nodes,'node'],[inventory.codes,codes,'code']]){
  for(const value of list){
   let raw;try{raw=hex(value);}catch{throw new CoverageStop('SEED_PREIMAGE_ENCODING',`${kind} preimage is not hex`);}
   stop(raw.length>2,'SEED_PREIMAGE_ENCODING',`empty ${kind} preimage`);
   const id=keccak256(raw);
   if(map.has(id)){kind==='node'?duplicateNodes++:duplicateCodes++;continue;}
   map.set(id,raw);
  }
 }
 stop(nodes.size<=LIMITS.nodes&&codes.size<=LIMITS.codes,'SEED_LIMIT','too many distinct preimages');
 return {seed:{checkpoint,nodes:Object.fromEntries(nodes),codes:Object.fromEntries(codes)},
  distinct:{nodes:nodes.size,codes:codes.size},duplicates:{nodes:duplicateNodes,codes:duplicateCodes}};
}

// A ProofCollector over the seed whose network function refuses and records every request.
export function offlineCollector(checkpoint,seed){
 const refused=[];
 const call=async(method,params)=>{refused.push({method,address:params[0]});
  throw Object.assign(new Error('OFFLINE_SESSION_NO_RPC'),{rpcRequest:{method,params}});};
 let collector;
 try{collector=new ProofCollector(checkpoint,call,seed);}
 catch(error){
  const message=String(error.message);
  const code=['CACHE_CHECKPOINT','CACHE_NODE_HASH','CACHE_CODE_HASH','CACHE_LIMIT','CACHE_CODE_LIMIT'].find(c=>message.includes(c))??'SEED_PREIMAGE_INVALID';
  throw new CoverageStop(code,message.split('\n')[0].slice(0,200));
 }
 return {collector,refused};
}

function gap(root,key,nodes){
 const r=lookup(root,keccak256(key),nodes);
 return r.status==='UNKNOWN'?{missingNodeHash:r.missingNodeHash,pathPrefix:r.prefix}:null;
}

async function dependencyRow(collector,d){
 stop(d&&typeof d==='object','DEPENDENCY_SHAPE','dependency must be an object');
 let address,keys;
 try{address=hex(d.address,20);keys=(d.slots??[]).map(slot);}catch{throw new CoverageStop('DEPENDENCY_SHAPE','address or slot encoding');}
 stop(keys.length<=LIMITS.slots&&new Set(keys).size===keys.length,'DEPENDENCY_SHAPE','at most 48 distinct slots per dependency');
 const root=collector.checkpoint.stateRoot;
 const row={address,source:d.source??null,account:'UNKNOWN',storage:[],code:d.code?'UNKNOWN':'NOT_REQUESTED'};
 let account=null;
 try{
  const v=await collector.proof(address,keys);account=v.account;
  row.storage=v.resolutions.map(r=>({slot:r.key,status:r.status==='ABSENT'?'PROVEN_ZERO':'PRESENT'}));
 }catch(error){
  if(!error.missingDependency)throw error;
  const known=collector.project(address,[]);
  if(known){
   account=known.verified.account;
   row.storage=keys.map(key=>{
    const one=collector.project(address,[key]);
    if(one)return {slot:key,status:one.verified.resolutions[0].status==='ABSENT'?'PROVEN_ZERO':'PRESENT'};
    return {slot:key,status:'UNKNOWN',...gap(account.storageRoot,key,collector.nodes)};
   });
  }else{
   Object.assign(row,gap(root,address,collector.nodes)??{});
   row.storage=keys.map(key=>({slot:key,status:'UNKNOWN'}));
  }
 }
 if(account){
  row.account=account.status==='ABSENT'?'PROVEN_ABSENT':'PRESENT';
  if(d.code){
   try{await collector.code(address);
    row.code=account.status==='ABSENT'||account.codeHash===EMPTY_CODE?'PROVEN_EMPTY':'PRESENT';}
   catch(error){if(!error.missingDependency)throw error;row.code='MISSING_PREIMAGE';row.codeHash=account.codeHash;}
  }
 }
 return row;
}

function trieUpdateAudit(collector){
 try{
  const a=auditForest(collector.checkpoint.stateRoot,collector.nodes,collector.codes);
  return {status:'PARTIAL_FOREST_AUDITED',accountFrontier:a.accountFrontier.length,unknownStorageFrontier:a.unknownStorageFrontier,
   possibleDeletionSiblingGaps:a.possibleDeletionSiblingGaps.length,completeness:a.completeness};
 }catch(error){return {status:'NOT_EVALUATED',reason:String(error.message).split('\n')[0].slice(0,200)};}
}

/** Resolve each declared dependency from the seed alone; never performs RPC. */
export async function coverage(checkpoint,inventory,dependencies){
 hash(checkpoint.blockHash);hash(checkpoint.stateRoot);
 stop(Array.isArray(dependencies)&&dependencies.length<=LIMITS.dependencies,'DEPENDENCY_LIMIT','at most 128 dependencies');
 const {seed,distinct,duplicates}=seedFrom(checkpoint,inventory);
 const {collector,refused}=offlineCollector(checkpoint,seed);
 const rows=[];
 for(const d of dependencies)rows.push(await dependencyRow(collector,d));
 assert.equal(collector.counts.networkProofs+collector.counts.networkCodes,0,'OFFLINE_INVARIANT');
 const count=(pick,value)=>rows.reduce((n,r)=>n+pick(r).filter(x=>x===value).length,0);
 const accounts=r=>[r.account],slots=r=>r.storage.map(s=>s.status),codes=r=>[r.code];
 const summary={dependencies:rows.length,
  accounts:{present:count(accounts,'PRESENT'),provenAbsent:count(accounts,'PROVEN_ABSENT'),unknown:count(accounts,'UNKNOWN')},
  slots:{present:count(slots,'PRESENT'),provenZero:count(slots,'PROVEN_ZERO'),unknown:count(slots,'UNKNOWN')},
  codes:{present:count(codes,'PRESENT'),provenEmpty:count(codes,'PROVEN_EMPTY'),missingPreimage:count(codes,'MISSING_PREIMAGE'),unknown:count(codes,'UNKNOWN')}};
 const unresolved=summary.accounts.unknown+summary.slots.unknown+summary.codes.missingPreimage+summary.codes.unknown;
 return {schema:COVERAGE_SCHEMA,checkpoint:structuredClone(checkpoint),
  status:unresolved===0?'STATIC_DEPENDENCIES_COVERED':'STATIC_DEPENDENCIES_MISSING',
  unresolvedDependencies:unresolved,summary,dependencies:rows,
  seed:{distinctNodes:distinct.nodes,distinctCodes:distinct.codes,duplicateNodes:duplicates.nodes,duplicateCodes:duplicates.codes},
  reuse:{cachedProofs:collector.counts.cachedProofs,cachedCodes:collector.counts.cachedCodes,requestedSlots:collector.counts.requestedSlots,
   derivedProjections:collector.projections.length},
  networkRequestsPerformed:0,networkRequestsRefused:refused.length,nativeExecutions:0,
  trieUpdateAudit:trieUpdateAudit(collector),dynamicClosure:'UNKNOWN',
  meaning:'Declared original-root reads answered from authenticated preimages only. Execution may read other state and trie updates may need more nodes; only a completed native run for an exact input establishes closure.'};
}

export {CoverageStop};
