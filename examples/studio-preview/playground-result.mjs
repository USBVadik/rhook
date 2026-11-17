// Existing RHOOK Studio rendering contract; retained unchanged for the public read-only adapter.
// Rendering contract only. Record identity/consistency is not an EVM proof.
const hex=v=>typeof v==='string'&&/^0x[0-9a-f]{64}$/.test(v),sha=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
function legacyValidate(r,job){
 if(!r||r.schema!=='rhook/studio-playground-result/0.1'||r.status!=='VERIFIED_PLAYGROUND_COMPARISON'||r.jobId!==job.jobId||r.requestCommitment!==job.requestCommitment||!sha(r.resultIdentity)||!sha(r.operationCommitment)||(job.sdkOperationCommitment!==undefined&&r.operationCommitment!==job.sdkOperationCommitment)||!sha(r.scenarioCommitment)||!hex(r.commonBootstrapRoot)||r.nativeExecutionPerformedNow!==true||r.independentEVMReexecution!==false||r.recordVerificationPerformedNow!==true||r.historicalAuthentication!==false||r.qualifiedClaims!==0||r.verification!=='RECORDED_INTEGRITY_NOT_EXECUTION_PROOF'||!Array.isArray(r.worlds)||r.worlds.length!==2)throw Error('Playground result identity or assurance mismatch.');
 for(const [i,w]of r.worlds.entries()){
  if(w.world!==['SCENARIO_BASELINE','SCENARIO_VARIANT'][i]||!hex(w.stateRoot)||!hex(w.receiptsRoot)||!Array.isArray(w.actions)||w.actions.length!==4)throw Error('Playground world mismatch.');
  for(const [n,a]of w.actions.entries())if(a.index!==n||a.kind!==['APPROVE','LAUNCH_POOL','BUY','BUY'][n]||![0,1].includes(a.receiptStatus)||(n<2&&a.receiptStatus!==1)||!Number.isSafeInteger(a.gasUsed)||a.gasUsed<0||!hex(a.transactionHash)||!hex(a.state?.guardWord)||!hex(a.state?.dynamicFeeWord))throw Error('Playground action evidence mismatch.');
 }
 return r;
}
function legacySummary(r){return ['Fresh hypothetical Playground · recorded consistency verified; no independent EVM proof.',...r.worlds.flatMap(w=>[w.world,...w.actions.map(a=>`${a.index+1}. ${a.kind}: ${a.receiptStatus?'SUCCESS':'REVERT'}; received net ${a.tokenTransferNetBaseUnits} test-token units; gas ${a.gasUsed}; outer fee pips ${a.outerSwapFeePips.join(',')}; guard ${a.state.guardWord}; dynamic ${a.state.dynamicFeeWord}`),`State ${w.stateRoot}`]),'Guard/dynamic values are worker-reported, not independently rederived. Two worlds do not identify causal contributions; matched controls remain outside this case.'].join('\n');}

export function validatePlaygroundResult(r,job){
 if(r?.schema!=='rhook/studio-playground-result/0.2')return legacyValidate(r,job);
 legacyValidate({...r,schema:'rhook/studio-playground-result/0.1'},job);
 if(r.executionProfile!=='nitro-hookr-playground/0.3'||r.baselinePolicy!=='COMMON_AS_DF_BURN_OFF'||r.tokenFlow?.schema!=='rhook/playground-token-flow/0.3'||r.tokenFlow.viewCalls!==60||r.tokenFlow.supplySemantics!=='TRANSFER_TO_DEAD_NOT_TOTAL_SUPPLY_BURN'||r.tokenFlow.claimSemantics!=='ACCRUED_QUOTE_CLAIM_NOT_WITHDRAWAL'||r.tokenFlow.provenance!=='WORKER_REPORTED_ABI_STATIC_CALL_NO_INDEPENDENT_MPT_PROOF'||r.tokenFlow.worlds?.length!==2)throw Error('Auto Burn evidence scope mismatch.');
 if(r.tokenFlow.burnDestination!=='0x000000000000000000000000000000000000dead'||(job.controller?.profile&&job.controller.profile!==r.executionProfile))throw Error('Auto Burn profile mismatch.');
 const keys=['traderBalance','deadBalance','poolManagerBalance','totalSupply','protocolClaimable'];
 const uint=v=>typeof v==='string'&&/^(0|[1-9][0-9]{0,77})$/.test(v)&&BigInt(v)<(1n<<256n);
 for(const [i,w]of r.tokenFlow.worlds.entries()){
  if(w.world!==r.worlds[i].world||w.snapshots?.length!==3||w.buys?.length!==2)throw Error('Auto Burn world observations missing.');
  for(const [n,o]of w.snapshots.entries())if(o.action!==['LAUNCH_POOL-1','BUY-2','BUY-3'][n]||o.transactionHash!==r.worlds[i].actions[n+1].transactionHash||o.accountingL1Block!==17||!o.values||Object.keys(o.values).length!==5||!keys.every(k=>uint(o.values[k])))throw Error('Auto Burn snapshot mismatch.');
  for(const [n,b]of w.buys.entries()){
   const names=['traderDeltaBaseUnits','sentToDeadBaseUnits','poolManagerDeltaBaseUnits','supplyDeltaBaseUnits','protocolClaimableDeltaWei'];
   if(b.action!==['BUY-2','BUY-3'][n]||b.transactionHash!==r.worlds[i].actions[n+2].transactionHash||b.receiptStatus!==r.worlds[i].actions[n+2].receiptStatus||!names.every(k=>typeof b[k]==='string'&&/^(0|-?[1-9][0-9]{0,77})$/.test(b[k]))||b.supplyDeltaBaseUnits!=='0')throw Error('Auto Burn observation binding mismatch.');
   const deltas=keys.map(k=>BigInt(w.snapshots[n+1].values[k])-BigInt(w.snapshots[n].values[k]));
   if(!names.every((k,j)=>BigInt(b[k])===deltas[j])||deltas[0]+deltas[1]+deltas[2]!==0n||deltas[0]<0n||deltas[1]<0n||deltas[4]<0n||(i===0&&deltas[1]!==0n)||(b.receiptStatus===0&&deltas.some(v=>v!==0n)))throw Error('Auto Burn balance consistency mismatch.');
  }
 }
 return r;
}
export function playgroundSummary(r){
 if(r.schema!=='rhook/studio-playground-result/0.2')return legacySummary(r);
 return ['Fresh hypothetical Playground 0.3 · recorded consistency, no independent EVM proof.','Control: same Anti-Snipe/Dynamic Fee, Auto Burn OFF. Variant: same settings, Auto Burn as requested.','Auto Burn sends tokens to DEAD; totalSupply is unchanged. Protocol amounts are accrued quote claims, not withdrawals.',...r.tokenFlow.worlds.flatMap(w=>[w.world,...w.buys.map(b=>`${b.action} ${b.receiptStatus?'SUCCESS':'REVERT'}: received ${b.traderDeltaBaseUnits} base units; sent to DEAD ${b.sentToDeadBaseUnits}; totalSupply delta ${b.supplyDeltaBaseUnits}; accrued protocol claim ${b.protocolClaimableDeltaWei} wei.`)]),'ABI observations are worker-reported, not independently reconstructed MPT proofs.'].join('\n');
}
