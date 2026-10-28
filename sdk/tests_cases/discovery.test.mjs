import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;assert(lib);
const load=p=>import(pathToFileURL(path.join(lib,p)));
const {validateRequest,serveDiscovery,DISCOVERY}=await load('rhook_alpha/cases/scenario/discovery.mjs');
const {ProofCollector}=await load('rhook_alpha/cases/witness/collector.mjs');
const {keccak256,toRlp,EMPTY_ROOT,EMPTY_CODE}=await load('engine/adapters/hookr-case/primitives.mjs');
const address='0x'+'11'.repeat(20),key='0x'+'22'.repeat(32);
const node=toRlp(['0x20'+keccak256(address).slice(2),toRlp(['0x01','0x',EMPTY_ROOT,EMPTY_CODE])]);
const cp={chainId:4663,blockNumber:1,blockHash:'0x'+'44'.repeat(32),stateRoot:keccak256(node)};
const request=(id=1)=>({schema:DISCOVERY,id,checkpoint:cp,world:'SCENARIO_BASELINE',phase:'SYSTEM_START_BLOCK',kind:'eth_getProof',address,slots:[key]});
test('broker rejects other roots, writes, worlds and malformed subjects before RPC',()=>{
 validateRequest(request(),cp,1);
 for(const q of [{...request(),checkpoint:{...cp,blockNumber:2}},{...request(),kind:'eth_sendRawTransaction'},
  {...request(),world:'ACTUAL'},{...request(),id:2},{...request(),slots:[key,key]},
  {...request(),slots:['0x1']},{...request(),address:'0x1'},{...request(),extra:true}])assert.throws(()=>validateRequest(q,cp,1));
});
function exchange(socket,q){return new Promise((resolve,reject)=>{
 const c=net.connect(socket),parts=[];c.on('error',reject);c.on('connect',()=>c.write(JSON.stringify(q)+'\n'));
 c.on('data',p=>parts.push(p));c.on('end',()=>resolve(JSON.parse(Buffer.concat(parts))));
});}
test('local discovery uses genuine cached proofs, preserves attribution and closes its socket',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhc-')),socket=path.join(dir,'b.sock'),ready=path.join(dir,'ready');
 let calls=0;const collector=new ProofCollector(cp,()=>{calls++;throw Error('network forbidden')},{checkpoint:cp,nodes:{[keccak256(node)]:node},codes:{}});
 const client={stats:()=>({requests:0,responseBytes:0,remainingMs:3000}),stop:()=>{}};
 const pending=serveDiscovery(socket,collector,client,ready);
 try{
  for(let i=0;i<100&&!fs.existsSync(ready);i++)await new Promise(r=>setTimeout(r,5));
  const p=await exchange(socket,request());assert.equal(p.result.storageProof[0].value,'0x0');
  const end={schema:DISCOVERY,id:2,checkpoint:cp,world:'CONTROL',phase:'DONE',kind:'finish',completed:true};
  assert.equal((await exchange(socket,end)).result.closed,true);
  const events=await pending;assert.equal(events.length,2);assert.equal(events[0].networkRequests,0);assert.equal(calls,0);
  assert.equal(events[0].request.phase,'SYSTEM_START_BLOCK');assert.equal(fs.existsSync(socket),false);
 }finally{fs.rmSync(dir,{recursive:true,force:true})}
});
test('a missing cached trie path is not answered as zero',async()=>{
 const collector=new ProofCollector(cp,async()=>{throw Error('exact state unavailable')});
 await assert.rejects(collector.proof(address,[key]),/exact state unavailable/);
 assert.equal(collector.project(address,[key]),null);
});
test('interrupting discovery closes the socket and aborts acquisition without a replacement',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhc-')),socket=path.join(dir,'b.sock'),ready=path.join(dir,'ready');
 const collector=new ProofCollector(cp,()=>{throw Error('network forbidden')});let stops=0;
 const controller=new AbortController();
 const pending=serveDiscovery(socket,collector,{stats:()=>({remainingMs:1000}),stop:()=>stops++},ready,{signal:controller.signal});
 const stopped=assert.rejects(pending,/DISCOVERY_INTERRUPTED/);
 try{
  for(let i=0;i<100&&!fs.existsSync(ready);i++)await new Promise(r=>setTimeout(r,5));
  controller.abort();await stopped;assert.equal(stops,1);assert.equal(fs.existsSync(socket),false);
 }finally{fs.rmSync(dir,{recursive:true,force:true})}
});
