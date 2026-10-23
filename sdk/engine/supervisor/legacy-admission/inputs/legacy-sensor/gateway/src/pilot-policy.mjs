// Experimental host-condition assessment. Neither this function nor NORMAL
// pressure authorizes execution or establishes available/reserved physical RAM.
import {need,closed} from './common.mjs';
export const PILOT=Object.freeze({format:'rhook/trusted-local-darwin-policy/0.2',enabledByDefault:false,
 requestCommitment:'85264966293ab4de5d7b211625a64310609a9662bfef1229e163b65fa318c33b',
 providerProfileCommitment:'191bff333443916ded3422e6e5ee308807f06a55874bb6018d4f512f0af8165f',
 limitsCommitment:'ab20e470c3df05856e1e535ccd1d46853a8a52c112a978f9287c25c25bb8cd06',
 workloadBytes:5368709120,nativeBytes:4294967296,serviceBytes:536870912,controlBytes:536870912,osReserveTargetBytes:1073741824,
 producerTimeoutMs:1800000,overallTimeoutMs:3600000,periodMs:250,maximumGapMs:375,maximumAgeMs:375,windowMs:5000,
 swapAdmission:'RESIDUAL_SWAP_ONLY_WHILE_PRESSURE_NORMAL_COUNTERS_QUIET_USAGE_NOT_GROWING',runtimeSwapRule:'SAME_CONTINUOUS_RULE',quantitativeMemoryReservation:false});
// Accepted storage-risk contract remains unchanged by this memory-policy revision.
export const PILOT_EVIDENCE_RISK=Object.freeze({format:'rhook/amount27-local-evidence-loss-risk/0.1',
 requestCommitment:PILOT.requestCommitment,scope:'ONE_TRUSTED_LOCAL_AMOUNT27_EXPERIMENT',
 acknowledgement:'FOUNDER_ACCEPTS_LOCAL_EVIDENCE_LOSS_RISK',independentBackupRequired:false,
 durableJournalRequired:true,noRepeatAccountingRequired:true,separateExecutionAuthorizationRequired:true,
 automaticRetryAllowed:false,corruptJournalOrUncertainGrant:'STOP',
 laterExperiment:'NEW_OPERATION_ID_NEW_GRANT_SEPARATE_FOUNDER_DECISION',publicGatewayBackupPolicyChanged:false});
const uint=s=>{need(typeof s==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(s),'PILOT_TELEMETRY_CLOCK');return BigInt(s);};
export function assessHost(s,nowNs,previous=null){
 need(s&&closed(s,['source','seq','beganNs','endedNs','pressureBefore','pressureAfter','swapUsedBeforeBytes','swapUsedBytes','swapInPagesBefore','swapInPages','swapOutPagesBefore','swapOutPages','swapPageBytes','physicalBytes']),'PILOT_TELEMETRY_MISSING');
 need(s.source==='DARWIN_SYSCTL_PRESSURE_SWAP_VM_STAT/0.2','PILOT_SOURCE');
 need(typeof nowNs==='bigint'&&Number.isSafeInteger(s.seq)&&s.seq>=0,'PILOT_TELEMETRY_CLOCK');
 const began=uint(s.beganNs),ended=uint(s.endedNs);
 need(began<=ended&&ended<=nowNs,'PILOT_TELEMETRY_CLOCK');
 need(nowNs-began<=BigInt(PILOT.maximumAgeMs)*1000000n,'PILOT_TELEMETRY_STALE');
 need(s.pressureBefore===1&&s.pressureAfter===1,'PILOT_HOST_PRESSURE');
 need(['swapUsedBeforeBytes','swapUsedBytes','swapInPagesBefore','swapInPages','swapOutPagesBefore','swapOutPages'].every(k=>Number.isSafeInteger(s[k])&&s[k]>=0)&&[4096,16384].includes(s.swapPageBytes)&&s.swapInPages>=s.swapInPagesBefore&&s.swapOutPages>=s.swapOutPagesBefore,'PILOT_SWAP_COUNTER_ANOMALY');
 need(s.swapInPages===s.swapInPagesBefore&&s.swapOutPages===s.swapOutPagesBefore,'PILOT_SWAP_ACTIVITY');
 need(s.swapUsedBytes<=s.swapUsedBeforeBytes,'PILOT_SWAP_GROWTH');
 need(Number.isSafeInteger(s.physicalBytes)&&s.physicalBytes>=25769803776,'PILOT_HOST_CAPACITY');
 if(previous){
  need(s.seq===previous.seq+1&&began>previous.ended&&began-previous.began<=BigInt(PILOT.maximumGapMs)*1000000n,'PILOT_SAMPLE_GAP');
  need(s.swapPageBytes===previous.swapPageBytes&&s.swapInPagesBefore>=previous.swapInPages&&s.swapOutPagesBefore>=previous.swapOutPages,'PILOT_SWAP_COUNTER_ANOMALY');
  need(s.swapInPagesBefore===previous.swapInPages&&s.swapOutPagesBefore===previous.swapOutPages,'PILOT_SWAP_ACTIVITY');
  need(s.swapUsedBeforeBytes<=previous.swapUsedBytes,'PILOT_SWAP_GROWTH');
 }
 return {healthy:true,seq:s.seq,began,ended,swapUsedBytes:s.swapUsedBytes,swapInPages:s.swapInPages,swapOutPages:s.swapOutPages,swapPageBytes:s.swapPageBytes,reservedBytes:0,quantitativeHeadroom:'NOT_ESTABLISHED',osReserveTargetBytes:PILOT.osReserveTargetBytes,osReserveEstablished:false,riskDecisionRequired:true,executionAuthorized:false};
}
export class PilotWindow{
 #first=null;#last=null;#count=0;#failed=false;
 add(s,nowNs){need(!this.#failed,'PILOT_STOP_LATCHED');try{const next=assessHost(s,nowNs,this.#last);this.#first??=next;this.#last=next;this.#count++;return next;}catch(e){this.#failed=true;throw e;}}
 finish(nowNs){need(!this.#failed,'PILOT_STOP_LATCHED');try{
  need(this.#count===21&&this.#last.began-this.#first.ended>=5000000000n&&this.#last.began-this.#first.ended<=5250000000n,'PILOT_ADMISSION_WINDOW');
  need(typeof nowNs==='bigint'&&nowNs>=this.#last.ended&&nowNs-this.#last.began<=375000000n,'PILOT_TELEMETRY_STALE');
  return {samples:this.#count,swapUsedBytes:this.#last.swapUsedBytes,swapInPages:this.#last.swapInPages,swapOutPages:this.#last.swapOutPages,quietIntervalNs:(this.#last.began-this.#first.ended).toString(),reservedBytes:0,quantitativeHeadroom:'NOT_ESTABLISHED',osReserveEstablished:false,riskDecisionRequired:true,executionAuthorized:false};
 }catch(e){this.#failed=true;throw e;}}
}
export function checkUsage(u){
 need(u&&closed(u,['A','B','service','control'])&&Object.values(u).every(v=>Number.isSafeInteger(v)&&v>=0),'PILOT_ACCOUNTING');
 need(u.A===0||u.B===0,'PILOT_PRODUCER_OVERLAP');
 const totalBytes=u.A+u.B+u.service+u.control;
 need(Number.isSafeInteger(totalBytes)&&u.A<=PILOT.nativeBytes&&u.B<=PILOT.nativeBytes&&u.service<=PILOT.serviceBytes&&u.control<=PILOT.controlBytes&&totalBytes<=PILOT.workloadBytes,'PILOT_RSS_BUDGET');
 return {totalBytes};
}
