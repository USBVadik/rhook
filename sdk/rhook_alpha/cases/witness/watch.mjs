import assert from 'node:assert/strict';
import {hex,quantity} from '../../../engine/adapters/hookr-case/primitives.mjs';
import {EVENT_FILTER} from './events.mjs';
export const WATCH_LIMITS=Object.freeze({observationMs:20000,discoveryMs:30000,discoveryRequests:16,discoveryBytes:8<<20,
  rangeBlocks:64,maximumRanges:4,maximumConnections:2,rawBytes:32768,messages:64,payloadBytes:4096,estimatedFreeCU:2000});
export function validateNotification(value){
  if(!value||value.address!==EVENT_FILTER.address||value.topics?.[0]!==EVENT_FILTER.topics[0]||value.topics?.[1]!==EVENT_FILTER.topics[1])return null;
  assert(value.removed!==true,'EVENT_REORG_REMOVED');assert(value.removed===undefined||value.removed===false,'EVENT_REMOVED_FLAG');
  hex(value.blockHash,32);hex(value.transactionHash,32);hex(value.data,192);assert(value.topics.length===3,'EVENT_TOPICS');for(const t of value.topics)hex(t,32);
  const number=quantity(value.blockNumber),ordinal=quantity(value.transactionIndex),index=quantity(value.logIndex);
  assert(number>0n&&number<BigInt(Number.MAX_SAFE_INTEGER),'EVENT_BLOCK_NUMBER');assert(ordinal>0n&&ordinal<8n,'EVENT_SUBJECT_ORDINAL');assert(index<8192n,'EVENT_LOG_INDEX');
  return structuredClone(value);
}
export async function observeEvents(client,stream,{now=()=>Number(process.hrtime.bigint()/1000000n),sleep=ms=>new Promise(r=>setTimeout(r,ms)),record=()=>{}}={}){
  const began=now(),deadline=began+WATCH_LIMITS.observationMs,seen=new Map(),ranges=[];
  let cursor=null,from=null,connections=0,duplicates=0,ignored=0;
  const consider=raw=>{
    const v=validateNotification(raw);if(!v){ignored++;return null;}
    const id=v.blockHash+':'+v.transactionHash+':'+v.logIndex,body=JSON.stringify([v.address,v.topics,v.data]);
    if(seen.has(id)){assert.equal(seen.get(id),body,'CONFLICTING_NOTIFICATION');duplicates++;return null;}
    assert(seen.size<WATCH_LIMITS.messages,'EVENT_COUNT_LIMIT');seen.set(id,body);return v;
  };
  const selected=(notification,mode,stamp={})=>({status:'EVENT_NOTIFICATION_SELECTED_UNAUTHENTICATED',authentication:'UNTRUSTED_DISCOVERY',notification,mode,eventReceivedMonotonicMs:stamp.receivedMonotonicMs??now(),eventReceivedUnixMs:stamp.receivedUnixMs??Date.now(),coveredFromBlock:from,coveredThroughBlock:cursor,ranges,connections,duplicates,ignored,nativeExecutions:0});
  const catchUp=async()=>{
    const head=Number(quantity(await client.call('eth_blockNumber',[])));assert(Number.isSafeInteger(head)&&head>=cursor,'DISCOVERY_HEAD_REGRESSION');
    assert(head-cursor<=WATCH_LIMITS.rangeBlocks*WATCH_LIMITS.maximumRanges,'DISCOVERY_RANGE_BUDGET');
    const candidates=[];
    while(cursor<head){
      const start=cursor+1,end=Math.min(head,cursor+WATCH_LIMITS.rangeBlocks),filter={...EVENT_FILTER,fromBlock:'0x'+start.toString(16),toBlock:'0x'+end.toString(16)};
      const logs=await client.call('eth_getLogs',[filter]);assert(Array.isArray(logs)&&logs.length<=WATCH_LIMITS.messages,'DISCOVERY_LOG_LIMIT');
      for(const raw of logs){const v=consider(raw);if(v){const n=Number(quantity(v.blockNumber));assert(n>=start&&n<=end,'DISCOVERY_LOG_RANGE');candidates.push(v);}}
      ranges.push({fromBlock:start,toBlock:end});cursor=end;record({kind:'CONTIGUOUS_RANGE',fromBlock:start,toBlock:end});
    }
    candidates.sort((a,b)=>Number(quantity(b.blockNumber)-quantity(a.blockNumber))||Number(quantity(b.transactionIndex)-quantity(a.transactionIndex)));
    return candidates[0]??null;
  };
  try{
    from=Number(quantity(await client.call('eth_blockNumber',[])));assert(Number.isSafeInteger(from)&&from>0,'DISCOVERY_INITIAL_HEAD');cursor=from-1;
    let fallback=false;
    while(connections<WATCH_LIMITS.maximumConnections&&now()<deadline){
      try{
        connections++;await stream.connect();
        const caught=await catchUp();if(caught)return selected(caught,'CONTIGUOUS_GETLOGS');
        while(now()<deadline){const raw=await stream.next(deadline);if(raw===null)break;const v=consider(raw.log??raw);if(v)return selected(v,'ALCHEMY_WSS',raw);}
        break;
      }catch(error){
        if(error.message==='WS_UNSUPPORTED'){fallback=true;break;}
        if(error.message!=='WS_DISCONNECTED')throw error;
        await stream.close();record({kind:'DISCONNECT',connections});
        if(connections>=WATCH_LIMITS.maximumConnections){fallback=true;break;}
      }
    }
    if(fallback){
      await stream.close();
      for(let i=0;i<7&&now()<deadline;i++){
        const v=await catchUp();if(v)return selected(v,'CONTIGUOUS_GETLOGS');
        if(i<6&&now()+2000<deadline)await sleep(2000);else break;
      }
    }else{
      const v=await catchUp();if(v)return selected(v,'CONTIGUOUS_GETLOGS');
    }
    return {status:'NO_ELIGIBLE_EVENT_OBSERVED',coveredFromBlock:from,coveredThroughBlock:cursor,ranges,connections,duplicates,ignored,elapsedMs:now()-began,nativeExecutions:0};
  }finally{await stream.close();}
}
