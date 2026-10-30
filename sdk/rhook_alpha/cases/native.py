"""Explicit native backend with retained v2 supervision and local one-shot consent."""
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import sys
import tempfile
import time
from developer.files import canonical, digest, load, no_links, read, require, save, sha, sync, tree, dependencies
from . import authority
from .adapters import get_adapter
from .capsule import MAX_PACKAGE, PROFILE
SDK_ROOT = Path(__file__).resolve().parents[2]
POLICY_SHA = '1b081fd77d61a4037ec0055a1a129d3fdcc4f9a075f9b56b3c7d66be318e4688'

def python_required():
    require(sys.version_info >= (3, 12) and not sys.flags.optimize, 'PYTHON_3_12_UNOPTIMIZED_REQUIRED')


def capture(command, directory, timeout, stdout_limit=65536, stderr_limit=65536):
    python_required()
    engine = str(SDK_ROOT / 'engine')
    if engine not in sys.path:
        sys.path.insert(0, engine)
    from sdk_alpha_v2._frozen import isolated_guards
    from .workflow import active_group, guard_module
    group = active_group()
    if group is not None:
        return guard_module(group=group).capture(command, directory, timeout, stdout_limit, stderr_limit)
    return isolated_guards().capture(command, directory, timeout, stdout_limit, stderr_limit)


def capture_workflow(command, directory, timeout, stdout_limit=65536, stderr_limit=65536):
    """Bound a whole CLI without imposing the diagnostic helper's hard limits.

    Descendant helpers retain their smaller caps; the native supervisor still
    enforces its own RSS/CPU/wall policy. This function issues no authority.
    """
    python_required()
    require(type(timeout) in (int, float) and 0 < timeout <= 180, 'WORKFLOW_CAPTURE_LIMIT')
    require(all(type(n) is int and 0 <= n <= 1 << 20 for n in (stdout_limit, stderr_limit)), 'WORKFLOW_CAPTURE_LIMIT')
    engine = str(SDK_ROOT / 'engine')
    if engine not in sys.path:
        sys.path.insert(0, engine)
    from .workflow import active_group, guard_module, finish_group
    require(active_group() is None, 'NESTED_WORKFLOW_CAPTURE_FORBIDDEN')
    module = guard_module(outer=True)
    result, stdout, stderr = module.capture(command, no_links(directory), timeout, stdout_limit, stderr_limit)
    return finish_group(no_links(directory), result), stdout, stderr


def code_files():
    result = {}
    for root in ('rhook_alpha', 'engine'):
        for p in sorted((SDK_ROOT / root).rglob('*')):
            if '__pycache__' in p.parts or 'node_modules' in p.parts:
                continue
            if p.is_file():
                result[str(p.relative_to(SDK_ROOT))] = sha(p)
    return result

def _settings(sdk=None):
    selected = getattr(sdk, '_native_profile', PROFILE)
    if selected == PROFILE:
        return PROFILE, POLICY_SHA, Path(__file__).with_name('verify.mjs')
    from .historical import PROFILE as historical
    require(selected == historical, 'UNSUPPORTED_EXECUTION_PROFILE')
    folder = Path(__file__).with_name('historical')
    return historical, sha(folder / 'policy.json'), folder / 'verify.mjs'

def _check_runtime(d, sdk=None):
    profile, policy, _ = _settings(sdk)
    python_required()
    dependencies(SDK_ROOT / 'engine/adapters/hookr-case/node_modules')
    require(set(d) == {'schema', 'profile', 'sourceCommitment', 'policySha256', 'files'}, 'RUNTIME_FIELDS')
    require(d['schema'] == 'rhook/case-runtime/0.1' and d['profile'] == profile and (d['policySha256'] == policy), 'RUNTIME_PROFILE')
    require(set(d['files']) == {'worker', 'sensor', 'node'}, 'RUNTIME_ARTIFACTS')
    for row in d['files'].values():
        require(set(row) == {'path', 'sha256'} and sha(no_links(row['path'])) == row['sha256'], 'RUNTIME_ARTIFACT_DRIFT')
    worker = d['files']['worker']['path']
    with tempfile.TemporaryDirectory(prefix='rhook-runtime-check-') as name:
        result, stdout, stderr = capture([worker, '--identity'], Path(name).resolve() / 'capture', 5, 4095, 4095)
    require(result['ownedChildReaped'] and result['exitCode'] == 0 and not result['stop'] and not stderr, 'WORKER_IDENTITY_FAILED')
    require(json.loads(stdout) == {k: d[k] for k in ('profile', 'sourceCommitment', 'policySha256')}, 'WORKER_BUILD_IDENTITY')
    return d

def configure(sdk, path):
    d = _check_runtime(load(path, 65536), sdk)
    sdk.registry._prepare()
    save(sdk.home / 'RUNTIME.json', {'runtime': d, 'sdkFiles': code_files()})
    key = sdk.home / '.case-consent.key'
    with key.open('xb') as stream:
        stream.write(os.urandom(32))
        stream.flush()
        os.fsync(stream.fileno())
    key.chmod(0o600)
    sync(sdk.home)
    return {'status': 'RUNTIME_REGISTERED', 'profile': _settings(sdk)[0], 'nativeExecuted': False}

def read_key(home):
    path = no_links(home / '.case-consent.key')
    require(home.stat().st_uid == os.getuid() and home.stat().st_mode & 0o077 == 0, 'PRIVATE_CASE_HOME_REQUIRED')
    require(path.stat().st_uid == os.getuid() and path.stat().st_mode & 0o077 == 0, 'PRIVATE_CONSENT_KEY_REQUIRED')
    key = read(path, 32)
    require(len(key) == 32, 'CONSENT_KEY_SIZE')
    return key


def runtime(sdk):
    path = sdk.home / 'RUNTIME.json'
    if not path.exists():
        raise FileNotFoundError(2, 'NATIVE_RUNTIME_MISSING: explicitly register a compatible worker, sensor and Node runtime in RUNTIME.json.', str(path))
    saved = load(path, 2 << 20)
    require(saved['sdkFiles'] == code_files(), 'REGISTERED_SDK_CODE_DRIFT')
    return _check_runtime(saved['runtime'], sdk)

def authenticate(sdk, case, *, trusted_checkpoint=None, plan=None):
    path, d = sdk.registry.resolve(case)
    if trusted_checkpoint is not None:
        require(trusted_checkpoint == d['checkpoint']['blockHash'], 'TRUSTED_CHECKPOINT_MISMATCH')
    adapter = get_adapter(d)
    if plan is None:
        plan = {'caseId': case, 'capsuleId': d['capsuleId'], 'runtimePlan': adapter.authentication_plan(d)}
    r = runtime(sdk)
    with tempfile.TemporaryDirectory(prefix='.authenticate-', dir=sdk.home) as name:
        plan_path = Path(name) / 'PLAN.json'
        save(plan_path, plan)
        result, stdout, stderr = capture([r['files']['worker']['path'], '--authenticate', str(path / 'CAPSULE.json'), str(plan_path), str(path / 'BLOCK_PACKAGE.json')], Path(name) / 'capture', 12, 65536, 65536)
    require(result['ownedChildReaped'] and result['exitCode'] == 0 and not result['stop'], 'CASE_AUTHENTICATION_FAILED: ' + str(result['stop']) + ': ' + stderr.decode(errors='replace')[:512])
    value = json.loads(stdout)
    require(value.get('status') == 'PROOFS_VERIFIED_AT_DECLARED_ROOT' and value.get('capsuleId') == d['capsuleId'] and (value.get('nativeExecutions') == 0), 'AUTHENTICATOR_RESULT')
    return dict(value, caseId=case, chainTrust='OPERATOR_PINNED_CHECKPOINT' if trusted_checkpoint else 'NOT_ESTABLISHED', witnessClosure='NOT_EVALUATED')

def binding(sdk, plan, trust):
    path, d = sdk.registry.resolve(plan['caseId'])
    r = runtime(sdk)
    require(trust == d['checkpoint']['blockHash'], 'EXPLICIT_TRUSTED_CHECKPOINT_REQUIRED')
    body = {'schema': 'rhook/case-native-request/0.1', 'profile': _settings(sdk)[0], 'planId': plan['planId'], 'caseId': d['caseId'], 'capsuleId': d['capsuleId'], 'capsuleSha256': sha(path / 'CAPSULE.json'), 'planSha256': sha(sdk.home / 'plans' / plan['planId'] / 'PLAN.json'), 'packageSha256': d['assets']['BLOCK_PACKAGE.json']['sha256'], 'binarySha256': r['files']['worker']['sha256'], 'sourceCommitment': r['sourceCommitment'], 'policySha256': _settings(sdk)[1], 'runtimeSha256': digest(canonical(r)), 'trustedCheckpoint': trust, 'outputPath': str(sdk.home / 'runs' / plan['planId']), 'ownerUid': os.getuid(), 'host': os.uname().nodename, 'maximumInvocations': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, 'RPC': 0, 'WSS': 0, 'workflowSeconds': 180, 'nativeStageSeconds': 140, 'executionContext': 'require_escalated', 'externalDelivery': 'HOLD'}
    body['operationCommitment'] = digest(b'rhook/case-operation/0.1\n' + canonical(body))
    return body

def operation(sdk, ref, *, trusted_checkpoint=None):
    p = sdk.describe(ref)
    require(trusted_checkpoint == p['runtimePlan']['checkpoint']['blockHash'], 'EXPLICIT_TRUSTED_CHECKPOINT_REQUIRED')
    return binding(sdk, p, trusted_checkpoint)


def authorize(sdk, ref, *, local_owner=False, mac_ready=False, trusted_checkpoint=None, expected_operation=None):
    require(local_owner is True and mac_ready is True, 'EXPLICIT_LOCAL_OWNER_AND_POWER_LID_CONSENT_REQUIRED')
    require(sys.platform == 'darwin' and platform.machine() == 'arm64' and (not sys.flags.optimize), 'SUPPORTED_NATIVE_HOST_REQUIRED')
    p = sdk.describe(ref)
    b = binding(sdk, p, trusted_checkpoint)
    if expected_operation is not None:
        require(type(expected_operation) is str and len(expected_operation) == 64
                and expected_operation == b['operationCommitment'], 'REVIEWED_OPERATION_MISMATCH')
    authenticate(sdk, p['caseId'], trusted_checkpoint=trusted_checkpoint, plan=p)
    key = read_key(sdk.home)
    return authority.issue(sdk.home / 'consents', b, key)

def guards():
    engine = str(SDK_ROOT / 'engine')
    if engine not in sys.path:
        sys.path.insert(0, engine)
    from case_sdk.workflow import operation_lock, supervise, cleanup_confirmed
    from case_sdk.resources import admission
    from case_sdk.common import portable
    from .workflow import active_group, guard_module
    group = active_group()
    if group is not None and getattr(portable.guards, 'WORKFLOW_PGID', None) != group:
        previous = portable.guards
        portable.guards = guard_module(group=group)
        portable.guards.ROOT, portable.guards.WS = previous.ROOT, previous.WS
    return (operation_lock, supervise, cleanup_confirmed, admission)

def _node_verify(sdk, out, timeout=40, record=False):
    r = runtime(sdk)
    command = [r['files']['node']['path'], str(_settings(sdk)[2]), str(out)]
    if record:
        result, stdout, stderr = capture(command, out / 'runtime' / 'VERIFIER', timeout, 2 << 20, 65536)
    else:
        with tempfile.TemporaryDirectory(prefix='.verify-', dir=sdk.home) as name:
            result, stdout, stderr = capture(command, Path(name) / 'capture', timeout, 2 << 20, 65536)
    require(result['ownedChildReaped'] and result['exitCode'] == 0 and not result['stop'], 'CASE_VERIFICATION_FAILED: ' + str(result['stop']) + ': ' + stderr.decode(errors='replace')[:512])
    value = json.loads(stdout)
    require(value['status'] == 'RECORDED_PAIR_INTEGRITY_PASS' and value['qualifiedClaims'] == 0, 'VERIFIER_RESULT')
    return value


def validate_completion(value, operation, expected_profile=PROFILE):
    require(type(value) is dict and value.get('operationCommitment') == operation, 'NATIVE_OPERATION_LINK')
    if expected_profile != PROFILE:
        from .historical import PROFILE as historical, DOMAIN
        require(expected_profile == historical and value.get('profile') == historical
                and value.get('schema') == DOMAIN+'/completion' and value.get('ownedBridgesClosed') is True,
                'HISTORICAL_COMPLETION_DOMAIN_OR_CLEANUP')
    result = value.get('result')
    require(type(result) is dict, 'NATIVE_COMPLETION_SHAPE')
    counts = result.get('nativeInvocations')
    require(type(counts) is dict and set(counts) == {'ACTUAL', 'BRANCH', 'B'} and all(type(v) is int for v in counts.values()) and 0 <= counts['BRANCH'] <= counts['ACTUAL'] <= 1 and counts['B'] == 0, 'NATIVE_COUNTS_UNVERIFIED')
    require(type(result.get('canonicalActualValid')) is bool and type(result.get('RPC')) is int and result['RPC'] == 0 and type(result.get('WSS')) is int and result['WSS'] == 0, 'NATIVE_SCOPE')
    if counts['BRANCH']:
        require(result['canonicalActualValid'], 'CANONICAL_GATE_MISSING')
    require(result.get('terminal') in {'HOST_STOP', 'HOST_STOP_MISSING_STATE', 'RUNTIME_OR_RESOURCE_STOP', 'CANONICAL_EXECUTION_MISMATCH', 'BRANCH_HOST_STOP', 'BRANCH_STOP', 'INTERRUPTED_UNVERIFIED', 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED'}, 'NATIVE_TERMINAL')
    detail = value.get('failureDetail')
    if detail is not None:
        require(type(detail) is dict and set(detail) == {'phase', 'code', 'classification'} and detail['phase'] in {'ACTUAL', 'BRANCH'} and type(detail['code']) is str and 0 < len(detail['code']) < 128 and type(detail['classification']) is str, 'TYPED_FAILURE_DETAIL')
        missing = {'PROOF_SOURCE_UNAVAILABLE', 'CODE_SOURCE_UNAVAILABLE', 'ACCOUNT_PREIMAGE_UNAVAILABLE', 'STORAGE_PREIMAGE_UNAVAILABLE', 'TRIE_UPDATE_PREIMAGE_UNAVAILABLE', 'MISSING_ORIGINAL_HEADER', 'NITRO_SYSTEM_CONTEXT_UNAVAILABLE', 'CHAIN_CONFIG_UNAVAILABLE'}
        require((detail['classification'] == 'HOST_STOP_MISSING_STATE') == (detail['code'] in missing), 'TYPED_FAILURE_CLASSIFICATION')
    return value


def replay(sdk, ref, grant):
    python_required()
    require(signal.getitimer(signal.ITIMER_REAL)[0] == 0, 'CALLER_TIMER_ACTIVE')
    began = time.monotonic()
    p = sdk.describe(ref)
    value = load(grant, 65536)
    b = binding(sdk, p, value['body']['binding']['trustedCheckpoint'])
    r = runtime(sdk)
    lock, supervise, cleanup, admission = guards()
    with lock(sdk.home):
        body = authority.consume(grant, sdk.home / 'consents', b, read_key(sdk.home))
        try:
            return execute_consumed(sdk, p, b, r, body, began, supervise, cleanup, admission)
        except BaseException as error:
            out = no_links(b['outputPath'])
            dispatched = (out / 'runtime/DISPATCH_INTENT.json').exists()
            result = {'status': 'INTERRUPTED_UNVERIFIED' if dispatched else 'HOST_STOP',
                      'caseId': b['caseId'], 'capsuleId': b['capsuleId'],
                      'operationCommitment': b['operationCommitment'],
                      'causeCode': type(error).__name__ + ': ' + str(error)[:1024],
                      'nativeInvocations': None if dispatched else {'ACTUAL': 0, 'BRANCH': 0, 'B': 0},
                      'cleanupConfirmed': not dispatched, 'operationPermanentlyClosed': True,
                      'automaticRetry': False, 'RPC': 0, 'WSS': 0, 'externalDelivery': 'HOLD',
                      'runDirectory': str(out)}
            # The consent directory survives even if the output cannot be created.
            save(no_links(grant).parent / 'RESULT.json', result)
            if out.is_dir() and not (out / 'RESULT.json').exists():
                save(out / 'RESULT.json', result)
                if not (out / 'MANIFEST.json').exists():
                    save(out / 'MANIFEST.json', {'files': tree(out), 'authenticity': 'LOCAL_INTEGRITY_NOT_SIGNATURE'})
            return result


def execute_consumed(sdk, p, b, r, body, began, supervise, cleanup, admission):
    out = no_links(b['outputPath'])
    out.mkdir(mode=0o700)
    sync(out.parent)
    rt = out / 'runtime'
    rt.mkdir(mode=0o700)
    raw = canonical(body) + b'\n'
    save(rt / 'STARTED.json', {'operationCommitment': b['operationCommitment'], 'authoritySha256': digest(raw), 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'authorityConsumed': True})
    final = {'status': 'INTERRUPTED_UNVERIFIED', 'caseId': p['caseId'], 'capsuleId': p['capsuleId'], 'operationCommitment': b['operationCommitment'], 'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}, 'RPC': 0, 'WSS': 0, 'automaticRetry': False, 'operationPermanentlyClosed': True, 'externalDelivery': 'HOLD'}
    dispatched = False
    measured = None
    admission_started = False
    native = None

    def interrupted(signum, frame):
        raise InterruptedError('NATIVE_WORKFLOW_INTERRUPTED_OR_DEADLINE')
    require(signal.getitimer(signal.ITIMER_REAL)[0] == 0, 'CALLER_TIMER_ACTIVE')
    old = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM)}
    signal.setitimer(signal.ITIMER_REAL, max(0.001, 135 - (time.monotonic() - began)))
    try:
        for directory in ('inputs', 'artifacts'):
            (out / directory).mkdir(mode=0o700)
        path, _ = sdk.registry.resolve(p['caseId'])
        for src, dest in [(path / 'CAPSULE.json', out / 'inputs/CAPSULE.json'), (path / 'BLOCK_PACKAGE.json', out / 'inputs/BLOCK_PACKAGE.json'), (sdk.home / 'plans' / p['planId'] / 'PLAN.json', out / 'inputs/PLAN.json')]:
            with dest.open('xb') as stream:
                stream.write(read(src, MAX_PACKAGE))
                stream.flush()
                os.fsync(stream.fileno())
        for name, target in [('worker', 'rhook-saved-pair'), ('sensor', 'rhook-host-sensor')]:
            shutil.copyfile(r['files'][name]['path'], out / 'artifacts' / target)
            require(sha(out / 'artifacts' / target) == r['files'][name]['sha256'], 'STAGING_ARTIFACT_DRIFT')
            (out / 'artifacts' / target).chmod(0o700)
        save(out / 'BINDING.json', b)
        save(rt / 'AUTHORITY.json', body)
        if _settings(sdk)[0] != PROFILE:
            from .scenario.power import observe
            observe(rt / 'POWER')
        admission_started = True
        decision, samples = admission(out / 'artifacts/rhook-host-sensor', rt / 'HOST')
        save(rt / 'HOST_ADMISSION.json', {'accepted': True, 'profile': _settings(sdk)[0], 'policySha256': _settings(sdk)[1], 'decision': decision})
        require(time.monotonic() - began < 10, 'PREPARATION_ADMISSION_DEADLINE')
        save(rt / 'DISPATCH_INTENT.json', {'operationCommitment': b['operationCommitment']})
        dispatched = True
        final['nativeInvocations'] = None
        measured = supervise(raw, out, out / 'artifacts/rhook-host-sensor', samples[-1])
        final['resources'] = measured
        native = validate_completion(load(rt / 'NATIVE_COMPLETION.json'), b['operationCommitment'], _settings(sdk)[0])
        final['nativeInvocations'] = native['result']['nativeInvocations']
        final['rawTerminal'] = native['result']['terminal']
        final['failureDetail'] = native.get('failureDetail')
        require(measured['workerReaped'] and measured['exitCode'] == 0 and (measured['stop'] is None) and measured['resourcesReliable'] and (measured['wallSeconds'] <= 120) and (measured['workerAndObserverCpuSeconds'] <= 120) and (measured['sampledPeakWorkerRSS'] <= 1 << 30), 'NATIVE_OR_RESOURCE_STOP')
        require(native['result']['terminal'] == 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED' and native['result']['canonicalActualValid'] and (native['result']['nativeInvocations'] == {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}), 'NATIVE_COMPLETION_REQUIRED')
        require(time.monotonic() - began <= 140, 'NATIVE_STAGE_DEADLINE')
        signal.setitimer(signal.ITIMER_REAL, 0)
        verified = _node_verify(sdk, out, max(0.001, 180 - (time.monotonic() - began)), record=True)
        save(rt / 'VERIFIED.json', verified)
        require(sum(x.stat().st_size for x in rt.rglob('*') if x.is_file()) <= 128 << 20, 'RUNTIME_STORAGE_LIMIT')
        require(time.monotonic() - began <= 180, 'WORKFLOW_DEADLINE')
        final['status'] = 'COMPLETED'
    except BaseException as error:
        final['causeCode'] = type(error).__name__ + ': ' + str(error)[:1024]
        final['status'] = 'HOST_STOP' if not dispatched else 'INTERRUPTED_UNVERIFIED'
        if native:
            detail = native.get('failureDetail') or {}
            if detail.get('classification') == 'HOST_STOP_MISSING_STATE':
                final['status'] = 'MISSING_WITNESS'
            elif native['result']['terminal'] == 'CANONICAL_EXECUTION_MISMATCH':
                final['status'] = 'CANONICAL_MISMATCH'
            elif native['result']['terminal'] != 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED':
                final['status'] = 'HOST_STOP'
            elif str(error).startswith('CASE_VERIFICATION_FAILED'):
                final['status'] = 'VERIFICATION_FAILED'
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for sig, handler in old.items():
            signal.signal(sig, handler)
    clean = cleanup(out, dispatched, measured, admission_started)
    final.update(cleanupConfirmed=clean, workerDispatchAttempted=dispatched, elapsedSeconds=time.monotonic() - began, runDirectory=str(out))
    if not clean:
        final['status'] = 'INTERRUPTED_UNVERIFIED'
    seal_result(out, final)
    return final


def seal_result(out, result):
    files = tree(out)
    files['RESULT.json'] = digest(canonical(result) + b'\n')
    save(out / 'MANIFEST.json', {'files': files, 'authenticity': 'LOCAL_INTEGRITY_NOT_SIGNATURE'})
    # Publish the terminal status only after its evidence inventory is durable.
    save(out / 'RESULT.json', result)


def verify(sdk, run):
    out = no_links(run)
    require(out.parent == sdk.home / 'runs', 'RUN_HOME_REQUIRED')
    manifest = load(out / 'MANIFEST.json', 2 << 20)
    require(tree(out, omit=('MANIFEST.json',)) == manifest['files'], 'RECORDED_MANIFEST_DRIFT')
    final = load(out / 'RESULT.json')
    require(final['status'] == 'COMPLETED' and final['cleanupConfirmed'] is True, 'COMPLETED_CLEAN_RUN_REQUIRED')
    b = load(out / 'BINDING.json')
    p = sdk.describe(b['planId'])
    require(binding(sdk, p, b['trustedCheckpoint']) == b and str(out) == b['outputPath'], 'RUN_BINDING_DRIFT')
    for path, key in [('inputs/CAPSULE.json', 'capsuleSha256'), ('inputs/PLAN.json', 'planSha256'), ('inputs/BLOCK_PACKAGE.json', 'packageSha256'), ('artifacts/rhook-saved-pair', 'binarySha256')]:
        require(sha(out / path) == b[key], 'RECORDED_INPUT_OR_BINARY_DRIFT')
    value = _node_verify(sdk, out)
    return dict(value, caseId=p['caseId'], capsuleId=p['capsuleId'], mode='RECORDED_VERIFICATION', witnessClosure='COMPLETE_FOR_THIS_EXECUTED_PLAN_ONLY')
