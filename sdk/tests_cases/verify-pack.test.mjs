import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {promisify} from 'node:util';
import {headerHash, receiptBytes, trieRoot} from '../engine/plan_native/ethereum.mjs';
import {LIMITATIONS, chainContextFromPackage, renderText, sha256Hex, stableJson, verifyPack, verifyPackDirectory} from '../verify-pack/verify-pack.mjs';
import {SYNTHETIC_DIR, SYNTHETIC_PINS, buildSyntheticPack} from '../verify-pack/synthetic-pack.mjs';

const run = promisify(execFile);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SDK = path.resolve(HERE, '..');
const CLI = path.join(SDK, 'verify-pack/cli.mjs');
const fixture = await buildSyntheticPack();
const PINS = JSON.parse(fixture.pins);
const TRUSTED = fixture.trustedBlockHash;
const read = (files, name) => JSON.parse(files[name]);
const bytes = (value) => Buffer.from(stableJson(value));
const copy = () => Object.fromEntries(Object.entries(fixture.files).map(([n, b]) => [n, Buffer.from(b)]));
const verify = (files = copy(), pins = PINS, trustedBlockHash = TRUSTED) => verifyPack({files, pins, trustedBlockHash});

// Re-derive every value the recorded-world verifier recomputes, so a forged world stays self-consistent.
function reseal(record) {
  const r = record.result;
  r.receiptsRoot = trieRoot(r.receipts.map(receiptBytes));
  r.producedHeader.receiptsRoot = r.receiptsRoot;
  r.producedHeader.stateRoot = r.stateRoot;
  const hash = headerHash(r.producedHeader);
  r.producedHeader.hash = hash;
  r.blockHash = hash;
  for (const receipt of r.receipts) {
    receipt.blockHash = hash;
    for (const log of receipt.logs ?? []) log.blockHash = hash;
  }
  return record;
}

function buyerTransfer(record) {
  const plan = record.result.observation.plan;
  const receipt = record.result.receipts[plan.nativeOrdinal];
  return receipt.logs.find((l) => l.address === '0x3c022d43a9f826cd206c2ba60bc753d8b36185c4');
}

function assertFailed(report, level, code) {
  assert.equal(report.outcome, 'CHECK_FAILED');
  assert.equal(report.failure.level, level, JSON.stringify(report.failure));
  if (code) assert.equal(report.failure.code, code, JSON.stringify(report.failure));
  assert.equal(report.economics, null);
  assert.deepEqual(report.limitations, LIMITATIONS);
}

test('checked-in synthetic example is exactly what the generator produces', () => {
  for (const [name, b] of Object.entries(fixture.files)) assert.deepEqual(fs.readFileSync(path.join(SYNTHETIC_DIR, name)), b, name);
  assert.deepEqual(fs.readFileSync(SYNTHETIC_PINS), fixture.pins);
  assert.equal(read(fixture.files, 'CHAIN_CONTEXT.json').origin, 'SYNTHETIC_TEST_FIXTURE_NOT_CHAIN_DATA');
});

test('pinned and anchored synthetic pack passes only within the stated scope', async () => {
  const report = await verify();
  assert.equal(report.failure, null);
  assert.equal(report.outcome, 'CHECKS_PASSED_WITHIN_STATED_SCOPE');
  assert.equal(report.levels.artifactIntegrity.status, 'MATCH_EXTERNAL_PINS');
  assert.equal(report.levels.chainContext.status, 'BOUND_TO_TRUSTED_BLOCK');
  assert.equal(report.levels.canonicalActual.status, 'RECORDED_ACTUAL_MATCHES_TRUSTED_CANONICAL_BLOCK');
  assert.equal(report.levels.recordedBranch.status, 'RECORDED_BRANCH_INTERNALLY_CONSISTENT');
  assert.equal(report.levels.recordedBranch.claim, 'RHOOK_ENGINE_CLAIM_NOT_REEXECUTED');
  assert.equal(report.inputs['CHAIN_CONTEXT.json'].status, 'NOT_PINNED_BOUND_BY_TRUSTED_BLOCK_HASH');
  assert.deepEqual(report.limitations, {prestateAuthentication: 'NOT_PERFORMED', nativeReexecution: 'NOT_PERFORMED',
    heterogeneousAgreement: 'NOT_EVALUATED', economicAssurance: 'UNRESOLVED', qualifiedClaims: 0});
  assert.equal(report.reexecution, 'NONE');
  assert.equal(report.economics.actual.basis, 'CANONICAL_RECEIPTS_OF_TRUSTED_BLOCK');
  assert.equal(report.economics.branch.basis, 'RHOOK_ENGINE_RECORD_NOT_REEXECUTED');
  assert.equal(report.economics.buyerRhookTransferNetDeltaBaseUnits, (5000n * 10n ** 18n).toString());
  assert.equal(report.economics.buyerRhookTransferNetDeltaPercent, '+0.5000000000');
  assert.deepEqual([report.economics.actual.outerSwapFeePips, report.economics.branch.outerSwapFeePips], ['11000', '7000']);
  assert.deepEqual(report.case.intervention, {account: '0x2222222222222222222222222222222222222222', field: 'RulesConfig.lpBps',
    from: 100, pool: report.case.intervention.pool, slot: report.case.intervention.slot, to: 50});
});

test('the report never claims execution verification or a proof', async () => {
  const json = stableJson(await verify());
  assert.doesNotMatch(json, /"(?:status|outcome|claim)": "[A-Z_]*(?:VERIFIED|PROOF|PROVEN|CORRECT)[A-Z_]*"/);
  assert.doesNotMatch(json, /CRYPTOGRAPHIC_PROOF_VALID|EXECUTION_VERIFIED|"VERIFIED"/);
});

test('without pins or a trusted block hash every anchored status stays unanchored', async () => {
  const report = await verify(copy(), null, null);
  assert.equal(report.failure, null);
  assert.equal(report.levels.artifactIntegrity.status, 'NOT_ANCHORED_NO_EXTERNAL_PINS');
  assert.equal(report.anchor.status, 'UNANCHORED');
  assert.equal(report.levels.chainContext.status, 'BOUND_TO_PLAN_UNANCHORED');
  assert.equal(report.levels.canonicalActual.status, 'RECORDED_ACTUAL_CONSISTENT_UNANCHORED');
  assert.equal(report.economics.actual.basis, 'RECORDED_RECEIPTS_UNANCHORED');
  for (const name of Object.keys(report.inputs)) assert.equal(report.inputs[name].status, 'NOT_PINNED');
  assert.match(renderText(report), /Warning: without --trusted-block-hash/);
  assert.match(renderText(report), /Warning: without --pins/);
});

test('changing one byte in any pinned file fails artifact integrity', async () => {
  for (const name of ['ACTUAL.json', 'BRANCH.json', 'RUNTIME_PLAN.json']) {
    const files = copy();
    const at = files[name].indexOf('0x') + 5;
    files[name][at] = files[name][at] === 0x61 ? 0x62 : 0x61;
    assertFailed(await verify(files), 'artifactIntegrity', 'PINNED_HASH_MISMATCH');
  }
});

test('changing one byte anywhere in the chain context fails even though it is not pinned', async () => {
  const original = fixture.files['CHAIN_CONTEXT.json'];
  const positions = [];
  for (let i = original.indexOf('0x'); i !== -1; i = original.indexOf('0x', i + 2)) positions.push(i + 2);
  assert(positions.length > 40);
  for (const at of positions) {
    const files = copy();
    files['CHAIN_CONTEXT.json'][at] = files['CHAIN_CONTEXT.json'][at] === 0x61 ? 0x62 : 0x61;
    const report = await verify(files);
    assert.equal(report.outcome, 'CHECK_FAILED', `context byte ${at} was accepted`);
  }
});

test('a wrong external SHA-256 or malformed pins fail', async () => {
  const wrong = structuredClone(PINS);
  wrong.files['BRANCH.json'] = 'f'.repeat(64);
  assertFailed(await verify(copy(), wrong), 'artifactIntegrity', 'PINNED_HASH_MISMATCH');
  const partial = structuredClone(PINS);
  delete partial.files['ACTUAL.json'];
  assertFailed(await verify(copy(), partial), 'artifactIntegrity', 'PINS_SHAPE');
  const upper = structuredClone(PINS);
  upper.files['ACTUAL.json'] = upper.files['ACTUAL.json'].toUpperCase();
  assertFailed(await verify(copy(), upper), 'artifactIntegrity', 'PINS_SHAPE');
});

test('a wrong or malformed trusted block hash fails', async () => {
  assertFailed(await verify(copy(), PINS, '0x' + '1'.repeat(64)), 'chainContext', 'TRUSTED_BLOCK_HASH_MISMATCH');
  assertFailed(await verify(copy(), PINS, '0x1234'), 'chainContext', 'TRUSTED_BLOCK_HASH_FORMAT');
  const parentHash = read(fixture.files, 'CHAIN_CONTEXT.json').parent.hash;
  assertFailed(await verify(copy(), PINS, parentHash), 'chainContext', 'TRUSTED_BLOCK_HASH_MISMATCH');
});

test('substituted ACTUAL receipts fail against the canonical receipts root', async () => {
  const forged = read(fixture.files, 'ACTUAL.json');
  const log = buyerTransfer(forged);
  log.data = '0x' + (BigInt(log.data) * 2n).toString(16).padStart(64, '0');
  const files = copy();
  files['ACTUAL.json'] = bytes(reseal(forged));
  assertFailed(await verify(files, null), 'canonicalActual');

  const rootOnly = read(fixture.files, 'ACTUAL.json');
  rootOnly.result.receiptsRoot = '0x' + '4'.repeat(64);
  files['ACTUAL.json'] = bytes(rootOnly);
  assertFailed(await verify(files, null), 'canonicalActual');

  const status = read(fixture.files, 'ACTUAL.json');
  status.result.receipts[1].status = '0x0';
  files['ACTUAL.json'] = bytes(status);
  assertFailed(await verify(files, null), 'canonicalActual');
});

test('changing the plan or its intervention fails even without pins', async () => {
  const cases = [
    ['recordedBranch', null, (p) => { p.newValue = '49'; p.plan.intervention.newWord = p.plan.intervention.newWord.replace(/0032(?=0{40}$|[0-9a-f]{40}$)/, '0031'); }],
    ['profile', 'UNSUPPORTED_INTERVENTION', (p) => { p.newValue = '49'; }],
    ['profile', 'UNSUPPORTED_INTERVENTION', (p) => { p.plan.intervention.mask = '0x' + 'f'.repeat(64); }],
    ['profile', 'UNSUPPORTED_INTERVENTION', (p) => { p.plan.intervention.newWord = p.plan.intervention.newWord.replace(/.$/, (c) => (c === '0' ? '1' : '0')); }],
    ['chainContext', 'CHAIN_CONTEXT_MISMATCH', (p) => { p.plan.stateRoot = '0x' + '5'.repeat(64); }],
    ['chainContext', 'CHAIN_CONTEXT_MISMATCH', (p) => { p.plan.arrivals = [...p.plan.arrivals].reverse(); p.plan.subject = p.plan.arrivals[1]; p.plan.observation.subject = p.plan.subject; }],
    ['canonicalActual', null, (p) => { p.plan.inputCommitment = '6'.repeat(64); }],
  ];
  for (const [level, code, mutate] of cases) {
    const plan = read(fixture.files, 'RUNTIME_PLAN.json');
    mutate(plan);
    const files = copy();
    files['RUNTIME_PLAN.json'] = bytes(plan);
    assertFailed(await verify(files, null), level, code);
  }
});

test('incompatible profiles and incomplete packs fail before any record check', async () => {
  const mutateFile = async (name, mutate, level, code) => {
    const value = read(fixture.files, name);
    mutate(value);
    const files = copy();
    files[name] = bytes(value);
    assertFailed(await verify(files, null), level, code);
  };
  await mutateFile('RUNTIME_PLAN.json', (p) => { p.schema = 'rhook/hookr-runtime-plan/0.1'; }, 'profile', 'INCOMPATIBLE_PROFILE');
  await mutateFile('RUNTIME_PLAN.json', (p) => { p.plan.checkpoint.chainId = 1; p.plan.intervention.checkpoint.chainId = 1; }, 'profile', 'INCOMPATIBLE_PROFILE');
  await mutateFile('RUNTIME_PLAN.json', (p) => { p.plan.extra = true; }, 'profile', 'INCOMPATIBLE_PROFILE');
  await mutateFile('RUNTIME_PLAN.json', (p) => { p.plan.source = 'RPC'; }, 'profile', 'INCOMPATIBLE_PROFILE');
  await mutateFile('BRANCH.json', (b) => { delete b.result.patch; }, 'profile', 'INCOMPATIBLE_PROFILE');
  await mutateFile('CHAIN_CONTEXT.json', (c) => { c.schema = 'rhook/other/0.1'; }, 'chainContext', 'CHAIN_CONTEXT_SHAPE');
  await mutateFile('CHAIN_CONTEXT.json', (c) => { c.state = []; }, 'chainContext', 'CHAIN_CONTEXT_SHAPE');
  for (const name of ['ACTUAL.json', 'BRANCH.json', 'CHAIN_CONTEXT.json', 'RUNTIME_PLAN.json']) {
    const files = copy();
    delete files[name];
    assertFailed(await verify(files), 'artifactIntegrity', 'INCOMPLETE_PACK');
  }
  const duplicate = copy();
  duplicate['RUNTIME_PLAN.json'] = Buffer.from(duplicate['RUNTIME_PLAN.json'].toString().replace('{', '{"schema":"x",'));
  assertFailed(await verify(duplicate, null), 'artifactIntegrity', 'MALFORMED_JSON');
});

test('a self-consistent forged BRANCH passes only as recorded consistency, never as execution', async () => {
  const forged = read(fixture.files, 'BRANCH.json');
  const log = buyerTransfer(forged);
  log.data = '0x' + (BigInt(log.data) * 2n).toString(16).padStart(64, '0');
  forged.result.stateRoot = '0x' + '7'.repeat(64);
  const files = copy();
  files['BRANCH.json'] = bytes(reseal(forged));

  // Bound to the real block but not to any published result: the forgery is internally consistent.
  const report = await verify(files, null);
  assert.equal(report.outcome, 'CHECKS_PASSED_WITHIN_STATED_SCOPE');
  assert.equal(report.levels.recordedBranch.status, 'RECORDED_BRANCH_INTERNALLY_CONSISTENT');
  assert.equal(report.levels.recordedBranch.claim, 'RHOOK_ENGINE_CLAIM_NOT_REEXECUTED');
  assert.match(report.levels.recordedBranch.doesNotEstablish, /self-consistent forgery passes/);
  assert.equal(report.levels.artifactIntegrity.status, 'NOT_ANCHORED_NO_EXTERNAL_PINS');
  assert.equal(report.limitations.nativeReexecution, 'NOT_PERFORMED');
  assert.equal(report.economics.branch.basis, 'RHOOK_ENGINE_RECORD_NOT_REEXECUTED');
  assert.equal(report.economics.branch.buyerRhookTransferNetBaseUnits, (2_010_000n * 10n ** 18n).toString());

  // Against the published pins of the real result the same forgery is rejected.
  assertFailed(await verify(files, PINS), 'artifactIntegrity', 'PINNED_HASH_MISMATCH');
});

test('reports are deterministic and the CLI reports the same result', async () => {
  assert.equal(stableJson(await verify()), stableJson(await verify()));
  const args = ['verify', '--bundle', SYNTHETIC_DIR, '--pins', SYNTHETIC_PINS, '--trusted-block-hash', TRUSTED];
  const json = await run(process.execPath, [CLI, ...args, '--json']);
  assert.equal(json.stdout, stableJson(await verifyPackDirectory(SYNTHETIC_DIR, {pinsFile: SYNTHETIC_PINS, trustedBlockHash: TRUSTED})));
  const text = await run(process.execPath, [CLI, ...args]);
  assert.match(text.stdout, /B {2}Canonical ACTUAL {7}RECORDED_ACTUAL_MATCHES_TRUSTED_CANONICAL_BLOCK/);
  assert.match(text.stdout, /Delta .*\(\+0\.5000000000%\)/);
  assert.match(text.stdout, /Outcome: CHECKS_PASSED_WITHIN_STATED_SCOPE/);

  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'verify-pack-'));
  try {
    const out = path.join(directory, 'REPORT.json');
    await run(process.execPath, [CLI, ...args, '--report', out]);
    assert.equal(fs.readFileSync(out, 'utf8'), json.stdout);
    await assert.rejects(run(process.execPath, [CLI, ...args, '--report', out]), (e) => e.code === 2);
    await assert.rejects(run(process.execPath, [CLI, ...args.slice(0, 5), '--trusted-block-hash', '0x' + '1'.repeat(64)]),
      (e) => e.code === 1 && /TRUSTED_BLOCK_HASH_MISMATCH/.test(e.stdout));
    await assert.rejects(run(process.execPath, [CLI, 'verify']), (e) => e.code === 2);
  } finally {
    fs.rmSync(directory, {recursive: true, force: true});
  }
});

test('hash lists shipped inside a pack are reported as ignored, never used as pins', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'verify-pack-'));
  try {
    for (const [name, b] of Object.entries(fixture.files)) fs.writeFileSync(path.join(directory, name), b);
    fs.writeFileSync(path.join(directory, 'PINS.json'), fixture.pins);
    const report = await verifyPackDirectory(directory, {trustedBlockHash: TRUSTED});
    assert.deepEqual(report.ignoredFiles, ['PINS.json']);
    assert.equal(report.levels.artifactIntegrity.status, 'NOT_ANCHORED_NO_EXTERNAL_PINS');
    assert.equal(report.pins, null);
  } finally {
    fs.rmSync(directory, {recursive: true, force: true});
  }
});

test('pack directories reject symlinked files', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'verify-pack-'));
  try {
    for (const [name, b] of Object.entries(fixture.files)) fs.writeFileSync(path.join(directory, name), b);
    fs.rmSync(path.join(directory, 'BRANCH.json'));
    fs.symlinkSync(path.join(SYNTHETIC_DIR, 'BRANCH.json'), path.join(directory, 'BRANCH.json'));
    await assert.rejects(verifyPackDirectory(directory), /PACK_FILE_TYPE/);
  } finally {
    fs.rmSync(directory, {recursive: true, force: true});
  }
});

test('make-context refuses a package that does not match the plan', async () => {
  await assert.rejects(chainContextFromPackage(Buffer.from('{}'), fixture.files['RUNTIME_PLAN.json']), /PACKAGE_SHA256/);
});

test('README quick start uses the synthetic fixture block hash', () => {
  const readme = fs.readFileSync(path.join(SDK, 'verify-pack/README.md'), 'utf8');
  assert(readme.includes(`--trusted-block-hash ${TRUSTED}`));
  assert(readme.includes(`(${TRUSTED.slice(0, 10)}…${TRUSTED.slice(-6)})`));
});

test('published Pair03 pins are the hashes printed in the case study', () => {
  const pins = JSON.parse(fs.readFileSync(path.join(SDK, 'verify-pack/pins/hookr-pair03-lp50.json')));
  const study = fs.readFileSync(path.join(SDK, '../docs/research/hookr-pair03-100-to-50.md'), 'utf8');
  assert.deepEqual(Object.keys(pins.files).sort(), ['ACTUAL.json', 'BRANCH.json', 'RUNTIME_PLAN.json']);
  for (const [name, pin] of Object.entries(pins.files)) assert(study.includes('`' + pin + '`'), `${name} pin is not in the case study`);
  assert(study.includes('`0xc73ef372869ad5bf2a664bc1bc4cbe411c3adeb1938f349dd7686d82425398cd`'));
});

// Optional acceptance against the real recorded Pair03 LP50 pack. The pack is not in Git;
// set RHOOK_VERIFY_PACK_REAL_BUNDLE to a directory holding its four files to run it.
const REAL = process.env.RHOOK_VERIFY_PACK_REAL_BUNDLE;
test('real Pair03 LP100->50 pack against published pins and the canonical block', {skip: !REAL && 'RHOOK_VERIFY_PACK_REAL_BUNDLE not set'}, async () => {
  const report = await verifyPackDirectory(REAL, {pinsFile: path.join(SDK, 'verify-pack/pins/hookr-pair03-lp50.json'),
    trustedBlockHash: '0xc73ef372869ad5bf2a664bc1bc4cbe411c3adeb1938f349dd7686d82425398cd'});
  assert.equal(report.failure, null, JSON.stringify(report.failure));
  assert.equal(report.levels.artifactIntegrity.status, 'MATCH_EXTERNAL_PINS');
  assert.equal(report.levels.canonicalActual.status, 'RECORDED_ACTUAL_MATCHES_TRUSTED_CANONICAL_BLOCK');
  assert.equal(report.levels.canonicalActual.receiptsRecomputed, 7);
  assert.equal(report.economics.actual.buyerRhookTransferNetBaseUnits, '291469365928126821002944');
  assert.equal(report.economics.branch.buyerRhookTransferNetBaseUnits, '292938400920971228766928');
  assert.equal(report.economics.buyerRhookTransferNetDeltaPercent, '+0.5040100829');
  assert.equal(sha256Hex(fs.readFileSync(path.join(REAL, 'RUNTIME_PLAN.json'))), 'd54448edc0cff6786f2b00281e4d2e83dc02af83b2bf163426c88bbcc659f110');
});
