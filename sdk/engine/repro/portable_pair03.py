#!/usr/bin/env python3
"""Portable, one-use Pair03 launcher. `prepare` never samples or runs history.

Authority is a trusted local workflow latch, not a cryptographic identity system.
The portable worker receives no provider and constructs the preserved nil Source.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portable_legacy_guards', REPO/'repro/portable/legacy_guards.py')
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)

RULES_CODE_HASH = '0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b'
LIMITS = {
    'pairWallSeconds': 120, 'workerKernelCpuSeconds': 120,
    'workerSampledRssBytes': 4 << 30, 'workerTelemetryMs': 100,
    'maximumTelemetryGapSeconds': 2, 'hostGateSeconds': 8,
    'ownedCleanupSeconds': 5, 'overallAfterConsumptionSeconds': 140,
    'stdoutStderrBytes': 64 << 20, 'perFileKernelBytes': 64 << 20,
    'sampledRuntimeBytes': 128 << 20, 'GOMAXPROCS': 2,
    'GOMEMLIMIT_advisoryBytes': 1 << 30,
    'memoryEnforcement': 'SAMPLED_NOT_HARD_RESERVATION_OR_EXACT_PEAK',
}


def require(ok, cause):
    if not ok: raise ValueError(cause)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def commitment(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def path_without_links(value):
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'ABSOLUTE_LOCAL_PATH_REQUIRED')
    require(all(not p.is_symlink() for p in [path, *path.parents]), 'SYMLINK_PATH_REJECTED')
    return path


def local_file(value, maximum=None):
    path = path_without_links(value)
    require(path.is_file(), 'LOCAL_INPUT_FILE_REQUIRED')
    if maximum is not None: require(path.stat().st_size <= maximum, 'INPUT_SIZE_LIMIT')
    return path


def fresh_output(value, inputs):
    path = path_without_links(value)
    require(not path.exists(), 'OUTPUT_ALREADY_USED')
    require(path.parent.is_dir(), 'OUTPUT_PARENT_REQUIRED')
    require(all(not p.is_relative_to(path) for p in map(Path, inputs)), 'OUTPUT_INPUT_OVERLAP')
    return path


def specification(repo):
    return json.loads((repo/'repro/portable/plan.json').read_text())


def validate_package(raw, p):
    require(len(raw) <= 32 << 20, 'PACKAGE_SIZE_LIMIT')
    require(hashlib.sha256(raw).hexdigest() == p['packageSha256'], 'PACKAGE_SHA256')
    x = json.loads(raw)
    cp = p['checkpoint']; block = x['block']; parent = x['parent']
    require(x['checkpoint'] == cp and cp['chainId'] == 4663, 'ORIGINAL_CHECKPOINT')
    require(int(parent['number'], 16) == cp['blockNumber'] and parent['hash'] == cp['blockHash']
            and parent['stateRoot'] == cp['stateRoot'], 'ORIGINAL_PARENT_HEADER')
    require(int(block['number'], 16) == p['blockNumber'] == 93251803
            and block['hash'] == p['blockHash'] and block['parentHash'] == cp['blockHash']
            and block['stateRoot'] == p['stateRoot'] and block['receiptsRoot'] == p['receiptsRoot'],
            'CANONICAL_BLOCK_IDENTITY')
    txs = block['transactions']
    require(len(txs) == len(x['rawTransactions']) == 7, 'ALL_SEVEN_ARRIVALS_REQUIRED')
    require([t['hash'] for t in txs] == p['arrivals'], 'ORIGINAL_ARRIVALS_ORDER')
    for i, t in enumerate(txs):
        require(int(t['transactionIndex'], 16) == i and int(t['chainId'], 16) == 4663
                and t['blockHash'] == p['blockHash'] and int(t['blockNumber'], 16) == p['blockNumber'],
                'ARRIVALS_METADATA')
    rules = p['intervention']; found = 0
    for proof in x['proofs']:
        if proof['address'].lower() != rules['account'].lower(): continue
        require(proof['proof']['codeHash'].lower() == RULES_CODE_HASH, 'RULES_CODE_HASH')
        for slot in proof['proof']['storageProof']:
            if int(slot['key'], 16) == int(rules['slot'], 16):
                require(int(slot['value'], 16) == int(rules['expectedOldWord'], 16), 'RULES_OLD_WORD')
                found += 1
    require(found > 0, 'RULES_SLOT_PROOF_REQUIRED')
    # SHA + structural validation here; unchanged Go admission checks MPT,
    # headers, raw transaction hashes and nil-Source original state before Run.
    return {'packageSha256': p['packageSha256'], 'transactions': 7, 'chainId': 4663,
            'blockNumber': 93251803, 'cryptographicStateAdmission': 'IN_WORKER_BEFORE_RUN'}


def function_text(path, name):
    text = path.read_text()
    return next(ast.get_source_segment(text, n) for n in ast.parse(text).body
                if isinstance(n, ast.FunctionDef) and n.name == name)


def verify_preserved(repo):
    lock = json.loads((repo/'repro/dependencies.lock.json').read_text())
    wanted = {x['path'] for x in lock['sourceFiles']}
    require({str(p.relative_to(repo)) for p in (repo/'native').rglob('*') if p.is_file()} == wanted,
            'NATIVE_SOURCE_SET_CHANGED')
    for x in lock['sourceFiles']:
        f = local_file(repo/x['path'])
        require(f.stat().st_size == x['bytes'] and sha(f) == x['sha256'], 'PRESERVED_ENGINE_CHANGED')
    pins = json.loads((repo/'repro/portable/guard-pins.json').read_text())
    for pin in pins:
        original = function_text(repo/pin['source'], pin['name'])
        copied = function_text(repo/'repro/portable/legacy_guards.py', pin['name'])
        require(original == copied and hashlib.sha256(copied.encode()).hexdigest() == pin['sha256'],
                'PRESERVED_GUARD_CHANGED')
    plan = json.loads((repo/'native/saved-pair/plan.json').read_text())
    plan.pop('packagePath')
    portable = specification(repo); portable.pop('arrivals')
    require(plan == portable and 'packagePath' not in portable, 'PORTABLE_PLAN_DRIFT')
    return {'nativeFiles': len(wanted), 'guardFunctions': len(pins)}


def source_closure(repo):
    result = {}
    for directory in ['native', 'supervisor', 'repro']:
        for p in sorted((repo/directory).rglob('*')):
            if '__pycache__' in p.parts: continue
            require(not p.is_symlink(), 'SOURCE_SYMLINK')
            if p.is_file(): result[str(p.relative_to(repo))] = sha(p)
    return result


def authority(raw, b, now):
    require(len(raw) < 16384, 'AUTHORITY_SIZE')
    a = json.loads(raw)
    require(a.get('founderApproved') is True and a.get('domain') == 'PORTABLE_SAVED_PAIR03',
            'FRESH_DIRECT_FOUNDER_AUTHORITY_REQUIRED')
    for key in ['operationCommitment', 'binarySha256', 'packagePath', 'outputPath', 'executionContext']:
        require(a.get(key) == b[key], 'EXACT_AUTHORITY_'+key)
    require(a.get('executionContext') == 'require_escalated', 'EXACT_EXECUTION_CONTEXT')
    require(a.get('maximumInvocations') == {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}
            and type(a.get('RPC')) is int and a['RPC'] == 0
            and type(a.get('WSS')) is int and a['WSS'] == 0, 'OFFLINE_ONE_PAIR_SCOPE')
    require(a.get('notBeforeUnix', now+1) <= now and a.get('expiresUnix', 0)-now >= 140
            and a['expiresUnix']-a['notBeforeUnix'] <= 600, 'AUTHORITY_WINDOW')
    require(a.get('macOnPowerOpenLid') is True and a.get('noRetry') is True, 'HOST_AND_NO_RETRY')
    return a


def verify_build(repo, binary, record_path):
    record_path = local_file(record_path, 2 << 20)
    result = json.loads(record_path.read_text())
    require(result['status'] == 'PORTABLE_ADAPTER_BUILD_ONLY_PASS'
            and result['nativeInvocations'] == {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}, 'PORTABLE_BUILD_RECORD_REQUIRED')
    require(os.access(binary, os.X_OK) and result['binarySha256'] == sha(binary), 'BUILD_BINARY_MISMATCH')
    require(result['sourceFiles'] == source_closure(repo)
            and result['planSha256'] == sha(repo/'repro/portable/plan.json'), 'BUILD_SOURCE_MISMATCH')
    return {'recordPath': str(record_path), 'recordSha256': sha(record_path),
            'binarySha256': result['binarySha256'], 'planSha256': result['planSha256']}


def prepare(repo, binary, package, output, node, proposal, build_record):
    require(not sys.flags.optimize, 'PYTHON_OPTIMIZATION_FORBIDDEN')
    preserved = verify_preserved(repo)
    binary = local_file(binary); package = local_file(package, 32 << 20); node = local_file(node)
    provenance = verify_build(repo, binary, build_record)
    output = fresh_output(output, [binary, package, node, repo])
    proposal = fresh_output(proposal, [binary, package, node, repo, output])
    admitted = validate_package(package.read_bytes(), specification(repo))
    b = {'format': 'rhook/portable-pair03/1', 'binaryPath': str(binary), 'binarySha256': sha(binary),
         'packagePath': str(package), 'packageSha256': admitted['packageSha256'],
         'outputPath': str(output), 'nodePath': str(node), 'nodeSha256': sha(node),
         'planSha256': sha(repo/'repro/portable/plan.json'), 'sourceFiles': source_closure(repo),
         'limits': LIMITS, 'executionContext': 'require_escalated',
         'maximumInvocations': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, 'RPC': 0, 'WSS': 0,
         'externalDelivery': 'HOLD', 'preserved': preserved, 'inputAdmission': admitted,
         'buildProvenance': provenance}
    b['operationCommitment'] = commitment(b)
    proposal.mkdir(mode=0o700)
    guards.store(proposal/'AUTHORIZATION_BINDINGS.json', b)
    template = {k: b[k] for k in ['operationCommitment', 'binarySha256', 'packagePath', 'outputPath',
                                  'executionContext', 'maximumInvocations', 'RPC', 'WSS']}
    template.update({'domain': 'PORTABLE_SAVED_PAIR03', 'founderApproved': False,
                     'notBeforeUnix': 0, 'expiresUnix': 0, 'macOnPowerOpenLid': False, 'noRetry': True})
    guards.store(proposal/'AUTHORIZATION_TEMPLATE_NOT_GRANTED.json', template)
    return b


def host_admission(repo, node, rt):
    guards.WS = repo
    capture, stdout, stderr = guards.capture(
        [str(node), str(repo/'supervisor/legacy-admission/tools/host_check.mjs')], rt/'HOST_SENSOR', 7)
    guards.store(rt/'HOST_RAW.json', {'nodeCapture': capture,
                 'stdoutFile': 'HOST_SENSOR/stdout.bin', 'stderrFile': 'HOST_SENSOR/stderr.bin'})
    decision = guards.evaluate(capture, stdout, stderr, guards.assess_host)
    accepted = decision['status'] == 'LEGACY_ADMISSION_PASS'
    guards.store(rt/'HOST_ADMISSION.json', {'accepted': accepted, 'recorded': decision})
    return accepted, decision


def result_projection(result):
    # Full receipts and economic observations, including unchanged values.
    return {k: result[k] for k in ['world', 'inputCommitment', 'witnessCommitment', 'stateRoot',
            'receiptsRoot', 'blockHash', 'transactions', 'gasUsed', 'receipts', 'observation']}


def compare_baseline(repo, rt):
    expected = json.loads((repo/'repro/portable/baseline.json').read_text())
    compared = {}
    for world in ['ACTUAL', 'BRANCH']:
        value = json.loads((rt/(world+'.json')).read_text())
        require(not value.get('error') and not value['missingLookupAttempts'], 'BASELINE_WORLD_ERROR')
        compared[world] = commitment(result_projection(value['result'])) == expected[world]['projectionSha256']
    return {'status': 'PASS' if all(compared.values()) else 'PAIR03_BASELINE_MISMATCH', 'worlds': compared,
            'comparison': 'Exact canonical roots/hash, all receipts, gas and full economic observation'}


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def consume_output(out):
    out.mkdir(mode=0o700)
    sync_directory(out.parent)
    rt = out/'runtime'; rt.mkdir()
    sync_directory(out)
    return rt


def reconcile_completion(final, measured, native):
    reliable = not measured['stop'] and measured['resourcesReliable'] and measured['workerReaped']
    result = native['result']
    # Exact native failures deliberately exit 1. Preserve their terminal,
    # partial canonical result and counts when the process was reliably reaped.
    expected_exit = 0 if result['terminal'] == 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED' else 1
    if reliable and measured['exitCode'] == expected_exit:
        final.update(result)
    else:
        final['cause'] = measured['stop'] or 'UNVERIFIED_PROCESS_COMPLETION'


def accept_native_completion(repo, rt, final, measured, native):
    reconcile_completion(final, measured, native)
    if final['terminal'] == 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED':
        # A worker success is provisional until the baseline comparison itself
        # completes. Missing/corrupt records must never leave a success marker.
        final['terminal'] = 'INTERRUPTED_UNVERIFIED'
        compared = compare_baseline(repo, rt)
        final['baselineComparison'] = compared
        final['terminal'] = ('GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED' if compared['status'] == 'PASS'
                             else 'PAIR03_BASELINE_MISMATCH')


def replay(repo, binding_path, authority_path, package_path, output_path):
    require(not sys.flags.optimize, 'PYTHON_OPTIMIZATION_FORBIDDEN')
    # Both required files are checked before even looking at sensors or workers.
    raw = local_file(authority_path, 16383).read_bytes()
    b = json.loads(local_file(binding_path, 2 << 20).read_text())
    base = dict(b); base.pop('operationCommitment')
    require(commitment(base) == b['operationCommitment'], 'BINDINGS_COMMITMENT')
    a = authority(raw, b, time.time())
    require(str(package_path) == b['packagePath'] and str(output_path) == b['outputPath'], 'EXPLICIT_IO_BINDINGS')
    require(b['limits'] == LIMITS, 'PINNED_RESOURCE_LIMITS')
    verify_preserved(repo)
    require(source_closure(repo) == b['sourceFiles'], 'SOURCE_CLOSURE_CHANGED')
    binary = local_file(b['binaryPath']); node = local_file(b['nodePath'])
    provenance = verify_build(repo, binary, b['buildProvenance']['recordPath'])
    require(provenance == b['buildProvenance'], 'BUILD_RECORD_CHANGED')
    require(sha(binary) == b['binarySha256'] and sha(node) == b['nodeSha256'], 'EXECUTABLE_SHA256')
    package = local_file(package_path, 32 << 20)
    validate_package(package.read_bytes(), specification(repo))
    out = fresh_output(output_path, [repo, binary, node, package])
    # Exclusive, durable consumption before one host check; any later failure
    # closes this authority. Output must never be removed to retry an operation.
    rt = consume_output(out)
    guards.store(rt/'STARTED.json', {'operationCommitment': b['operationCommitment'],
                 'authoritySha256': hashlib.sha256(raw).hexdigest(), 'utc': guards.utc(),
                 'automaticRetry': False, 'bothWorldsOriginalParent': True})
    with (rt/'AUTHORITY_RAW.json').open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    sync_directory(rt)
    final = {'operationCommitment': b['operationCommitment'], 'terminal': 'INTERRUPTED_UNVERIFIED',
             'externalDelivery': 'HOLD', 'economicAssurance': 'UNRESOLVED',
             'heterogeneousAgreement': 'NOT_EVALUATED', 'RPC': 0, 'WSS': 0,
             'automaticRetry': False, 'authorityPermanentlyClosed': True}
    began = time.monotonic()
    try:
        (out/'proposal').mkdir(); (out/'artifacts').mkdir()
        guards.store(out/'proposal/AUTHORIZATION_BINDINGS.json', b)
        shutil.copyfile(binary, out/'artifacts/rhook-saved-pair')
        (out/'artifacts/rhook-saved-pair').chmod(0o700)
        require(sha(out/'artifacts/rhook-saved-pair') == b['binarySha256'], 'COPIED_BINARY_SHA256')
        accepted, decision = host_admission(repo, node, rt)
        if not accepted:
            final.update({'terminal': 'HOST_STOP', 'hostDecision': decision,
                          'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}})
        else:
            require(time.monotonic()-began < 10 and time.time()+125 < a['expiresUnix'], 'ORIGINAL_AUTHORITY_DEADLINE')
            guards.ROOT = out
            measured = guards.monitored(raw, rt, LIMITS)
            final['resources'] = measured
            completion = rt/'NATIVE_COMPLETION.json'
            if completion.is_file():
                n = json.loads(completion.read_text())
                require(n['operationCommitment'] == b['operationCommitment'], 'NATIVE_OPERATION_LINK')
                final['native'] = n
                accept_native_completion(repo, rt, final, measured, n)
            else: final['cause'] = measured['stop'] or 'NATIVE_COMPLETION_MISSING'
    except BaseException as e:
        final['cause'] = type(e).__name__+': '+str(e)[:1024]
    final.update({'elapsedSeconds': time.monotonic()-began, 'utc': guards.utc()})
    guards.store(rt/'FINAL_RESULT.json', final)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare', help='Offline proposal only; no host or native execution')
    for name in ['binary', 'package', 'output', 'node', 'proposal', 'build-record']: p.add_argument('--'+name, required=True)
    p = sub.add_parser('replay', help='Requires separately founder-approved fresh one-use authority')
    for name in ['bindings', 'authority', 'package', 'output']: p.add_argument('--'+name, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        b = prepare(REPO, args.binary, args.package, args.output, args.node, args.proposal, args.build_record)
        print(json.dumps({'status': 'PREPARED_NOT_AUTHORIZED', 'operationCommitment': b['operationCommitment'],
                          'ACTUAL': 0, 'BRANCH': 0, 'RPC': 0, 'WSS': 0}))
    else:
        result = replay(REPO, args.bindings, args.authority, args.package, args.output)
        print(json.dumps(result))
        if result['terminal'] != 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED': sys.exit(1)


if __name__ == '__main__': main()
