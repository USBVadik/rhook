// Authenticates recorded data; never launches or emulates an EVM.
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { validateRuntime, readBoundedJson } from '../adapters/hookr-case/runtime.ts';
import { canonical, commitment } from '../adapters/hookr-case/primitives.mjs';
import { authenticatePackage, verifyPair } from '../plan_native/verify.mjs';
const sha = raw => createHash('sha256').update(raw).digest('hex');
export async function verifyRecorded(packageBytes, runtimeBytes, records) {
    const runtime = validateRuntime(packageBytes, runtimeBytes);
    assert.equal(Buffer.from(runtimeBytes).toString('utf8'), canonical(runtime) + '\n', 'RUNTIME_ENCODING');
    const pkg = await authenticatePackage(packageBytes, runtime.plan);
    return { ...verifyPair(records.actual, records.branch, runtime.plan, pkg), status: 'RECORDED_INTEGRITY_PASS', mode: 'RECORDED_VERIFICATION', semanticPlanCommitment: runtime.semanticPlanCommitment, runtimePlanSha256: sha(runtimeBytes) };
}
export function verifyLinks(root, runtimeBytes) {
    const read = (relative, max = 32 << 20) => readBoundedJson(path.join(root, relative), max, true);
    const b = read('proposal/AUTHORIZATION_BINDINGS.json', 65536).value;
    let body = { ...b };
    delete body.operationCommitment;
    assert.equal(b.operationCommitment, commitment('rhook/hookr-operation/0.2', body));
    delete body.requestCommitment;
    assert.equal(b.requestCommitment, commitment('rhook/native-plan-request/0.2', body));
    const a = read('runtime/AUTHORITY.json', 16383), start = read('runtime/STARTED.json', 16384).value;
    assert.deepEqual(a.value, { ...b, founderApproved: true, macOnPowerOpenLid: true, noRetry: true, notBeforeUnix: a.value.notBeforeUnix, expiresUnix: a.value.expiresUnix });
    assert.equal(b.domain, 'HOOKR_UNIFIED_PLAN_NATIVE_0_1');
    assert.equal(b.profile, 'hookr-case-darwin-arm64/0.1');
    assert.deepEqual(b.maximumInvocations, { ACTUAL: 1, BRANCH: 1, B: 0 });
    assert.equal(b.RPC, 0);
    assert.equal(b.WSS, 0);
    assert.equal(b.runtimePlanSha256, sha(runtimeBytes));
    assert.equal(start.authoritySha256, sha(a.raw));
    assert.equal(start.operationCommitment, b.operationCommitment);
    assert(Number.isInteger(a.value.notBeforeUnix) && Number.isInteger(a.value.expiresUnix));
    const began = Date.parse(start.utc) / 1000;
    assert(began >= a.value.notBeforeUnix && began < a.value.expiresUnix && a.value.expiresUnix - a.value.notBeforeUnix <= 600);
    const native = read('runtime/NATIVE_COMPLETION.json').value;
    assert.equal(native.operationCommitment, b.operationCommitment);
    assert.equal(native.runtimePlanSha256, b.runtimePlanSha256);
    assert.equal(native.result.terminal, 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED');
    assert.equal(native.result.canonicalActualValid, true);
    assert.deepEqual(native.result.nativeInvocations, { ACTUAL: 1, BRANCH: 1, B: 0 });
    const journal = readRawJournal(path.join(root, 'runtime/JOURNAL.jsonl'));
    assert.deepEqual(journal.map(r => r.event), ['ACTUAL_ENTERED', 'CANONICAL_ACTUAL_MATCH', 'BRANCH_ENTERED', 'PAIR_OBSERVED_UNQUALIFIED']);
    assert.deepEqual(journal[0].data, { ACTUAL: 1, BRANCH: 0, B: 0 });
    assert.deepEqual(journal[2].data, { ACTUAL: 1, BRANCH: 1, B: 0 });
    assert.deepEqual(journal[3].data, native.result);
    const resources = read('runtime/PROCESS_COMPLETION.json').value;
    assert.equal(resources.workerReaped, true);
    assert.equal(resources.exitCode, 0);
    assert.equal(resources.stop, null);
    assert.equal(resources.resourcesReliable, true);
    assert(resources.wallSeconds <= 120 && resources.workerAndObserverCpuSeconds <= 120 && resources.sampledPeakWorkerRSS <= 1073741824);
    const comparison = read('runtime/COMPARISON.json').value;
    for (const prefix of ['actual', 'branch']) {
        const record = read('runtime/' + prefix.toUpperCase() + '.json').value.result;
        for (const field of ['StateRoot', 'GasUsed', 'Receipts', 'Observation'])
            assert.deepEqual(comparison[prefix + field], record[field[0].toLowerCase() + field.slice(1)]);
    }
    return b;
}
// Use the same descriptor opening discipline for a JSONL stream, then parse rows.
import fs from 'node:fs';
import { strictBytes } from '../adapters/hookr-case/runtime.ts';
export function readRawJournal(file) {
    file = path.resolve(file);
    for (let p = file;; p = path.dirname(p)) {
        assert(!fs.lstatSync(p).isSymbolicLink());
        if (p === path.dirname(p))
            break;
    }
    const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
    let raw;
    try {
        const st = fs.fstatSync(fd);
        assert(st.isFile() && st.size <= 1048576);
        const buf = Buffer.alloc(1048577);
        let n = 0, k;
        while ((k = fs.readSync(fd, buf, n, buf.length - n, null)) > 0)
            n += k;
        assert(n <= 1048576);
        raw = buf.subarray(0, n);
    }
    finally {
        fs.closeSync(fd);
    }
    assert(raw.length && raw.at(-1) === 10);
    let previous = '';
    const rows = [];
    let start = 0;
    for (let end = 0; end < raw.length; end++) {
        if (raw[end] !== 10)
            continue;
        const line = raw.subarray(start, end);
        const row = strictBytes(line);
        assert.equal(row.sequence, rows.length);
        assert.equal(row.previousSha256, previous);
        previous = sha(line);
        rows.push(row);
        start = end + 1;
    }
    return rows;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const [packagePath, runtimePath, root] = process.argv.slice(2);
    assert(root, 'USAGE: verify.mjs PACKAGE PLAN RUN');
    const pkg = readBoundedJson(packagePath, 2 << 20), runtime = readBoundedJson(runtimePath, 32768);
    const b = verifyLinks(root, runtime.raw);
    const records = { actual: readBoundedJson(path.join(root, 'runtime/ACTUAL.json'), 32 << 20).value, branch: readBoundedJson(path.join(root, 'runtime/BRANCH.json'), 32 << 20).value };
    const result = await verifyRecorded(pkg.raw, runtime.raw, records);
    assert.equal(result.semanticPlanCommitment, b.semanticPlanCommitment);
    assert.equal(sha(pkg.raw), b.packageSha256);
    console.log(JSON.stringify({ ...result, operationCommitment: b.operationCommitment }));
}
