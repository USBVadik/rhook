"""Exact one-shot workflow; callers must supply separate direct approval."""
import contextlib
import fcntl
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import threading
import time
from .common import DOMAIN, PROFILE, HERE, ROOT, canonical, no_links, portable, read, require, sha, store, strict
from .contract import prepare_request, validate_approval, validate_runtime, normalize_result, validate_build
from .resources import admission, RuntimeGuard
from sdk_alpha_v2.kit import sample_developer
_MUTEX = threading.Lock()

@contextlib.contextmanager
def operation_lock(workspace):
    require(threading.current_thread() is threading.main_thread(), 'MAIN_THREAD_REQUIRED')
    require(_MUTEX.acquire(blocking=False), 'OPERATION_BUSY')
    fd = None
    try:
        workspace = no_links(workspace)
        fd = os.open(workspace / '.replay.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 384)
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'LOCK_FILE_TYPE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('OPERATION_BUSY') from error
        yield
    finally:
        if fd is not None:
            os.close(fd)
        _MUTEX.release()

def supervise(raw, out, sensor, previous):
    guards = portable.guards
    guard = RuntimeGuard(sensor, out / 'runtime/HOST_RUNTIME', previous)
    original, old_root = (guards.sample_owned, guards.ROOT)
    try:
        guards.sample_owned = lambda proc: sample_developer(proc, original, guard, out / 'runtime')
        guards.ROOT = out
        return guards.monitored(raw, out / 'runtime', portable.LIMITS)
    finally:
        guards.sample_owned, guards.ROOT = (original, old_root)

def run_verifier(out, b, remaining):
    rt = out / 'runtime'
    require(remaining > 0, 'WORKFLOW_DEADLINE')
    with (rt / 'VERIFICATION.json').open('xb') as stdout, (rt / 'VERIFICATION.stderr').open('xb') as stderr:
        result = subprocess.run([b['nodePath'], '--import', str(ROOT / 'adapters/hookr-case/test/no-network.mjs'), str(HERE / 'verify.mjs'), str(out / 'inputs/BLOCK_PACKAGE.json'), str(out / 'inputs/RUNTIME_PLAN.json'), str(out)], env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'TZ': 'UTC'}, stdout=stdout, stderr=stderr, timeout=remaining)
    require(result.returncode == 0, 'VERIFICATION_FAILED')
    verified = strict(read(rt / 'VERIFICATION.json'))
    require(verified['status'] == 'RECORDED_INTEGRITY_PASS' and verified['mode'] == 'RECORDED_VERIFICATION' and (verified['operationCommitment'] == b['operationCommitment']) and (verified['runtimePlanSha256'] == b['runtimePlanSha256']) and (verified['semanticPlanCommitment'] == b['semanticPlanCommitment']) and (verified['qualifiedClaims'] == 0) and (verified['economicAssurance'] == 'UNRESOLVED') and (verified['heterogeneousAgreement'] == 'NOT_EVALUATED'), 'VERIFIER_RESULT_REQUIRED')
    return verified

def completion(out, b):
    n = strict(read(out / 'runtime/NATIVE_COMPLETION.json'))
    require(type(n) is dict and n.get('operationCommitment') == b['operationCommitment'] and (n.get('runtimePlanSha256') == b['runtimePlanSha256']), 'NATIVE_COMPLETION_LINK')
    r = n['result']
    require(type(r) is dict, 'NATIVE_COMPLETION_SHAPE')
    require(r.get('terminal') in {'HOST_STOP', 'HOST_STOP_MISSING_STATE', 'RUNTIME_OR_RESOURCE_STOP', 'CANONICAL_EXECUTION_MISMATCH', 'BRANCH_HOST_STOP', 'BRANCH_STOP', 'INTERRUPTED_UNVERIFIED', 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED'}, 'NATIVE_TERMINAL')
    require(type(r.get('canonicalActualValid')) is bool and r.get('RPC') == 0 and (type(r.get('RPC')) is int) and (r.get('WSS') == 0) and (type(r.get('WSS')) is int) and (r.get('economicAssurance') == 'UNRESOLVED') and (r.get('heterogeneousAgreement') == 'NOT_EVALUATED') and (r.get('externalDelivery') == 'HOLD'), 'NATIVE_SCOPE')
    normalize_result(r['terminal'], None, {'counts': r['nativeInvocations']})
    detail = n.get('failureDetail')
    if detail is not None:
        require(type(detail) is dict and set(detail) == {'phase', 'code', 'classification'} and (detail['phase'] in ['ACTUAL', 'BRANCH']) and (type(detail['code']) is str) and (len(detail['code']) < 128), 'TYPED_FAILURE_DETAIL')
        missing = {'PROOF_SOURCE_UNAVAILABLE', 'CODE_SOURCE_UNAVAILABLE', 'ACCOUNT_PREIMAGE_UNAVAILABLE', 'STORAGE_PREIMAGE_UNAVAILABLE', 'TRIE_UPDATE_PREIMAGE_UNAVAILABLE', 'MISSING_ORIGINAL_HEADER', 'NITRO_SYSTEM_CONTEXT_UNAVAILABLE', 'CHAIN_CONFIG_UNAVAILABLE'}
        require((detail['classification'] == 'HOST_STOP_MISSING_STATE') == (detail['code'] in missing), 'TYPED_FAILURE_CLASSIFICATION')
    return n

def cleanup_confirmed(out, dispatched, measured, admission_started):
    if dispatched and (not (measured and measured.get('workerReaped') is True)):
        return False
    results = list((out / 'runtime').glob('HOST*/**/RESULT.json'))
    processes = list((out / 'runtime').glob('HOST*/**/PROCESS.json'))
    if admission_started and (not results):
        return False
    if any((not (p.parent / 'RESULT.json').exists() for p in processes)):
        return False
    try:
        return all((strict(read(p), allow_fractions=True).get('ownedChildReaped') is True for p in results))
    except (ValueError, OSError, AttributeError):
        return False

def execute(binding_path: Path, authority_path: Path, build_path: Path) -> dict:
    require(not sys.flags.optimize and sys.version_info >= (3, 12), 'PYTHON_RUNTIME_REQUIRED')
    b = strict(read(binding_path, 65536))
    try:
        raw = read(authority_path, 16383)
        validate_approval(b, raw, int(time.time()))
    except (ValueError, OSError) as error:
        raise ValueError('NOT_AUTHORIZED') from error
    with operation_lock(Path(b['workspace'])):
        build = strict(read(build_path))
        plan = validate_runtime(read(b['packagePath'], 2 << 20), read(b['runtimePlanPath'], 32768))
        paths = {k: b[k] for k in ['workspace', 'planId', 'outputPath', 'packagePath', 'semanticPlanPath', 'runtimePlanPath']}
        require(canonical(b) == canonical(prepare_request(build, plan, paths)), 'SEALED_BINDING_DRIFT')
        out = no_links(b['outputPath'])
        portable.fresh_output(out, [ROOT, Path(b['packagePath']), Path(build['workerPath'])])
        validate_approval(b, raw, int(time.time()))
        require(signal.getitimer(signal.ITIMER_REAL)[0] == 0, 'CALLER_TIMER_ACTIVE')
        began = time.monotonic()
        rt = portable.consume_output(out)
        store(rt / 'STARTED.json', dict(operationCommitment=b['operationCommitment'], authoritySha256=sha(raw), utc=portable.guards.utc(), authorityConsumed=True, automaticRetry=False))
        with (rt / 'AUTHORITY.json').open('xb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        final = {'status': 'INTERRUPTED_UNVERIFIED', 'stage': 'PREPARATION', 'operationCommitment': b['operationCommitment'], 'semanticPlanCommitment': b['semanticPlanCommitment'], 'runtimePlanSha256': b['runtimePlanSha256'], 'authorityConsumed': True, 'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}, 'RPC': 0, 'WSS': 0, 'automaticRetry': False, 'externalDelivery': 'HOLD', 'economicAssurance': 'UNRESOLVED', 'heterogeneousAgreement': 'NOT_EVALUATED', 'qualifiedClaims': 0}
        dispatched = False
        measured = None
        admission_started = False
        verified = False
        native = None

        def deadline(signum, frame):
            raise TimeoutError('NATIVE_STAGE_DEADLINE')
        old = signal.signal(signal.SIGALRM, deadline)
        interruption = {sig: signal.signal(sig, deadline) for sig in [signal.SIGINT, signal.SIGTERM]}
        signal.setitimer(signal.ITIMER_REAL, max(0.001, 135 - (time.monotonic() - began)))
        try:
            for name in ['proposal', 'artifacts', 'inputs']:
                (out / name).mkdir()
            store(out / 'proposal/AUTHORIZATION_BINDINGS.json', b)
            items = [(build['workerPath'], 'artifacts/rhook-saved-pair', b['binarySha256']), (b['sensorPath'], 'artifacts/rhook-host-sensor', b['sensorSha256']), (b['packagePath'], 'inputs/BLOCK_PACKAGE.json', b['packageSha256']), (b['runtimePlanPath'], 'inputs/RUNTIME_PLAN.json', b['runtimePlanSha256'])]
            for src, dest, pin in items:
                payload = read(src, 256 << 20)
                require(sha(payload) == pin, 'STAGING_PIN')
                with (out / dest).open('xb') as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                if dest.startswith('artifacts/'):
                    (out / dest).chmod(448)
            final['stage'] = 'ADMISSION'
            admission_started = True
            decision, samples = admission(out / 'artifacts/rhook-host-sensor', rt / 'HOST')
            store(rt / 'HOST_ADMISSION.json', dict(accepted=True, profile=PROFILE, policySha256=b['policySha256'], decision=decision))
            require(time.monotonic() - began < 10, 'PREPARATION_ADMISSION_DEADLINE')
            store(rt / 'DISPATCH_INTENT.json', dict(operationCommitment=b['operationCommitment']))
            dispatched = True
            final.update(stage='NATIVE', nativeInvocations=None)
            measured = supervise(raw, out, out / 'artifacts/rhook-host-sensor', samples[-1])
            final['resources'] = measured
            native = completion(out, b)
            require(native['result']['terminal'] == 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED' and native['result']['canonicalActualValid'] is True and (native['result']['nativeInvocations'] == {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}), 'NATIVE_STOP')
            require(measured['workerReaped'] is True and measured['exitCode'] == 0 and (measured['stop'] is None) and (measured['resourcesReliable'] is True) and (measured['wallSeconds'] <= 120) and (measured['workerAndObserverCpuSeconds'] <= 120) and (measured['sampledPeakWorkerRSS'] <= 1 << 30), 'RESOURCE_COMPLETION')
            require(time.monotonic() - began <= 140, 'NATIVE_STAGE_ELAPSED')
            signal.setitimer(signal.ITIMER_REAL, 0)
            validate_build(build)
            for _, dest, pin in items:
                require(sha(read(out / dest, 256 << 20)) == pin, 'STAGED_INPUT_DRIFT')
            final['stage'] = 'VERIFY'
            run_verifier(out, b, 180 - (time.monotonic() - began))
            require(time.monotonic() - began <= 180, 'WORKFLOW_DEADLINE')
            verified = True
        except BaseException as error:
            final['cause'] = type(error).__name__ + ': ' + str(error)[:2048]
            if not dispatched:
                final.update(status='HOST_STOP', causeCode=str(error)[:128])
            elif final['stage'] == 'VERIFY':
                final['status'] = 'VERIFICATION_FAILED'
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
            for sig, handler in interruption.items():
                signal.signal(sig, handler)
        clean = cleanup_confirmed(out, dispatched, measured, admission_started)
        if dispatched and measured and (measured.get('workerReaped') is True):
            try:
                native = completion(out, b)
                result = normalize_result(native['result']['terminal'], native.get('failureDetail'), {'counts': native['result']['nativeInvocations'], 'verified': verified, 'cleanupConfirmed': clean, 'resourcesVerified': verified, 'typedFailureVerified': True})
                if final['status'] == 'VERIFICATION_FAILED':
                    result['status'] = 'VERIFICATION_FAILED'
                final.update(result)
            except BaseException as error:
                final['completionEvidenceError'] = type(error).__name__ + ': ' + str(error)[:2048]
        if not clean:
            final['status'] = 'INTERRUPTED_UNVERIFIED'
        completion_path = rt / 'NATIVE_COMPLETION.json'
        if completion_path.exists():
            try:
                final['recordedNativeCompletion'] = {'path': 'runtime/NATIVE_COMPLETION.json', 'sha256': sha(read(completion_path))}
            except ValueError:
                pass
        final.update(elapsedSeconds=time.monotonic() - began, workerDispatchAttempted=dispatched, cleanupConfirmed=clean)
        store(rt / 'FINAL_RESULT.json', final)
        if clean:
            files = {str(p.relative_to(out)): sha(read(p, 256 << 20)) for p in sorted(out.rglob('*')) if p.is_file()}
            store(out / 'MANIFEST.json', dict(files=files, authenticity='LOCAL_INTEGRITY_NOT_SIGNATURE'))
        return final
