"""Trusted-local single-use launcher. --check never launches native execution."""
import datetime
import hashlib
import importlib.util
import math
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            result.update(chunk)
    return result.hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def store(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def operation_id(operation):
    raw = json.dumps(operation, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(b'rhook/canonical-actual-operation/0.1\n' + raw).hexdigest()


def verify_static():
    freeze = json.loads((ROOT / 'FREEZE.json').read_text())
    assert sha(ROOT / 'MANIFEST.json') == freeze['manifestSha256'], 'MANIFEST_PIN'
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    expected = {'MANIFEST.json', 'FREEZE.json'}
    for entry in manifest['files']:
        rel = Path(entry['path'])
        assert not rel.is_absolute() and '..' not in rel.parts and rel.parts[0] != 'runtime'
        p = ROOT / rel
        assert not p.is_symlink() and p.is_file() and p.stat().st_size == entry['bytes']
        assert sha(p) == entry['sha256'], entry['path']
        expected.add(rel.as_posix())
    actual = set()
    for p in ROOT.rglob('*'):
        assert not p.is_symlink(), 'SYMLINK'
        if p.is_file() and p.name != '.DS_Store' and p.relative_to(ROOT).parts[0] != 'runtime':
            actual.add(p.relative_to(ROOT).as_posix())
    assert expected == actual, 'STATIC_FILE_SET'
    assert len(manifest['files']) == manifest['fileCount'] == freeze['contentFiles']
    op = json.loads((ROOT / 'proposal/OPERATION.json').read_text())
    oid = operation_id(op)
    assert oid == freeze['operationCommitment'], 'OPERATION_BINDING'
    for identity in op['externalIdentities']:
        p = Path(identity['path'])
        assert p.stat().st_size == identity['bytes'] and sha(p) == identity['sha256'], 'EXTERNAL_IDENTITY'
    for predecessor in op['preservedManifests']:
        path = Path(predecessor['path'])
        assert sha(path) == predecessor['sha256'], 'PREDECESSOR_MANIFEST'
        for entry in json.loads(path.read_text())['files']:
            rel = Path(entry['path'])
            assert not rel.is_absolute() and '..' not in rel.parts
            p = path.parent / rel
            assert p.is_file() and not p.is_symlink() and p.stat().st_size == entry['bytes']
            assert sha(p) == entry['sha256'], 'PREDECESSOR_CONTENT'
    return op, oid


def require_authority(path, oid):
    path = Path(path)
    assert path.is_file() and not path.is_symlink() and path.stat().st_size < 8192, 'AUTHORITY_REQUIRED'
    auth = json.loads(path.read_text())
    assert auth.get('founderApproved') is True and auth.get('operationCommitment') == oid, 'EXACT_FOUNDER_AUTHORITY_REQUIRED'
    assert auth.get('maximumInvocations') == {'ACTUAL': 1, 'BRANCH': 0, 'B': 0}, 'INVOCATION_AUTHORITY'
    assert auth.get('rpcRequests') == 64 and auth.get('retries') == 0 and auth.get('prospectiveSelectionAuthorized') is True, 'AUTHORITY_SCOPE'
    return auth


def assess_host(raw):
    assert raw['bootBefore'] == raw['bootAfter'] and raw['bootAfter'], 'BOOT_CHANGED'
    samples = raw['samples']
    assert len(samples) == 2, 'SAMPLE_COUNT'
    x, y = samples
    for index, s in enumerate(samples):
        assert s['source'] == 'DARWIN_SYSCTL_PRESSURE_SWAP_VM_STAT/0.2' and s['seq'] == index
        assert s['physicalBytes'] == 25769803776 and s['swapPageBytes'] in (4096, 16384)
        assert 0 < int(s['beganNs']) <= int(s['endedNs'])
        for key in ['swapInPagesBefore', 'swapInPages', 'swapOutPagesBefore', 'swapOutPages', 'swapUsedBeforeBytes', 'swapUsedBytes']:
            assert type(s[key]) is int and 0 <= s[key] <= 9007199254740991, 'COUNTER_ENCODING'
        assert s['swapInPages'] >= s['swapInPagesBefore'] and s['swapOutPages'] >= s['swapOutPagesBefore'], 'COUNTER_REGRESSION'
    assert x['swapPageBytes'] == y['swapPageBytes'], 'PAGE_SIZE_CHANGED'
    gap = (int(y['beganNs']) - int(x['endedNs'])) / 1e9
    assert 0.9 <= gap <= 2, 'UNRELIABLE_TIMING'
    assert y['swapInPagesBefore'] >= x['swapInPages'] and y['swapOutPagesBefore'] >= x['swapOutPages'], 'COUNTER_REGRESSION'
    pressures = [s[k] for s in samples for k in ['pressureBefore', 'pressureAfter']]
    assert all(type(v) is int and v in (1, 2, 4) for v in pressures), 'PRESSURE_ENCODING'
    assert all(v == 1 for v in pressures), 'ABNORMAL_MEMORY_PRESSURE'
    outs = y['swapOutPages'] - x['swapOutPagesBefore']
    swaps = [x['swapUsedBeforeBytes'], x['swapUsedBytes'], y['swapUsedBeforeBytes'], y['swapUsedBytes']]
    assert outs == 0 and swaps == sorted(swaps, reverse=True), 'ACTIVE_SWAP_OUTPUT_OR_USAGE_GROWTH_INCONCLUSIVE'
    return {'status': 'ADMISSION_PASS', 'pressureReads': pressures, 'swapOutDeltaPages': outs,
            'swapInDeltaPages': y['swapInPages'] - x['swapInPagesBefore'], 'swapUsedBytes': y['swapUsedBytes'],
            'bootSession': raw['bootAfter'], 'reservedHeadroomEstablished': False, 'continuousHostPressureMonitoring': False}


def host_admission(op, directory):
    observer = op['hostObserver']
    began = time.monotonic()
    proc = subprocess.run([observer['node'], str(ROOT / 'tools/host_check.mjs')],
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=8,
                          env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'TZ': 'UTC'})
    store(directory / 'HOST_RAW.json', {'stdout': proc.stdout.decode(errors='replace'),
                                      'stderr': proc.stderr.decode(errors='replace'), 'exitCode': proc.returncode,
                                      'elapsedSeconds': time.monotonic() - began})
    assert proc.returncode == 0 and not proc.stderr and len(proc.stdout) < 65536, 'UNRELIABLE_HOST_OBSERVER'
    admitted = assess_host(json.loads(proc.stdout))
    store(directory / 'HOST_ADMISSION.json', admitted)
    return admitted


def process_rows():
    # Executable identity only: never argv, environment or command-line secrets.
    p = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,rss=,comm='],
                       capture_output=True, text=True, timeout=1, check=True)
    assert len(p.stdout) < 2 * 1024 * 1024, 'PROCESS_OBSERVER_OUTPUT'
    rows = {}
    for line in p.stdout.splitlines():
        fields = line.strip().split(None, 4)
        assert len(fields) == 5, 'PROCESS_OBSERVER_ENCODING'
        pid, ppid, pgid, rss = map(int, fields[:4])
        assert pid > 0 and min(ppid, pgid, rss) >= 0
        rows[pid] = {'pid': pid, 'ppid': ppid, 'pgid': pgid, 'rssBytes': rss * 1024}
    return rows


def run_monitored(command, directory, limits, env, stdin_payload=None):
    """Sampled RSS enforcement, kernel CPU/file caps, bounded stream capture."""
    directory = Path(directory)
    directory.mkdir(exist_ok=False)
    def child_limits():
        resource.setrlimit(resource.RLIMIT_CPU, (limits['cpuSeconds'], limits['cpuSeconds']))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits['outputBytes'], limits['outputBytes']))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    began = time.monotonic()
    proc = None
    stop = None
    count, peak, captured = 0, 0, 0
    selected = selectors.DefaultSelector()
    files = {}
    last_sample = None
    interrupted = []
    prior_handlers = {}
    diagnostic = None
    native_phase = None
    native_events = 0
    event_buffer = b''
    try:
        for name in ('stdout', 'stderr'):
            files[name] = (directory / (name + '.log')).open('xb')
        telemetry = (directory / 'resources.jsonl').open('x')
        for sig in (signal.SIGTERM, signal.SIGINT):
            prior_handlers[sig] = signal.signal(sig, lambda number, frame: interrupted.append(number))
        proc = subprocess.Popen(command, stdin=subprocess.PIPE if stdin_payload is not None else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, cwd=ROOT, start_new_session=True, preexec_fn=child_limits)
        if stdin_payload is not None:
            assert len(stdin_payload) <= 8192
            proc.stdin.write(stdin_payload)
            proc.stdin.close()
        store(directory / 'PROCESS_STARTED.json', {'pid': proc.pid, 'pgid': proc.pid, 'utc': utc(), 'command': command,
                                                   'kernelCpuSeconds': limits['cpuSeconds'], 'noRepeat': True})
        for stream, name in ((proc.stdout, 'stdout'), (proc.stderr, 'stderr')):
            os.set_blocking(stream.fileno(), False)
            selected.register(stream, selectors.EVENT_READ, name)
        while proc.poll() is None or selected.get_map():
            now = time.monotonic()
            if now - began > limits['wallSeconds']:
                stop = 'WALL_TIME_LIMIT'
            if native_phase is not None and now - native_phase > limits.get('nativeWallSeconds', 120):
                stop = 'NATIVE_WALL_TIME_LIMIT'
            if interrupted:
                stop = 'EXTERNAL_SIGNAL'
            if proc.poll() is None and (last_sample is None or now - last_sample >= limits['monitorMs'] / 1000):
                if last_sample is not None and now - last_sample > limits['maximumTelemetryGapSeconds']:
                    stop = 'RESOURCE_TELEMETRY_GAP'
                rows = process_rows()
                observed = time.monotonic()
                if observed - now > limits['maximumTelemetryGapSeconds'] or (last_sample is not None and observed - last_sample > limits['maximumTelemetryGapSeconds']):
                    stop = 'RESOURCE_TELEMETRY_GAP'
                native = rows.get(proc.pid)
                if native:
                    assert native['pgid'] == proc.pid, 'PROCESS_GROUP_CHANGED'
                    descendants = [r for r in rows.values() if r['ppid'] == proc.pid]
                    if descendants:
                        stop = 'UNEXPECTED_NATIVE_CHILD_PROCESS'
                    rss = native['rssBytes']
                    peak = max(peak, rss)
                    if rss > limits['nativeRssBytes']:
                        stop = 'OBSERVED_NATIVE_RSS_LIMIT'
                    own = rows.get(os.getpid())
                    if own is None or own['rssBytes'] > limits['launcherRssBytes']:
                        stop = 'LAUNCHER_RSS_OR_TELEMETRY_FAILURE'
                    telemetry.write(json.dumps({'elapsedSeconds': observed - began, 'sampleDurationSeconds': observed - now, 'pid': proc.pid,
                                                'nativeRssBytes': rss, 'launcherRssBytes': own['rssBytes'] if own else None}) + '\n')
                    telemetry.flush()
                    count += 1
                last_sample = now
            if stop:
                break
            for key, _ in selected.select(timeout=limits['monitorMs'] / 1000):
                data = os.read(key.fileobj.fileno(), min(65536, limits['outputBytes'] - captured + 1))
                if not data:
                    selected.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                remaining = limits['outputBytes'] - captured
                files[key.data].write(data[:remaining])
                captured += min(len(data), remaining)
                if key.data == 'stdout' and limits.get('requireJsonEvents'):
                    event_buffer += data[:remaining]
                    while b'\n' in event_buffer:
                        line, event_buffer = event_buffer.split(b'\n', 1)
                        assert len(line) <= 262144, 'NATIVE_EVENT_LINE_LIMIT'
                        event = json.loads(line)
                        if event.get('event') == 'NATIVE_REPLAY_ENTERED':
                            native_events += 1
                            assert native_events == 1, 'DUPLICATE_NATIVE_ENTRY'
                            native_phase = time.monotonic()
                    assert len(event_buffer) <= 262144, 'NATIVE_EVENT_LINE_LIMIT'
                if len(data) > remaining:
                    stop = 'COMBINED_OUTPUT_LIMIT'
                    break
    except BaseException as exc:
        stop = stop or 'LAUNCH_OR_TELEMETRY_FAILURE_' + type(exc).__name__
        diagnostic = type(exc).__name__ + ':' + str(exc)[:512]
    finally:
        if proc is not None:
            # Only our newly created session; no lookup or termination of other jobs.
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                stop = stop or 'OWNED_PROCESS_CLEANUP_UNCERTAIN'
        for key in list(selected.get_map().values()):
            key.fileobj.close()
        selected.close()
        for stream in list(files.values()) + ([telemetry] if 'telemetry' in locals() else []):
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        for sig, handler in prior_handlers.items():
            signal.signal(sig, handler)
    result = {'exitCode': proc.returncode if proc else None, 'stopCode': stop, 'diagnostic': diagnostic,
              'elapsedSeconds': time.monotonic() - began, 'nativePeakRssBytesSampled': peak,
              'resourceSamples': count, 'capturedOutputBytes': captured, 'nativeEntryEvents': native_events, 'retries': 0,
              'memoryEnforcement': 'SAMPLED_RSS_NOT_ATOMIC_RESERVATION_OR_EXACT_PEAK'}
    store(directory / 'PROCESS_COMPLETION.json', result)
    return result


def credential_payload(op):
    loader = Path(op['credentialBinding']['loader'])
    assert sha(loader) == op['credentialBinding']['loaderSha256'], 'CREDENTIAL_LOADER_PIN'
    spec = importlib.util.spec_from_file_location('credential_channel_only', loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    endpoint, _ = module.endpoint()
    from urllib.parse import urlsplit
    u = urlsplit(endpoint)
    assert u.scheme == 'https' and u.netloc == op['credentialBinding']['host'] and u.path.startswith('/v2/') and not u.query and not u.fragment, 'ENDPOINT_CAPABILITY_BINDING'
    return json.dumps({'endpoint': endpoint}).encode()


def validate_native_completion(native, directory, op, monitored):
    result = native['result']
    allowed = {'CANONICAL_ACTUAL_ROOTS_MATCH', 'HOST_STOP_MISSING_STATE', 'CANONICAL_EXECUTION_MISMATCH', 'RUNTIME_OR_RESOURCE_STOP', 'PROSPECTIVE_TARGET_NOT_FOUND'}
    assert result['terminal'] in allowed and result['nativeAttempts'] in (0, 1)
    assert result['rpcRequests'] <= op['limits']['rpcRequests'] and result['responseBytesRead'] <= op['limits']['responseBytes'], 'RPC_BUDGET'
    assert native['resourceUsageReliable'] is True, 'NATIVE_RESOURCE_TELEMETRY'
    assert native['maxRSSBytes'] <= op['limits']['nativeRssBytes'], 'KERNEL_PEAK_RSS_LIMIT'
    assert native['cpuUsedSeconds'] <= op['limits']['cpuSeconds'], 'KERNEL_CPU_LIMIT'
    transcript = (directory / 'RPC_TRANSCRIPT.json').read_bytes()
    assert hashlib.sha256(b'rhook/prospective-rpc-transcript/0.1\n' + transcript).hexdigest() == result['rpcTranscriptCommitment'], 'RPC_TRANSCRIPT_COMMITMENT'
    if result.get('finalWitnessCommitment'):
        raw = (directory / 'FINAL_WITNESS.json').read_bytes()
        assert hashlib.sha256(b'rhook/native-prestate-witness/0.1\n' + raw).hexdigest() == result['finalWitnessCommitment'], 'FINAL_WITNESS_COMMITMENT'
    if result['nativeAttempts']:
        assert monitored['nativeEntryEvents'] == 1
        precommit = json.loads((directory / 'INPUT_PRECOMMIT.json').read_text())
        assert sha(directory / 'BLOCK_PACKAGE.json') == result['inputPackageSha256'] == precommit['packageSha256']
        assert precommit['inventory'] == result['inventory']
        assert precommit['initialWitnessCommitment'] == result['initialWitnessCommitment']
        assert precommit['finalWitnessFrozenBeforeExecution'] is False
        assert precommit['prospectiveOperationCommitment'] == operation_id(op), 'PRECOMMIT_POLICY_BINDING'
        assert precommit['acquisitionExecutionPolicyFrozenBeforeCapture'] is True
    if result['terminal'] == 'CANONICAL_ACTUAL_ROOTS_MATCH':
        assert monitored['exitCode'] == 0 and result['nativeAttempts'] == 1 and result['nativeResult']['matched'] is True
        inv = result['inventory']; out = result['nativeResult']
        assert out['inputCommitment'] == inv['inputCommitment']
        assert out['stateRoot'] == inv['expectedStateRoot'] and out['receiptsRoot'] == inv['expectedReceiptsRoot']
        assert out['blockHash'] == inv['blockHash'] and out['transactions'] == inv['transactions']
        assert 2 <= out['transactions'] <= 8 and result['finalWitnessComplete'] is True
    else:
        assert monitored['exitCode'] != 0
    return result


def launch():
    op, oid = verify_static()
    runtime = ROOT / 'runtime'
    auth = require_authority(runtime / 'FOUNDER_AUTHORIZATION.json', oid)
    store(runtime / 'STARTED.json', {'operationCommitment': oid, 'authoritySha256': sha(runtime / 'FOUNDER_AUTHORIZATION.json'),
                                   'utc': utc(), 'maximumInvocations': auth['maximumInvocations'], 'prospectiveSelectionAuthorized': True, 'automaticRetry': False})
    started = time.monotonic()
    result = {'terminal': 'RUNTIME_OR_RESOURCE_STOP', 'operationCommitment': oid, 'automaticSuccessor': False}
    try:
        host_admission(op, runtime)
        payload = credential_payload(op)
        remaining_ms = math.floor((op['limits']['wallSeconds'] - (time.monotonic() - started)) * 1000)
        assert remaining_ms > 0, 'OVERALL_DEADLINE'
        limits = dict(op['limits']); limits['wallSeconds'] = remaining_ms / 1000
        monitored = run_monitored([str(ROOT / 'artifacts/prestate-prospective'), '--run-prospective', str(runtime / 'native')],
                                  runtime / 'native', limits,
                                  {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'TZ': 'UTC', 'GOMAXPROCS': '2',
                                   'GOMEMLIMIT': '1073741824', 'GOTRACEBACK': 'single', 'RHOOK_EXACT_OPERATION': oid,
                                   'RHOOK_REMAINING_MS': str(remaining_ms)}, stdin_payload=payload)
        del payload
        result['monitor'] = monitored
        completion = runtime / 'native/NATIVE_COMPLETION.json'
        if not monitored['stopCode'] and completion.is_file():
            native = json.loads(completion.read_text())
            assert native['operationCommitment'] == oid
            validated = validate_native_completion(native, runtime / 'native', op, monitored)
            result['terminal'] = validated['terminal']; result['nativeResult'] = native
        else:
            result['cause'] = monitored['stopCode'] or 'INCOMPLETE_NATIVE_COMPLETION'
            result['partialEvidenceOnly'] = True
    except BaseException as exc:
        # Never stringify credential-provider/transport exception objects.
        result['cause'] = 'OPERATION_EXCEPTION_' + type(exc).__name__
    store(runtime / 'FINAL_RESULT.json', result)
    print(json.dumps(result))
    return 0 if result['terminal'] == 'CANONICAL_ACTUAL_ROOTS_MATCH' else 1


if __name__ == '__main__':
    if sys.argv[1:] == ['--check']:
        op, oid = verify_static()
        print(json.dumps({'status': 'STATIC_READY_NO_EXECUTION', 'operationCommitment': oid,
                          'authorityPresent': (ROOT / 'runtime/FOUNDER_AUTHORIZATION.json').exists(),
                          'started': (ROOT / 'runtime/STARTED.json').exists(), 'nativeExecutions': 0}))
    elif sys.argv[1:] == ['--run']:
        sys.exit(launch())
    else:
        raise SystemExit('Use --check or --run; --run requires separate exact founder authorization.')
