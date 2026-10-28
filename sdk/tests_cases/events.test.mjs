// Authenticated receipt selection and bounded near-head observations; no EVM.
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;
assert(lib,'RHOOK_TEST_INSTALLED_LIB required');
const load=name=>import(pathToFileURL(path.join(lib,name)));
const events=await load('rhook_alpha/cases/witness/capture.mjs');
const {headerHash,bloom,receiptBytes,trieRoot}=await load('engine/plan_native/ethereum.mjs');
const {keccak256,EMPTY_ROOT}=await load('engine/adapters/hookr-case/primitives.mjs');
const manager='0x8366a39cc670b4001a1121b8f6a443a643e40951',pool='0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780';
const topic=keccak256('0x'+Buffer.from('Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)').toString('hex'));
function fixture(number=2000,matched=true){
 const log={address:manager,topics:[topic,pool,'0x'+'11'.repeat(32)],data:'0x'+'00'.repeat(192)};
 const txs=[{hash:'0x'+'22'.repeat(32),type:'0x6a'},{hash:'0x'+'33'.repeat(32),type:'0x2'}];
 const rs=txs.map((tx,i)=>({type:tx.type,status:'0x1',cumulativeGasUsed:'0x'+(21000*(i+1)).toString(16),logsBloom:bloom(i===1&&matched?[log]:[]),logs:i===1&&matched?[log]:[],transactionIndex:'0x'+i.toString(16),transactionHash:tx.hash}));
 const h={parentHash:'0x'+'00'.repeat(32),sha3Uncles:'0x'+'11'.repeat(32),miner:'0x'+'00'.repeat(20),stateRoot:EMPTY_ROOT,transactionsRoot:EMPTY_ROOT,
  receiptsRoot:trieRoot(rs.map(receiptBytes)),logsBloom:bloom(matched?[log]:[]),difficulty:'0x1',number:'0x'+number.toString(16),gasLimit:'0x989680',gasUsed:'0xa410',timestamp:'0x1',
  extraData:'0x'+'00'.repeat(32),mixHash:'0x'+'00'.repeat(32),nonce:'0x'+'00'.repeat(8),baseFeePerGas:'0x1',transactions:txs};
 h.hash=headerHash(h);for(const r of rs){r.blockHash=h.hash;r.blockNumber=h.number;}return {block:h,receipts:rs};
}
function clock(){let t=0;return {now:()=>t,sleep:async ms=>{t+=ms;}};}
test('near-head selector exits normally after three bloom-negative observations',async()=>{
 const c=clock(),calls=[];const result=await events.selectNearHead({call:async(method,params)=>{calls.push({method,params,t:c.now()});return fixture(2000+calls.length,false).block;}},c);
 assert.equal(result.status,'NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW');assert.equal(calls.length,3);assert(calls.every(x=>x.method==='eth_getBlockByNumber'&&x.params[0]==='latest'&&x.params[1]===true));
 assert(calls[1].t-calls[0].t>=1500);assert(calls[2].t-calls[1].t>=1500);assert.equal(result.nativeExecutions,0);
});
test('near-head event is authenticated by the entire ordered receipt root',async()=>{
 const f=fixture(),calls=[];const r=await events.selectNearHead({call:async(method,params)=>{calls.push({method,params});return method==='eth_getBlockReceipts'?f.receipts:f.block;}},clock());
 assert.equal(r.status,'RECEIPTS_AUTHENTICATED_EVENT_SELECTED');assert.equal(r.blockHash,f.block.hash);assert.equal(r.subjectIndex,1);assert.equal(r.transactionHash,f.block.transactions[1].hash);
 assert.equal(r.authentication,'OBSERVED_HEADER_RECEIPTS_ROOT');assert.equal(calls.length,2);assert.deepEqual(calls[1].params,[f.block.hash]);
});
test('receipt mutation cannot manufacture a supported pool interaction',async()=>{
 const f=fixture();f.receipts[1].logs[0].data='0x'+'11'.repeat(192);
 await assert.rejects(events.selectNearHead({call:async method=>method==='eth_getBlockReceipts'?f.receipts:f.block},clock()),/RECEIPT|BLOOM/);
});
test('receipt order and transaction identity are bound to the selected block',async()=>{
 for(const mutate of [r=>r.reverse(),r=>{r[1].transactionHash='0x'+'99'.repeat(32);},r=>{r[1].blockHash='0x'+'99'.repeat(32);}]){
  const f=fixture();mutate(f.receipts);await assert.rejects(events.selectNearHead({call:async method=>method==='eth_getBlockReceipts'?f.receipts:f.block},clock()),/RECEIPT/);
 }
});
test('a receipt source error closes observation without fallback or retry',async()=>{
 const f=fixture(),calls=[];await assert.rejects(events.selectNearHead({call:async method=>{calls.push(method);if(method==='eth_getBlockReceipts')throw Error('METHOD_UNAVAILABLE');return f.block;}},clock()),/METHOD_UNAVAILABLE/);
 assert.deepEqual(calls,['eth_getBlockByNumber','eth_getBlockReceipts']);
});
test('bloom false positives do not produce an eligible subject',async()=>{
 const f=fixture(2000,false);f.block.logsBloom=bloom([{address:manager,topics:[topic,pool],data:'0x'}]);f.block.hash=headerHash(f.block);for(const r of f.receipts)r.blockHash=f.block.hash;
 await assert.rejects(events.selectNearHead({call:async method=>method==='eth_getBlockReceipts'?f.receipts:f.block},clock()),/BLOCK_LOGS_BLOOM/);
});
test('a slow header does not extend the observation into more polling',async()=>{
 let t=0,calls=0;const result=await events.selectNearHead({call:async()=>{calls++;t=5000;return fixture(2000,false).block;}},{now:()=>t,sleep:async()=>{throw Error('NO_SLEEP');}});
 assert.equal(result.status,'NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW');assert.equal(calls,1);
});
test('authenticated bloom false positives are observed once without inventing a swap',async()=>{
 const f=fixture(2000,false),logs=[{address:manager,topics:[],data:'0x'},{address:'0x'+'44'.repeat(20),topics:[topic,pool],data:'0x'}];
 f.receipts[1].logs=logs;f.receipts[1].logsBloom=bloom(logs);f.block.logsBloom=bloom(logs);f.block.receiptsRoot=trieRoot(f.receipts.map(receiptBytes));f.block.hash=headerHash(f.block);for(const r of f.receipts)r.blockHash=f.block.hash;
 let receipts=0;const r=await events.selectNearHead({call:async m=>{if(m==='eth_getBlockReceipts'){receipts++;return f.receipts;}return f.block;}},clock());
 assert.equal(r.status,'NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW');assert.equal(receipts,1);
});
test('a consensus-empty receipt log list accepts the retained Nitro null representation',async()=>{
 const f=fixture();f.receipts[0].logs=null;
 const r=await events.selectNearHead({call:async m=>m==='eth_getBlockReceipts'?f.receipts:f.block},clock());assert.equal(r.status,'RECEIPTS_AUTHENTICATED_EVENT_SELECTED');
});
test('capture reuses the authenticated observed block and records its actual observation time',async()=>{
 const {rawFromRpc}=await load('rhook_alpha/cases/witness/transactions.mjs');
 const {toRlp}=await load('engine/adapters/hookr-case/primitives.mjs');const fs=await import('node:fs'),os=await import('node:os');
 const first={type:'0x6a',chainId:'0x1237',input:'0x0102'};first.hash=keccak256('0x6a'+toRlp(['0x1237','0x0102']).slice(2));
 const second={type:'0x2',chainId:'0x1237',nonce:'0x0',maxPriorityFeePerGas:'0x1',maxFeePerGas:'0x2',gas:'0x5208',to:'0x'+'11'.repeat(20),value:'0x0',input:'0x',accessList:[],v:'0x0',r:'0x1',s:'0x2'};
 second.hash=keccak256('0x02'+toRlp(['0x1237','0x','0x01','0x02','0x5208',second.to,'0x','0x',[],'0x','0x01','0x02']).slice(2));
 const parent=fixture(1999,false).block;parent.stateRoot='0x'+'55'.repeat(32);parent.hash=headerHash(parent);
 const block={...fixture().block,parentHash:parent.hash,transactions:[first,second],transactionsRoot:trieRoot([rawFromRpc(first),rawFromRpc(second)])};block.hash=headerHash(block);
 const selection={blockNumber:2000,blockHash:block.hash,subjectIndex:1,transactionHash:second.hash,observedBlock:block,observedUnixMs:123456,authentication:'OBSERVED_HEADER_RECEIPTS_ROOT'};
 const calls=[],dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhook-capture-context-'));
 try{
  await assert.rejects(events.captureBlock({call:async(method,params)=>{calls.push({method,params});if(method==='eth_chainId')return '0x1237';if(method==='eth_getBlockByNumber')return parent;throw Error('FIRST_PROOF_BOUNDARY');}},2000,dir,{selection}),/FIRST_PROOF_BOUNDARY/);
  assert.deepEqual(calls.map(x=>x.method),['eth_chainId','eth_getBlockByNumber','eth_getProof']);
  const evidence=JSON.parse(fs.readFileSync(path.join(dir,'FIRST_PROOF_WINDOW.json')));assert.equal(evidence.headBeforeProof.observedUnixMs,123456);
  const saved=JSON.parse(fs.readFileSync(path.join(dir,'EVENT_SELECTION.json')));assert.equal(saved.authentication,'OBSERVED_HEADER_RECEIPTS_ROOT');assert(!('observedBlock' in saved));
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('slow replies preserve at least 1.5seconds between actual observation starts',async()=>{
 let t=0;const starts=[];
 const r=await events.selectNearHead({call:async()=>{starts.push(t);if(starts.length===1)t+=2000;return fixture(2000+starts.length,false).block;}},{now:()=>t,sleep:async ms=>{t+=ms;}});
 assert.equal(r.status,'NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW');assert.deepEqual(starts,[0,2000,3500]);
});
test('an eligible event from a permitted in-flight head observation is retained',async()=>{
 let t=0,heads=0,receipts=0;const f=fixture();
 const r=await events.selectNearHead({call:async method=>{
  if(method==='eth_getBlockReceipts'){receipts++;return f.receipts;}
  if(++heads<3)return fixture(2000+heads,false).block;t+=1500;return f.block;
 }},{now:()=>t,sleep:async ms=>{t+=ms;}});
 assert.equal(heads,3);assert.equal(receipts,1);assert.equal(r.status,'RECEIPTS_AUTHENTICATED_EVENT_SELECTED');
});

const {authenticateNotification,checkFreeAccount}=await load('rhook_alpha/cases/witness/event-capture.mjs');
function notificationFixture(){
 const f=fixture(),parent=fixture(1999,false).block;f.block.parentHash=parent.hash;f.block.hash=headerHash(f.block);
 for(const r of f.receipts){r.blockHash=f.block.hash;r.blockNumber=f.block.number;}
 const notification={...f.receipts[1].logs[0],blockHash:f.block.hash,blockNumber:f.block.number,transactionHash:f.receipts[1].transactionHash,transactionIndex:'0x1',logIndex:'0x0'};
 return {...f,parent,found:{notification,mode:'ALCHEMY_WSS',eventReceivedMonotonicMs:0,eventReceivedUnixMs:1}};
}
test('a notification is authenticated against the exact block, original parent and ordered receipts',async()=>{
 const f=notificationFixture(),calls=[];let t=0;
 const selected=await authenticateNotification({call:async(m,p)=>{calls.push([m,p]);t+=10;return m==='eth_getBlockReceipts'?f.receipts:p[0]===f.block.hash?f.block:f.parent;}},f.found,{now:()=>t});
 assert.equal(selected.checkpoint.blockHash,f.parent.hash);assert.equal(selected.parentPinnedMonotonicMs,20);assert.equal(selected.latency.eventToReceiptAuthenticationMs,30);
 assert.equal(selected.logIndex,0);assert.deepEqual(calls.map(x=>x[1][0]),[f.block.hash,f.parent.hash,f.block.hash]);
});
test('changed notification block, parent link and receipt contents fail before capture',async()=>{
 for(const kind of ['block','parent','receipt','logIndex']){
  const f=notificationFixture();if(kind==='block')f.block.stateRoot='0x'+'99'.repeat(32);
  if(kind==='parent')f.parent.stateRoot='0x'+'99'.repeat(32);
  if(kind==='receipt')f.receipts[1].logs[0].data='0x'+'99'.repeat(192);
  if(kind==='logIndex')f.found.notification.logIndex='0x1';
  await assert.rejects(authenticateNotification({call:async(m,p)=>m==='eth_getBlockReceipts'?f.receipts:p[0]===f.found.notification.blockHash?f.block:f.parent},f.found),/HASH|PARENT|ROOT|RECEIPT|BLOOM|EVENT/);
 }
});
test('late receipts do not reset the pinned-parent age or trigger a retry',async()=>{
 const f=notificationFixture();let t=0,reads=0;
 const selected=await authenticateNotification({call:async(m,p)=>{
  if(m==='eth_getBlockReceipts'){reads++;t+=2500;return f.receipts;}t+=10;return p[0]===f.block.hash?f.block:f.parent;
 }},f.found,{now:()=>t});
 assert.equal(reads,1);assert.equal(selected.parentPinnedMonotonicMs,20);assert.equal(selected.latency.eventToReceiptAuthenticationMs,2520);
});
test('Free account assertions require fresh quota and an explicit WSS entitlement',()=>{
 const now=1000000,base={schema:'rhook/alchemy-free-assertions/0.1',freePlan:true,paidUsageDisabled:true,chainId:4663,websocketEntitled:true,remainingCU:2000,observedUnixMs:now};
 assert.equal(checkFreeAccount(base,now).sessionEstimatedCUBudget,2000);
 for(const change of [{paidUsageDisabled:false},{websocketEntitled:null},{remainingCU:1999},{observedUnixMs:now-600001},{observedUnixMs:now+1}])assert.throws(()=>checkFreeAccount({...base,...change},now));
 assert.equal(checkFreeAccount({...base,websocketEntitled:false,remainingCU:0},now).sessionEstimatedCUBudget,0);
});
