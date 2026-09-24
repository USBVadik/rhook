import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { createInterface } from 'node:readline'
import { mkdirSync,writeFileSync } from 'node:fs'
import { executeInstrumentedBlock } from '../../../host/src/index.mjs'
import { exportEnvelopeEvidence } from '../../../core/src/index.mjs'
import { bytes,hex,write } from './common.mjs'
const [mode,countText]=process.argv.slice(2),count=Number(countText)
assert(['off','on'].includes(mode));assert([2,10,50].includes(count))
const dir=`results/actual/RHOOK_${mode.toUpperCase()}`;mkdirSync(`${dir}/envelopes`,{recursive:true})
const child=spawn(process.env.RHOOK_NATIVE_RUNNER,['-count',String(count),'-bridge',mode,'-witness','inputs/witness.json'],{stdio:['pipe','pipe','pipe']})
let stderr='';child.stderr.setEncoding('utf8').on('data',x=>stderr+=x)
const closed=new Promise((resolve,reject)=>{child.once('error',reject);child.once('close',(code,signal)=>resolve({code,signal}))})
const timer=setTimeout(()=>child.kill('SIGKILL'),600000)
const reader=createInterface({input:child.stdout})[Symbol.asyncIterator]()
const ipc=[],blocks=[],hosts=[],finalizations=[];let boundary=null
async function receive(){const line=await reader.next();assert(!line.done,`native EOF ${stderr}`);const r=JSON.parse(line.value);ipc.push({direction:'native-to-host',...r});assert.notEqual(r.status,'EXECUTION_ERROR',JSON.stringify(r));return r}
const send=r=>{ipc.push({direction:'host-to-native',...r});child.stdin.write(JSON.stringify(r)+'\n')}
const events=new EventEmitter(),vm={events,stateManager:{async getStateRoot(){assert(boundary);send({command:'root',sequence:boundary.sequence});const r=await receive();assert.equal(r.event,'root');assert.equal(r.sequence,boundary.sequence);return bytes(r.stateRoot)}}}
try {
 for(let b=0;b<count;b++){
  const ready=await receive();assert.equal(ready.event,'ready');assert.equal(Number(ready.blockNumber),70397227+b)
  const block={header:{number:BigInt(ready.blockNumber)},transactions:ready.transactions.map(t=>({hash:()=>bytes(t.hash),gasLimit:BigInt(t.gasLimit)}))}
  const identities=ready.transactions.map((t,index)=>({blockNumber:ready.blockNumber,transactionIndex:index,transactionHash:t.hash}))
  const eventResult=(e,r,i)=>{
   assert.equal(e.transactionHash,ready.transactions[i].hash);assert.equal(e.usedGas,r.gasUsed);assert(Object.hasOwn(r,'logs'))
   return {transaction:block.transactions[i],totalGasSpent:BigInt(e.usedGas),amountSpent:BigInt(e.feePaid),receipt:{...r,status:Number(BigInt(r.status))},execResult:{...(e.executionError===null?{}:{exceptionError:e.executionError}),returnValue:e.returnData,logs:(r.logs??[]).map(({address,topics,data})=>({address,topics,data}))}}
  }
  const dispatch=async(name,payload)=>{for(const listener of events.listeners(name))await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('unacknowledged '+name)),5000);try{listener(payload,()=>{clearTimeout(t);resolve()})}catch(e){clearTimeout(t);reject(e)}})}
  async function runBlock(actualVM,options){
   assert.equal(actualVM,vm);assert.equal(options.block,block);assert.equal(options.forcedHistoricalEnvelopeReplay,false)
   for(const k of ['generate','skipHeaderValidation','skipBlockValidation','setHardfork'])assert.equal(options[k],true)
   send({command:'start'})
   let result
   for(;;){const r=await receive();if(r.status==='BLOCK_EXECUTED_UNCOMPARED'){result=r;blocks.push(r);break}
    assert.equal(mode,'on');boundary=r
    if(r.event==='beforeTx'){assert.equal(r.payload.hash,ready.transactions[r.index].hash);await dispatch('beforeTx',block.transactions[r.index])}
    else if(r.event==='afterTx')await dispatch('afterTx',eventResult(r.payload.execution,r.payload.receipt,r.index))
    else {assert(['beforeBlockFinalization','afterBlockFinalization'].includes(r.event));finalizations.push({block:ready.blockNumber,boundary:r.event,root:hex(await vm.stateManager.getStateRoot())})}
    send({command:'continue',sequence:r.sequence});boundary=null
   }
   return {results:result.executions.map((e,i)=>eventResult(e,result.receipts[i],i)),receipts:result.receipts.map(r=>({...r,status:Number(BigInt(r.status))})),gasUsed:BigInt(result.gasUsed),receiptsRoot:bytes(result.receiptsRoot),stateRoot:bytes(result.finalStateRoot)}
  }
  const host=await executeInstrumentedBlock({vm,block,mode:'ACTUAL',canonicalEnvelopeIdentities:identities,evidenceEnabled:mode==='on',runBlock})
  assert.equal(events.listenerCount('beforeTx'),0);assert.equal(events.listenerCount('afterTx'),0)
  for(const [i,e] of (host.envelopes??[]).entries())writeFileSync(`${dir}/envelopes/${ready.blockNumber}-${i}.json`,exportEnvelopeEvidence(e))
  hosts.push(host)
 }
 const summary=await receive();assert.equal(summary.status,'SESSION_EXECUTED_UNCOMPARED');assert.equal(summary.count,count)
 child.stdin.end();const exit=await closed;assert.equal(exit.code,0,stderr)
 write(`${dir}/native.json`,{blocks,summary});write(`${dir}/host.json`,hosts);write(`${dir}/ipc.json`,ipc);write(`${dir}/finalization.json`,finalizations);write(`${dir}/process.json`,{...exit,stderr})
 console.log(JSON.stringify({mode,count,transactions:blocks.reduce((n,b)=>n+b.transactionHashes.length,0),finalRoot:summary.finalRoot}))
}finally{clearTimeout(timer);if(child.exitCode===null)child.kill('SIGKILL')}
