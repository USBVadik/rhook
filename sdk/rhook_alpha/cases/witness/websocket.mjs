import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {parseStrictEvidenceJson} from '../../../engine/adapters/hookr-case/strict-json.mjs';
import {EVENT_FILTER} from './events.mjs';
import {WATCH_LIMITS as L} from './watch.mjs';
const require=createRequire(new URL('../../../engine/adapters/hookr-case/package.json',import.meta.url));
const WebSocket=require('ws');
const clock=()=>Number(process.hrtime.bigint()/1000000n);
export function readCredential(file){
  let fd;
  try{
    fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);const s=fs.fstatSync(fd);
    assert(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o077)===0&&s.size>0&&s.size<=4096,'CREDENTIAL_FILE');
    const buf=Buffer.alloc(4097),n=fs.readSync(fd,buf,0,4097,0);assert(n===s.size&&n<=4096,'CREDENTIAL_SIZE');
    const value=new TextDecoder('utf-8',{fatal:true}).decode(buf.subarray(0,n)).trim();assert(/^[A-Za-z0-9_-]{16,128}$/.test(value),'CREDENTIAL_FORMAT');return value;
  }catch{throw Error('CREDENTIAL_FILE');}finally{if(fd!==undefined)fs.closeSync(fd);}
}
export function createAlchemyLogStream({credentialFile,factory=(url,options)=>new WebSocket(url,options),record=()=>{},timeoutMs=3000}={}){
  assert(Number.isInteger(timeoutMs)&&timeoutMs>0&&timeoutMs<=3000,'WS_TIMEOUT');
  const token=readCredential(credentialFile),tokenBytes=Buffer.from(token),queue=[];
  let connection=null,fatal=null,waiter=null,connections=0,closedConnections=0,rawBytes=0,messages=0,controls=0,unsubscribeConfirmed=0;
  const stats=()=>({endpoint:'wss://robinhood-mainnet.g.alchemy.com/v2/[REDACTED]',connections,closedConnections,activeConnections:connections-closedConnections,rawBytes,messages,controls,estimatedCU:controls*10+Math.ceil(rawBytes*0.04),unsubscribeConfirmed});
  const fail=code=>{
    fatal??=Error(code);connection?.rejectConnect?.(fatal);if(waiter){clearTimeout(waiter.timer);waiter.reject(fatal);waiter=null;}
    connection?.socket.terminate();
  };
  const account=(kind,value,persist=true)=>{
    const data=Buffer.from(value);rawBytes+=data.length;
    if(data.includes(tokenBytes)){record({kind:'CREDENTIAL_ECHO',bytes:data.length,sha256:createHash('sha256').update(data).digest('hex')});throw Error('CREDENTIAL_ECHO');}
    assert(data.length<=L.payloadBytes,'WS_MESSAGE_LIMIT');assert(rawBytes<=L.rawBytes&&stats().estimatedCU<=L.estimatedFreeCU,'WS_BANDWIDTH_OR_CU_LIMIT');
    if(persist)record({kind,data});
  };
  const send=request=>{controls++;const raw=Buffer.from(JSON.stringify(request));account('OUT',raw);connection.socket.send(raw);};
  const connect=async()=>{
    assert(connection===null,'WS_PREVIOUS_CONNECTION_OWNED');assert(connections<L.maximumConnections,'WS_CONNECTION_LIMIT');fatal=null;queue.length=0;connections++;
    let socket;
    try{socket=factory('wss://robinhood-mainnet.g.alchemy.com/v2/'+token,{followRedirects:false,rejectUnauthorized:true,perMessageDeflate:false,autoPong:false,maxPayload:L.payloadBytes,handshakeTimeout:timeoutMs});}
    catch{closedConnections++;throw Error('WS_TRANSPORT');}
    const c={socket,subscription:null,closing:false,closed:false};connection=c;
    c.closedPromise=new Promise(resolve=>{c.resolveClosed=resolve;});
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>fail('WS_SUBSCRIBE_TIMEOUT'),timeoutMs);c.rejectConnect=e=>{clearTimeout(timer);reject(e);};
      socket.on('open',()=>{try{send({jsonrpc:'2.0',id:1,method:'eth_subscribe',params:['logs',EVENT_FILTER]});}catch(error){fail(error.message);}});
      socket.on('unexpected-response',(_request,response)=>{const unsupported=[404,405,501].includes(response.statusCode);fail(unsupported?'WS_UNSUPPORTED':'WS_HANDSHAKE_REJECTED');response.destroy();});
      socket.on('error',error=>fail(error.code==='WS_ERR_UNSUPPORTED_MESSAGE_LENGTH'?'WS_MESSAGE_LIMIT':'WS_DISCONNECTED'));
      socket.on('ping',data=>{try{account('PING',data);if(!fatal){account('PONG',data);socket.pong(data);}}catch(error){fail(error.message);}});
      socket.on('close',()=>{
        if(!c.closed){c.closed=true;closedConnections++;c.resolveClosed();}
        clearTimeout(timer);if(!c.closing)fail('WS_DISCONNECTED');
      });
      socket.on('message',(value,binary)=>{
        try{
          assert(!binary,'WS_BINARY_MESSAGE');account('IN',value,false);assert(++messages<=L.messages,'WS_MESSAGE_COUNT');
          const p=parseStrictEvidenceJson(new TextDecoder('utf-8',{fatal:true}).decode(value));
          if(JSON.stringify(p).includes(token)){record({kind:'CREDENTIAL_ECHO',bytes:value.length,sha256:createHash('sha256').update(value).digest('hex')});throw Error('CREDENTIAL_ECHO');}
          record({kind:'IN',data:Buffer.from(value)});assert(p?.jsonrpc==='2.0','WS_RPC_ENVELOPE');
          if(p.id===1){
            if(p.error)throw Error([-32601,-32004].includes(p.error.code)?'WS_UNSUPPORTED':'WS_SUBSCRIBE_REJECTED');
            assert(!c.subscription&&typeof p.result==='string'&&/^0x[0-9a-f]{1,128}$/.test(p.result),'WS_SUBSCRIPTION_ID');
            c.subscription=p.result;clearTimeout(timer);c.rejectConnect=null;resolve();return;
          }
          if(p.id===2){c.unsubscribeResolve?.(p.result===true&&!p.error);return;}
          assert(p.method==='eth_subscription'&&c.subscription&&p.params?.subscription===c.subscription&&p.params.result,'WS_NOTIFICATION_ENVELOPE');
          if(c.closing)return;
          const notification={log:p.params.result,receivedMonotonicMs:clock(),receivedUnixMs:Date.now()};
          if(waiter){const next=waiter;waiter=null;clearTimeout(next.timer);next.resolve(notification);}
          else{assert(queue.length<L.messages,'WS_NOTIFICATION_QUEUE');queue.push(notification);}
        }catch(error){fail(/^[A-Z0-9_]+$/.test(error.message)?error.message:'WS_INVALID_PACKET');}
      });
    });
  };
  const next=deadline=>{
    if(fatal)return Promise.reject(fatal);if(queue.length)return Promise.resolve(queue.shift());assert(!waiter,'WS_SINGLE_CONSUMER');
    const ms=Math.max(0,deadline-clock());if(!ms)return Promise.resolve(null);
    return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{waiter=null;resolve(null);},ms);waiter={resolve,reject,timer};});
  };
  const close=async()=>{
    const c=connection;if(!c)return;c.closing=true;
    // A fatal packet may arrive while HTTP catch-up owns the control flow.
    // Closing the socket must not turn that failure into a no-event success.
    let cleanupFailure=fatal&&!['WS_DISCONNECTED','WS_UNSUPPORTED'].includes(fatal.message)?fatal.message:null;
    if(waiter){clearTimeout(waiter.timer);waiter.resolve(null);waiter=null;}
    if(!c.closed&&c.subscription&&c.socket.readyState===1&&!fatal){
      let timer;try{const ack=new Promise(resolve=>{c.unsubscribeResolve=resolve;timer=setTimeout(()=>resolve(false),500);});send({jsonrpc:'2.0',id:2,method:'eth_unsubscribe',params:[c.subscription]});if(await ack)unsubscribeConfirmed++;}catch(error){cleanupFailure=/^[A-Z0-9_]+$/.test(error.message)?error.message:'WS_CLEANUP_FAILURE';}finally{clearTimeout(timer);}
    }
    if(!c.closed)c.socket.close();
    let timer;const wait=()=>Promise.race([c.closedPromise,new Promise(resolve=>{timer=setTimeout(resolve,500);})]);await wait();clearTimeout(timer);
    if(!c.closed){c.socket.terminate();await wait();clearTimeout(timer);}
    assert(c.closed,'WS_CLEANUP_UNCONFIRMED');connection=null;queue.length=0;if(cleanupFailure)throw Error(cleanupFailure);
  };
  return {connect,next,close,stats};
}
