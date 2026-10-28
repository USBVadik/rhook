// A bounded observation window, not a subscription or a historical search.
import assert from 'node:assert/strict';
import {hex,keccak256} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {headerHash,bloom,receiptBytes,trieRoot} from '../../../engine/plan_native/ethereum.mjs';
const manager='0x8366a39cc670b4001a1121b8f6a443a643e40951',pool='0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780';
const topic=keccak256('0x'+Buffer.from('Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)').toString('hex'));
export const EVENT_FILTER=Object.freeze({address:manager,topics:Object.freeze([topic,pool])});
const wanted=Buffer.from(bloom([{address:manager,topics:[topic,pool]}]).slice(2),'hex');
function mayContainEvent(value){
 const actual=Buffer.from(hex(value,256).slice(2),'hex');
 return wanted.every((byte,i)=>(actual[i]&byte)===byte);
}
export function authenticatePoolEvent(block,receipts,expected=null){
 assert.equal(headerHash(block),block.hash,'EVENT_HEADER_HASH');
 assert(Array.isArray(block.transactions)&&block.transactions.length>=2&&block.transactions.length<=8,'EVENT_WORKLOAD_LIMIT');
 assert(Array.isArray(receipts)&&receipts.length===block.transactions.length,'RECEIPT_COUNT');
 let cumulative=0n;const allLogs=[];
 for(let i=0;i<receipts.length;i++){
  const r=receipts[i],tx=block.transactions[i];
  assert(r&&BigInt(r.transactionIndex)===BigInt(i)&&r.transactionHash===tx.hash,'RECEIPT_TRANSACTION_IDENTITY');
  assert(r.blockHash===block.hash&&r.blockNumber===block.number,'RECEIPT_BLOCK_IDENTITY');
  assert(BigInt(r.type)===BigInt(tx.type),'RECEIPT_TYPE');
  assert(['0x0','0x1'].includes(r.status)&&(!r.root||r.root==='0x'),'RECEIPT_STATUS');
  assert(Object.hasOwn(r,'logs')&&(r.logs===null||Array.isArray(r.logs)),'RECEIPT_LOG_LIST');
  const logs=r.logs??[];assert(logs.length<=1024,'RECEIPT_LOG_LIMIT');
  for(const log of logs){
   hex(log.address,20);hex(log.data);assert(Array.isArray(log.topics)&&log.topics.length<=4,'RECEIPT_TOPICS');for(const t of log.topics)hex(t,32);
   assert(log.removed===undefined||log.removed===false,'RECEIPT_REMOVED_LOG');
  }
  assert.equal(bloom(logs),r.logsBloom,'RECEIPT_LOGS_BLOOM');
  const used=BigInt(r.cumulativeGasUsed);assert(used>=cumulative,'RECEIPT_CUMULATIVE_GAS');cumulative=used;allLogs.push(...logs);
 }
 assert.equal(cumulative,BigInt(block.gasUsed),'RECEIPT_BLOCK_GAS');
 assert.equal(trieRoot(receipts.map(receiptBytes)),block.receiptsRoot,'ORDERED_RECEIPTS_ROOT');
 assert.equal(bloom(allLogs),block.logsBloom,'BLOCK_LOGS_BLOOM');
 let globalLogIndex=(receipts[0].logs??[]).length;
 for(let i=1;i<receipts.length;i++)for(const log of receipts[i].logs??[]){
  const logIndex=globalLogIndex++;
  if(log.address!==manager||log.topics[0]!==topic||log.topics[1]!==pool)continue;
  if(expected&&(block.transactions[i].hash!==expected.transactionHash||i!==Number(BigInt(expected.transactionIndex))||logIndex!==Number(BigInt(expected.logIndex))))continue;
  if(expected)assert.deepEqual({address:log.address,topics:log.topics,data:log.data},{address:expected.address,topics:expected.topics,data:expected.data},'NOTIFICATION_RECEIPT_LOG_MISMATCH');
  assert(receipts[i].status==='0x1'&&log.topics.length===3,'SUPPORTED_SWAP_LOG');hex(log.data,192);
  return {status:'RECEIPTS_AUTHENTICATED_EVENT_SELECTED',authentication:'OBSERVED_HEADER_RECEIPTS_ROOT',blockNumber:Number(BigInt(block.number)),blockHash:block.hash,
   subjectIndex:i,transactionHash:block.transactions[i].hash,logIndex,receiptsRoot:block.receiptsRoot,receiptCount:receipts.length,
   chainTrust:'OBSERVED_RPC_HEADER_NOT_INDEPENDENT_FINALITY',nativeExecutions:0};
 }
 return null;
}
export async function selectNearHead(client,{now=()=>Number(process.hrtime.bigint()/1000000n),sleep=ms=>new Promise(r=>setTimeout(r,ms))}={}){
 const began=now(),observations=[],checked=new Set();let lastStart=-Infinity;
 for(let i=0;i<3;i++){
  if(i){const wait=Math.max(0,lastStart+1500-now());if(now()+wait>=began+4000)break;if(wait)await sleep(wait);}
  if(now()>=began+4000)break;
  lastStart=now();
  const block=await client.call('eth_getBlockByNumber',['latest',true]),observedUnixMs=Date.now();
  assert.equal(headerHash(block),block.hash,'HEAD_HEADER_HASH');
  const number=Number(BigInt(block.number));assert(Number.isSafeInteger(number)&&number>0,'HEAD_NUMBER');
  const candidate=mayContainEvent(block.logsBloom);observations.push({number,hash:block.hash,offsetMs:now()-began,bloomCandidate:candidate});
  if(!candidate||checked.has(block.hash))continue;checked.add(block.hash);
  const receipts=await client.call('eth_getBlockReceipts',[block.hash]);
  const selected=authenticatePoolEvent(block,receipts);
  if(selected)return {...selected,observedBlock:block,observedUnixMs,observations};
 }
 return {status:'NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW',observations,maximumHeadObservations:3,observationStartWindowMs:4000,elapsedMs:now()-began,nativeExecutions:0};
}
