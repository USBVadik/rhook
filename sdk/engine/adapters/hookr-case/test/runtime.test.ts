import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { planCase, runtimeDocument, readBoundedJson, validateRuntime } from '../runtime.ts';
const raw = fs.readFileSync(process.env.RHOOK_PACKAGE!);
test('runtime admission rejects a rehashed out-of-scope plan', () => {
    const p = planCase(raw, { expectedOld: '100', newValue: '50' });
    const runtime = runtimeDocument(raw, p);
    assert.equal(runtime.plan.intervention.newWord, '0x0000000007d0000000000032000000020000000000000000002cec0000000000');
    assert.deepEqual(validateRuntime(raw, Buffer.from(JSON.stringify(runtime))), runtime);
    const bad = structuredClone(runtime);
    bad.plan.intervention.slot = '0x00';
    assert.throws(() => validateRuntime(raw, Buffer.from(JSON.stringify(bad))));
    for (const n of ['100', '101', '-1', '00', '1e1', true])
        assert.throws(() => planCase(raw, { expectedOld: '100', newValue: n as string }));
});
test('descriptor reader rejects links, invalid UTF8 and deep JSON', () => {
    const root = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'case-reader-'));
    try {
        const p = path.join(root, 'input');
        fs.writeFileSync(p, '{}');
        assert.deepEqual(readBoundedJson(p, 2).value, {});
        assert.throws(() => readBoundedJson(p, 1));
        fs.symlinkSync(p, path.join(root, 'link'));
        assert.throws(() => readBoundedJson(path.join(root, 'link'), 20));
        for (const data of [Buffer.from([34, 255, 34]), Buffer.from('['.repeat(65) + '0' + ']'.repeat(65)), Buffer.from('{"x":1,"x":2}')]) {
            fs.writeFileSync(p, data);
            assert.throws(() => readBoundedJson(p, 1000));
        }
    }
    finally {
        fs.rmSync(root, { recursive: true });
    }
});
