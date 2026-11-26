// SPDX-License-Identifier: Apache-2.0
// Documentation example: derive a portable inspection summary from the public recorded result.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {isDeepStrictEqual} from 'node:util';

const PUBLIC_COMMIT = '493dc5b7a7ab101a2cfcd0be40f13eaa326405a2';
const REFERENCE = {
  file: 'reference.json.gz', bytes: 140974,
  sha256: 'dc9dde06421d040024a59cf8c3e7fa803dfd1da6256871da74bd5950c91fdc21',
};
const CASE_DIRECTORY = 'examples/robinhood-v4';
const [checkout, output] = process.argv.slice(2);
assert(checkout && output && process.argv.length === 4, 'Usage: node project-public-reference.mjs PUBLIC_CHECKOUT OUTPUT.json');

const publicExample = resolve(checkout, CASE_DIRECTORY);
const {unpackVerified, verifyRecords} = await import(pathToFileURL(resolve(publicExample, 'scripts/artifacts.mjs')));
const reference = unpackVerified(readFileSync(resolve(publicExample, REFERENCE.file)), REFERENCE);
const actual = verifyRecords(reference.envelopes.ACTUAL, reference.expected.actualLifecycle);
const branch = verifyRecords(reference.envelopes.COUNTERFACTUAL, reference.expected.counterfactualLifecycle);
const location = envelope => envelope.blockNumber + ':' + envelope.transactionIndex;
const compareCoordinate = (a, b) => Number(a.blockNumber) - Number(b.blockNumber) ||
  Number(a.transactionIndex) - Number(b.transactionIndex);
const branches = new Map(branch.map(x => [location(x.body.envelope), x]));
assert.equal(branches.size, 321);
actual.sort((a, b) => compareCoordinate(a.body.envelope, b.body.envelope));
assert.equal(new Set(actual.map(x => location(x.body.envelope))).size, 321);

const change = reference.expected.intervention.body.canonicalEnvelopeIdentity;
assert.equal(reference.expected.blocks, 50);
assert.equal(location(change), '70397227:3');
const target = actual.findIndex(x => location(x.body.envelope) === location(change));
assert(target >= 0);
assert.equal(actual[target].body.envelope.transactionHash, change.transactionHash);

const rows = actual.map((record, index) => {
  const env = record.body.envelope;
  const other = branches.get(location(env));
  assert(other && isDeepStrictEqual(env, other.body.envelope), 'Unpaired envelope');
  const a = record.body.execution.lifecycle;
  const b = other.body.execution.lifecycle;
  return {
    ordinal: index, subject: {chainId: '4663', ...env},
    position: index < target ? 'PREFIX' : index === target ? 'TARGET' : 'DOWNSTREAM',
    classification: a === b ? 'UNCHANGED' : 'CHANGED', actual: a, branch: b,
  };
});
const selected = rows.find(row => location(row.subject) === '70397227:4');
assert(selected && selected.actual === 'SUCCESS' && selected.branch === 'REVERT');
assert.equal(rows.filter(row => row.classification === 'CHANGED').length, 16);

const hash = data => createHash('sha256').update(data).digest('hex');
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
}
const commit = (domain, body) => hash(canonical({domain, body}));
const provenance = {kind: 'PUBLIC_RECORDED_PROJECTION', commit: PUBLIC_COMMIT, referenceSha256: REFERENCE.sha256};
const worldId = commit('rhook/public-recorded-projection-world/0.2', provenance);
const branchContextId = commit('rhook/public-recorded-projection-context/0.2', {
  ...provenance, recordedInterventionCommitment: reference.expected.intervention.commitmentSha256,
});
const {subject} = selected;
const P = {kind: 'NATIVE_ENVELOPE_LIFECYCLE', phase: 'AFTER_SELECTED_ENVELOPE',
  referenceDomain: 'COMPLETE_DECLARED_50_BLOCK_DOMAIN', resultCodec: 'LIFECYCLE_JSON_STRING_3'};
const components = {H: provenance, R: {branchContextId}, C: {worldId}, I: {
  ...provenance, target: change, recordedInterventionCommitment: reference.expected.intervention.commitmentSha256,
}, subject, P, theta: {}};
const query = {format: 'rhook/branch-query/0.2', ...Object.fromEntries(Object.entries(components)
  .map(([k, value]) => [k + 'Commitment', commit('rhook/query-component/' + k + '/0.2', value)]))};
const projected = value => commit('rhook/projected-result/0.2', {
  projectionCommitment: query.PCommitment, subjectCommitment: query.subjectCommitment,
  parametersCommitment: query.thetaCommitment, value,
});
const claim = {format: 'rhook/branch-claim/0.2', queryCommitment: commit('rhook/branch-query/0.2', query),
  actualResultCommitment: projected(selected.actual), branchResultCommitment: projected(selected.branch)};
const envelope = {format: 'rhook/evidence-envelope/0.2', claimCommitment: commit('rhook/branch-claim/0.2', claim),
  verifierProfileCommitment: commit('rhook/public-recorded-projection-profile/0.2', 'DECLARED_NOT_ADMITTED'),
  payloadCommitment: commit('rhook/evidence-payload/0.2', null)};
const inspection = {worldId, branchContextId, scope: 'all', projection: 'lifecycle', authority: 'SDK_LOCAL_INSPECTION_ONLY',
  inventory: {total: rows.length, prefix: target, target: 1, downstream: rows.length - target - 1},
  rowCount: rows.length, rows, counts: {changed: 16, unchanged: 305, unresolved: 0}};
const body = {query, claim, envelope, disclosedComponents: {I: components.I, subject, P, theta: {}},
  selectedValues: {actual: selected.actual, branch: selected.branch}, inspection, reportedVerification: null, payload: null};
const packet = {format: 'rhook/portable-inspection-package/0.1', bodySha256: hash(canonical(body)), body};
writeFileSync(output, JSON.stringify(packet, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({source: provenance, subject: location(subject), actual: selected.actual, branch: selected.branch,
  recordedEnvelopeChecks: actual.length + branch.length, pairs: rows.length, lifecycleChanges: 16, nativeReplayPerformed: false}));
