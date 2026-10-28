import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {EventEmitter} from 'node:events';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;assert(lib,'RHOOK_TEST_INSTALLED_LIB required');
const api=await import(pathToFileURL(path.join(lib,'rhook_alpha/cases/witness/websocket.mjs'))).catch(()=>({}));
const token='test-key-1234567890-not-live';
function fixture(){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhook-wss-test-')),key=path.join(dir,'key'),records=[],sockets=[],requests=[];fs.writeFileSync(key,token,{mode:0o600});let options,url;
 const factory=(u,o)=>{url=u;options=o;const ws=new EventEmitter();ws.readyState=0;
  ws.send=body=>{const request=JSON.parse(body);requests.push(request);setImmediate(()=>ws.emit('message',Buffer.from(JSON.stringify({jsonrpc:'2.0',id:request.id,result:request.method==='eth_subscribe'?'0x1':true})),false));};
  ws.close=ws.terminate=()=>{if(ws.readyState!==3){ws.readyState=3;ws.emit('close');}};ws.pong=()=>{};sockets.push(ws);setImmediate(()=>{ws.readyState=1;ws.emit('open');});return ws;
 };
 const stream=()=>api.createAlchemyLogStream({credentialFile:key,factory,record:r=>records.push(r),timeoutMs:100});
 return {dir,key,records,sockets,requests,stream,get options(){return options;},get url(){return url;},cleanup:()=>fs.rmSync(dir,{recursive:true,force:true})};
}
test('Alchemy WSS uses only the pinned host and narrow logs filter without logging its key',async()=>{
 const f=fixture();let s;
 try{s=f.stream();await s.connect();assert.equal(f.options.followRedirects,false);assert.equal(f.options.rejectUnauthorized,true);assert.equal(f.options.perMessageDeflate,false);assert(f.url.startsWith('wss://robinhood-mainnet.g.alchemy.com/v2/'));assert.equal(f.requests[0].params[0],'logs');assert.equal(f.requests[0].params[1].topics.length,2);await s.close();assert.equal(s.stats().activeConnections,0);assert.equal(JSON.stringify(f.records).includes(token),false);}
  finally{await s?.close();f.cleanup();}
});
test('credential echo is hashed and rejected before raw persistence',async()=>{
 const f=fixture();let s;
 try{s=f.stream();await s.connect();const next=s.next(Number(process.hrtime.bigint()/1000000n)+1000);f.sockets[0].emit('message',Buffer.from(JSON.stringify({echo:token})),false);await assert.rejects(next,/CREDENTIAL_ECHO/);assert(!JSON.stringify(f.records).includes(token));assert(f.records.some(x=>x.kind==='CREDENTIAL_ECHO'));await assert.rejects(s.close(),/CREDENTIAL_ECHO/);}
 finally{await s?.close();f.cleanup();}
});
test('oversized stream messages fail closed with owned socket cleanup',async()=>{
 const f=fixture();let s;
 try{s=f.stream();await s.connect();const next=s.next(Number(process.hrtime.bigint()/1000000n)+1000);f.sockets[0].emit('message',Buffer.alloc(4097,32),false);await assert.rejects(next,/WS_MESSAGE_LIMIT/);await assert.rejects(s.close(),/WS_MESSAGE_LIMIT/);assert.equal(s.stats().activeConnections,0);}
 finally{await s?.close();f.cleanup();}
});
test('a symlink credential is rejected before opening a socket',()=>{
 const f=fixture();try{const link=path.join(f.dir,'link');fs.symlinkSync(f.key,link);assert.throws(()=>api.createAlchemyLogStream({credentialFile:link,factory:()=>{throw Error('MUST_NOT_CONNECT');}}),/CREDENTIAL|ELOOP/);}finally{f.cleanup();}
});
test('a disconnect is surfaced without automatic reconnection inside the transport',async()=>{
 const f=fixture();let s;
 try{s=f.stream();await s.connect();const next=s.next(Number(process.hrtime.bigint()/1000000n)+1000);f.sockets[0].terminate();await assert.rejects(next,/WS_DISCONNECTED/);assert.equal(f.sockets.length,1);}
 finally{await s?.close();f.cleanup();}
});
test('a stream failure during HTTP catch-up cannot be swallowed by final cleanup',async()=>{
 const f=fixture();let s;
 try{s=f.stream();await s.connect();f.sockets[0].emit('message',Buffer.alloc(4097,32),false);await assert.rejects(s.close(),/WS_MESSAGE_LIMIT/);assert.equal(s.stats().activeConnections,0);}
 finally{await s?.close();f.cleanup();}
});
test('the retained ws implementation completes a loopback subscribe, notification and owned close',async()=>{
 const {createRequire}=await import('node:module');const require=createRequire(path.join(lib,'engine/adapters/hookr-case/package.json'));
 const {WebSocket,WebSocketServer}=require('ws');const server=new WebSocketServer({host:'127.0.0.1',port:0});
 await new Promise((resolve,reject)=>{server.once('listening',resolve);server.once('error',reject);});
 const f=fixture();let stream;
 server.on('connection',socket=>socket.on('message',raw=>{
  const request=JSON.parse(raw);socket.send(JSON.stringify({jsonrpc:'2.0',id:request.id,result:request.id===1?'0x123':true}));
  if(request.id===1)socket.send(JSON.stringify({jsonrpc:'2.0',method:'eth_subscription',params:{subscription:'0x123',result:{marker:'LOOPBACK_ONLY'}}}));
 }));
 try{
  stream=api.createAlchemyLogStream({credentialFile:f.key,factory:(_url,options)=>new WebSocket('ws://127.0.0.1:'+server.address().port,options),timeoutMs:1000});
  await stream.connect();const event=await stream.next(Number(process.hrtime.bigint()/1000000n)+1000);assert.equal(event.log.marker,'LOOPBACK_ONLY');
  await stream.close();assert.equal(stream.stats().activeConnections,0);assert.equal(stream.stats().unsubscribeConfirmed,1);
 }finally{await stream?.close();for(const socket of server.clients)socket.terminate();await new Promise(resolve=>server.close(resolve));f.cleanup();}
});
