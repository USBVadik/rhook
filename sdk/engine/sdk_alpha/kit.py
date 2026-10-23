"""Local workspace API. No function runs history unless replay() is called explicitly."""
import hashlib
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import time
import threading

from .common import (REPO, require, sha, commitment, local_file, path_without_links,
                     read_json, store, exact_copy, sources, portable)
from .build import DOMAIN, CONTEXT, POLICY_HASH, verify_build
from .resources import POLICY, admission, RuntimeGuard

_operator_mutex = threading.Lock()


@contextlib.contextmanager
def operator_lock(directory):
    # The preserved supervisor uses module-local context; reject overlap rather
    # than silently sharing it between two Python API callers.
    require(threading.current_thread() is threading.main_thread(), 'MAIN_THREAD_OPERATOR_ACTION_REQUIRED')
    require(_operator_mutex.acquire(blocking=False), 'OPERATOR_ACTION_ALREADY_ACTIVE_IN_PROCESS')
    fd = None
    old_handlers = {}
    def interrupted(signum, frame):
        raise KeyboardInterrupt('OPERATOR_SIGNAL_'+str(signum))
    try:
        path = path_without_links(directory)
        local_file(path/'KIT.json')
        fd = os.open(path/'.OPERATOR_LOCK', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'REGULAR_OPERATOR_LOCK_REQUIRED')
        try: fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error: raise ValueError('WORKSPACE_OPERATOR_ACTION_ALREADY_ACTIVE') from error
        # Before worker supervision installs its own handlers, signals must
        # unwind bounded sensor capture so its owned child is killed/reaped.
        for sig in [signal.SIGTERM, signal.SIGINT]:
            old_handlers[sig] = signal.signal(sig, interrupted)
        yield
    finally:
        for sig, handler in old_handlers.items(): signal.signal(sig, handler)
        if fd is not None: os.close(fd)
        _operator_mutex.release()


def workspace(value):
    path = path_without_links(value)
    config = read_json(path/'KIT.json')
    require(config['format'] == 'rhook/developer-kit/1' and config['profile'] == POLICY['profile'], 'KIT_PROFILE')
    build = verify_build(config['buildRecord'])
    require(sha(config['buildRecord']) == config['buildRecordSha256'], 'KIT_BUILD_RECORD_DRIFT')
    package = local_file(path/'inputs/BLOCK_PACKAGE.json', 32<<20)
    portable.validate_package(package.read_bytes(), portable.specification(REPO))
    return path, config, build, package


def initialize(directory, package, build_record):
    directory = path_without_links(directory)
    require(not directory.is_relative_to(REPO), 'KIT_MUST_BE_OUTSIDE_SOURCE_CHECKOUT')
    record = verify_build(build_record)
    package = local_file(package, 32<<20)
    admitted = portable.validate_package(package.read_bytes(), portable.specification(REPO))
    portable.fresh_output(directory, [REPO, package, Path(build_record), Path(record['worker']), Path(record['sensor'])])
    directory.mkdir(mode=0o700)
    for name in ['inputs', 'proposals', 'runs', 'diagnostics']: (directory/name).mkdir()
    exact_copy(package, directory/'inputs/BLOCK_PACKAGE.json', 32<<20)
    config = {'format': 'rhook/developer-kit/1', 'profile': POLICY['profile'],
              'packageSha256': admitted['packageSha256'], 'buildRecord': str(local_file(build_record)),
              'buildRecordSha256': sha(build_record), 'externalDelivery': 'HOLD'}
    store(directory/'KIT.json', config)
    return {'status': 'KIT_READY_NATIVE_NOT_RUN', 'workspace': str(directory), 'profile': POLICY['profile'],
            'package': admitted, 'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}}


def identifier(name):
    require(isinstance(name, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) is not None, 'SAFE_RUN_NAME_REQUIRED')
    return name


def _doctor(directory, name):
    path, _, build, _ = workspace(directory)
    target = path/'diagnostics'/identifier(name)
    require(not target.exists(), 'DIAGNOSTIC_ALREADY_EXISTS')
    target.mkdir()
    result = {'status': 'HOST_STOP', 'profile': POLICY['profile'], 'policySha256': POLICY_HASH,
              'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}, 'RPC': 0, 'WSS': 0,
              'qualifiedScientificAdmission': False, 'reusableAdmission': False}
    try:
        decision, _ = admission(build['sensor'], target/'host')
        result.update({'status': 'DOCTOR_PASS', 'decision': decision})
    except BaseException as error:
        result['cause'] = (type(error).__name__+': ' if isinstance(error, KeyboardInterrupt) else '')+str(error)
    store(target/'RESULT.json', result)
    return result


def doctor(directory, name):
    with operator_lock(directory):
        _doctor(directory, name)
        return diagnostic(path_without_links(directory)/'diagnostics'/identifier(name))


def diagnostic(directory):
    """Present saved raw sensor values, including a rejected first sample."""
    path = path_without_links(directory)
    result = read_json(path/'RESULT.json')
    result['diagnosticPath'] = str(path)
    result['policyMatchesCurrent'] = result.get('policySha256') == POLICY_HASH
    result['observed'] = []
    for folder in sorted((path/'host').glob('sample-*')):
        try: raw = json.loads(local_file(folder/'stdout.bin', 8192).read_bytes())
        except (OSError, ValueError): continue
        if not isinstance(raw, dict) or raw.get('source') != 'DARWIN_HOST_VM64/1': continue
        keys = ['physicalBytes', 'freePages', 'pageBytes', 'pressureBefore', 'pressureAfter', 'swapUsedBytes']
        if not all(type(raw.get(k)) is int and 0 <= raw[k] < 1<<64 for k in keys): continue
        free = raw['freePages']*raw['pageBytes']
        result['observed'].append({'freeBytes': free, 'freeMiB': round(free/(1<<20), 2),
            'physicalGiB': round(raw['physicalBytes']/(1<<30), 2),
            'pressureBefore': raw['pressureBefore'], 'pressureAfter': raw['pressureAfter'],
            'swapUsedGiB': round(raw['swapUsedBytes']/(1<<30), 2),
            'requiredAdmissionFreeGiB': POLICY['minimumAdmissionFreeBytes']/(1<<30),
            'rawSample': str(folder/'stdout.bin')})
    result['newMeasurements'] = 0
    return result


def prepare(directory, name):
    path, config, build, package = workspace(directory)
    name = identifier(name)
    output = path/'runs'/name
    proposal = path/'proposals'/name
    portable.fresh_output(output, [REPO, package])
    portable.fresh_output(proposal, [REPO, package, output])
    b = {'format': 'rhook/developer-run/1', 'profile': POLICY['profile'], 'policySha256': POLICY_HASH,
         'binaryPath': build['worker'], 'binarySha256': build['workerSha256'],
         'sensorPath': build['sensor'], 'sensorSha256': build['sensorSha256'],
         'packagePath': str(package), 'packageSha256': config['packageSha256'], 'outputPath': str(output),
         'planSha256': sha(REPO/'repro/portable/plan.json'), 'sourceFiles': sources(),
         'executionContext': CONTEXT, 'limits': dict(portable.LIMITS), 'resourcePolicy': POLICY,
         'maximumInvocations': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, 'RPC': 0, 'WSS': 0,
         'externalDelivery': 'HOLD', 'buildRecord': config['buildRecord'],
         'buildRecordSha256': config['buildRecordSha256']}
    b['operationCommitment'] = commitment(b)
    proposal.mkdir()
    store(proposal/'BINDINGS.json', b)
    return b


def validate_binding(b, config, build, package, output):
    base = dict(b); base.pop('operationCommitment')
    require(commitment(base) == b['operationCommitment'], 'BINDINGS_COMMITMENT')
    require(b['profile'] == POLICY['profile'] and b['policySha256'] == POLICY_HASH
            and b['resourcePolicy'] == POLICY and b['limits'] == portable.LIMITS, 'EXACT_DEVELOPER_PROFILE')
    require(b['sourceFiles'] == sources() and b['planSha256'] == sha(REPO/'repro/portable/plan.json'), 'SOURCE_DRIFT')
    require(b['binaryPath'] == build['worker'] and b['binarySha256'] == build['workerSha256']
            and b['sensorPath'] == build['sensor'] and b['sensorSha256'] == build['sensorSha256'], 'BUILD_ARTIFACT_DRIFT')
    require(b['buildRecord'] == config['buildRecord'] and b['buildRecordSha256'] == config['buildRecordSha256'], 'BUILD_RECORD_DRIFT')
    require(b['packagePath'] == str(package) and b['packageSha256'] == sha(package)
            and b['outputPath'] == str(output) and b['executionContext'] == CONTEXT, 'EXACT_RUN_PATHS')
    require(b['maximumInvocations'] == POLICY['maximumInvocations']
            and type(b['RPC']) is int and b['RPC'] == 0 and type(b['WSS']) is int and b['WSS'] == 0, 'OFFLINE_ONE_PAIR')


def operator_consent(b, confirmed, mac_ready, now):
    require(confirmed is True and mac_ready is True, 'EXPLICIT_NATIVE_CONFIRMATION_AND_MAC_READY_REQUIRED')
    a = {key: b[key] for key in ['operationCommitment', 'binarySha256', 'packagePath', 'outputPath',
                                 'executionContext', 'profile', 'policySha256', 'maximumInvocations', 'RPC', 'WSS']}
    a.update({'domain': DOMAIN, 'operatorApproved': True, 'macOnPowerOpenLid': True,
              'noRetry': True, 'notBeforeUnix': int(now), 'expiresUnix': int(now)+300})
    return json.dumps(a, sort_keys=True).encode()


def sample_developer(proc, original_sample, guard, runtime):
    try:
        row = original_sample(proc)
    except AssertionError as error:
        # Darwin ps can lose/change its row after worker exit. An exited/reaped
        # process no longer needs live RSS telemetry; completion still has to
        # pass exit-code, resource and native-result checks separately.
        if proc.poll() is not None: return None
        store(runtime/'WORKER_OBSERVER_STOP.json', {'cause': str(error), 'pid': proc.pid})
        raise
    if row is not None: guard.poll()
    return row


def supervise(raw, out, sensor, previous):
    guards = portable.guards
    guard = RuntimeGuard(sensor, out/'runtime/HOST_RUNTIME', previous)
    original_sample, original_root = guards.sample_owned, guards.ROOT

    def sample(proc):
        return sample_developer(proc, original_sample, guard, out/'runtime')

    try:
        guards.sample_owned = sample
        guards.ROOT = out
        return guards.monitored(raw, out/'runtime', portable.LIMITS)
    finally:
        guards.sample_owned, guards.ROOT = original_sample, original_root


def file_manifest(directory):
    files = {}
    for p in sorted(directory.rglob('*')):
        require(not p.is_symlink(), 'RUN_SYMLINK')
        if p.is_file() and p != directory/'MANIFEST.json':
            files[str(p.relative_to(directory))] = {'sha256': sha(p), 'bytes': p.stat().st_size}
    return files


def _replay(directory, name, *, confirm_native=False, mac_ready=False):
    # Require consent before any setup, host sample or worker launch.
    require(confirm_native is True and mac_ready is True, 'EXPLICIT_NATIVE_CONFIRMATION_AND_MAC_READY_REQUIRED')
    require(not __import__('sys').flags.optimize, 'PYTHON_OPTIMIZATION_FORBIDDEN')
    path, config, build, package = workspace(directory)
    name = identifier(name)
    proposal = path/'proposals'/name/'BINDINGS.json'
    b = read_json(proposal) if proposal.exists() else prepare(directory, name)
    out = path/'runs'/name
    validate_binding(b, config, build, package, out)
    portable.fresh_output(out, [REPO, package, Path(build['worker']), Path(build['sensor'])])
    raw = operator_consent(b, confirm_native, mac_ready, time.time())
    rt = portable.consume_output(out)
    store(rt/'STARTED.json', {'operationCommitment': b['operationCommitment'],
          'authoritySha256': hashlib.sha256(raw).hexdigest(), 'profile': POLICY['profile'],
          'utc': portable.guards.utc(), 'automaticRetry': False})
    with (rt/'OPERATOR_CONSENT.json').open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    final = {'terminal': 'INTERRUPTED_UNVERIFIED', 'profile': POLICY['profile'], 'policySha256': POLICY_HASH,
             'operationCommitment': b['operationCommitment'], 'externalDelivery': 'HOLD',
             'economicAssurance': 'UNRESOLVED', 'heterogeneousAgreement': 'NOT_EVALUATED',
             'qualifiedClaims': 0, 'RPC': 0, 'WSS': 0, 'automaticRetry': False,
             'nativeInvocations': None, 'operatorRunClosed': True}
    began = time.monotonic()
    try:
        (out/'proposal').mkdir(); (out/'artifacts').mkdir(); (out/'inputs').mkdir()
        store(out/'proposal/AUTHORIZATION_BINDINGS.json', b)
        exact_copy(package, out/'inputs/BLOCK_PACKAGE.json', 32<<20)
        for source, dest, pin in [(build['worker'], 'rhook-saved-pair', build['workerSha256']),
                                  (build['sensor'], 'rhook-host-sensor', build['sensorSha256'])]:
            exact_copy(source, out/'artifacts'/dest, 256<<20)
            require(sha(out/'artifacts'/dest) == pin, 'COPIED_EXECUTABLE_SHA256')
            (out/'artifacts'/dest).chmod(0o700)
        try:
            decision, samples = admission(out/'artifacts/rhook-host-sensor', rt/'HOST')
        except Exception as error:
            decision, samples = {'status': 'HOST_STOP', 'cause': str(error)}, []
        accepted = decision['status'] == 'PASS'
        store(rt/'HOST_ADMISSION.json', {'accepted': accepted, 'profile': POLICY['profile'],
              'policySha256': POLICY_HASH, 'decision': decision})
        if not accepted:
            final.update({'terminal': 'HOST_STOP', 'hostDecision': decision,
                          'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}})
        else:
            require(time.monotonic()-began < 10, 'HOST_ADMISSION_OR_PREPARATION_DEADLINE')
            store(rt/'WORKER_DISPATCH_INTENT.json', {'operationCommitment': b['operationCommitment'],
                  'profile': POLICY['profile'], 'maximumInvocations': POLICY['maximumInvocations']})
            measured = supervise(raw, out, out/'artifacts/rhook-host-sensor', samples[-1])
            final['resources'] = measured
            completion = rt/'NATIVE_COMPLETION.json'
            if completion.exists():
                native = read_json(completion)
                require(native['operationCommitment'] == b['operationCommitment'], 'NATIVE_OPERATION_LINK')
                final['native'] = native
                portable.accept_native_completion(REPO, rt, final, measured, native)
                if final['terminal'] == 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED':
                    final['terminal'] = 'DEVELOPER_PAIR03_REPLAY_PASS'
            else:
                final['cause'] = measured['stop'] or 'NATIVE_COMPLETION_MISSING'
    except BaseException as error:
        final['cause'] = type(error).__name__+': '+str(error)[:2048]
    final['workerDispatchAttempted'] = (rt/'WORKER_DISPATCH_INTENT.json').exists()
    if not final['workerDispatchAttempted']:
        final['nativeInvocations'] = {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}
    final.update({'elapsedSeconds': time.monotonic()-began, 'utc': portable.guards.utc()})
    store(rt/'FINAL_RESULT.json', final)
    # A completion manifest is only published after confirmed worker cleanup.
    # Missing completion after dispatch leaves partial evidence, never a seal.
    dispatch_intent = rt/'WORKER_DISPATCH_INTENT.json'
    if not dispatch_intent.exists() or (rt/'PROCESS_COMPLETION.json').exists() and read_json(rt/'PROCESS_COMPLETION.json')['workerReaped']:
        store(out/'MANIFEST.json', {'format': 'rhook/developer-run-manifest/1', 'files': file_manifest(out),
                                  'authenticity': 'LOCAL_INTEGRITY_ONLY_NOT_A_SIGNATURE'})
    return final


def replay(directory, name, *, confirm_native=False, mac_ready=False):
    require(confirm_native is True and mac_ready is True, 'EXPLICIT_NATIVE_CONFIRMATION_AND_MAC_READY_REQUIRED')
    with operator_lock(directory):
        return _replay(directory, name, confirm_native=confirm_native, mac_ready=mac_ready)


def verify_run(directory):
    out = path_without_links(directory)
    manifest = read_json(out/'MANIFEST.json')
    require(manifest['files'] == file_manifest(out), 'RUN_FILE_SET_OR_HASH_MISMATCH')
    final = read_json(out/'runtime/FINAL_RESULT.json')
    require(final['profile'] == POLICY['profile'] and final['policySha256'] == POLICY_HASH, 'RUN_PROFILE')
    require(final['terminal'] == 'DEVELOPER_PAIR03_REPLAY_PASS', 'RUN_NOT_SUCCESSFUL: '+final['terminal'])
    compared = portable.compare_baseline(REPO, out/'runtime')
    require(compared['status'] == 'PASS' and final['baselineComparison'] == compared, 'BASELINE_MISMATCH')
    native = read_json(out/'runtime/NATIVE_COMPLETION.json')
    measured = read_json(out/'runtime/PROCESS_COMPLETION.json')
    binding = read_json(out/'proposal/AUTHORIZATION_BINDINGS.json')
    base = dict(binding); base.pop('operationCommitment')
    require(commitment(base) == binding['operationCommitment'] == final['operationCommitment']
            == native['operationCommitment'], 'RUN_OPERATION_LINK')
    require(binding['profile'] == POLICY['profile'] and binding['policySha256'] == POLICY_HASH
            and binding['resourcePolicy'] == POLICY and binding['limits'] == portable.LIMITS, 'RUN_BINDING_PROFILE')
    started = read_json(out/'runtime/STARTED.json')
    consent_path = out/'runtime/OPERATOR_CONSENT.json'
    consent = read_json(consent_path, 16383)
    require(started['authoritySha256'] == sha(consent_path)
            and started['operationCommitment'] == binding['operationCommitment'], 'RUN_CONSENT_LINK')
    expected = json.loads(operator_consent(binding, True, True, consent['notBeforeUnix']))
    require(consent == expected and final['resources'] == measured, 'RUN_CONSENT_OR_RESOURCE_RECORD')
    for name, pin in [('artifacts/rhook-saved-pair', 'binarySha256'), ('artifacts/rhook-host-sensor', 'sensorSha256'),
                      ('inputs/BLOCK_PACKAGE.json', 'packageSha256')]:
        require(sha(out/name) == binding[pin], 'RUN_ARTIFACT_HASH')
    host = read_json(out/'runtime/HOST_ADMISSION.json')
    require(host['accepted'] is True and host['profile'] == POLICY['profile'] and host['policySha256'] == POLICY_HASH,
            'RUN_HOST_ADMISSION')
    samples = read_json(out/'runtime/HOST/SAMPLES.json')
    from .resources import assess, validate_sample
    require(len(samples) == 2, 'RUN_ADMISSION_SAMPLE_COUNT')
    for i, expected_sample in enumerate(samples):
        p = out/'runtime/HOST'/('sample-'+str(i))
        capture = read_json(p/'RESULT.json')
        require(capture['exitCode'] == 0 and not capture['stop'] and capture['ownedChildReaped']
                and not any(capture['truncated'].values()) and not (p/'stderr.bin').read_bytes()
                and json.loads(local_file(p/'stdout.bin', 8192).read_bytes()) == expected_sample,
                'ADMISSION_SENSOR_CAPTURE')
    require(host['decision'] == assess(samples), 'RUN_HOST_SAMPLE_DECISION')
    previous = samples[-1]
    captures = out/'runtime/HOST_RUNTIME'
    require(not (captures/'STOP.json').exists(), 'RUNTIME_HOST_STOP')
    directories = [p for p in captures.iterdir() if p.is_dir()]
    require(len(directories) > 0 and {p.name for p in directories} == {str(i) for i in range(len(directories))},
            'RUNTIME_SAMPLE_SEQUENCE')
    for i in range(len(directories)):
        p = captures/str(i)
        capture = read_json(p/'RESULT.json')
        require(capture['exitCode'] == 0 and not capture['stop'] and capture['ownedChildReaped']
                and not any(capture['truncated'].values()) and not (p/'stderr.bin').read_bytes(), 'RUNTIME_SENSOR_CAPTURE')
        current = validate_sample(json.loads(local_file(p/'stdout.bin', 8192).read_bytes()))
        assess([previous, current], runtime=True)
        previous = current
    require(native['result']['nativeInvocations'] == {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}
            and final['nativeInvocations'] == native['result']['nativeInvocations']
            and native['result']['canonicalActualValid'] is True, 'NATIVE_COUNTS_OR_CANONICAL')
    require(not measured['stop'] and measured['workerReaped'] is True
            and measured['resourcesReliable'] is True and measured['exitCode'] == 0, 'PROCESS_NOT_VERIFIED')
    for key in ['wallSeconds', 'workerAndObserverCpuSeconds', 'sampledPeakWorkerRSS']:
        require(type(measured[key]) in (int, float) and math.isfinite(measured[key]) and measured[key] >= 0,
                'RESOURCE_NUMBER_ENCODING')
    require(type(final['elapsedSeconds']) in (int, float) and math.isfinite(final['elapsedSeconds'])
            and 0 <= final['elapsedSeconds'] <= 140, 'OVERALL_PLAN_TIME_LIMIT')
    require(measured['wallSeconds'] <= 120 and measured['workerAndObserverCpuSeconds'] <= 120
            and measured['sampledPeakWorkerRSS'] <= POLICY['workerRssBytes'], 'RESOURCE_LIMIT')
    return {'status': 'SAVED_DEVELOPER_RESULT_VERIFIED', 'profile': POLICY['profile'], 'comparison': compared,
            'nativeInvocations': native['result']['nativeInvocations'], 'EVMReexecuted': False,
            'economicAssurance': 'UNRESOLVED', 'heterogeneousAgreement': 'NOT_EVALUATED',
            'qualifiedClaims': 0, 'externalDelivery': 'HOLD'}
