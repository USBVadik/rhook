import test from 'node:test';import assert from 'node:assert/strict';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;assert(lib);
const {reserveFinalHeader}=await import(new URL('file://'+lib+'/rhook_alpha/cases/scenario/checkpoint-budget.mjs'));
const cp={chainId:4663,blockNumber:100,blockHash:'0x'+'11'.repeat(32),stateRoot:'0x'+'22'.repeat(32)};
function fixture(){
 const calls=[];let inFlight=0,delay=null;
 const raw={call:async(method,params)=>{calls.push({method,params});inFlight++;try{if(delay)await delay;return 'ok';}finally{inFlight--; }},pinCheckpoint:()=>{},stats:()=>({requests:calls.length,inFlight})};
 const c=reserveFinalHeader(raw);return {c,calls,raw,delay:p=>{delay=p;}};
}
test('ordinary discovery cannot spend the64th header slot',async()=>{
 const {c,calls}=fixture();c.pinCheckpoint(cp,0);
 for(let i=0;i<63;i++)await c.call('eth_getProof',[]);
 await assert.rejects(c.call('eth_getProof',[]),/RPC_BUDGET_RESERVED_FINAL_HEADER/);assert.equal(calls.length,63);
 assert.equal(await c.finalHeader('0x64'),'ok');assert.equal(calls.length,64);assert.deepEqual(calls.at(-1),{method:'eth_getBlockByNumber',params:['0x64',false]});
 await assert.rejects(c.finalHeader('0x64'),/ALREADY_ISSUED/);await assert.rejects(c.call('eth_getCode',[]),/ALREADY_FINALIZED/);
});
test('concurrent queued issuance still preserves exactly one header slot',async()=>{
 const {c,calls,delay}=fixture();c.pinCheckpoint(cp,0);for(let i=0;i<61;i++)await c.call('eth_getProof',[]);
 let release;delay(new Promise(r=>{release=r;}));const a=c.call('eth_getProof',[]),b=c.call('eth_getProof',[]);
 await assert.rejects(c.call('eth_getProof',[]),/RESERVED_FINAL_HEADER/);assert.equal(calls.length,63);
 await assert.rejects(c.finalHeader('0x64'),/PENDING_OR_BUDGET_DRIFT/);release();await Promise.all([a,b]);delay(null);await c.finalHeader('0x64');assert.equal(calls.length,64);
});
test('final selector must match the one pinned checkpoint',async()=>{
 const {c,calls}=fixture();await assert.rejects(c.finalHeader('0x64'),/PINNED_CHECKPOINT_REQUIRED/);
 c.pinCheckpoint(cp,0);assert.throws(()=>c.pinCheckpoint({...cp,blockNumber:101},0),/CHECKPOINT_DRIFT/);
 await assert.rejects(c.finalHeader('0x65'),/FINAL_HEADER_SELECTOR/);assert.equal(calls.length,0);assert.equal(c.reservation().finalIssued,0);
 await c.finalHeader('0x64');assert.equal(c.reservation().finalIssued,1);
});
test('a failed final header does not authorize a retry or ordinary continuation',async()=>{
 const {c,raw}=fixture();raw.call=async()=>{throw Error('PROVIDER_STOP')};c.pinCheckpoint(cp,0);
 await assert.rejects(c.finalHeader('0x64'),/PROVIDER_STOP/);await assert.rejects(c.finalHeader('0x64'),/ALREADY_ISSUED/);
 await assert.rejects(c.call('eth_getProof',[]),/ALREADY_FINALIZED/);
});
