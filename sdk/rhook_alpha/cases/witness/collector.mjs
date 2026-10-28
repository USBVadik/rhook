// One original-root cache, never shared across checkpoint identities.
import assert from 'node:assert/strict';
import {authenticateProof} from '../../../engine/adapters/hookr-case/proof.mjs';
import {hex,hash,slot,keccak256,fromRlp,EMPTY_CODE,EMPTY_ROOT} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {makeNodes,lookup,proofPath} from './trie.mjs';

function unavailable(error,method,params,checkpoint,codeHash){
  const request=error.rpcRequest??{method,params},proof=request.method==='eth_getProof';
  const missingDependency={kind:proof?'ACCOUNT_OR_STORAGE_PROOF':'CODE',address:request.params[0],checkpoint,
    ...(proof?{slots:request.params[1]}:{}),...(!proof&&request.params[0]===params[0]&&codeHash?{codeHash}:{})};
  return Object.assign(new Error(error.message,{cause:error}),{missingDependency});
}
export class ProofCollector{
  constructor(checkpoint,call,seed=null){
    this.checkpoint=Object.freeze({...checkpoint});hash(checkpoint.blockHash);hash(checkpoint.stateRoot);
    this.call=call;this.pendingCodes=new Map();this.nodes=new Map();this.codes=new Map();this.accounts=new Map();this.proofs=[];this.projections=[];
    this.counts={networkProofs:0,cachedProofs:0,networkCodes:0,cachedCodes:0,requestedSlots:0,fetchedSlots:0};
    if(seed){
      assert.deepEqual(seed.checkpoint,this.checkpoint,'CACHE_CHECKPOINT');
      assert(Object.keys(seed.nodes).length<=8192&&Object.keys(seed.codes).length<=8192,'CACHE_LIMIT');
      this.nodes=makeNodes(Object.values(seed.nodes));
      for(const [id,raw]of Object.entries(seed.nodes))assert.equal(keccak256(raw),id,'CACHE_NODE_HASH');
      for(const [id,raw]of Object.entries(seed.codes)){hex(raw);assert(raw.length<=524290,'CACHE_CODE_LIMIT');assert.equal(keccak256(raw),id,'CACHE_CODE_HASH');this.codes.set(id,raw);}
    }
  }
  project(address,keys){
    const root=this.checkpoint.stateRoot,a=lookup(root,keccak256(address),this.nodes);
    if(a.status==='UNKNOWN')return null;
    const fields=a.status==='PROVEN_ABSENT'?['0x','0x',EMPTY_ROOT,EMPTY_CODE]:fromRlp(a.value,'hex');
    assert(Array.isArray(fields)&&fields.length===4,'ACCOUNT_RLP');
    const q=n=>n==='0x'?'0x0':'0x'+BigInt(n).toString(16);
    const storage=[];
    for(const key of keys){
      const s=lookup(fields[2],keccak256(key),this.nodes);if(s.status==='UNKNOWN')return null;
      storage.push({key,value:s.value===null?'0x0':q(fromRlp(s.value,'hex')),proof:proofPath(fields[2],keccak256(key),this.nodes)});
    }
    const proof={address,nonce:q(fields[0]),balance:q(fields[1]),storageHash:fields[2],codeHash:fields[3],
      accountProof:proofPath(root,keccak256(address),this.nodes),storageProof:storage};
    return {proof,verified:authenticateProof(root,address,keys,proof)};
  }
  async proof(subject,requested){
    const address=hex(subject,20),keys=requested.map(slot);assert(keys.length<=48&&new Set(keys).size===keys.length,'STORAGE_SUBJECT_LIMIT');
    this.counts.requestedSlots+=keys.length;
    let resolved=this.project(address,keys),derived=true;
    if(!resolved){
      const account=this.project(address,[]);
      const missing=account?keys.filter(key=>!this.project(address,[key])):keys;
      let value;try{value=await this.call('eth_getProof',[address,missing,{blockHash:this.checkpoint.blockHash,requireCanonical:true}]);}
      catch(error){throw unavailable(error,'eth_getProof',[address,missing],this.checkpoint);}
      const verified=authenticateProof(this.checkpoint.stateRoot,address,missing,{...value,storageProof:value.storageProof??[]});
      for(const [id,raw]of verified.nodes)this.nodes.set(id,raw);
      this.proofs.push({address,slots:missing,proof:{...value,storageProof:value.storageProof??[]}});
      this.counts.networkProofs++;this.counts.fetchedSlots+=missing.length;
      resolved=this.project(address,keys);assert(resolved,'AUTHENTICATED_CACHE_PATH_MISSING');
      derived=missing.length!==keys.length;
    }else this.counts.cachedProofs++;
    if(derived&&!this.proofs.some(p=>p.address===address&&p.slots.length===keys.length&&p.slots.every((k,i)=>k===keys[i]))){
      this.proofs.push({address,slots:keys,proof:resolved.proof});
      this.projections.push({address,slots:keys,kind:'DERIVED_FROM_AUTHENTICATED_ORIGINAL_TRIE_PATHS',rpcRequests:0});
    }
    this.accounts.set(address,resolved.verified.account);return resolved.verified;
  }
  async code(subject){
    const address=hex(subject,20);if(!this.accounts.has(address))await this.proof(address,[]);
    const account=this.accounts.get(address);
    if(account.status==='ABSENT'||account.codeHash===EMPTY_CODE)return '0x';
    if(this.codes.has(account.codeHash)){this.counts.cachedCodes++;return this.codes.get(account.codeHash);}
    if(this.pendingCodes.has(account.codeHash)){this.counts.cachedCodes++;return this.pendingCodes.get(account.codeHash);}
    const fetch=(async()=>{
      let raw;try{raw=await this.call('eth_getCode',[address,{blockHash:this.checkpoint.blockHash,requireCanonical:true}]);}
      catch(error){throw unavailable(error,'eth_getCode',[address],this.checkpoint,account.codeHash);}
      assert.equal(keccak256(raw),account.codeHash,'ACCOUNT_CODE_HASH_MISMATCH');
      this.codes.set(account.codeHash,raw);this.counts.networkCodes++;return raw;
    })();
    this.pendingCodes.set(account.codeHash,fetch);
    try{return await fetch;}finally{this.pendingCodes.delete(account.codeHash);}
  }
}
