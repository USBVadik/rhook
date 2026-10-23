import './no-network.mjs';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {inspect, plan, ruleId, type PlanRequest} from '../index.ts';
import {commitment} from '../primitives.mjs';
import {authenticateProof} from '../proof.mjs';

assert(process.env.RHOOK_PAIR03_PACKAGE, 'Set RHOOK_PAIR03_PACKAGE to the separately retained package');
const bytes = fs.readFileSync(process.env.RHOOK_PAIR03_PACKAGE);
const accepted = JSON.parse(fs.readFileSync(new URL('../../../repro/portable/plan.json', import.meta.url), 'utf8'));
const request = (newValue = '0'): PlanRequest => ({
  caseId: inspect(bytes).caseId, ruleId, expectedOld: '100', newValue,
});

test('inspect authenticates the known release and all sixteen config fields', () => {
  const x = inspect(bytes);
  assert.equal(x.generation, 'hookr-1');
  assert.equal(x.stateAuthenticity, 'ORIGINAL_ROOT_PROOFS_AND_CODE_MATCH');
  assert.equal(Object.keys(x.config).length, 16);
  assert.equal(x.config.lpBps, '100');
  assert.equal(x.config.maxFeePips, '11500');
  assert.equal(x.config.protocolShareBps, '2000');
  assert.equal(x.baseLpFeePips, '3000');
  assert.equal(x.caps.maxLpFeePips, '17800');
  assert.equal(x.historicalSwapBuilderCompatibility, 'NOT_ESTABLISHED');
  assert.equal(x.nativeExecution, 'NOT_RUN');
});

test('100to0 is exactly the accepted existing intervention', () => {
  const x = plan(bytes, request());
  assert.deepEqual(x.intervention, accepted.intervention);
  assert.equal(x.savedInterventionMatch, true);
  assert.equal(x.status, 'PLANNED_NOT_EXECUTED');
  assert.equal(x.executionAuthorized, false);
  assert.equal(x.branchResult, null);
});

test('100to50 changes only LP bits and does not invent a branch result', () => {
  const x = plan(bytes, request('50'));
  const mask = BigInt(accepted.intervention.mask);
  const next = BigInt(x.intervention.newWord), old = BigInt(x.intervention.expectedOldWord);
  assert.equal((next >> 160n) & 65535n, 50n);
  assert.equal((next ^ old) & ~mask, 0n);
  assert.equal(x.savedInterventionMatch, false);
  assert.equal(x.executionSupport, 'NEW_NATIVE_PLAN_REQUIRED');
  assert.equal(x.witnessClosure, 'NOT_EVALUATED');
  assert.equal(x.branchResult, null);
});

test('every supported changed value preserves every other bit', () => {
  const template = request();
  for (let n = 0; n < 100; n++) {
    const x = plan(bytes, {...template, newValue: String(n)});
    assert.equal((BigInt(x.intervention.newWord) ^ BigInt(x.intervention.expectedOldWord)) &
      ~BigInt(x.intervention.mask), 0n);
  }
});

test('plan commitment is deterministic and binds the requested value', () => {
  const a = plan(bytes, request('50')), b = plan(bytes, request('50'));
  assert.deepEqual(a, b);
  const {planCommitment, ...body} = a;
  assert.equal(planCommitment, commitment('rhook/hookr-plan/0.1', body));
  assert.notEqual(a.planCommitment, plan(bytes, request()).planCommitment);
});

test('mutating a returned inspection cannot influence a later plan', () => {
  const x = inspect(bytes);
  x.config.lpBps = '9';
  x.checkpoint.stateRoot = 'untrusted';
  assert.equal(plan(bytes, request('50')).intervention.expectedOldWord, accepted.intervention.expectedOldWord);
});

for (const value of ['-1', '101', '1000', '65535', '100', '01', '1.5', '0x32', '5e1', '', ' 50', '５０']) {
  test(`reject unsupported or noncanonical value ${JSON.stringify(value)}`, () => {
    assert.throws(() => plan(bytes, request(value)));
  });
}

test('numbers and booleans are not decimal-string inputs', () => {
  for (const value of [50, true, null])
    assert.throws(() => plan(bytes, {...request(), newValue: value} as unknown as PlanRequest));
});

test('stale expectedOld, other generation/rule/case and override fields are refused', () => {
  for (const change of [
    {expectedOld: '50'}, {caseId: 'unknown'}, {ruleId: 'hookr-0.2.lpBps'},
    {slot: '0x00'}, {rpcUrl: 'https://invalid.example'}, {command: 'replay'},
  ]) assert.throws(() => plan(bytes, {...request(), ...change}));
});

test('accessors and inherited request prototypes are refused without invoking getters', () => {
  const x = request();
  Object.defineProperty(x, 'newValue', {get() { throw new Error('GETTER_RAN'); }, enumerable: true});
  assert.throws(() => plan(bytes, x), /REQUEST_FIELDS/);
  assert.throws(() => plan(bytes, Object.create(request())), /REQUEST_OBJECT/);
});

test('tampered or other block packages cannot be inspected', () => {
  const x = JSON.parse(bytes.toString());
  x.parent.stateRoot = '0x' + '00'.repeat(32);
  assert.throws(() => inspect(Buffer.from(JSON.stringify(x))), /PACKAGE_SHA256/);
  assert.throws(() => inspect(Buffer.alloc(2 * 1024 * 1024 + 1)), /PACKAGE_INPUT_LIMIT/);
  assert.throws(() => inspect(Buffer.from('{}')), /PACKAGE_SHA256/);
});

test('network calls are forbidden throughout fixture tests', async () => {
  assert.throws(() => fetch('https://invalid.example'), /OFFLINE_TEST_NETWORK_FORBIDDEN/);
});

test('reused proof verification refuses a substituted parent root', () => {
  const packet = JSON.parse(bytes.toString());
  const row = packet.proofs[0];
  const keys = row.proof.storageProof.map((s: {key: string}) => s.key);
  assert.throws(() => authenticateProof('0x' + '00'.repeat(32), row.address, keys, row.proof));
});

test('reused proof verification refuses unauthenticated value metadata', () => {
  const packet = JSON.parse(bytes.toString());
  const row = packet.proofs[0];
  const keys = row.proof.storageProof.map((s: {key: string}) => s.key);
  row.proof.storageProof[0].value = '0x123';
  assert.throws(() => authenticateProof(packet.checkpoint.stateRoot, row.address, keys, row.proof));
});
