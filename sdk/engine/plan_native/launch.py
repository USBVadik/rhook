"""Future one-shot launcher. No authority is issued by preparation or this module."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from .core import DOMAIN, HERE, PLAN_SHA, POLICY_SHA, REQUEST, SEMANTIC, canonical, inputs, read, require, sha, source_commitment, strict, verifier_dependencies
from .common import portable, store
from .resources import admission, RuntimeGuard
from sdk_alpha_v2.kit import sample_developer


def pins(source):
    return dict(sourceCommitment=source, profile='plan-native-darwin-arm64/0.1',
                semanticPlanCommitment=SEMANTIC, nativeRequestCommitment=REQUEST,
                policySha256=POLICY_SHA, runtimePlanSha256=PLAN_SHA)


def binding(build, package, output, sensor, node):
    plan, policy = inputs()
    source = source_commitment()
    require(build['status'] == 'BUILD_ONLY_PASS' and build['sourceCommitment'] == source, 'REVIEWED_BUILD_SOURCE_REQUIRED')
    require(build['runtimePlanSha256'] == PLAN_SHA and build['productionWorkerLaunched'] is False, 'BUILD_PLAN_OR_LAUNCH_RECORD')
    require(sha(read(package, 2 << 20)) == plan['packageSha256'], 'PACKAGE_PIN')
    body = dict(pins(source), domain=DOMAIN, binarySha256=build['binarySha256'], planSha256=PLAN_SHA,
                packageSha256=plan['packageSha256'], packagePath=str(Path(package).absolute()),
                outputPath=str(Path(output).absolute()), sensorPath=str(Path(sensor).absolute()),
                sensorSha256=sha(read(sensor, 2 << 20)), nodePath=str(Path(node).absolute()),
                nodeSha256=sha(read(node, 256 << 20)), resourcePolicy=policy, limits=portable.LIMITS,
                verifierDependenciesCommitment=sha(canonical(verifier_dependencies())),
                executionContext='require_escalated', maximumInvocations={'ACTUAL': 1, 'BRANCH': 1, 'B': 0},
                RPC=0, WSS=0, workflowSeconds=180, nativeStageSeconds=140, externalDelivery='HOLD')
    return dict(body, operationCommitment=sha(canonical(body)))


def authority(b, raw, now):
    a = strict(raw)
    expected = dict(pins(b['sourceCommitment']), domain=DOMAIN, operationCommitment=b['operationCommitment'],
                    binarySha256=b['binarySha256'], packagePath=b['packagePath'], outputPath=b['outputPath'],
                    founderApproved=True, noRetry=True, macOnPowerOpenLid=True, executionContext='require_escalated',
                    maximumInvocations={'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, RPC=0, WSS=0,
                    notBeforeUnix=a.get('notBeforeUnix'), expiresUnix=a.get('expiresUnix'))
    require(canonical(a) == canonical(expected), 'EXACT_FRESH_FOUNDER_AUTHORITY_REQUIRED')
    begin, end = a['notBeforeUnix'], a['expiresUnix']
    require(type(begin) is int and type(end) is int and begin <= now < end and 0 < end - begin <= 600, 'AUTHORITY_WINDOW')
    return a


def supervise(raw, out, sensor, previous):
    guards = portable.guards
    guard = RuntimeGuard(sensor, out / 'runtime/HOST_RUNTIME', previous)
    original, old_root = guards.sample_owned, guards.ROOT
    try:
        guards.sample_owned = lambda proc: sample_developer(proc, original, guard, out / 'runtime')
        guards.ROOT = out
        return guards.monitored(raw, out / 'runtime', portable.LIMITS)
    finally:
        guards.sample_owned, guards.ROOT = original, old_root


def journal(runtime, native):
    raw = read(runtime / 'JOURNAL.jsonl'); require(raw.endswith(b'\n'), 'INCOMPLETE_JOURNAL')
    rows = []; previous = ''
    for index, line in enumerate(raw.splitlines()):
        row = strict(line)
        require(row['sequence'] == index and row['previousSha256'] == previous, 'JOURNAL_HASH_CHAIN')
        previous = sha(line); rows.append(row)
    require([r['event'] for r in rows] == ['ACTUAL_ENTERED', 'CANONICAL_ACTUAL_MATCH', 'BRANCH_ENTERED', 'PAIR_OBSERVED_UNQUALIFIED'], 'NATIVE_ORDER_OR_REPEAT')
    require(rows[0]['data'] == {'ACTUAL': 1, 'BRANCH': 0, 'B': 0} and rows[2]['data'] == {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, 'NATIVE_COUNTS')
    require(rows[-1]['data'] == native['result'], 'COMPLETION_JOURNAL_LINK')


def verify_completion(out, b, measured):
    rt = out / 'runtime'; native = strict(read(rt / 'NATIVE_COMPLETION.json'))
    require(native['operationCommitment'] == b['operationCommitment'], 'NATIVE_OPERATION_LINK')
    expected = dict(terminal='GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED', nativeInvocations={'ACTUAL': 1, 'BRANCH': 1, 'B': 0},
                    RPC=0, WSS=0, canonicalActualValid=True, economicAssurance='UNRESOLVED',
                    heterogeneousAgreement='NOT_EVALUATED', externalDelivery='HOLD')
    require(native['result'] == expected, 'NATIVE_INCOMPLETE_OR_STOP')
    require(not measured['stop'] and measured['workerReaped'] and measured['exitCode'] == 0
            and measured['resourcesReliable'] and measured['wallSeconds'] <= 125
            and measured['workerAndObserverCpuSeconds'] <= 120
            and measured['sampledPeakWorkerRSS'] <= 1 << 30, 'RESOURCE_COMPLETION')
    journal(rt, native)
    a = strict(read(rt / 'ACTUAL.json'))['result']; branch = strict(read(rt / 'BRANCH.json'))['result']
    comparison = strict(read(rt / 'COMPARISON.json'))
    for prefix, result in [('actual', a), ('branch', branch)]:
        for field in ['StateRoot', 'GasUsed', 'Receipts', 'Observation']:
            require(comparison[prefix + field] == result[field[0].lower() + field[1:]], 'RAW_COMPARISON_LINK')
    return native


def execute(binding_path, authority_path, build_path, binary):
    # Reject missing consent before staging, sensors, or process creation.
    require(not sys.flags.optimize, 'PYTHON_OPTIMIZATION_FORBIDDEN')
    b = strict(read(binding_path)); raw = read(authority_path, 16383)
    authority(b, raw, int(time.time()))
    require(strict(raw)['expiresUnix'] - int(time.time()) >= 180, 'AUTHORITY_MUST_COVER_WORKFLOW')
    build = strict(read(build_path)); out = Path(b['outputPath'])
    require(b == binding(build, b['packagePath'], out, b['sensorPath'], b['nodePath']), 'SEALED_BINDING_DRIFT')
    require(sha(read(binary, 256 << 20)) == b['binarySha256'], 'BINARY_PIN')
    portable.fresh_output(out, [HERE.parents[0], Path(b['packagePath']), Path(binary)])
    began = time.monotonic(); rt = portable.consume_output(out)
    store(rt / 'STARTED.json', dict(operationCommitment=b['operationCommitment'], authoritySha256=sha(raw),
          utc=portable.guards.utc(), authorityConsumed=True, automaticRetry=False))
    with (rt / 'AUTHORITY.json').open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    final = dict(terminal='INTERRUPTED_UNVERIFIED', operationCommitment=b['operationCommitment'],
                 externalDelivery='HOLD', economicAssurance='UNRESOLVED', heterogeneousAgreement='NOT_EVALUATED',
                 nativeInvocations={'ACTUAL': 0, 'BRANCH': 0, 'B': 0}, RPC=0, WSS=0, automaticRetry=False)
    measured = None; dispatched = False
    def deadline(signum, frame):
        raise TimeoutError('NATIVE_STAGE_DEADLINE')
    old = signal.signal(signal.SIGALRM, deadline)
    # Reserve five seconds for owned-child kill/reap within the 140 second stage.
    signal.setitimer(signal.ITIMER_REAL, 135)
    try:
        for name in ['proposal', 'artifacts', 'inputs']: (out / name).mkdir()
        store(out / 'proposal/AUTHORIZATION_BINDINGS.json', b)
        for src, dest, pin in [(binary, 'artifacts/rhook-saved-pair', b['binarySha256']),
                               (b['sensorPath'], 'artifacts/rhook-host-sensor', b['sensorSha256']),
                               (b['packagePath'], 'inputs/BLOCK_PACKAGE.json', b['packageSha256'])]:
            payload = read(src, 256 << 20); require(sha(payload) == pin, 'STAGING_PIN')
            with (out / dest).open('xb') as f: f.write(payload); f.flush(); os.fsync(f.fileno())
            if dest.startswith('artifacts/'): (out / dest).chmod(0o700)
        decision, samples = admission(out / 'artifacts/rhook-host-sensor', rt / 'HOST')
        store(rt / 'HOST_ADMISSION.json', dict(accepted=True, profile=b['profile'], policySha256=POLICY_SHA, decision=decision))
        require(time.monotonic() - began < 10, 'PREPARATION_ADMISSION_DEADLINE')
        store(rt / 'DISPATCH_INTENT.json', dict(operationCommitment=b['operationCommitment']))
        dispatched = True; final['nativeInvocations'] = None
        measured = supervise(raw, out, out / 'artifacts/rhook-host-sensor', samples[-1])
        final['resources'] = measured
        native_path = rt / 'NATIVE_COMPLETION.json'
        if native_path.exists():
            # Keep untrusted structure out of the terminal result serializer.
            final['recordedNativeCompletion'] = dict(path='runtime/NATIVE_COMPLETION.json',
                                                       sha256=sha(read(native_path)))
        verify_completion(out, b, measured)
        require(source_commitment() == b['sourceCommitment']
                and sha(canonical(verifier_dependencies())) == b['verifierDependenciesCommitment'], 'VERIFIER_SOURCE_OR_DEPENDENCY_DRIFT')
        for name, pin in [('artifacts/rhook-saved-pair', 'binarySha256'),
                          ('artifacts/rhook-host-sensor', 'sensorSha256'),
                          ('inputs/BLOCK_PACKAGE.json', 'packageSha256')]:
            require(sha(read(out / name, 256 << 20)) == b[pin], 'STAGED_INPUT_DRIFT')
        require(time.monotonic() - began <= 140, 'NATIVE_STAGE_ELAPSED')
        signal.setitimer(signal.ITIMER_REAL, 0)
        # Verification process has no worker dispatch capability or provider input.
        with (rt / 'VERIFICATION.json').open('xb') as stdout, (rt / 'VERIFICATION.stderr').open('xb') as stderr:
            remaining = 180 - (time.monotonic() - began)
            require(remaining > 0, 'WORKFLOW_DEADLINE')
            result = subprocess.run([b['nodePath'], '--import', str(HERE.parent / 'adapters/hookr-case/test/no-network.mjs'),
                                     str(HERE / 'verify.mjs'), str(out / 'inputs/BLOCK_PACKAGE.json'), str(rt)],
                                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'TZ': 'UTC'},
                                    stdout=stdout, stderr=stderr, timeout=remaining)
        require(result.returncode == 0 and time.monotonic() - began <= 180, 'PLAN_AWARE_VERIFICATION_FAILED')
        verified = strict(read(rt / 'VERIFICATION.json'))
        require(verified['status'] == 'RECORDED_PAIR_INTEGRITY_PASS' and verified['qualifiedClaims'] == 0
                and verified['economicAssurance'] == 'UNRESOLVED'
                and verified['heterogeneousAgreement'] == 'NOT_EVALUATED', 'VERIFIER_RESULT_REQUIRED')
        final['verificationSha256'] = sha(read(rt / 'VERIFICATION.json'))
        final.update(nativeInvocations={'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, terminal='GO_HOOKR_PLAN_PAIR_OBSERVED_UNQUALIFIED')
    except BaseException as error:
        final['cause'] = type(error).__name__ + ': ' + str(error)[:2048]
        if not dispatched: final['terminal'] = 'HOST_STOP'
        elif measured and measured.get('workerReaped') and (rt / 'NATIVE_COMPLETION.json').exists():
            try:
                recorded = strict(read(rt / 'NATIVE_COMPLETION.json'))
                require(type(recorded) is dict and recorded.get('operationCommitment') == b['operationCommitment'],
                        'RECORDED_COMPLETION_LINK')
                result = recorded['result']
                fields = {'terminal', 'nativeInvocations', 'canonicalActualValid', 'RPC', 'WSS',
                          'economicAssurance', 'heterogeneousAgreement', 'externalDelivery'}
                require(type(result) is dict and fields <= result.keys(), 'RECORDED_COMPLETION_FIELDS')
                counts = result['nativeInvocations']
                require(type(counts) is dict and set(counts) == {'ACTUAL', 'BRANCH', 'B'}
                        and all(type(v) is int for v in counts.values())
                        and 0 <= counts['BRANCH'] <= counts['ACTUAL'] <= 1 and counts['B'] == 0,
                        'RECORDED_INVOCATION_COUNTS')
                terminals = {'HOST_STOP', 'HOST_STOP_MISSING_STATE', 'CANONICAL_EXECUTION_MISMATCH',
                             'BRANCH_HOST_STOP', 'BRANCH_STOP', 'INTERRUPTED_UNVERIFIED',
                             'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED'}
                require(result['terminal'] in terminals and type(result['canonicalActualValid']) is bool
                        and all(type(result[k]) is int and result[k] == 0 for k in ['RPC', 'WSS'])
                        and result['economicAssurance'] == 'UNRESOLVED'
                        and result['heterogeneousAgreement'] == 'NOT_EVALUATED'
                        and result['externalDelivery'] == 'HOLD', 'RECORDED_COMPLETION_SCOPE')
            except BaseException as completion_error:
                # Recovery must not lose FINAL_RESULT to a second parse/shape failure.
                final['completionEvidenceError'] = type(completion_error).__name__ + ': ' + str(completion_error)[:2048]
            else:
                final['nativeInvocations'] = counts
                final['nativeInvocationsEvidence'] = 'RECORDED_NATIVE_COMPLETION'
                if result['terminal'] != 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED':
                    final['terminal'] = result['terminal']
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old)
    final.update(elapsedSeconds=time.monotonic() - began, workerDispatchAttempted=dispatched)
    store(rt / 'FINAL_RESULT.json', final)
    # Preserve partials; publish a manifest only when all owned native writers are reaped.
    if not dispatched or measured and measured['workerReaped']:
        files = {str(p.relative_to(out)): sha(read(p, 256 << 20)) for p in sorted(out.rglob('*')) if p.is_file()}
        store(out / 'MANIFEST.json', dict(files=files, authenticity='LOCAL_INTEGRITY_NOT_SIGNATURE'))
    return final


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bindings', required=True); p.add_argument('--authority', required=True)
    p.add_argument('--build-record', required=True); p.add_argument('--binary', required=True)
    a = p.parse_args()
    result = execute(a.bindings, a.authority, a.build_record, a.binary)
    print(json.dumps(result))
    return 0 if result['terminal'] == 'GO_HOOKR_PLAN_PAIR_OBSERVED_UNQUALIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
