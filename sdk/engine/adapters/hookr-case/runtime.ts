import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { inspect, plan } from './index.ts';
import { canonical, commitment } from './primitives.mjs';
import { parseStrictEvidenceJson } from './strict-json.mjs';
import { parseRecordedJson } from '../../case_sdk/json.mjs';
function requireValue(ok: unknown, code: string): asserts ok { if (!ok)
    throw new Error(code); }
export function strictBytes(raw: Uint8Array, allowFractions = false): any {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
    let depth = 0, quoted = false, escape = false;
    for (const c of text) {
        if (quoted) {
            if (escape)
                escape = false;
            else if (c === '\\')
                escape = true;
            else if (c === '"')
                quoted = false;
        }
        else if (c === '"')
            quoted = true;
        else if (c === '[' || c === '{') {
            requireValue(++depth <= 64, 'JSON_DEPTH');
        }
        else if (c === ']' || c === '}')
            depth--;
    }
    return allowFractions ? parseRecordedJson(text) : parseStrictEvidenceJson(text);
}
export function readBoundedJson(file: string, maximum: number, allowFractions = false): {
    raw: Buffer;
    value: any;
} {
    file = path.resolve(file);
    for (let p = file;; p = path.dirname(p)) {
        requireValue(!fs.lstatSync(p).isSymbolicLink(), 'INPUT_SYMLINK');
        if (p === path.dirname(p))
            break;
    }
    const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
    try {
        const st = fs.fstatSync(fd);
        requireValue(st.isFile() && st.size <= maximum, 'INPUT_TYPE_OR_SIZE');
        const raw = Buffer.alloc(maximum + 1);
        let used = 0;
        while (used < raw.length) {
            const n = fs.readSync(fd, raw, used, raw.length - used, null);
            if (!n)
                break;
            used += n;
        }
        requireValue(used <= maximum, 'INPUT_SIZE');
        const bytes = raw.subarray(0, used);
        return { raw: bytes, value: strictBytes(bytes, allowFractions) };
    }
    finally {
        fs.closeSync(fd);
    }
}
const descriptorFile = fileURLToPath(new URL('../../case_sdk/case.json', import.meta.url));
const descriptor = readBoundedJson(descriptorFile, 32768);
const digest = (raw: Uint8Array) => createHash('sha256').update(raw).digest('hex');
export function inspectCase(input: Uint8Array) {
    const result = inspect(input);
    requireValue(result.caseId === descriptor.value.caseId, 'CASE_DESCRIPTOR');
    return { ...result, caseDescriptorSha256: digest(descriptor.raw), supportedRule: { ruleId: result.supportedRule.ruleId, minimum: '0', maximum: '99', noOpAllowed: false } };
}
export function planCase(input: Uint8Array, request: {
    expectedOld: string;
    newValue: string;
}) {
    requireValue(request && Object.keys(request).sort().join(',') === 'expectedOld,newValue', 'REQUEST_FIELDS');
    requireValue(typeof request.newValue === 'string' && /^(0|[1-9][0-9]?)$/.test(request.newValue), 'CASE_LP_RANGE');
    const old = plan(input, { caseId: descriptor.value.caseId, ruleId: descriptor.value.ruleId, ...request });
    const body = { schema: 'rhook/hookr-plan/0.2', caseId: old.caseId, caseDescriptorSha256: digest(descriptor.raw), packageSha256: old.packageSha256,
        ruleId: old.ruleId, expectedOld: old.expectedOld, newValue: old.newValue, intervention: old.intervention, status: 'PLANNED', branchResult: null, executionAuthorized: false, witnessClosure: 'NOT_EVALUATED' };
    return { ...body, planCommitment: commitment('rhook/hookr-plan/0.2', body) };
}
export function runtimeDocument(input: Uint8Array, semantic: any) {
    const expected = planCase(input, { expectedOld: semantic.expectedOld, newValue: semantic.newValue });
    requireValue(canonical(expected) === canonical(semantic), 'PLAN_MISMATCH');
    const runtime = structuredClone(descriptor.value.plan);
    runtime.intervention = expected.intervention;
    return { schema: 'rhook/hookr-runtime-plan/0.2', caseDescriptorSha256: digest(descriptor.raw), semanticPlanCommitment: expected.planCommitment, newValue: expected.newValue, plan: runtime };
}
export function validateRuntime(input: Uint8Array, raw: Uint8Array) {
    requireValue(raw.byteLength <= 32768, 'RUNTIME_SIZE');
    const value = strictBytes(raw);
    const expected = runtimeDocument(input, planCase(input, { expectedOld: '100', newValue: value.newValue }));
    requireValue(canonical(expected) === canonical(value), 'RUNTIME_MISMATCH');
    return expected;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const [action, file, value] = process.argv.slice(2);
    const raw = readBoundedJson(file, 2 << 20).raw;
    if (action === 'inspect')
        console.log(JSON.stringify(inspectCase(raw)));
    else if (action === 'plan')
        console.log(JSON.stringify(planCase(raw, { expectedOld: '100', newValue: value })));
    else
        throw new Error('UNKNOWN_COMMAND');
}
