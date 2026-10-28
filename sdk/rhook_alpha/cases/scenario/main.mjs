import fs from 'node:fs';
import path from 'node:path';
import {readBoundedJson} from '../io.mjs';
import {checkEnvironment,writeNew} from '../witness/files.mjs';
import {rpcClient} from '../witness/rpc.mjs';
import {accountObservation,provider,ENDPOINT,ACQUISITION} from './provider.mjs';
import {acquire} from './acquire.mjs';
const config=readBoundedJson(process.argv[2],65536).value;let client=null,result={status:'SCENARIO_ACQUISITION_STOP',nativeExecutions:0};
try{
 checkEnvironment(process.env);if(config.readOnlyApproved!==true)throw Error('EXPLICIT_READ_ONLY_REQUIRED');
 const account=accountObservation(readBoundedJson(config.accountAssertions,65536).value);
 writeNew(path.join(config.output,'ACCOUNT_BUDGET.json'),Buffer.from(JSON.stringify(account)+'\n'));
 let records=0;const record=v=>writeNew(path.join(config.output,'redacted-'+(++records)+'.json'),Buffer.from(JSON.stringify(v)+'\n'));
 client=rpcClient(config.output,{transport:provider({credentialFile:config.credentialFile,record}),limits:ACQUISITION,maxInFlight:2,endpointLabel:ENDPOINT});
 result=await acquire(client,config.intent,config.engine,config.output);
}catch(e){result={status:'SCENARIO_ACQUISITION_STOP',causeCode:String(e.message).slice(0,1024),nativeExecutions:0};
 if(fs.existsSync(path.join(config.output,'CHECKPOINT.json')))result.checkpoint=readBoundedJson(path.join(config.output,'CHECKPOINT.json'),65536).value.checkpoint;
 if(fs.existsSync(path.join(config.output,'MISSING_DEPENDENCY.json')))result.missingDependency=readBoundedJson(path.join(config.output,'MISSING_DEPENDENCY.json'),65536).value;
}
finally{await client?.close();result={...result,acquisition:client?.stats()??{requests:0},externalDelivery:'HOLD'};writeNew(path.join(config.output,'ACQUISITION_RESULT.json'),Buffer.from(JSON.stringify(result)+'\n'));console.log(JSON.stringify(result));}
process.exitCode=result.status==='AUTHENTICATED_SCENARIO_CAPTURED'?0:1;
