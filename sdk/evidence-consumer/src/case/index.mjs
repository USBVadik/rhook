// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import {fail, freeze, need} from '../codec.mjs';
import {blockHash, evidenceRef, localRoot, parseEvidence, readPinned} from './evidence.mjs';
import {eth, pair03, tx70} from './projections.mjs';
import {verifyEthereum, verifyPair} from './verifiers.mjs';

const pins = freeze(parseEvidence(fs.readFileSync(new URL('./pins.json', import.meta.url))));

const pairId = 'hookr-pair03-lp50';
const ethereumId = 'ethereum-tx70-x3';
const cases = Object.freeze({
  [pairId]: {chainId: 4663, profile: 'rhook/hookr-runtime-plan/0.2', pins: pins.pair03, project: pair03},
  [ethereumId]: {chainId: 1, profile: 'rhook/ethereum-actual-capsule/0.1', pins: pins.tx70, project: tx70},
});

function check(name, status, basis, scope, evidence = []) {
  return {name, status, basis, scope, evidence};
}

const recorded = (name, scope, evidence) => check(name, 'PASS', 'RECORDED_ASSERTION', scope, evidence);
const recomputed = (name, scope, evidence) => check(name, 'PASS', 'RECOMPUTED_FROM_BYTES', scope, evidence);
const unresolved = (name, scope) => check(name, 'UNRESOLVED', null, scope);

function dimensions(isPair, projection, details) {
  const pairVerdict = details.verifyPack;
  const chainVerdict = details.portableChain;
  const observation = isPair ? ['PAIR03_VERIFIER_REPORT.json'] : [eth.branch];
  const recordedAnc = isPair
    ? [recorded('priorTrustedTargetBinding', 'Prior verification against a separately trusted target hash', observation),
      unresolved('canonicalFinality', 'An external Robinhood block hash does not establish L1 finality')]
    : [projection.recorded.portableChainTerminal
      ? recorded('priorPortableChain', projection.recorded.portableChainTerminal, [eth.recorded])
      : unresolved('priorPortableChain', 'No retained portable chain receipt supplied')];
  if (pairVerdict?.status === 'PASS') recordedAnc.push(
    recomputed('trustedTargetBinding', 'Target hash, Nitro arrivals and parent header linkage', ['CHAIN_CONTEXT.json']));
  if (chainVerdict) {
    recordedAnc.push(chainVerdict.status === 'PASS'
      ? recomputed('portableChain', 'Weak-subjectivity checkpoint → beacon → SSZ payload → EL ancestry → capsule',
        [eth.ssz, eth.el, eth.capsule])
      : check('portableChain', chainVerdict.status, null, chainVerdict.reason ?? chainVerdict.terminal));
  } else if (!isPair) {
    recordedAnc.push(unresolved('portableChain', 'Full chain not checked by this invocation'));
  }

  const actual = [recorded('actualReplay', isPair ? 'Historical execution at the pinned Nitro block' :
    'Historical full-block ACTUAL execution and retained receipt/state controls', observation)];
  const branch = [recorded('branchReplay', isPair ? 'Prior LP50 execution within the case profile' :
    'Prior tx70 execution and dependency closure within this capsule', observation),
  unresolved('independentNativeReplay', 'The common consumer has no EVM execution route')];
  if (pairVerdict?.status === 'PASS') {
    actual.push(recomputed('recordedActualReceipts', 'Seven receipts and covered roots match the trusted block', ['ACTUAL.json']));
    branch.push(recomputed('recordedBranchIntegrity', 'Recorded receipts, bloom, gas and header consistency', ['BRANCH.json']));
  }

  return [
    {id: 'originalStateAuthentication', checks: isPair
      ? [unresolved('prestateWitness', 'The four-file pack has no prestate witness')]
      : [recorded('authenticatedP2PAcquisition', 'Previously checked against the declared parent state root', [eth.discovery, eth.capsule]),
        unresolved('consumerStateProofCheck', 'The common consumer does not rerun witness authentication')]},
    {id: 'consensusAnchoring', checks: recordedAnc},
    {id: 'actualExecutionAgreement', checks: actual},
    {id: 'branchReproducibility', checks: branch},
    {id: 'interventionSemantics', checks: [recorded('scopedIntervention', isPair
      ? 'LP BPS change and resulting Transfer-event observations'
      : 'Derived Message.Data amountIn change and recorded pool consumption', observation)]},
    {id: 'heterogeneousAgreement', checks: isPair
      ? [recorded('lp50GoRustAgreement', projection.recorded.heterogeneous.fields, ['PAIR03_CROSS_ENGINE.json'])]
      : [unresolved('heterogeneousReplay', 'No second engine execution retained for tx70')]},
    {id: 'verificationProvenance', checks: [
      recomputed('pinnedRecordIdentity', 'Case-specific SHA-256, size and role/subject links checked'),
      unresolved('nativeReplayPerformed', 'Execution results are prior recorded assertions')]},
    {id: 'policyAcceptance', checks: [unresolved('consumerPolicy', 'No policy applied yet')]},
  ];
}

const policies = new Set(['recorded-review', 'ethereum-consensus', 'independent-native-replay']);
const availableChecks = new Set(['pair03-recorded-integrity', 'ethereum-consensus', 'independent-native-replay']);

export function openCase({id, input, chainId, profile} = {}) {
  const chosen = Object.hasOwn(cases, id) ? cases[id] : null;
  need(chosen, 'CASE_NOT_SUPPORTED');
  need((chainId === undefined || chainId === chosen.chainId) &&
    (profile === undefined || profile === chosen.profile), 'CASE_IDENTITY_MISMATCH');
  const isPair = id === pairId;
  const root = localRoot(input);
  const pinFor = name => {
    need(typeof name === 'string' && Object.hasOwn(chosen.pins, name), 'EVIDENCE_REF_UNKNOWN');
    return chosen.pins[name];
  };
  const read = name => readPinned(root, name, pinFor(name));
  const projected = freeze(chosen.project(read, chosen.pins));
  const checkedReports = new WeakSet();
  const {comparison, ...caseFields} = projected;
  const capabilityChecks = [isPair ? 'pair03-recorded-integrity' : 'ethereum-consensus'];
  const summary = freeze({id, chainId: chosen.chainId, profile: chosen.profile, ...caseFields,
    capabilities: {acquisition: false, execution: false, verification: capabilityChecks},
    evidence: Object.entries(chosen.pins).map(([name, pin]) => evidenceRef(name, pin))});

  function inspect() { return summary; }

  function compare(projection = 'subject') {
    need(projection === 'subject', 'PROJECTION_NOT_SUPPORTED');
    return comparison;
  }

  function resolveEvidence(name) {
    const ref = evidenceRef(name, pinFor(name));
    return {ref, bytes: read(name)};
  }

  async function verify({checks = [], trustedBlockHash, trustedCheckpoint, verifyPackRoot, ethereumVerifierRoot} = {}) {
    need(Array.isArray(checks) && new Set(checks).size === checks.length && checks.every(name => availableChecks.has(name)),
      'CHECK_NOT_SUPPORTED');
    need((trustedBlockHash === undefined || typeof trustedBlockHash === 'string' && blockHash.test(trustedBlockHash)) &&
      (trustedCheckpoint === undefined || typeof trustedCheckpoint === 'string' && blockHash.test(trustedCheckpoint)), 'TRUST_ANCHOR_FORMAT');
    const details = {};
    if (checks.includes('pair03-recorded-integrity')) {
      details.verifyPack = isPair
        ? await verifyPair({read, verifyPackRoot, trustedBlockHash, pins: pins.verifyPack, projection: projected})
        : {status: 'UNSUPPORTED', reason: 'NITRO_VERIFY_PACK_PROFILE_REQUIRED'};
    }
    if (checks.includes('ethereum-consensus')) {
      details.portableChain = isPair
        ? {status: 'UNSUPPORTED', reason: 'ETHEREUM_PROFILE_REQUIRED'}
        : await verifyEthereum({read, trustedCheckpoint, pins: chosen.pins, projection: projected,
          linuxPins: pins.ethereumLinuxAmd64, verifierRoot: ethereumVerifierRoot});
    }
    if (checks.includes('independent-native-replay')) {
      details.nativeReplay = {status: 'UNSUPPORTED', reason: 'FRESH_NATIVE_EXECUTION_OUT_OF_SCOPE'};
    }
    const result = freeze({caseId: id, nativeReplayPerformed: false, details,
      dimensions: dimensions(isPair, projected, details)});
    checkedReports.add(result);
    return result;
  }

  function evaluatePolicy(policy, result) {
    need(policies.has(policy), 'POLICY_NOT_SUPPORTED');
    need(checkedReports.has(result), 'CHECK_RESULT_NOT_ADMITTED');
    let verdict = 'UNRESOLVED';
    let reason;
    if (Object.values(result.details).some(entry => entry.status === 'FAIL')) {
      verdict = 'REJECTED';
      reason = 'REQUESTED_VERIFICATION_FAILED';
    } else if (policy === 'recorded-review') {
      verdict = 'ACCEPTED';
      reason = 'PINNED_RECORDS_AND_CASE_IDENTITY_WITH_RECORDED_ASSERTIONS_EXPLICITLY_ALLOWED';
    } else if (policy === 'ethereum-consensus') {
      verdict = !isPair && result.details.portableChain?.status === 'PASS' ? 'ACCEPTED' : 'UNRESOLVED';
      reason = verdict === 'ACCEPTED' ? 'CURRENT_OFFLINE_CHAIN_VERIFIED_AGAINST_EXTERNAL_CHECKPOINT' :
        result.details.portableChain?.reason ?? 'FULL_ETHEREUM_CHAIN_VERIFICATION_REQUIRED';
    } else {
      reason = 'FRESH_NATIVE_EXECUTION_REQUIRED';
    }
    return freeze({policy, verdict, reason});
  }

  return Object.freeze({inspect, compare, resolveEvidence, verify, evaluatePolicy});
}

export function checkPolicyName(policy) {
  if (!policies.has(policy)) fail('POLICY_NOT_SUPPORTED');
}
