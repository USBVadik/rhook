import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readCredential} from '../witness/websocket.mjs';
import {createTransport} from '../witness/transport.mjs';
import {parseStrictEvidenceJson} from '../../../engine/adapters/hookr-case/strict-json.mjs';
export const ENDPOINT='https://robinhood-mainnet.g.alchemy.com/v2';
export const ACQUISITION=Object.freeze({requests:64,wallMs:30000,requestMs:3000,gapMs:125,bytes:8<<20,body:2<<20,header:8192});
export function accountObservation(value,now=Date.now()){
 assert(value?.schema==='rhook/scenario-account-assertions/0.1'&&value.freePlan===true&&value.paidUsageDisabled===true&&value.chainId===4663,'CONFIRMED_FREE_ACCOUNT_REQUIRED');
 assert(Number.isSafeInteger(value.remainingCU)&&value.remainingCU>=2000&&Number.isSafeInteger(value.throughputCUPerSecond)&&value.throughputCUPerSecond>=200,'ACCOUNT_BUDGET_REQUIRED');
 assert(Number.isSafeInteger(value.observedUnixMs)&&value.observedUnixMs<=now&&now-value.observedUnixMs<=600000,'FRESH_ACCOUNT_OBSERVATION_REQUIRED');
 return {freePlan:true,paidUsageDisabled:true,remainingCU:value.remainingCU,throughputCUPerSecond:value.throughputCUPerSecond,observedUnixMs:value.observedUnixMs,maximumEstimatedCU:1280};
}
export function provider({credentialFile,makeTransport=createTransport,record=()=>{}}){
 const token=readCredential(credentialFile),secret=Buffer.from(token);
 const wire=makeTransport({endpoint:ENDPOINT,authorization:'Bearer '+token,maxSockets:2});
 const allowed=new Set(['eth_chainId','eth_getBlockByNumber','eth_getBlockByHash','eth_getProof','eth_getCode']);
 return {close:()=>wire.close(),send:async(body,context)=>{
  const q=JSON.parse(body);assert(allowed.has(q.method),'SCENARIO_READ_ONLY_METHOD');
  const reply=await wire.send(body,context);let echo=reply.body.includes(secret)||reply.headers.includes(secret),invalid=false;
  if(!reply.failure&&reply.body.length){try{echo||=JSON.stringify(parseStrictEvidenceJson(new TextDecoder('utf-8',{fatal:true}).decode(reply.body))).includes(token);}catch{invalid=true;}}
  if(echo||invalid){record({kind:echo?'CREDENTIAL_ECHO':'INVALID_PROVIDER_JSON',bodySha256:createHash('sha256').update(reply.body).digest('hex'),headerSha256:createHash('sha256').update(reply.headers).digest('hex')});return {...reply,body:Buffer.alloc(0),headers:Buffer.alloc(0),failure:echo?'CREDENTIAL_ECHO':'INVALID_PROVIDER_JSON'};}
  return reply;
 }};
}
