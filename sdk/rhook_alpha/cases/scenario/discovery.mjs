import assert from 'node:assert/strict';
import fs from 'node:fs';
import net from 'node:net';
import {canonical} from './build.mjs';
import {writeNew} from '../witness/files.mjs';
import {parseStrictEvidenceJson} from '../../../engine/adapters/hookr-case/strict-json.mjs';
export const DISCOVERY='rhook/scenario-witness-discovery/0.1';

export function validateRequest(q,checkpoint,id){
 assert.equal(q.schema,DISCOVERY);assert.equal(q.id,id);assert.deepEqual(q.checkpoint,checkpoint,'DISCOVERY_CHECKPOINT');
 assert(typeof q.phase==='string'&&/^[ -~]{1,128}$/.test(q.phase),'DISCOVERY_PHASE');
 if(q.kind==='finish'){
  assert.equal(q.world,'CONTROL');assert.equal(q.completed,true);
  assert.deepEqual(Object.keys(q).sort(),['schema','id','checkpoint','world','phase','kind','completed'].sort());return;
 }
 assert(['ADMISSION','SCENARIO_BASELINE','SCENARIO_VARIANT'].includes(q.world),'DISCOVERY_WORLD');
 assert(['eth_getProof','eth_getCode'].includes(q.kind),'DISCOVERY_READ_ONLY');
 assert(/^0x[0-9a-fA-F]{40}$/.test(q.address),'DISCOVERY_ADDRESS');
 assert.deepEqual(Object.keys(q).sort(),['schema','id','checkpoint','world','phase','kind','address',...(q.kind==='eth_getProof'?['slots']:[])].sort());
 if(q.kind==='eth_getProof')assert(Array.isArray(q.slots)&&q.slots.length<=48&&new Set(q.slots).size===q.slots.length&&q.slots.every(k=>/^0x[0-9a-fA-F]{64}$/.test(k)),'DISCOVERY_SLOTS');
}

// One worker, one request at a time, one immutable root and one RPC budget.
// Receiving "finish" closes acquisition, not proof of an accepted offline run.
export async function serveDiscovery(socket,collector,client,readyPath,{signal,storageWindow}={}){
 assert(socket.length<=103&&!fs.existsSync(socket),'FRESH_DISCOVERY_SOCKET');
 const sockets=new Set(),events=[];let sequence=0,active=false,done=false,timer,resolve,reject;
 const outcome=new Promise((a,b)=>{resolve=a;reject=b});
 // listen errors can arrive before the await below attaches its handler.
 outcome.catch(()=>{});
 const stop=e=>{if(done)return;done=true;client.stop(e);reject(e)};
 const interrupted=()=>stop(Error('DISCOVERY_INTERRUPTED'));
 signal?.addEventListener('abort',interrupted,{once:true});
 const server=net.createServer(connection=>{
  // A just-flushed reply may still be closing as the next request connects.
  if(sockets.size>=4||done){connection.destroy();stop(Error('DISCOVERY_CONNECTION_LIMIT'));return}
  sockets.add(connection);let buffer=Buffer.alloc(0),handled=false;
  connection.setTimeout(3500,()=>stop(Error('DISCOVERY_SOCKET_TIMEOUT')));
  connection.on('error',stop);connection.on('close',()=>sockets.delete(connection));
  connection.on('data',async chunk=>{
   if(handled||done)return stop(Error('DISCOVERY_EXTRA_DATA'));
   buffer=Buffer.concat([buffer,chunk]);if(buffer.length>65536)return stop(Error('DISCOVERY_REQUEST_LIMIT'));
   const end=buffer.indexOf(10);if(end<0)return;
   handled=true;
   try{
    assert(end===buffer.length-1&&!active,'DISCOVERY_CONCURRENT_OR_TRAILING');active=true;
    const q=parseStrictEvidenceJson(buffer.subarray(0,end).toString('utf8'));validateRequest(q,collector.checkpoint,++sequence);assert(sequence<=128,'DISCOVERY_REQUEST_COUNT');
    const before=client.stats();let result;
    if(q.kind==='finish')result={closed:true};
    else if(q.kind==='eth_getProof'){
     if(storageWindow)result=await storageWindow.fetch(collector,q.address,q.slots);
     else{await collector.proof(q.address,q.slots);result=collector.project(q.address,q.slots).proof;}
    }
    else result=await collector.code(q.address);
    const after=client.stats();events.push({request:q,networkRequests:after.requests-before.requests,responseBytes:after.responseBytes-before.responseBytes});
    const reply=Buffer.from(canonical({id:q.id,result})+'\n');assert(reply.length<=2<<20,'DISCOVERY_REPLY_LIMIT');
    active=false;connection.end(reply,()=>{if(q.kind==='finish'&&!done){done=true;resolve(events)}});
   }catch(e){active=false;connection.destroy();stop(e)}
  });
  connection.on('end',()=>{if(!handled&&!done)stop(Error('DISCOVERY_EARLY_EOF'))});
 });
 server.on('error',stop);
 try{
  assert(!signal?.aborted,'DISCOVERY_INTERRUPTED');
  await new Promise((a,b)=>{server.once('error',b);server.listen(socket,a)});fs.chmodSync(socket,0o600);
  writeNew(readyPath,Buffer.from(canonical({socket,checkpoint:collector.checkpoint,profile:DISCOVERY})+'\n'));
  timer=setTimeout(()=>stop(Error('DISCOVERY_DEADLINE')),Math.max(1,client.stats().remainingMs));
  return await outcome;
 }finally{
  signal?.removeEventListener('abort',interrupted);
  clearTimeout(timer);for(const connection of sockets)connection.destroy();await new Promise(a=>server.close(a));
 }
}
