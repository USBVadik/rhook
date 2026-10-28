// The Python API creates one private output directory. This child only writes
// new bounded files there; it never imports code from a case or witness.
import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs';
import {readBoundedJson} from '../io.mjs';
import {checkEnvironment,writeNew} from './files.mjs';
import {rpcClient,LIMITS} from './rpc.mjs';
import {analyze,mergeWitness,projectProfile,sha} from './material.mjs';
import {captureBlock,selectRecent,selectNearHead} from './capture.mjs';
import {qualifyRoot} from './qualify.mjs';
import {observeEvents,WATCH_LIMITS} from './watch.mjs';
import {createAlchemyLogStream} from './websocket.mjs';
import {checkFreeAccount,authenticateNotification} from './event-capture.mjs';
const config=readBoundedJson(process.argv[2],65536).value;
const output=config.output;
const save=(name,value)=>writeNew(path.join(output,name),Buffer.from(JSON.stringify(value)+'\n'));
let client=null,discovery=null,stream=null,discoveryReport=null,report=null,result={status:'FORGE_STOP',nativeExecutions:0};
try{
  checkEnvironment(process.env);
  if(config.action==='watch'){
    assert(config.readOnlyApproved===true&&config.chain===4663,'READ_ONLY_ACQUISITION_APPROVAL_REQUIRED');
    const account=checkFreeAccount(readBoundedJson(config.accountAssertions,65536).value);save('ACCOUNT_BUDGET.json',account);
    const discoveryPath=path.join(output,'DISCOVERY'),wsPath=path.join(output,'WSS');fs.mkdirSync(discoveryPath,{mode:0o700});fs.mkdirSync(wsPath,{mode:0o700});let frame=0,step=0;
    const record=value=>{
      assert(++frame<=256,'WS_EVIDENCE_COUNT');const {data,...meta}=value;
      if(data)writeNew(path.join(wsPath,`frame-${frame}.bin`),data);
      writeNew(path.join(wsPath,`frame-${frame}.json`),Buffer.from(JSON.stringify({...meta,bytes:data?.length??meta.bytes??0})+'\n'));
    };
    stream=account.websocketEntitled?createAlchemyLogStream({credentialFile:config.credentialFile,record}):{connect:async()=>{throw Error('WS_UNSUPPORTED');},next:async()=>null,close:async()=>{},stats:()=>({connections:0,estimatedCU:0,knownUnsupportedEntitlement:true})};
    discovery=rpcClient(discoveryPath,{limits:{...LIMITS,requests:WATCH_LIMITS.discoveryRequests,wallMs:WATCH_LIMITS.discoveryMs,bytes:WATCH_LIMITS.discoveryBytes}});
    const found=await observeEvents(discovery,stream,{record:value=>save(`discovery-step-${++step}.json`,value)});
    discoveryReport={...found,account,websocket:stream.stats()};save('WATCH_DISCOVERY.json',discoveryReport);
    if(found.status==='EVENT_NOTIFICATION_SELECTED_UNAUTHENTICATED'){
      const selection=await authenticateNotification(discovery,found);const {observedBlock,observedParent,...summary}=selection;save('EVENT_SELECTION_PROPOSAL.json',summary);
      await discovery.close();
      client=rpcClient(output,{maxInFlight:2});result=await captureBlock(client,selection.blockNumber,output,{selection});result.selection=summary;
    }else result=found;
  }else if(['capture','capture-recent','select','qualify-root'].includes(config.action)){
    assert(config.readOnlyApproved===true&&config.chain===4663,'READ_ONLY_ACQUISITION_APPROVAL_REQUIRED');
    client=rpcClient(output,['select','qualify-root'].includes(config.action)?{limits:{...LIMITS,requests:config.action==='select'?2:4,wallMs:10000,bytes:1<<20}}:{maxInFlight:2});
    if(config.action==='select')result=await selectRecent(client);
    else if(config.action==='qualify-root')result=await qualifyRoot(client,output);
    else{
      const seed=config.witness?readBoundedJson(config.witness,8<<20).value:null;
      if(seed)assert.equal(seed.format,'rhook/remote-witness-seed/0.1','CHECKPOINT_SEED_FORMAT');
      const selection=config.action==='capture-recent'?await selectNearHead(client):null;
      const {observedBlock,...summary}=selection??{};
      if(selection)save('EVENT_SELECTION_PROPOSAL.json',summary);
      if(selection?.status==='NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW')result=summary;
      else{
        result=await captureBlock(client,selection?.blockNumber??config.block,output,{selection,seed});
        if(selection)result.selection=summary;
      }
    }
  }else if(config.action==='forge'||config.action==='diagnose'){
    let p=readBoundedJson(config.package,8<<20).value;
    if(config.witness)p=mergeWitness(p,readBoundedJson(config.witness,8<<20).value);
    if(config.action==='forge'){
      const projected=projectProfile(p);p=projected.package;
      save('DERIVED_PROOF_PROJECTIONS.json',{projections:projected.projections,meaning:'Local native-import projections; not RPC acquisition records or provider statements.'});
    }
    save('BLOCK_PACKAGE.json',p);result={status:'MATERIAL_IMPORTED',nativeExecutions:0};
  }else throw Error('UNKNOWN_FORGE_ACTION');
}catch(error){result={status:'ACQUISITION_STOP',causeCode:String(error.message).slice(0,1024),nativeExecutions:0};}
finally{
  const cleanupErrors=[];
  for(const component of [stream,discovery,client])try{await component?.close();}catch(error){cleanupErrors.push(String(error.message).slice(0,256));}
  if(cleanupErrors.length)result={...result,status:'ACQUISITION_STOP',causeCode:'OWNED_CLEANUP_UNCONFIRMED',cleanupErrors};
  if(['capture','capture-recent','watch','forge','diagnose'].includes(config.action)&&fs.existsSync(path.join(output,'BLOCK_PACKAGE.json'))){
    try{
      const {raw,value:p}=readBoundedJson(path.join(output,'BLOCK_PACKAGE.json'),8<<20);
      report=await analyze(p);save('DEPENDENCIES.json',{...report,packageSha256:sha(raw)});
    }catch(error){result={...result,status:'FORGE_STOP',diagnosticError:String(error.message).slice(0,1024)};}
  }
  result={...result,diagnostics:report?{status:report.status,authentication:report.authentication,inputCommitment:report.inputCommitment,witnessCommitment:report.witnessCommitment,
    knownDependenciesPresent:report.knownDependenciesPresent,missingCount:report.missing.length,completeForCase:false}:null,
    discovery:discovery?{...discoveryReport,acquisition:discovery.stats(),websocket:stream?.stats()}:null,
    acquisition:client?.stats()??{requests:0},nativeExecutions:0,externalDelivery:'HOLD'};
  save('ACQUISITION_RESULT.json',result);console.log(JSON.stringify(result));
}
process.exitCode=['CAPTURED_SEED','MATERIAL_IMPORTED','UNAUTHENTICATED_EVENT_SELECTED','FRESH_ROOT_PROOF_AUTHENTICATED','NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW','NO_ELIGIBLE_EVENT_OBSERVED'].includes(result.status)?0:1;
