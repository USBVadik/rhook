import assert from 'node:assert/strict';
import path from 'node:path';
import {createTransport} from './transport.mjs';
import {writeNew} from './files.mjs';
import {parseStrictEvidenceJson} from '../../../engine/adapters/hookr-case/strict-json.mjs';
export const ENDPOINT='https://rpc.mainnet.chain.robinhood.com';
export const LIMITS=Object.freeze({requests:32,wallMs:30000,requestMs:3000,gapMs:334,bytes:8<<20,body:2<<20,header:8192});
const methods=new Set(['eth_chainId','eth_blockNumber','eth_getBlockByHash','eth_getBlockByNumber','eth_getBlockReceipts','eth_getLogs','eth_getProof','eth_getCode','eth_getRawTransactionByHash']);
export function rpcClient(directory,{transport,limits=LIMITS,maxInFlight=1,endpointLabel=ENDPOINT,
  now=()=>Number(process.hrtime.bigint()/1000000n),sleep=ms=>new Promise(r=>setTimeout(r,ms))}={}){
  assert([1,2].includes(maxInFlight),'RPC_CONCURRENCY');
  transport??=createTransport({endpoint:ENDPOINT,maxSockets:maxInFlight});
  const began=now(),timeline=[],waiters=[],pending=new Set(),budgetWaiters=[];
  const aborter=new AbortController();
  let gate=Promise.resolve(),calls=0,dispatched=0,bytes=0,reserved=0,active=0,peak=0,last=-Infinity,fatal=null,closedAt=null,pin=null;
  const store=(name,value)=>writeNew(path.join(directory,name),Buffer.from(JSON.stringify(value)+'\n'));
  const acquire=()=>active<maxInFlight?(active++,peak=Math.max(peak,active),Promise.resolve()):new Promise(resolve=>waiters.push(resolve));
  const release=()=>{const next=waiters.shift();if(next)next();else active--;};
  const wakeBudget=()=>{for(const resolve of budgetWaiters.splice(0))resolve();};
  const stop=(error,request)=>{
    if(!fatal){fatal=error;if(request)fatal.rpcRequest=request;aborter.abort();wakeBudget();}
  };
  const serialized=fn=>{const result=gate.then(fn);gate=result.catch(()=>{});return result;};
  const call=(method,params)=>{
    const operation=(async()=>{
      await acquire();let allocation=0,i;
      try{
        const launched=await serialized(async()=>{
          if(fatal)throw fatal;
          assert(closedAt===null,'RPC_CLIENT_CLOSED');assert(methods.has(method),'READ_ONLY_METHOD_REQUIRED');
          assert(calls<limits.requests&&bytes<limits.bytes,'RPC_BUDGET');
          while(limits.bytes-bytes-reserved<=limits.header&&reserved>0){await new Promise(resolve=>budgetWaiters.push(resolve));if(fatal)throw fatal;}
          const wait=Math.max(0,last+limits.gapMs-now());assert(now()+wait<began+limits.wallMs,'ACQUISITION_DEADLINE');
          if(wait)await sleep(wait);if(fatal)throw fatal;
          assert(now()<began+limits.wallMs,'ACQUISITION_DEADLINE');
          const available=Math.min(limits.body+limits.header,limits.bytes-bytes-reserved);assert(available>limits.header,'RPC_RESPONSE_BUDGET');allocation=available;reserved+=allocation;
          i=++calls;const request={jsonrpc:'2.0',id:i,method,params},body=Buffer.from(JSON.stringify(request));assert(body.length<=65536,'REQUEST_LIMIT');
          store(`intent-${i}.json`,{request,offsetMs:now()-began,retries:0});
          assert(now()<began+limits.wallMs,'ACQUISITION_DEADLINE');last=now();
          const observation={index:i,method,params:structuredClone(params),transportStartedOffsetMs:last-began,transportStartedMonotonicMs:last,transportStartedUnixMs:Date.now(),
            ...(pin?{checkpoint:pin.checkpoint,ageSinceParentPinnedMs:last-pin.at,chainTimestampAgeMs:Date.now()-pin.timestamp*1000}:{}),remainingRequests:limits.requests-calls,remainingBytes:limits.bytes-bytes-reserved,remainingMs:began+limits.wallMs-last};
          timeline.push(observation);dispatched++;
          return {observation,promise:transport.send(body,{signal:aborter.signal,deadline:BigInt(Math.min(began+limits.wallMs,last+limits.requestMs))*1000000n,
            maxBody:Math.min(limits.body,allocation),maxHeader:limits.header,maxResponse:allocation})};
        });
        const response=await launched.promise,o=launched.observation;o.responseCompleteOffsetMs=now()-began;o.responseCompleteMonotonicMs=now();o.responseCompleteUnixMs=Date.now();
        assert(response.body.length+response.headers.length<=allocation,'TRANSPORT_RESPONSE_RESERVATION');bytes+=response.body.length+response.headers.length;
        writeNew(path.join(directory,`body-${i}.bin`),response.body);writeNew(path.join(directory,`headers-${i}.bin`),response.headers);
        store(`response-${i}.json`,{...o,status:response.status,failure:response.failure??null,elapsedMs:o.responseCompleteOffsetMs-o.transportStartedOffsetMs,offsetMs:now()-began,bodyBytes:response.body.length,headerBytes:response.headers.length});
        assert(bytes<=limits.bytes,'RESPONSE_BUDGET');assert(!response.failure,response.failure);assert.equal(response.status,200,'HTTP_'+response.status);assert(now()<began+limits.wallMs,'ACQUISITION_DEADLINE');
        const packet=parseStrictEvidenceJson(new TextDecoder('utf-8',{fatal:true}).decode(response.body));
        assert(packet?.jsonrpc==='2.0'&&packet.id===i&&Object.hasOwn(packet,'result')&&!Object.hasOwn(packet,'error'),packet?.error?'RPC_ERROR: '+JSON.stringify(packet.error).slice(0,400):'RPC_ENVELOPE');
        assert(packet.result!==null,'RPC_NULL_RESULT');if(fatal)throw fatal;return packet.result;
      }catch(error){stop(error,i?{index:i,method,params:structuredClone(params)}:undefined);if(i)store(`stop-${i}.json`,{reason:String(fatal.message).slice(0,512)});throw fatal;}
      finally{reserved-=allocation;wakeBudget();release();}
    })();
    pending.add(operation);operation.then(()=>pending.delete(operation),()=>pending.delete(operation));return operation;
  };
  return {call,stop,close:async()=>{closedAt??=now();aborter.abort();transport.close();wakeBudget();await Promise.allSettled([...pending]);},
    pinCheckpoint:(checkpoint,timestamp,observedAt=now())=>{assert(Number.isFinite(observedAt)&&observedAt<=now(),'CHECKPOINT_OBSERVATION_TIME');if(pin)assert.deepEqual(pin.checkpoint,checkpoint,'RPC_CHECKPOINT_REPLACEMENT');else pin={checkpoint:Object.freeze(structuredClone(checkpoint)),at:observedAt,timestamp:Number(BigInt(timestamp))};return pin.at;},
    observations:()=>structuredClone(timeline),
    stats:()=>({requests:calls,httpRequestsDispatched:dispatched,responseBytes:bytes,elapsedMs:(closedAt??now())-began,retries:0,endpoint:endpointLabel,maxInFlight,peakInFlight:peak,inFlight:active,reservedBytes:reserved,remainingRequests:limits.requests-calls,remainingBytes:limits.bytes-bytes,remainingMs:Math.max(0,began+limits.wallMs-(closedAt??now()))})};
}
