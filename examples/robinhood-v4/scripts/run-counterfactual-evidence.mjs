import assert from 'node:assert/strict'
import {spawn} from 'node:child_process'
import {createInterface} from 'node:readline'
import {mkdirSync,writeFileSync} from 'node:fs'
import {buildExecutedEnvelopeEvidence,buildInvalidatedEnvelopeEvidence} from '../../../runtime/src/index.mjs'
import {exportEnvelopeEvidence} from '../../../core/src/index.mjs'
import {read,write} from './common.mjs'
const count=Number(process.argv[2]),mode=process.argv[3]??'on',dir=`results/F${({1:1,2:2,10:3,50:4})[count]}/${mode.toUpperCase()}`;assert([1,2,10,50].includes(count))
mkdirSync(`${dir}/envelopes`,{recursive:true})
const child=spawn(process.env.RHOOK_NATIVE_RUNNER,['-branch','COUNTERFACTUAL','-count',String(count),'-bridge',mode],{stdio:['pipe','pipe','pipe']})
const closed=new Promise((resolve,reject)=>{child.on('error',reject);child.on('close',(code,signal)=>resolve({code,signal}))})
let stderr='';child.stderr.setEncoding('utf8').on('data',x=>stderr+=x)
const timer=setTimeout(()=>child.kill('SIGKILL'),600000),lines=createInterface({input:child.stdout})[Symbol.asyncIterator](),ipc=[],blocks=[],envelopes=[],bindings=[]
const send=x=>{ipc.push({direction:'host-to-native',...x});child.stdin.write(JSON.stringify(x)+'\n')}
async function receive(){const line=await lines.next();assert(!line.done,stderr);const x=JSON.parse(line.value);ipc.push({direction:'native-to-host',...x});assert.notEqual(x.status,'EXECUTION_ERROR',JSON.stringify(x.failure));return x}
async function root(event){send({command:'root',sequence:event.sequence});const r=await receive();assert.equal(r.event,'root');assert.equal(r.sequence,event.sequence);return r.stateRoot}
try{
 for(let i=0;i<count;i++){
  const ready=await receive();assert.equal(ready.event,'ready');assert.equal(Number(ready.blockNumber),70397227+i);send({command:'start'})
  let before=null,covered=0
  for(;;){
   const e=await receive()
   if(e.status==='BLOCK_EXECUTED_UNCOMPARED'){assert.equal(covered,mode==='off'?0:ready.transactions.length);blocks.push(e);break}
   if(e.event==='beforeTx'){
    assert.equal(e.index,covered);assert.equal(e.payload.hash,ready.transactions[e.index].hash);assert.equal(before,null)
    before={index:e.index,stateRoot:await root(e)}
   }else if(e.event==='afterTx'||e.event==='invalidatedTx'){
    assert.equal(e.index,before.index);const post=await root(e),tx=ready.transactions[e.index]
    let built
    if(e.event==='afterTx'){
     const {execution:x,receipt:r}=e.payload;assert.equal(x.transactionHash,tx.hash)
     built=buildExecutedEnvelopeEvidence({blockNumber:ready.blockNumber,transactionIndex:e.index,transactionHash:tx.hash,executedTransactionHash:tx.hash,gasLimit:BigInt(tx.gasLimit),gasUsed:BigInt(x.usedGas),feePaid:x.feePaid,predecessorStateRoot:before.stateRoot,successorStateRoot:post,receiptStatus:Number(BigInt(r.status)),exception:x.executionError,returnData:x.returnData,logs:r.logs??[]})
    }else{
     const x=e.payload;assert.equal(post,before.stateRoot);assert.equal(x.preStateRoot,post);assert.equal(x.postStateRoot,post);assert.equal(x.callEntries,0);assert.equal(x.opcodeCount,0)
     built=buildInvalidatedEnvelopeEvidence({blockNumber:ready.blockNumber,transactionIndex:e.index,transactionHash:tx.hash,gasLimit:BigInt(tx.gasLimit),stateRoot:post,classification:x.invalidation.classification})
    }
    const file=`${ready.blockNumber}-${e.index}.json`;writeFileSync(`${dir}/envelopes/${file}`,exportEnvelopeEvidence(built.evidence));envelopes.push(built.evidence)
    bindings.push({block:Number(ready.blockNumber),index:e.index,transactionHash:tx.hash,event:e.event,gasLimit:tx.gasLimit,preStateRoot:before.stateRoot,postStateRoot:post,nativePayload:e.payload,resultProjection:built.resultProjection,envelope:file})
    before=null;covered++
   }else {assert(['beforeBlockFinalization','afterBlockFinalization'].includes(e.event));await root(e)}
   send({command:'continue',sequence:e.sequence})
  }
 }
 const summary=await receive();assert.equal(summary.status,'SESSION_EXECUTED_UNCOMPARED');child.stdin.end();const exit=await closed;assert.equal(exit.code,0,stderr)
 write(`${dir}/native.json`,{blocks,summary});write(`${dir}/bindings.json`,bindings);write(`${dir}/ipc.json`,ipc);write(`${dir}/process.json`,{...exit,stderr})
 console.log(JSON.stringify({gate:count,status:'CF_EVIDENCE_COLLECTED',envelopes:envelopes.length,finalRoot:summary.finalRoot}))
}finally{clearTimeout(timer);if(child.exitCode===null)child.kill('SIGKILL')}
