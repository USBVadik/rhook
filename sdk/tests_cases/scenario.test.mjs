import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const lib=process.env.RHOOK_TEST_INSTALLED_LIB;assert(lib);const load=n=>import(pathToFileURL(path.join(lib,'rhook_alpha/cases/scenario',n)));
const build=await load('build.mjs'),source=await load('provider.mjs');
const {headerHash}=await import(pathToFileURL(path.join(lib,'engine/plan_native/ethereum.mjs')));
const require=createRequire(path.join(lib,'engine/adapters/hookr-case/package.json'));const {recoverTransactionAddress,parseTransaction}=require('viem');
const intent={schema:'rhook/on-demand-hookr-intent/0.1',poolId:build.profile.poolId,lpBps:50};
test('only the selected LP field differs and the simulated caller/input have explicit mappings',async()=>{
 const h={parentHash:'0x'+'00'.repeat(32),sha3Uncles:'0x'+'11'.repeat(32),miner:'0x'+'00'.repeat(20),stateRoot:'0x'+'22'.repeat(32),transactionsRoot:'0x'+'33'.repeat(32),receiptsRoot:'0x'+'44'.repeat(32),logsBloom:'0x'+'00'.repeat(256),difficulty:'0x1',number:'0x10',gasLimit:'0x1e84800',gasUsed:'0x0',timestamp:'0x64',extraData:'0x'+'00'.repeat(32),mixHash:'0x'+'00'.repeat(8)+'000000000000002c'+'000000000000003d'+'00'.repeat(8),nonce:'0x'+'00'.repeat(8),baseFeePerGas:'0x5f5e100'};h.hash=headerHash(h);
 const cp={chainId:4663,blockNumber:16,blockHash:h.hash,stateRoot:h.stateRoot};const engine={sourceSha256:'1'.repeat(64),binarySha256:'2'.repeat(64),policySha256:'3'.repeat(64)};
 const spec=await build.buildSpec(intent,h,cp,[],[],'0x',build.profile.baselineConfigWords,engine);
 const mask=65535n<<160n;assert.equal((BigInt(spec.configurations.baseline[0])^BigInt(spec.configurations.variant[0]))&~mask,0n);
 assert.equal((BigInt(spec.configurations.variant[0])>>160n)&65535n,50n);assert.equal(spec.origin.kind,'AUTHENTICATED_CHECKPOINT_SCENARIO');assert.equal(spec.commonSetup.fundingWei,'1000000000000000000');
 assert.equal((await recoverTransactionAddress({serializedTransaction:spec.actions[0].signedTransaction})).toLowerCase(),spec.commonSetup.actor);
 const signed=parseTransaction(spec.actions[0].signedTransaction);
 assert.equal(signed.gas,10000000n);assert.equal(spec.actions[0].gas,Number(signed.gas));
 assert(signed.gas>6802619n,'fund the observed Hookr lane reserve before call-forwarding overhead');
 assert(signed.gas*signed.gasPrice+signed.value<=BigInt(spec.commonSetup.fundingWei));
 assert.equal(spec.environment.l1BlockNumber,44);assert.equal(spec.actions[0].amountInWei,'1000000000000000');assert(!('canonicalActualValid' in spec));
 const copy={...spec};delete copy.scenarioCommitment;assert.equal(spec.scenarioCommitment,build.commit(build.DOMAIN,copy));
});
test('unknown input fields and unsupported original configurations cannot pass through the builder',()=>{
 assert.throws(()=>build.intent({...intent,amountInWei:'1'}),/INTENT_FIELDS/);assert.throws(()=>build.intent({...intent,lpBps:100}),/SUPPORTED_SCENARIO_INTENT/);
});
test('HTTP acquisition needs fresh Free quota, paid-disabled confirmation and sufficient throughput',()=>{
 const now=1000000,v={schema:'rhook/scenario-account-assertions/0.1',freePlan:true,paidUsageDisabled:true,chainId:4663,remainingCU:2000,throughputCUPerSecond:300,observedUnixMs:now};assert.equal(source.accountObservation(v,now).maximumEstimatedCU,1280);
 for(const change of [{paidUsageDisabled:false},{remainingCU:1999},{throughputCUPerSecond:100},{observedUnixMs:now-600001}])assert.throws(()=>source.accountObservation({...v,...change},now));
});
test('authenticated transport pins the credential destination and redacts an echoed secret before persistence',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhook-scenario-secret-')),file=path.join(dir,'key'),token='test-only-scenario-key-1234567890';fs.writeFileSync(file,token,{mode:0o600});let options;const records=[];
 const p=source.provider({credentialFile:file,record:r=>records.push(r),makeTransport:o=>(options=o,{send:async()=>({status:200,body:Buffer.from(JSON.stringify({jsonrpc:'2.0',id:1,error:{message:token}})),headers:Buffer.from('{}')}),close(){}})});
 try{const r=await p.send(Buffer.from('{"method":"eth_getProof"}'),{});assert.equal(options.endpoint,'https://robinhood-mainnet.g.alchemy.com/v2');assert.equal(options.authorization,'Bearer '+token);assert.equal(r.failure,'CREDENTIAL_ECHO');assert.equal(r.body.length,0);assert.equal(JSON.stringify(records).includes(token),false);await assert.rejects(p.send(Buffer.from('{"method":"eth_sendRawTransaction"}'),{}),/READ_ONLY/);}finally{p.close();fs.rmSync(dir,{recursive:true,force:true});}
});

const system=await load('system.mjs').catch(()=>({}));
test('Arbitrum history-ring subjects follow each checkpoint and retain the existing slot union',()=>{
 assert.equal(system.historySlot(98335490),'0x'+'a9e2'.padStart(64,'0'));
 assert.equal(system.historySlot(393167),'0x'+(393167).toString(16).padStart(64,'0'));
 assert.equal(system.historySlot(393168),'0x'+'0'.repeat(64));
 const hints=new Map([[system.HISTORY_ADDRESS,new Set(['0x'+'1'.padStart(64,'0')])]]);
 system.addHistorySubject(hints,{chainId:4663,blockNumber:98335490});system.addHistorySubject(hints,{chainId:4663,blockNumber:98335490});
 assert.equal(hints.get(system.HISTORY_ADDRESS).size,2);assert(hints.get(system.HISTORY_ADDRESS).has(system.historySlot(98335490)));
 for(const n of [-1,Number.MAX_SAFE_INTEGER+1,1.5,null])assert.throws(()=>system.historySlot(n),/CHECKPOINT_L2/);
 assert.throws(()=>system.addHistorySubject(new Map(),{chainId:1,blockNumber:98335490}),/HISTORY_CHAIN/);
});

test('transaction filter keys follow each signed action, preserving existing grouped slots',()=>{
 const h='0x662082f787950e94cc829ba1f8c903107b37d0e56f6beb7b258e87a0f0d5b850';
 assert.equal(system.transactionFilterSlot(h),'0x8f5282fa5f3912b74832adfa2b019a21029f46fd80046984a2bdbb15be0f2c50');
 assert.notEqual(system.transactionFilterSlot(h.slice(0,-2)+'51'),system.transactionFilterSlot(h));
 const subjects=new Map([[system.FILTER_ADDRESS,new Set(['0x'+'00'.repeat(32)])]]);
 system.addActionSubjects(subjects,[{signedTransaction:'0x1234'},{signedTransaction:'0x5678'}]);
 assert.equal(subjects.size,1);assert.equal(subjects.get(system.FILTER_ADDRESS).size,3);
 assert.throws(()=>system.transactionFilterSlot('0x1'));
});
