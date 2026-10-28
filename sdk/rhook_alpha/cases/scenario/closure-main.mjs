// Separate entry point: acquisition plus explicitly approved native discovery.
// The ordinary read-only acquisition entry point never starts a worker.
import fs from 'node:fs';
import path from 'node:path';
import {readBoundedJson} from '../io.mjs';
import {checkEnvironment,writeNew} from '../witness/files.mjs';
import {rpcClient} from '../witness/rpc.mjs';
import {accountObservation,provider,ENDPOINT,ACQUISITION} from './provider.mjs';
import {acquire} from './acquire.mjs';
import {serveDiscovery,DISCOVERY} from './discovery.mjs';
import {canonical} from './build.mjs';
import {ExecutorWindow} from './executor-window.mjs';
const config=readBoundedJson(process.argv[2],65536).value;
let client=null,result={status:'SCENARIO_CLOSURE_STOP',discoveryOnly:true,finalOfflineExecution:false};
const aborter=new AbortController();
const interrupt=()=>{aborter.abort();client?.stop(Error('DISCOVERY_INTERRUPTED'))};
process.on('SIGTERM',interrupt);process.on('SIGINT',interrupt);
try{
 checkEnvironment(process.env);
 if(config.readOnlyApproved!==true||config.discoveryApproved!==true||config.profile!==DISCOVERY)throw Error('EXPLICIT_CLOSURE_APPROVAL_REQUIRED');
 const account=accountObservation(readBoundedJson(config.accountAssertions,65536).value);
 writeNew(path.join(config.output,'ACCOUNT_BUDGET.json'),Buffer.from(canonical(account)+'\n'));
 let records=0;const record=v=>writeNew(path.join(config.output,'redacted-'+(++records)+'.json'),Buffer.from(canonical(v)+'\n'));
 client=rpcClient(config.output,{transport:provider({credentialFile:config.credentialFile,record}),limits:ACQUISITION,maxInFlight:2,endpointLabel:ENDPOINT});
 result=await acquire(client,config.intent,config.engine,config.output,{discover:async(spec,collector)=>{
  writeNew(path.join(config.output,'PROVISIONAL_SCENARIO.json'),Buffer.from(canonical(spec)+'\n'));
  const window=new ExecutorWindow(collector);
  try{
   const events=await serveDiscovery(config.socket,collector,client,path.join(config.output,'DISCOVERY_READY.json'),{signal:aborter.signal,storageWindow:window});
   writeNew(path.join(config.output,'DISCOVERY_REQUESTS.json'),Buffer.from(canonical({profile:DISCOVERY,discoveryOnly:true,requests:events})+'\n'));
  }finally{writeNew(path.join(config.output,'EXECUTOR_WINDOW_EVENTS.json'),Buffer.from(canonical(window.snapshot())+'\n'));}
 }});
 result={...result,discoveryOnly:true,finalOfflineExecution:false,coverage:'DISCOVERY_COMPLETED_FINAL_NIL_SOURCE_EXECUTION_REQUIRED'};
}catch(e){
 result={status:'SCENARIO_CLOSURE_STOP',causeCode:String(e.message).slice(0,1024),discoveryOnly:true,finalOfflineExecution:false};
 if(fs.existsSync(path.join(config.output,'CHECKPOINT.json')))result.checkpoint=readBoundedJson(path.join(config.output,'CHECKPOINT.json'),65536).value.checkpoint;
}
finally{
 process.off('SIGTERM',interrupt);process.off('SIGINT',interrupt);
 await client?.close();result={...result,acquisition:client?.stats()??{requests:0},externalDelivery:'HOLD'};
 writeNew(path.join(config.output,'ACQUISITION_RESULT.json'),Buffer.from(canonical(result)+'\n'));console.log(JSON.stringify(result));
}
process.exitCode=result.status==='AUTHENTICATED_SCENARIO_CAPTURED'?0:1;
