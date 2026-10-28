import assert from 'node:assert/strict';
import path from 'node:path';
import {keccak256} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {headerHash,trieRoot} from '../../../engine/plan_native/ethereum.mjs';
import {writeNew} from './files.mjs';
import {C,chunkSlots,checkHeaders} from './material.mjs';
import {ProofCollector} from './collector.mjs';
import {rawFromRpc} from './transactions.mjs';
export {selectNearHead} from './events.mjs';
async function boundedEach(items,fn,client){
  let cursor=0,failure=null;
  await Promise.all(Array.from({length:Math.min(2,items.length)},async()=>{
    while(!failure&&cursor<items.length){const item=items[cursor++];try{await fn(item);}catch(error){failure??=error;client.stop?.(error);}}
  }));
  if(failure)throw failure;
}
export async function captureBlock(client,blockNumber,output,{selection=null,seed=null}={}){
  assert(Number.isSafeInteger(blockNumber)&&blockNumber>0,'EXPLICIT_BLOCK_NUMBER_REQUIRED');
  const call=client.call;
  let p=null,collector=null,headBeforeProof=null,failure=null,parentPinnedAt=null;
  const save=(name,value)=>writeNew(path.join(output,name),Buffer.from(JSON.stringify(value)+'\n'));
  try{
    assert.equal(await call('eth_chainId',[]),'0x1237','CHAIN_ID');
    const block=selection?.observedBlock??await call('eth_getBlockByNumber',['0x'+blockNumber.toString(16),true]);
    assert.equal(Number(BigInt(block.number)),blockNumber,'SELECTED_BLOCK_CHANGED');
    assert.equal(headerHash(block),block.hash,'TARGET_HASH');
    assert(Array.isArray(block.transactions)&&block.transactions.length>=2&&block.transactions.length<=8&&BigInt(block.gasUsed)<=20000000n,'CAPTURE_WORKLOAD_LIMIT');
    if(selection){
      assert.equal(selection.blockNumber,blockNumber,'EVENT_BLOCK_NUMBER_CHANGED');assert.equal(selection.blockHash,block.hash,'EVENT_BLOCK_HASH_CHANGED');
      assert.equal(block.transactions[selection.subjectIndex]?.hash,selection.transactionHash,'EVENT_SUBJECT_CHANGED');
      const {observedBlock,observedParent,...summary}=selection;
      save('EVENT_SELECTION.json',{...summary,authentication:selection.authentication??'PROVISIONAL_RPC_LOG_NOT_RECEIPT_ROOT_PROOF'});
    }
    save('SELECTED_BLOCK.json',block);
    const parent=selection?.observedParent??await call('eth_getBlockByNumber',['0x'+(blockNumber-1).toString(16),false]);
    p={checkpoint:{chainId:4663,blockNumber:blockNumber-1,blockHash:parent.hash,stateRoot:parent.stateRoot},parent,block,rawTransactions:[],state:[],codes:[],proofs:[]};
    checkHeaders(p);parentPinnedAt=client.pinCheckpoint?.(p.checkpoint,parent.timestamp,selection?.parentPinnedMonotonicMs)??Number(process.hrtime.bigint()/1000000n);save('CHECKPOINT.json',p.checkpoint);
    p.rawTransactions=block.transactions.map(rawFromRpc);
    assert.equal(trieRoot(p.rawTransactions),block.transactionsRoot,'ORDERED_TRANSACTIONS_ROOT');
    save('RAW_INPUT_PROVENANCE.json',{source:'SIGNED_RPC_FIELDS_REENCODED_AND_HASH_ROOT_VERIFIED',transactionHashes:block.transactions.map(t=>t.hash),rawRPCRequests:0});
    collector=new ProofCollector(p.checkpoint,call,seed);const proof=(a,s)=>collector.proof(a,s);
    const observed=selection?.observedBlock??await call('eth_getBlockByNumber',['latest',false]);
    assert.equal(headerHash(observed),observed.hash,'HEAD_HEADER_HASH');assert(BigInt(observed.number)>=BigInt(block.number),'HEAD_BEHIND_TARGET');
    headBeforeProof={number:Number(BigInt(observed.number)),hash:observed.hash,observedUnixMs:selection?.observedUnixMs??Date.now(),parentHeaderTimestamp:Number(BigInt(parent.timestamp)),
      distanceFromParent:Number(BigInt(observed.number)-BigInt(parent.number)),meaning:'ADJACENT_ENDPOINT_OBSERVATION_NOT_BACKEND_HEAD_GUARANTEE'};
    // Save the supported rule before acquiring less time-sensitive inputs.
    const rules=await proof(C.rules,[C.slot]);
    assert.equal(rules.account.codeHash,C.rulesCode,'UNSUPPORTED_HOOKR_GENERATION');
    // Fetch a bounded common prefix together with its authenticated length.
    // Longer configurations fetch only the unresolved tail; no length is assumed.
    const accounts=new Map([[C.rules,rules.account]]);
    const subjects=new Map([[C.arbos,[C.version,C.length,C.gas,...chunkSlots(640)]],[C.filtered,[]],[C.root,[C.executorSlot,C.executorHashSlot]],[C.executor,[]]]);
    for(const tx of block.transactions.slice(1))for(const address of [tx.from,tx.to].filter(Boolean).map(x=>x.toLowerCase()))
      if(address!==C.rules&&!subjects.has(address))subjects.set(address,[]);
    await boundedEach([...subjects],async([address,slots])=>{
      const result=await proof(address,slots);accounts.set(address,result.account);
      if(address===C.arbos){assert.equal(result.resolutions[0].value,'61','UNSUPPORTED_ARBOS_VERSION');await proof(C.arbos,chunkSlots(Number(result.resolutions[1].value)));}
    },client);
    await boundedEach([...accounts.keys()],address=>collector.code(address),client);
    const again=await call('eth_getBlockByNumber',[block.number,false]);
    assert.equal(headerHash(again),block.hash,'TARGET_REORG_OR_HEADER_MISMATCH');
    return {status:'CAPTURED_SEED',targetRechecked:true,requestGraph:collector.counts};
  }catch(error){failure=error;client.stop?.(error);throw error;}finally{
    if(p){
      if(failure?.missingDependency)save('MISSING_DEPENDENCY.json',failure.missingDependency);
      const calls=client.observations?.()??[],proofs=calls.filter(x=>x.method==='eth_getProof');
      save('CAPTURE_LATENCY.json',{eventReceivedMonotonicMs:selection?.eventReceivedMonotonicMs??null,parentPinnedMonotonicMs:parentPinnedAt,
        eventToParentPinMs:typeof parentPinnedAt==='number'&&selection?.eventReceivedMonotonicMs!==undefined?parentPinnedAt-selection.eventReceivedMonotonicMs:null,
        firstProofStartedMonotonicMs:proofs.length?Math.min(...proofs.map(x=>x.transportStartedMonotonicMs)):null,
        lastProofCompletedMonotonicMs:proofs.length?Math.max(...proofs.map(x=>x.responseCompleteMonotonicMs??x.transportStartedMonotonicMs)):null,
        rootAgeMeaning:'Client observation/pin age, not backend retention or root creation age',budget:client.stats?.()??null});
      if(collector){p.state=[...collector.nodes.values()];p.codes=[...collector.codes.values()];p.proofs=collector.proofs;
        save('DERIVED_PROOF_PROJECTIONS.json',{projections:collector.projections,meaning:'Verified original-root paths, not provider acquisition records'});
        save('REQUEST_GRAPH.json',collector.counts);}
      const first=client.observations?.().find(x=>x.method==='eth_getProof')??null;
      const parentObservation=client.observations?.().find(x=>x.method==='eth_getBlockByNumber'&&x.params[0]===p.parent.number)??null;
      save('FIRST_PROOF_WINDOW.json',{checkpoint:p.checkpoint,headBeforeProof,firstProofRequest:first,
        ageSinceParentObservedMs:first&&parentObservation?first.transportStartedOffsetMs-parentObservation.responseCompleteOffsetMs:null,
        ageFromHeadObservationMs:first&&headBeforeProof?first.transportStartedUnixMs-headBeforeProof.observedUnixMs:null,
        chainTimestampAgeMs:first?first.transportStartedUnixMs-Number(BigInt(p.parent.timestamp))*1000:null,
        exactBackendHeadAtDispatch:'NOT_OBSERVABLE_FROM_CLIENT',clockCaveat:'Wall clock minus chain timestamp is not a monotonic age or finality bound'});
      save('BLOCK_PACKAGE.json',p);
    }
  }
}
export async function selectRecent(client){
  const head=await client.call('eth_getBlockByNumber',['latest',false]);
  assert.equal(headerHash(head),head.hash,'HEAD_HEADER_HASH');
  const number=Number(BigInt(head.number));assert(Number.isSafeInteger(number)&&number>1024,'HEAD_NUMBER');
  const manager='0x8366a39cc670b4001a1121b8f6a443a643e40951',pool='0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780';
  const topic=keccak256('0x'+Buffer.from('Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)').toString('hex'));
  const logs=await client.call('eth_getLogs',[{address:manager,topics:[topic,pool],fromBlock:'0x'+(number-1024).toString(16),toBlock:'0x'+(number-1).toString(16)}]);
  assert(Array.isArray(logs)&&logs.length<=1024,'LOG_SELECTION_LIMIT');
  const candidates=logs.filter(l=>l.address===manager&&l.topics?.[0]===topic&&l.topics?.[1]===pool&&l.removed===false&&BigInt(l.blockNumber)>=BigInt(number-1024)&&BigInt(l.blockNumber)<BigInt(number)&&BigInt(l.transactionIndex)>0n);
  candidates.sort((a,b)=>Number(BigInt(b.blockNumber)-BigInt(a.blockNumber)));
  assert(candidates.length,'NO_SUPPORTED_POOL_EVENT_IN_BOUNDED_WINDOW');const log=candidates[0];
  return {status:'UNAUTHENTICATED_EVENT_SELECTED',blockNumber:Number(BigInt(log.blockNumber)),blockHash:log.blockHash,subjectIndex:Number(BigInt(log.transactionIndex)),transactionHash:log.transactionHash,
    latestNumber:number,ageBlocks:number-Number(BigInt(log.blockNumber)),checkpointSelected:false};
}
