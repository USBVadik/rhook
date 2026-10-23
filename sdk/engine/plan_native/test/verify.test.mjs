// Saved results are data fixtures. No native execution occurs in these tests.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {test} from 'node:test';
import {readJson, authenticatePackage, verifyWorld, verifyPair, economics} from '../verify.mjs';
import {bloom, receiptBytes, trieRoot, headerHash} from '../ethereum.mjs';

const fixture = process.env.RHOOK_PAIR03_FIXTURE;
assert(fixture, 'Explicit retained fixture directory required');
const plan = readJson(new URL('../../repro/portable/plan.json', import.meta.url)).value;
const fifty = readJson(new URL('../plan.json', import.meta.url)).value;
const raw = readJson(fixture + '/inputs/BLOCK_PACKAGE.json').raw;
const pkg = await authenticatePackage(raw, plan);
const actual = readJson(fixture + '/runtime/ACTUAL.json').value;
const branch = readJson(fixture + '/runtime/BRANCH.json').value;
const clone = x => structuredClone(x);

test('legacy zero fixture validates without requiring it as a future branch baseline', () => {
  const result = verifyPair(actual, branch, plan, pkg);
  assert.equal(result.worlds.ACTUAL.buyerRhookTransferNetBaseUnits, '291469365928126821002944');
  assert.equal(result.worlds.BRANCH.buyerRhookTransferNetBaseUnits, '294409762269997223561475');
  assert.equal(result.worlds.ACTUAL.outerSwap.feePips, '11048');
  assert.equal(result.worlds.BRANCH.outerSwap.feePips, '3048');
});
test('old zero branch is not an admitted fifty result', () => {
  assert.throws(() => verifyPair(actual, branch, fifty, pkg));
});
for (const [label, change] of [
  ['checkpoint', p => p.checkpoint.blockNumber++],
  ['old word', p => p.intervention.expectedOldWord = '0x' + '00'.repeat(32)],
  ['arrivals', p => p.arrivals.reverse()],
  ['witness pin', p => p.witnessCommitment = '0'.repeat(64)],
  ['extra mutation', p => p.intervention.newWord = p.intervention.newWord.slice(0, -1) + '1'],
]) test('package rejects changed ' + label, async () => {
  const p = clone(plan); change(p); await assert.rejects(authenticatePackage(raw, p));
});
for (const field of ['state', 'codes']) test('actual loaded ' + field + ' bytes are authenticated, not names or counts', async () => {
  const changed = clone(pkg); changed[field][0] = '0x00';
  const bytes = Buffer.from(JSON.stringify(changed));
  const p = clone(plan); p.packageSha256 = createHash('sha256').update(bytes).digest('hex');
  await assert.rejects(authenticatePackage(bytes, p));
});
test('incomplete witness rejected even with a recomputed package hash', async () => {
  const changed = clone(pkg); changed.state.pop(); const bytes = Buffer.from(JSON.stringify(changed));
  const p = clone(plan); p.packageSha256 = createHash('sha256').update(bytes).digest('hex');
  await assert.rejects(authenticatePackage(bytes, p));
});
for (const [label, change] of [
  ['header state root', r => r.result.producedHeader.stateRoot = '0x' + '00'.repeat(32)],
  ['receipt gas', r => r.result.receipts[3].gasUsed = '0x1'],
  ['event data', r => r.result.receipts[3].logs[0].data = '0x'],
  ['receipt order', r => r.result.receipts.reverse()],
  ['missing state', r => r.missingLookupAttempts = [{kind: 'code'}]],
  ['incomplete calls', r => r.result.observation.complete = false],
  ['wrong initial state', r => r.result.observation.beforeFirstArrival.storage[0].value = plan.intervention.newWord],
  ['world name', r => r.result.world = 'BRANCH'],
  ['canonical match flag', r => r.result.matched = false],
  ['call-tree parent', r => r.result.observation.subjectCalls[1].parent = 2],
]) test('reject inconsistent recorded result: ' + label, () => {
  const record = clone(actual); change(record); assert.throws(() => verifyWorld(record, 'ACTUAL', plan, pkg));
});
test('reverted and unchanged economics remain observations, never forced improvements', () => {
  const fake = clone(actual.result); fake.receipts[3].logs = []; fake.receipts[3].status = '0x0';
  const e = economics(fake, plan);
  assert.equal(e.subjectStatus, 'REVERT'); assert.equal(e.buyerRhookTransferNetBaseUnits, '0');
  assert.equal(e.outerSwap, null); assert.equal(e.outerSwapStatus, 'NOT_APPLICABLE');
  assert.equal(e.economicAssurance, 'UNRESOLVED');
  assert.deepEqual(economics(actual.result, plan), economics(clone(actual.result), plan));
});
test('receipt encoding and header hashing are bound to original canonical data', () => {
  assert.equal(trieRoot(actual.result.receipts.map(receiptBytes)), plan.receiptsRoot);
  assert.equal(headerHash(actual.result.producedHeader), plan.blockHash);
  assert.equal(bloom(actual.result.receipts[3].logs), actual.result.receipts[3].logsBloom);
});
