import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;
assert(lib,'RHOOK_TEST_INSTALLED_LIB required');
const {rpcClient,LIMITS}=await import(pathToFileURL(path.join(lib,'rhook_alpha/cases/witness/rpc.mjs')));
const flush=()=>new Promise(r=>setImmediate(r));
const packet=id=>({status:200,headers:Buffer.from('{}'),body:Buffer.from(JSON.stringify({jsonrpc:'2.0',id,result:'0x1237'}))});
function setup(limits={},maxInFlight=2){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhook-rpc-concurrency-')),sent=[];let clock=0;
 const transport={send:(body,ctx)=>new Promise(resolve=>{const row={request:JSON.parse(body),ctx,resolve,start:clock};sent.push(row);ctx.signal?.addEventListener('abort',()=>resolve({...packet(row.request.id),failure:'CANCELLED'}),{once:true});}),close:()=>{}};
 const client=rpcClient(dir,{transport,limits:{...LIMITS,gapMs:0,...limits},maxInFlight,now:()=>clock,sleep:async ms=>{clock+=ms;}});
 return {client,sent,dir,cleanup:async()=>{for(const row of sent)row.resolve(packet(row.request.id));await client.close();fs.rmSync(dir,{recursive:true,force:true});}};
}
test('three pending RPC calls use no more than two transport slots',async()=>{
 const x=setup();const pending=Array.from({length:3},()=>x.client.call('eth_chainId',[]));
 try{
  await flush();assert.equal(x.sent.length,2);x.sent[0].resolve(packet(1));await flush();assert.equal(x.sent.length,3);
  x.sent[1].resolve(packet(2));x.sent[2].resolve(packet(3));assert.deepEqual(await Promise.all(pending),['0x1237','0x1237','0x1237']);
 }finally{await x.cleanup();await Promise.allSettled(pending);}
});
test('concurrent responses reserve disjoint portions of the byte budget',async()=>{
 const x=setup({bytes:200,body:80,header:20});const pending=[x.client.call('eth_chainId',[]),x.client.call('eth_chainId',[])];
 try{await flush();assert.equal(x.sent.length,2);assert(x.sent.reduce((s,r)=>s+r.ctx.maxResponse,0)<=200);for(const row of x.sent)row.resolve(packet(row.request.id));await Promise.all(pending);}
 finally{await x.cleanup();await Promise.allSettled(pending);}
});
test('first transport failure aborts its peer and never dispatches a queued successor',async()=>{
 const x=setup();const pending=Array.from({length:3},()=>x.client.call('eth_chainId',[]));const all=Promise.allSettled(pending);
 try{await flush();x.sent[0].resolve({...packet(1),failure:'SOURCE_FAILURE'});await flush();assert.equal(x.sent.length,2);assert.equal(x.sent[1].ctx.signal?.aborted,true);await all;}
 finally{await x.cleanup();}
});
test('shared pacing remains serial even when two transports overlap',async()=>{
 const x=setup({gapMs:10});const pending=Array.from({length:3},()=>x.client.call('eth_chainId',[]));
 try{await flush();assert.deepEqual(x.sent.map(r=>r.start),[0,10]);x.sent[0].resolve(packet(1));await flush();assert.deepEqual(x.sent.map(r=>r.start),[0,10,20]);for(const r of x.sent.slice(1))r.resolve(packet(r.request.id));await Promise.all(pending);}
 finally{await x.cleanup();await Promise.allSettled(pending);}
});
test('request ceiling is reserved atomically with concurrent callers',async()=>{
 const x=setup({requests:2,gapMs:10});const pending=Array.from({length:4},()=>x.client.call('eth_chainId',[]));const all=Promise.allSettled(pending);
 try{await flush();for(const r of [...x.sent])r.resolve(packet(r.request.id));await all;assert(x.sent.length<=2);assert(x.client.stats().requests<=2);}
 finally{await x.cleanup();}
});
test('a budget too small for response headers leaves no negative reservation',async()=>{
 const x=setup({bytes:10,header:20,body:80});
 try{await assert.rejects(x.client.call('eth_chainId',[]),/RPC_RESPONSE_BUDGET/);assert.equal(x.sent.length,0);assert.equal(x.client.stats().reservedBytes,0);}
 finally{await x.cleanup();}
});
