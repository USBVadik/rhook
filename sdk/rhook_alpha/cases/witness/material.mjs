// Original-root availability, adapted from the Remote Witness Importer and
// Coverage Gate. No EVM execution or write-closure certificate is produced here.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {authenticateProof} from '../../../engine/adapters/hookr-case/proof.mjs';
import {hex,hash,quantity,keccak256,fromRlp,toRlp,EMPTY_CODE} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {headerHash,trieRoot} from '../../../engine/plan_native/ethereum.mjs';
import {makeNodes,lookup,proofPath,auditForest} from './trie.mjs';
import {configProfile} from './profile.mjs';
const require=createRequire(new URL('../../../engine/adapters/hookr-case/package.json',import.meta.url));
const {parseTransaction,recoverTransactionAddress}=require('viem');
export const C=Object.freeze({rules:'0x4a71c270b1520f94064268102aebd744b0de7942',
  root:'0x89c9fb50d1f03192230ffb1c279bb6e7d3fe6acc',executor:'0x4b4c16681401454140a9dbca55e5c186bbe8d728',
  rootCode:'0xd336de325837e60a74cea11d87b5ebd1cc8961911f611f38de0508d23b6e779f',
  executorCode:'0xa454566f248677718ca1c6ed8df59e23bc6dc4b9f787a1c9bd687912d4ef508f',
  executorSlot:'0xdc5740eeafc78ca4488605782bceeee21ea0cec0908c37bbb90fb77c45910411',
  executorHashSlot:'0xdc5740eeafc78ca4488605782bceeee21ea0cec0908c37bbb90fb77c45910412',
  slot:'0x1ad7756ae873b72ee7b85d116a86b7b2c5244640095753f73687752bed4705aa',
  rulesCode:'0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b',
  arbos:'0xa4b05fffffffffffffffffffffffffffffffffff',
  filtered:'0xa4b0500000000000000000000000000000000001',
  version:'0x15fed0451499512d95f3ec5a41c878b9de55f21878b5b4e190d4667ec709b400',
  length:'0x696e3678057072f0c8dba2395c9474f6a52565714cff46262e4548533b097700',
  gas:'0xe54de2a4cdacc0a0059d2b6e16348103df8c4aff409c31e40ec73d11926c8201'});
export const sha=raw=>createHash('sha256').update(raw).digest('hex');
export const chunkSlots=length=>{
  assert(Number.isInteger(length)&&length>0&&length<=1536,'CONFIG_LENGTH_DOMAIN');
  return Array.from({length:Math.ceil(length/32)},(_,i)=>C.length.slice(0,-2)+(i+1).toString(16).padStart(2,'0'));
};
export function checkHeaders(p){
  const c=p.checkpoint;
  assert(c?.chainId===4663&&Number.isSafeInteger(c.blockNumber)&&c.blockNumber>=0,'CHECKPOINT_CHAIN');
  hash(c.blockHash);hash(c.stateRoot);
  assert.equal(headerHash(p.parent),c.blockHash,'PARENT_HEADER_HASH');
  assert.equal(p.parent.stateRoot,c.stateRoot,'CHECKPOINT_ROOT');
  assert.equal(Number(quantity(p.parent.number)),c.blockNumber);
  assert.equal(headerHash(p.block),p.block.hash,'TARGET_HEADER_HASH');
  assert.equal(p.block.parentHash,c.blockHash,'ORIGINAL_PARENT_LINK');
  assert.equal(quantity(p.block.number),BigInt(c.blockNumber)+1n);
  assert(quantity(p.block.timestamp)>=quantity(p.parent.timestamp));
  assert(Array.isArray(p.block.transactions)&&p.block.transactions.length>0&&p.block.transactions.length<=4096,'ARRIVAL_LIMIT');
}
export function material(p){
  checkHeaders(p);
  assert(Array.isArray(p.state)&&p.state.length<=8192&&Array.isArray(p.codes)&&p.codes.length<=8192&&Array.isArray(p.proofs)&&p.proofs.length<=128,'MATERIAL_LIMIT');
  for(const raw of p.state)assert(hex(raw).length<=8194,'NODE_LIMIT');
  const nodes=makeNodes(p.state),codes=new Map();
  for(const raw of p.codes){hex(raw);assert(raw.length<=524290,'CODE_LIMIT');codes.set(keccak256(raw),raw);}
  for(const item of p.proofs){
    const v=authenticateProof(p.checkpoint.stateRoot,item.address,item.slots??[],{...item.proof,storageProof:item.proof.storageProof??[]});
    for(const [id,raw]of v.nodes){if(nodes.has(id))assert.equal(nodes.get(id),raw);nodes.set(id,raw);}
  }
  return {nodes,codes};
}
export function dependency(cp,m,address,slot){
  hex(address,20);
  const a=lookup(cp.stateRoot,keccak256(address),m.nodes);
  const base={address,kind:slot?'STORAGE':'ACCOUNT',readerDomain:'ORIGINAL_PARENT',...(slot?{slot}:{})};
  if(slot)hash(slot);
  if(a.status==='UNKNOWN')return {...base,status:'MISSING',reason:'ACCOUNT_PATH_MISSING',missingNodeHash:a.missingNodeHash};
  if(a.status==='PROVEN_ABSENT')return {...base,status:'PROVEN_ABSENT',value:slot?'0':null};
  const fields=fromRlp(a.value,'hex');assert(Array.isArray(fields)&&fields.length===4,'ACCOUNT_RLP');
  assert.equal(toRlp(fields),a.value,'CANONICAL_ACCOUNT_RLP');
  for(const n of fields.slice(0,2))assert(typeof n==='string'&&n.length<=66&&(n==='0x'||!n.startsWith('0x00')),'ACCOUNT_INTEGER');
  if(!slot)return {...base,status:'PRESENT',codeHash:hash(fields[3]),storageRoot:hash(fields[2])};
  const s=lookup(hash(fields[2]),keccak256(slot),m.nodes);
  if(s.status==='UNKNOWN')return {...base,slot,status:'MISSING',reason:'STORAGE_PATH_MISSING',missingNodeHash:s.missingNodeHash};
  let value='0';
  if(s.value!==null){const n=fromRlp(s.value,'hex');assert(typeof n==='string'&&n.length<=66&&n!=='0x'&&!n.startsWith('0x00'),'STORAGE_INTEGER');assert.equal(toRlp(n),s.value);value=BigInt(n).toString();}
  return {...base,slot,status:s.status==='PROVEN_ABSENT'?'PROVEN_ABSENT':'PRESENT',value};
}
export async function analyze(p){
  const m=material(p),cp=p.checkpoint,rows=[];
  const add=(address,slot)=>{const row=dependency(cp,m,address,slot);rows.push(row);return row;};
  // The first Nitro system arrival has no ordinary EOA sender semantics.
  const addresses=new Set([C.rules,C.root,C.executor,C.arbos,C.filtered,...p.block.transactions.slice(1).flatMap(t=>[t.from,t.to]).filter(Boolean).map(x=>x.toLowerCase())]);
  assert(addresses.size<=128,'KNOWN_ACCOUNT_LIMIT');
  for(const address of addresses){
    const a=add(address);
    if(a.status==='PRESENT'&&a.codeHash!==EMPTY_CODE)rows.push({address,kind:'CODE',readerDomain:'ORIGINAL_PARENT',codeHash:a.codeHash,
      status:m.codes.has(a.codeHash)?'PRESENT':'MISSING',reason:m.codes.has(a.codeHash)?'ACCOUNT_CODE_HASH_BOUND':'CODE_PREIMAGE_MISSING'});
  }
  const rules=rows.find(x=>x.address===C.rules&&x.kind==='ACCOUNT');
  const supported=rules.status==='PRESENT'&&rules.codeHash===C.rulesCode;
  let unsupported=rules.status==='PROVEN_ABSENT'||rules.status==='PRESENT'&&!supported||
    [[C.root,C.rootCode],[C.executor,C.executorCode]].some(([a,h])=>rows.some(r=>r.address===a&&r.kind==='ACCOUNT'&&(r.status==='PROVEN_ABSENT'||r.status==='PRESENT'&&r.codeHash!==h)));
  const word=add(C.rules,C.slot),version=add(C.arbos,C.version),length=add(C.arbos,C.length),gas=add(C.arbos,C.gas);
  const executor=add(C.root,C.executorSlot),executorHash=add(C.root,C.executorHashSlot);
  const profileBlockers=[];
  if(version.value!==undefined&&version.value!=='61')profileBlockers.push('UNSUPPORTED_ARBOS_VERSION');
  // Match the retained native BigToAddress check: this is a packed word.
  if(executor.value!==undefined&&(BigInt(executor.value)&((1n<<160n)-1n))!==BigInt(C.executor))profileBlockers.push('HOOKR_EXECUTOR_BINDING_CHANGED');
  if(executorHash.value!==undefined&&BigInt(executorHash.value)!==BigInt(C.executorCode))profileBlockers.push('HOOKR_EXECUTOR_CODE_PIN_CHANGED');
  if(length.value!==undefined&&(Number(length.value)<=0||Number(length.value)>1536))profileBlockers.push('UNSUPPORTED_CHAIN_CONFIG_LENGTH');
  unsupported=unsupported||profileBlockers.length>0;
  let config=null;
  if(length.value!==undefined&&Number(length.value)>0&&Number(length.value)<=1536){
    const chunks=chunkSlots(Number(length.value)).map(slot=>add(C.arbos,slot));
    if(chunks.every(x=>x.value!==undefined)){
      const bytes=Buffer.concat(chunks.map((x,i)=>Buffer.from(BigInt(x.value).toString(16).padStart(64,'0'),'hex').subarray(32-Math.min(32,Number(length.value)-32*i))));
      const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
      profileBlockers.push(...configProfile(value));config=bytes;
    }
  }
  unsupported=unsupported||profileBlockers.length>0;
  const txs=p.block.transactions,raw=p.rawTransactions;
  assert(Array.isArray(raw)&&raw.length<=txs.length,'RAW_INPUT_LIMIT');
  for(let i=0;i<raw.length;i++)assert.equal(keccak256(hex(raw[i])),txs[i].hash,'RAW_TRANSACTION_IDENTITY');
  const completeInputs=raw.length===txs.length;
  if(completeInputs){
    assert.equal(trieRoot(raw),p.block.transactionsRoot,'ORDERED_TRANSACTIONS_ROOT');
    assert.equal(Number(quantity(txs[0].type)),106,'SYSTEM_FIRST');
    for(let i=1;i<raw.length;i++){
      const tx=parseTransaction(raw[i]);assert.equal(tx.chainId,4663,'TRANSACTION_CHAIN');
      assert.equal((await recoverTransactionAddress({serializedTransaction:raw[i]})).toLowerCase(),txs[i].from.toLowerCase());
      assert.equal(tx.to?.toLowerCase()??null,txs[i].to?.toLowerCase()??null);
    }
  }else rows.push({kind:'INPUT',status:'MISSING',reason:'ORDERED_RAW_TRANSACTIONS_MISSING',firstMissingOrdinal:raw.length});
  const knownReady=supported&&!unsupported&&rows.every(x=>x.status!=='MISSING')&&version.value==='61'&&config!==null&&BigInt(gas.value??'0')>0n;
  const base64=map=>Object.fromEntries([...map].sort(([a],[b])=>a.localeCompare(b)).map(([id,raw])=>[id,Buffer.from(raw.slice(2),'hex').toString('base64')]));
  // Byte serialization matches the retained native ImportBlock and Bridge.Seal.
  const context={chainId:cp.chainId,blockNumber:cp.blockNumber,blockHash:cp.blockHash,stateRoot:cp.stateRoot};
  const goJSON=value=>JSON.stringify(value).replace(/[<>&\u2028\u2029]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
  const input=completeInputs&&config?sha('rhook/external-canonical-block-inputs/0.1\n'+goJSON({Context:context,Parent:p.parent,Block:p.block,Raw:raw,Config:'0x'+config.toString('hex')})):null;
  const witness=sha('rhook/native-prestate-witness/0.1\n'+JSON.stringify({checkpoint:context,nodes:base64(m.nodes),codes:base64(m.codes),attempts:null}));
  return {schema:'rhook/case-dependency-report/0.1',status:unsupported?'UNSUPPORTED_EXECUTION_PROFILE':!m.nodes.has(cp.stateRoot)?'HEADERS_ONLY_INCOMPLETE':knownReady?'AUTHENTICATED_KNOWN_DEPENDENCIES_PRESENT':'AUTHENTICATED_INCOMPLETE',
    authentication:m.nodes.has(cp.stateRoot)?'PROOFS_VERIFIED_AT_DECLARED_ROOT':'HEADERS_VERIFIED_STATE_NOT_AUTHENTICATED',chainTrust:'CHECKPOINT_SOURCE_REQUIRES_OPERATOR_TRUST',checkpoint:cp,targetBlock:Number(quantity(p.block.number)),
    originalInputs:completeInputs?'AUTHENTICATED_ORDERED_RAW_INPUTS':'INCOMPLETE',inputCommitment:input,witnessCommitment:witness,
    rulesWord:word.value===undefined?null:'0x'+BigInt(word.value).toString(16).padStart(64,'0'),dependencies:rows,
    missing:rows.filter(x=>x.status==='MISSING'),profileBlockers,knownDependenciesPresent:knownReady,writeClosure:'UNKNOWN',completeForCase:false,nativeExecutions:0,
    limitation:'Original-parent dependency availability only. Dynamic reads, trie updates and native admission remain untested.'};
}

// EIP-1186-shaped paths derived from actual authenticated trie bytes. These
// are native-import projections, never invented provider responses or RPCs.
export function projectProof(p,address,slots){
  const m=material(p),a=dependency(p.checkpoint,m,address);
  assert(a.status==='PRESENT','PROJECTION_ACCOUNT_UNAVAILABLE');
  const account=lookup(p.checkpoint.stateRoot,keccak256(address),m.nodes),fields=fromRlp(account.value,'hex');
  const q=raw=>raw==='0x'?'0x0':'0x'+BigInt(raw).toString(16);
  const proof={address,accountProof:proofPath(p.checkpoint.stateRoot,keccak256(address),m.nodes),
    balance:q(fields[1]),nonce:q(fields[0]),codeHash:a.codeHash,storageHash:a.storageRoot,
    storageProof:slots.map(key=>{const s=dependency(p.checkpoint,m,address,key);assert(s.value!==undefined,'PROJECTION_STORAGE_UNAVAILABLE');
      return {key,value:'0x'+BigInt(s.value).toString(16),proof:proofPath(a.storageRoot,keccak256(key),m.nodes)};})};
  authenticateProof(p.checkpoint.stateRoot,address,slots,proof);
  return {address,slots,proof};
}
export function projectProfile(p){
  const requests=[[C.rules,[C.slot]],[C.root,[C.executorSlot,C.executorHashSlot]],[C.executor,[]],
    [C.arbos,[C.version,C.length,C.gas]],[C.filtered,[]]],projections=[];
  const m=material(p),length=dependency(p.checkpoint,m,C.arbos,C.length);
  if(length.value!==undefined&&Number(length.value)>0&&Number(length.value)<=1536)requests.push([C.arbos,chunkSlots(Number(length.value))]);
  let result=p;
  for(const [address,slots]of requests){
    if(result.proofs.some(v=>v.address===address&&slots.every(s=>(v.slots??[]).includes(s))))continue;
    try{const proof=projectProof(result,address,slots);result={...result,proofs:[...result.proofs,proof]};
      projections.push({address,slots,kind:'DERIVED_FROM_AUTHENTICATED_ORIGINAL_TRIE_PATHS',rpcRequests:0});}
    catch(error){if(!/PROJECTION_|UNKNOWN/.test(error.message))throw error;}
  }
  return {package:result,projections};
}
export function mergeWitness(p,w){
  const m=material(p);
  let nodes,codes;
  if(w.format==='rhook/remote-witness-seed/0.1'){
    assert.deepEqual(w.checkpoint,p.checkpoint,'WITNESS_CHECKPOINT');nodes=w.nodes;codes=w.codes;
  }else{
    assert(Array.isArray(w.headers)&&w.headers.length>0&&w.headers.length<=256,'WITNESS_HEADERS');
    for(let i=0;i<w.headers.length;i++){
      const h=w.headers[i],newer=i?w.headers[i-1]:p.block;
      assert.equal(headerHash(h),h.hash);assert.equal(newer.parentHash,h.hash);assert.equal(quantity(newer.number),quantity(h.number)+1n);
    }
    assert.equal(w.headers[0].stateRoot,p.checkpoint.stateRoot);
    assert(Array.isArray(w.state)&&w.state.length<=8192&&Array.isArray(w.codes)&&w.codes.length<=8192,'WITNESS_LIMIT');
    nodes=Object.fromEntries(w.state.map(raw=>[keccak256(hex(raw)),raw]));codes=Object.fromEntries(w.codes.map(raw=>[keccak256(hex(raw)),raw]));
  }
  for(const [target,values,limit]of [[m.nodes,nodes,4096],[m.codes,codes,262144]]){
    assert(values&&typeof values==='object'&&!Array.isArray(values)&&Object.keys(values).length<=8192,'WITNESS_MAP');
    for(const [id,raw]of Object.entries(values)){hash(id);hex(raw);assert(raw.length<=2+limit*2,'PREIMAGE_LIMIT');assert.equal(keccak256(raw),id,'PREIMAGE_HASH');if(target.has(id))assert.equal(target.get(id),raw);target.set(id,raw);}
  }
  const forest=auditForest(p.checkpoint.stateRoot,m.nodes,m.codes);
  assert.equal(forest.unanchoredSuppliedNodes.length,0,'UNANCHORED_WITNESS_NODE');
  assert.equal(forest.providedCodeHashesBoundToKnownAccounts.length,m.codes.size,'UNBOUND_WITNESS_CODE');
  return {...p,state:[...m.nodes.values()],codes:[...m.codes.values()]};
}
