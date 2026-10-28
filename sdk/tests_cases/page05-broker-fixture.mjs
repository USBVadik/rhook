// Offline integration fixture; never connects to a provider or executes EVM.
import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';
const lib=process.env.RHOOK_PAGE05_LIB;assert(lib);
const {ProofCollector}=await import(new URL('file://'+lib+'/rhook_alpha/cases/witness/collector.mjs'));
const {ExecutorWindow}=await import(new URL('file://'+lib+'/rhook_alpha/cases/scenario/executor-window.mjs'));
const {serveDiscovery}=await import(new URL('file://'+lib+'/rhook_alpha/cases/scenario/discovery.mjs'));
const {keccak256}=await import(new URL('file://'+lib+'/engine/adapters/hookr-case/primitives.mjs'));
const {commit,canonical,DOMAIN}=await import(new URL('file://'+lib+'/rhook_alpha/cases/scenario/build.mjs'));
const [socket,ready,resultPath]=process.argv.slice(2),spec=JSON.parse(fs.readFileSync(process.env.RHOOK_PAGE05_SCENARIO)),state=JSON.parse(fs.readFileSync(process.env.RHOOK_PAGE05_STATE));
assert.deepEqual(spec.checkpoint,state.checkpoint);
const map=raw=>Object.fromEntries(raw.map(v=>[keccak256(v),v]));
const retained=new ProofCollector(state.checkpoint,()=>{throw Error('NO_NETWORK')},{checkpoint:state.checkpoint,nodes:map(state.nodes),codes:map(state.codes)});
let calls=0,proofKeys=[];const collector=new ProofCollector(state.checkpoint,async(method,params)=>{
 assert.equal(method,'eth_getProof');assert.deepEqual(params[2],{blockHash:state.checkpoint.blockHash,requireCanonical:true});calls++;proofKeys.push(params[1]);
 const p=retained.project(params[0],params[1]);assert(p,'RETAINED_PROOF_UNAVAILABLE');return p.proof;
},{checkpoint:state.checkpoint,nodes:map(spec.inventory.nodes),codes:map(spec.inventory.codes)});
const address='0x4b4c16681401454140a9dbca55e5c186bbe8d728',key='0x290decd9548b62a8d60345a988386fc84ba6bc95484008f6362f93160ef3e62b';
const expected=retained.project(address,[key]);assert(expected);
fs.writeFileSync(resultPath+'.expected',JSON.stringify({address,key,value:expected.verified.resolutions[0].value}));
const window=new ExecutorWindow(collector),abort=new AbortController();
const stop=()=>abort.abort();process.on('SIGTERM',stop);process.on('SIGINT',stop);
try{
 const events=await serveDiscovery(socket,collector,{stats:()=>({remainingMs:8000,requests:calls,responseBytes:0}),stop(){}},ready,{signal:abort.signal,storageWindow:window});
 const byHash=(a,b)=>keccak256(a)<keccak256(b)?-1:keccak256(a)>keccak256(b)?1:0;
 const body={...spec,inventory:{nodes:[...collector.nodes.values()].sort(byHash),codes:[...collector.codes.values()].sort(byHash)}};delete body.scenarioCommitment;
 fs.writeFileSync(resultPath+'.closed-input',canonical({...body,scenarioCommitment:commit(DOMAIN,body)})+'\n');
 fs.writeFileSync(resultPath,JSON.stringify({calls,proofKeys,pages:window.snapshot().pages,additionalKeys:window.snapshot().additionalKeys,events:events.map(e=>({kind:e.request.kind,slots:e.request.slots??[]})),EVM:0,RPC:0}));
}finally{process.off('SIGTERM',stop);process.off('SIGINT',stop);}
