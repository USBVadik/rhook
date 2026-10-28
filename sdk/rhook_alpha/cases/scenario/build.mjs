import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import fs from 'node:fs';
import {headerHash} from '../../../engine/plan_native/ethereum.mjs';
import {keccak256} from '../../../engine/adapters/hookr-case/primitives.mjs';
const require=createRequire(new URL('../../../engine/adapters/hookr-case/package.json',import.meta.url));
const {encodeFunctionData}=require('viem'),{privateKeyToAccount}=require('viem/accounts');
export const DOMAIN='rhook/hookr-scenario/0.1';
export const profile=JSON.parse(fs.readFileSync(new URL('./native/profile.json',import.meta.url)));
export const canonical=value=>{
 if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
 if(typeof value==='number'){assert(Number.isSafeInteger(value),'INTEGER');return JSON.stringify(value);}
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 assert(value&&Object.getPrototypeOf(value)===Object.prototype,'OBJECT');return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
};
export const commit=(domain,v)=>createHash('sha256').update(domain+'\n'+canonical(v)).digest('hex');
const seed='RHOOK BUILD04 PUBLIC SIMULATION SIGNER; NEVER FUND OR BROADCAST';
// Public deterministic simulation identity. No wallet key is imported or saved.
const signer=()=>privateKeyToAccount(keccak256('0x'+Buffer.from(seed).toString('hex')));
export const actor=()=>signer().address.toLowerCase();
export const word=n=>'0x'+n.toString(16).padStart(64,'0');
export function intent(value){
 assert(value?.schema==='rhook/on-demand-hookr-intent/0.1'&&value.poolId===profile.poolId&&Number.isInteger(value.lpBps)&&value.lpBps>=0&&value.lpBps<=99,'SUPPORTED_SCENARIO_INTENT');
 assert.deepEqual(Object.keys(value).sort(),['lpBps','poolId','schema'],'INTENT_FIELDS');return structuredClone(value);
}
export function environment(parent){
 assert.equal(headerHash(parent),parent.hash,'CHECKPOINT_HEADER_HASH');const mix=Buffer.from(parent.mixHash.slice(2),'hex');assert.equal(mix.length,32,'NITRO_HEADER_MIX');assert.equal(mix.readBigUInt64BE(16),61n,'ARBOS_PROFILE');
 const l1=Number(mix.readBigUInt64BE(8));if(parent.l1BlockNumber!==undefined)assert.equal(Number(BigInt(parent.l1BlockNumber)),l1,'L1_HEADER_METADATA');
 const env={l2BlockNumber:Number(BigInt(parent.number))+1,l2Timestamp:Number(BigInt(parent.timestamp))+1,l1BlockNumber:l1,syntheticL1BaseFeeWei:'1000000000',poster:parent.miner.toLowerCase(),delayedMessagesRead:Number(BigInt(parent.nonce))};
 assert(Object.values(env).filter(x=>typeof x==='number').every(Number.isSafeInteger),'ENVIRONMENT_INTEGER');return env;
}
export async function buildSpec(value,parent,checkpoint,nodes,codes,chainConfig,words,engine){
 intent(value);const env=environment(parent);assert.deepEqual(words,profile.baselineConfigWords,'SUPPORTED_ORIGINAL_RULES_CONFIGURATION');
 const mask=65535n<<160n,configs={baseline:[...words],variant:[word((BigInt(words[0])&~mask)|(BigInt(value.lpBps)<<160n)),...words.slice(1)]};
 const price=BigInt(parent.baseFeePerGas)*2n>1000000000n?BigInt(parent.baseFeePerGas)*2n:1000000000n;
 // The authenticated Hookr lane requires a 6,802,619 gas entry floor for its
 // 3m executor cap. Leave room for the router and EIP-150 call forwarding.
 const fields={nonce:0,gas:10000000,gasPriceWei:price.toString(),amountInWei:'1000000000000000',minimumOutputBaseUnits:'1',sqrtPriceLimitX96:'4295128740',deadline:env.l2Timestamp+300};
 const data=encodeFunctionData({abi:profile.swapAbi,functionName:'swap',args:[{key:profile.poolKey,zeroForOne:true,amountSpecified:-1000000000000000n,amountBound:1n,sqrtPriceLimitX96:4295128740n,recipient:actor(),deadline:BigInt(fields.deadline)},'0x0000000000000000000000000000000000000000',[]]});
 const router=profile.manifest.contracts.find(c=>c.role==='router').address;
 const signedTransaction=await signer().signTransaction({type:'legacy',chainId:4663,nonce:0,gas:BigInt(fields.gas),gasPrice:price,to:router,data,value:1000000000000000n});
 const action={...fields,signedTransaction};action.id=commit(DOMAIN+'/action',action);
 const sorted=values=>[...values].sort((a,b)=>keccak256(a)<keccak256(b)?-1:keccak256(a)>keccak256(b)?1:0);
 const body={schema:DOMAIN,origin:{kind:'AUTHENTICATED_CHECKPOINT_SCENARIO',capsuleId:commit('rhook/scenario-checkpoint/0.1',{checkpoint,intent:value})},checkpoint,parent,chainConfig,
  inventory:{nodes:sorted(nodes),codes:sorted(codes)},releaseManifestSha256:commit(DOMAIN+'/release',profile.manifest),poolId:profile.poolId,configurations:configs,
  commonSetup:{actor:actor(),fundingWei:'1000000000000000000',nonce:0,requireOriginalAbsence:true},actions:[action],environment:env,engine,
  limits:{nativeWallSeconds:120,nativeCPUSeconds:120,workerRSSBytes:1<<30,stageWallSeconds:140,workflowWallSeconds:180,outputBytes:64<<20,rpc:0,worlds:2}};
 return {...body,scenarioCommitment:commit(DOMAIN,body)};
}
