import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs';
import { planCase, runtimeDocument, readBoundedJson } from '../../adapters/hookr-case/runtime.ts';
import { canonical } from '../../adapters/hookr-case/primitives.mjs';
import { verifyRecorded, readRawJournal } from '../verify.mjs';
const roots = [process.env.RHOOK_FIXTURE_0, process.env.RHOOK_FIXTURE_50];
for (const [index, value] of ['0', '50'].entries())
    test('retained ' + value + ' receipts verify without claiming new execution', async () => {
        const root = roots[index];
        assert(root, 'Explicit fixture required');
        const pkg = readBoundedJson(path.join(root, 'inputs/BLOCK_PACKAGE.json'), 2 << 20).raw;
        const runtime = Buffer.from(canonical(runtimeDocument(pkg, planCase(pkg, { expectedOld: '100', newValue: value }))) + '\n');
        const records = { actual: readBoundedJson(path.join(root, 'runtime/ACTUAL.json'), 32 << 20).value, branch: readBoundedJson(path.join(root, 'runtime/BRANCH.json'), 32 << 20).value };
        const result = await verifyRecorded(pkg, runtime, records);
        assert.equal(result.status, 'RECORDED_INTEGRITY_PASS');
        assert.equal(result.mode, 'RECORDED_VERIFICATION');
        assert.equal(result.worlds.ACTUAL.buyerRhookTransferNetBaseUnits, '291469365928126821002944');
        assert.equal(result.worlds.BRANCH.buyerRhookTransferNetBaseUnits, index ? '292938400920971228766928' : '294409762269997223561475');
        assert.equal(result.worlds.BRANCH.outerSwap.feePips, index ? '7048' : '3048');
        assert.equal(result.worlds.BRANCH.subjectGasUsed, index ? '1483206' : '1480996');
        const wrong = Buffer.from(canonical(runtimeDocument(pkg, planCase(pkg, { expectedOld: '100', newValue: index ? '0' : '50' }))) + '\n');
        await assert.rejects(verifyRecorded(pkg, wrong, records));
        const changed = structuredClone(records);
        changed.actual.result.receipts[3].gasUsed = '0x1';
        await assert.rejects(verifyRecorded(pkg, runtime, changed));
    });
import os from 'node:os';
test('journal rejects malformed UTF8 without repairing raw bytes', () => {
    const root = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'bad-journal-'));
    try {
        const file = path.join(root, 'JOURNAL.jsonl');
        fs.writeFileSync(file, Buffer.concat([Buffer.from('{"sequence":0,"previousSha256":"","utc":"'), Buffer.from([255]), Buffer.from('","event":"ignored","data":{}}\n')]));
        assert.throws(() => readRawJournal(file));
    }
    finally {
        fs.rmSync(root, { recursive: true });
    }
});
