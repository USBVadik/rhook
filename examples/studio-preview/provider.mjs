import {validatePlaygroundResult} from './playground-result.mjs';
import {INTEGRITY_SHA256} from './data-pins.mjs';

export const RECORD_IDS = ['a', 'b', 'burn'];
export async function sha256(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join('');
}
export function validateRecord(record) {
  if (record.schema !== 'rhook/public-studio-record/0.1' || !RECORD_IDS.includes(record.id)) throw Error('Unsupported public record.');
  const p = record.projection, a = record.acceptance, s = record.provenance.sidecar;
  validatePlaygroundResult(p, {jobId: p.jobId, requestCommitment: p.requestCommitment, sdkOperationCommitment: p.operationCommitment});
  if (record.provenance.newExecutionInPreview !== false || record.provenance.independentEVMReexecution !== false || record.provenance.qualifiedClaims !== 0 || a.nativeExecution !== 'COMPLETED' || a.recordedVerify !== 'PASS') throw Error('Assurance boundary mismatch.');
  if (record.id === 'burn') {
    if (a.originalController !== 'COMPARE_STOP' || a.savedResultAcceptance !== 'PASS' || a.originalLabResultInstalled !== false || a.originalQuarantineRetained !== true || s?.schema !== 'rhook/saved-native-acceptance/0.1' || s.status !== 'SAVED_NATIVE_RECORDED_ACCEPTANCE_PASS' || s.originalOperation !== p.operationCommitment || s.nativeExecutionPerformedNow !== false || s.originalNativeExecutionPerformed !== true || s.recordVerificationPerformedNow !== true || s.controllerRecordRewritten !== false || s.quarantineUnchanged !== 1 || s.LabResultInstalled !== false || s.verifierSha256 !== record.provenance.workerSha256) throw Error('Auto Burn sidecar provenance mismatch.');
  } else if (a.originalController !== 'VERIFY_COMPARE_READ_FINAL_PASS' || a.savedResultAcceptance !== 'NOT_APPLICABLE' || a.originalLabResultInstalled !== true || s) throw Error('Controller acceptance mismatch.');
  return record;
}
export function comparison(record) {
  const [base, variant] = record.projection.worlds;
  return base.actions.slice(2).map((b, i) => {
    const v = variant.actions[i + 2];
    return {buy: i + 1, baseline: b.tokenTransferNetBaseUnits, variant: v.tokenTransferNetBaseUnits,
      delta: String(BigInt(v.tokenTransferNetBaseUnits) - BigInt(b.tokenTransferNetBaseUnits)), gasDelta: v.gasUsed - b.gasUsed};
  });
}
export function burnTotals(record) {
  if (!record.projection.tokenFlow) return null;
  return record.projection.tokenFlow.worlds.map(w => ({world: w.world,
    sentToDeadBaseUnits: String(w.buys.reduce((s, b) => s + BigInt(b.sentToDeadBaseUnits), 0n)),
    supplyDeltaBaseUnits: String(w.buys.reduce((s, b) => s + BigInt(b.supplyDeltaBaseUnits), 0n)),
    accruedProtocolClaimWei: String(w.buys.reduce((s, b) => s + BigInt(b.protocolClaimableDeltaWei), 0n))}));
}
export function createProvider(fetcher = fetch) {
  let manifest;
  async function bytes(name) {
    const response = await fetcher(new URL('./data/' + name, import.meta.url), {credentials: 'omit', cache: 'no-store'});
    if (!response.ok) throw Error('Public dataset unavailable: ' + name);
    const data = await response.arrayBuffer();
    if (data.byteLength > 100000) throw Error('Public dataset exceeds its byte limit.');
    return data;
  }
  async function init() {
    const data = await bytes('integrity.json');
    if (await sha256(data) !== INTEGRITY_SHA256) throw Error('Integrity manifest changed.');
    manifest = JSON.parse(new TextDecoder().decode(data));
    if (manifest.schema !== 'rhook/public-studio-integrity/0.1') throw Error('Unknown integrity manifest.');
  }
  async function load(name) {
    if (!manifest) throw Error('Initialize public provider first.');
    if (!['catalog.json', ...RECORD_IDS.map(id => id + '.json')].includes(name)) throw Error('Unknown public resource.');
    const data = await bytes(name);
    if (await sha256(data) !== manifest.files[name]) throw Error('Public dataset hash mismatch: ' + name);
    return JSON.parse(new TextDecoder().decode(data));
  }
  return {init, catalog: () => load('catalog.json'), async record(id) {
    if (!RECORD_IDS.includes(id)) throw Error('Unknown recorded configuration.');
    return validateRecord(await load(id + '.json'));
  }};
}
