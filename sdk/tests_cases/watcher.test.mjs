import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;assert(lib,'RHOOK_TEST_INSTALLED_LIB required');
const watch=await import(pathToFileURL(path.join(lib,'rhook_alpha/cases/witness/watch.mjs'))).catch(()=>({}));
const {keccak256}=await import(pathToFileURL(path.join(lib,'engine/adapters/hookr-case/primitives.mjs')));
const topic=keccak256('0x'+Buffer.from('Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)').toString('hex'));
const log=()=>({address:'0x8366a39cc670b4001a1121b8f6a443a643e40951',topics:[topic,'0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780','0x'+'11'.repeat(32)],data:'0x'+'00'.repeat(192),blockHash:'0x'+'22'.repeat(32),blockNumber:'0x101',transactionHash:'0x'+'33'.repeat(32),transactionIndex:'0x3',logIndex:'0x5'});
function fixture({items=[],unsupported=false,disconnect=false,logs=()=>[],heads=[256,257,270]}={}){
 let t=0,connections=0,closed=0,reads=0,head=0;const calls=[];
 const client={call:async(method,params)=>{calls.push({method,params});if(method==='eth_blockNumber')return '0x'+heads[Math.min(head++,heads.length-1)].toString(16);if(method==='eth_getLogs')return logs(params[0]);throw Error('UNEXPECTED_RPC');}};
 const stream={connect:async()=>{connections++;if(unsupported)throw Error('WS_UNSUPPORTED');},next:async deadline=>{reads++;if(disconnect&&reads===1)throw Error('WS_DISCONNECTED');if(items.length)return items.shift();t=deadline;return null;},close:async()=>{closed++;},stats:()=>({connections,closed,reads})};
 return {client,stream,calls,now:()=>t,sleep:async ms=>{t+=ms;},stats:()=>({connections,closed,reads})};
}
test('one matching notification selects one untrusted discovery input and closes the stream',async()=>{
 const f=fixture({items:[log(),log()]});const r=await watch.observeEvents(f.client,f.stream,f);assert.equal(r.status,'EVENT_NOTIFICATION_SELECTED_UNAUTHENTICATED');assert.equal(r.notification.blockHash,log().blockHash);assert.equal(f.stats().reads,1);assert.equal(f.stats().closed,1);
});
test('unrelated Transfer-style events never select a Hookr case',async()=>{
 const wrong={...log(),topics:['0x'+'aa'.repeat(32)]};const f=fixture({items:[wrong,log()]});const r=await watch.observeEvents(f.client,f.stream,f);assert.equal(r.notification.transactionHash,log().transactionHash);assert.equal(f.stats().reads,2);
});
test('missing stream notifications are recovered from a contiguous saved cursor',async()=>{
 let n=0;const f=fixture({logs:()=>++n===2?[{...log(),blockNumber:'0x10a'}]:[]});const r=await watch.observeEvents(f.client,f.stream,f);assert.equal(r.mode,'CONTIGUOUS_GETLOGS');
 const ranges=f.calls.filter(c=>c.method==='eth_getLogs').map(c=>c.params[0]);assert.equal(BigInt(ranges[1].fromBlock),BigInt(ranges[0].toBlock)+1n);assert.equal(r.notification.blockNumber,'0x10a');
});
test('unsupported subscription uses bounded contiguous fallback without head sampling',async()=>{
 const f=fixture({unsupported:true,logs:()=>[log()]});const r=await watch.observeEvents(f.client,f.stream,f);assert.equal(r.mode,'CONTIGUOUS_GETLOGS');assert.equal(f.stats().connections,1);assert(f.calls.every(c=>['eth_blockNumber','eth_getLogs'].includes(c.method)));assert(f.calls.length<=16);
});
test('one disconnect permits one reconnect and catch-up without cursor reset',async()=>{
 let n=0;const f=fixture({disconnect:true,logs:()=>++n===2?[{...log(),blockNumber:'0x10a'}]:[]});const r=await watch.observeEvents(f.client,f.stream,f);assert.equal(r.status,'EVENT_NOTIFICATION_SELECTED_UNAUTHENTICATED');assert.equal(f.stats().connections,2);const ranges=f.calls.filter(c=>c.method==='eth_getLogs').map(c=>c.params[0]);assert.equal(BigInt(ranges[1].fromBlock),BigInt(ranges[0].toBlock)+1n);
});
test('a removed matching event stops instead of changing selected history',async()=>{
 const f=fixture({items:[{...log(),removed:true}]});await assert.rejects(watch.observeEvents(f.client,f.stream,f),/EVENT_REORG_REMOVED/);assert.equal(f.stats().closed,1);
});
test('no event completes a bounded session with an explicit contiguous coverage horizon',async()=>{
 const f=fixture();const r=await watch.observeEvents(f.client,f.stream,f);assert.equal(r.status,'NO_ELIGIBLE_EVENT_OBSERVED');assert.equal(r.coveredFromBlock,256);assert.equal(r.coveredThroughBlock,270);assert(f.now()<=30000);assert.equal(f.stats().closed,1);
});
test('a discovery gap larger than its budget cannot be silently skipped',async()=>{
 const f=fixture({heads:[256,1000]});await assert.rejects(watch.observeEvents(f.client,f.stream,f),/DISCOVERY_RANGE_BUDGET/);assert.equal(f.stats().closed,1);
});
test('repeated notifications in a contiguous response are counted without creating two candidates',async()=>{
 const f=fixture({unsupported:true,logs:()=>[log(),log()]});const r=await watch.observeEvents(f.client,f.stream,f);
 assert.equal(r.duplicates,1);assert.equal(r.status,'EVENT_NOTIFICATION_SELECTED_UNAUTHENTICATED');assert.equal(f.calls.filter(c=>c.method==='eth_getLogs').length,1);
});
