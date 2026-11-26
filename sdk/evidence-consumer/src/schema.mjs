import {closed,commit,isDigest,need,canonical} from './codec.mjs';

export const COMPONENTS=['H','R','C','I','subject','P','theta'];
export const LIFECYCLES=['SUCCESS','REVERT','PRE_EXECUTION_INVALIDATED'];
const decimal=s=>typeof s==='string' && /^(?:0|[1-9][0-9]{0,19})$/.test(s);
const natural=n=>Number.isSafeInteger(n) && n>=0;
const location=s=>s.chainId+':'+s.blockNumber+':'+s.transactionIndex;
export function subject(value) {
  closed(value,['chainId','blockNumber','transactionIndex','transactionHash']);
  need(['chainId','blockNumber','transactionIndex'].every(k=>decimal(value[k])) &&
    typeof value.transactionHash==='string' && /^0x[a-f0-9]{64}$/.test(value.transactionHash),'SUBJECT_INVALID');
  return value;
}
function wire(value,format,fields) {
  closed(value,['format',...fields]);
  need(value.format===format && fields.every(k=>isDigest(value[k])),'WIRE_INVALID');
}
function projected(query,value) {
  return commit('rhook/projected-result/0.2',{projectionCommitment:query.PCommitment,
    subjectCommitment:query.subjectCommitment,parametersCommitment:query.thetaCommitment,value});
}

export function checkInspection(value, selected, selectedValues) {
  closed(value,['worldId','branchContextId','scope','projection','authority','inventory','rowCount','rows','counts']);
  need(isDigest(value.worldId) && isDigest(value.branchContextId) && ['all','downstream'].includes(value.scope) &&
    value.projection==='lifecycle' && value.authority==='SDK_LOCAL_INSPECTION_ONLY','INSPECTION_INVALID');
  const inventory=closed(value.inventory,['total','prefix','target','downstream']);
  need(Object.values(inventory).every(natural) && inventory.target===1 && inventory.total>=1 && inventory.total<=321 &&
    inventory.total===inventory.prefix+inventory.target+inventory.downstream,'INSPECTION_INVALID');
  const start=value.scope==='all'?0:inventory.prefix+1,rows=value.rows;
  need(Array.isArray(rows) && rows.length===value.rowCount && value.rowCount===inventory.total-start,'INSPECTION_INVALID');
  const counts={changed:0,unchanged:0,unresolved:0},seen=new Set();let previous=null,selectedRow=null;
  for (let i=0;i<rows.length;i++) {
    const row=closed(rows[i],['ordinal','subject','position','classification','actual','branch']);subject(row.subject);
    const ordinal=start+i,position=ordinal<inventory.prefix?'PREFIX':ordinal===inventory.prefix?'TARGET':'DOWNSTREAM';
    need(row.ordinal===ordinal && row.position===position && row.subject.chainId===selected.chainId,'INSPECTION_INVALID');
    const loc=location(row.subject);need(!seen.has(loc),'INSPECTION_INVALID');seen.add(loc);
    if (previous) need(BigInt(row.subject.blockNumber)>BigInt(previous.blockNumber) ||
      row.subject.blockNumber===previous.blockNumber && BigInt(row.subject.transactionIndex)>BigInt(previous.transactionIndex),'INSPECTION_INVALID');
    previous=row.subject;
    if (row.actual===null || row.branch===null) {
      need((row.actual===null || LIFECYCLES.includes(row.actual)) && (row.branch===null || LIFECYCLES.includes(row.branch)) &&
        row.classification==='UNRESOLVED','INSPECTION_INVALID');
    } else need(LIFECYCLES.includes(row.actual) && LIFECYCLES.includes(row.branch) &&
      row.classification===(row.actual===row.branch?'UNCHANGED':'CHANGED'),'INSPECTION_INVALID');
    counts[row.classification.toLowerCase()]++;
    if (loc===location(selected)) {need(canonical(row.subject)===canonical(selected),'INSPECTION_SELECTED_MISMATCH');selectedRow=row}
  }
  closed(value.counts,['changed','unchanged','unresolved']);
  need(canonical(counts)===canonical(value.counts),'INSPECTION_COUNTS_MISMATCH');
  // A downstream view may omit an earlier selected subject; it cannot contradict one it includes.
  if (selectedRow) need(selectedRow.actual===selectedValues.actual && selectedRow.branch===selectedValues.branch,'INSPECTION_SELECTED_MISMATCH');
  return {...value,authority:'REPORTED_INSPECTION_ONLY',completeness:'DECLARED_NOT_INDEPENDENTLY_PROVEN'};
}

export function checkBody(body) {
  closed(body,['query','claim','envelope','disclosedComponents','selectedValues','inspection','reportedVerification','payload']);
  const {query,claim,envelope,disclosedComponents:c,selectedValues:values,payload}=body;
  wire(query,'rhook/branch-query/0.2',COMPONENTS.map(k=>k+'Commitment'));
  wire(claim,'rhook/branch-claim/0.2',['queryCommitment','actualResultCommitment','branchResultCommitment']);
  wire(envelope,'rhook/evidence-envelope/0.2',['claimCommitment','verifierProfileCommitment','payloadCommitment']);
  need(c && typeof c==='object' && !Array.isArray(c) && Object.keys(c).every(k=>COMPONENTS.includes(k)) &&
    ['subject','P','theta'].every(k=>Object.hasOwn(c,k)),'COMPONENTS_INVALID');
  subject(c.subject);
  closed(c.P,['kind','phase','referenceDomain','resultCodec']);
  need(c.P.kind==='NATIVE_ENVELOPE_LIFECYCLE' && c.P.phase==='AFTER_SELECTED_ENVELOPE' &&
    c.P.referenceDomain==='COMPLETE_DECLARED_50_BLOCK_DOMAIN' && c.P.resultCodec==='LIFECYCLE_JSON_STRING_3','PROJECTION_UNSUPPORTED');
  closed(c.theta,[]);
  closed(values,['actual','branch']);need(Object.values(values).every(v=>LIFECYCLES.includes(v)),'RESULT_UNSUPPORTED');
  const components=Object.fromEntries(COMPONENTS.map(k=>[k,'NOT_SUPPLIED']));
  for (const [key,value] of Object.entries(c)) {
    need(commit('rhook/query-component/'+key+'/0.2',value)===query[key+'Commitment'],'COMPONENT_COMMITMENT_MISMATCH');components[key]='MATCH';
  }
  const qc=commit('rhook/branch-query/0.2',query),cc=commit('rhook/branch-claim/0.2',claim);
  need(qc===claim.queryCommitment,'QUERY_CLAIM_MISMATCH');
  need(projected(query,values.actual)===claim.actualResultCommitment,'ACTUAL_RESULT_MISMATCH');
  need(projected(query,values.branch)===claim.branchResultCommitment,'BRANCH_RESULT_MISMATCH');
  need(cc===envelope.claimCommitment,'CLAIM_ENVELOPE_MISMATCH');
  const inspection=checkInspection(body.inspection,c.subject,values);
  if (body.reportedVerification!==null) {
    const v=closed(body.reportedVerification,['accepted','assurance','verifierProfileCommitment']);
    need(typeof v.accepted==='boolean' && v.assurance===(v.accepted?'ESTABLISHED_UNDER_PROFILE':'UNRESOLVED'),'RECORDED_RESULT_INVALID');
    need(v.verifierProfileCommitment===envelope.verifierProfileCommitment,'RECORDED_PROFILE_MISMATCH');
  }
  let payloadStatus='NOT_SUPPLIED';
  if (payload!==null) {
    need(commit('rhook/evidence-payload/0.2',payload)===envelope.payloadCommitment,'PAYLOAD_COMMITMENT_MISMATCH');
    closed(payload,['format','worldId','acquisitionProvenanceCommitment','components','actual','branch']);
    need(payload.format==='rhook/acquired-world-evidence/0.1' && payload.worldId===inspection.worldId &&
      isDigest(payload.acquisitionProvenanceCommitment),'PAYLOAD_INVALID');
    closed(payload.components,COMPONENTS);closed(payload.actual,['value']);closed(payload.branch,['value']);
    need(payload.actual.value===values.actual && payload.branch.value===values.branch,'PAYLOAD_RESULT_MISMATCH');
    for (const key of COMPONENTS) {
      need(commit('rhook/query-component/'+key+'/0.2',payload.components[key])===query[key+'Commitment'],'COMPONENT_COMMITMENT_MISMATCH');components[key]='MATCH';
    }
    payloadStatus='MATCH';
  }
  return {bindings:{status:payloadStatus==='MATCH' && Object.values(components).every(v=>v==='MATCH')?'MATCH':'PARTIAL',
      components,payload:payloadStatus,claimToQuery:'MATCH',actualResult:'MATCH',branchResult:'MATCH',envelopeToClaim:'MATCH',verifierProfile:'DECLARED_NOT_ADMITTED'},
    commitments:{query:qc,claim:cc,envelope:commit('rhook/evidence-envelope/0.2',envelope),payload:envelope.payloadCommitment,verifierProfile:envelope.verifierProfileCommitment},
    recordedComparison:{subject:c.subject.blockNumber+':'+c.subject.transactionIndex,subjectIdentity:c.subject,projection:'lifecycle',
      ...values,changed:values.actual!==values.branch,authority:'COMMITMENT_BOUND_RECORDED_ASSERTION'},
    reportedVerification:body.reportedVerification===null?null:{...body.reportedVerification,authority:'UNTRUSTED_RECORDED_REPORT'},
    inspection,changedSubjects:inspection.rows.filter(row=>row.position==='DOWNSTREAM' && row.classification==='CHANGED')};
}
