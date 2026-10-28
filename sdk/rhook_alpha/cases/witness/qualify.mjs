import assert from 'node:assert/strict';
import path from 'node:path';
import {headerHash} from '../../../engine/plan_native/ethereum.mjs';
import {authenticateProof} from '../../../engine/adapters/hookr-case/proof.mjs';
import {C} from './material.mjs';
import {writeNew} from './files.mjs';

// Fresh-root capability only. This does not select a trade or start a capture.
export async function qualifyRoot(client,output){
  let checkpoint=null,proofAuthenticated=false,after=null,stage='CHAIN',reason=null;
  let result;
  try{
    assert.equal(await client.call('eth_chainId',[]),'0x1237','CHAIN_ID');stage='HEADER';
    const h=await client.call('eth_getBlockByNumber',['latest',false]);assert.equal(headerHash(h),h.hash,'HEADER_HASH');
    checkpoint={chainId:4663,blockNumber:Number(BigInt(h.number)),blockHash:h.hash,stateRoot:h.stateRoot,timestamp:Number(BigInt(h.timestamp))};
    stage='PROOF';
    const value=await client.call('eth_getProof',[C.rules,[C.slot],{blockHash:h.hash,requireCanonical:true}]);
    const verified=authenticateProof(h.stateRoot,C.rules,[C.slot],value);proofAuthenticated=true;stage='HEAD_AFTER';
    const head=await client.call('eth_getBlockByNumber',['latest',false]);assert.equal(headerHash(head),head.hash,'HEAD_AFTER_HASH');
    assert(BigInt(head.number)>=BigInt(h.number),'OBSERVED_HEAD_REGRESSION');
    after={number:Number(BigInt(head.number)),hash:head.hash,distanceFromCheckpoint:Number(BigInt(head.number)-BigInt(h.number))};
    result={status:'FRESH_ROOT_PROOF_AUTHENTICATED',account:verified.account,slot:verified.resolutions[0],rulesGenerationMatches:verified.account.codeHash===C.rulesCode};
  }catch(error){
    reason=String(error.message).slice(0,1024);
    result={status:proofAuthenticated?'FRESH_PROOF_AUTHENTICATED_HEAD_OBSERVATION_STOP':stage==='PROOF'&&reason.includes('historical state')&&reason.includes('not available')?
      'FRESHLY_OBSERVED_ROOT_UNAVAILABLE':'FRESH_ROOT_QUALIFICATION_INCONCLUSIVE',stage,causeCode:reason};
  }
  const observations=client.observations?.()??[],first=observations.find(x=>x.method==='eth_getProof')??null,
    selected=observations.find(x=>x.method==='eth_getBlockByNumber')??null;
  result={...result,checkpoint,proofAuthenticated,headBeforeProof:checkpoint?{number:checkpoint.blockNumber,hash:checkpoint.blockHash}:null,headAfterProof:after,
    firstProofRequest:first,ageSinceCheckpointObservedMs:first&&selected?first.transportStartedOffsetMs-selected.responseCompleteOffsetMs:null,
    wallClockMinusChainTimestampMs:first&&checkpoint?first.transportStartedUnixMs-checkpoint.timestamp*1000:null,
    headDistanceMeaning:'Adjacent endpoint observations; exact head/backend distance at dispatch is unobservable.',
    ageMeaning:'Monotonic age since header response; wall minus chain timestamp may include clock skew, not root creation time.',
    exactRetentionConfiguration:'NOT_ESTABLISHED',eligibleHookrCaseSelected:false,completeForCase:false,nativeExecutions:0};
  writeNew(path.join(output,'FRESH_ROOT_QUALIFICATION.json'),Buffer.from(JSON.stringify(result)+'\n'));return result;
}
