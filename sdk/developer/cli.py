"""Controlled Pair03 interface. Planning and verification never execute history."""
import argparse
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

LIB = Path(__file__).resolve().parents[1]
PREFIX = LIB.parent
sys.path.insert(0, str(LIB))
from developer.files import accepted_source, artifact_pins, canonical, dependencies, digest, load, no_links, read, require, save, sha, sync, tree

SUCCESS = {'INSPECTED', 'PLANNED', 'COMPLETED', 'RECORDED_INTEGRITY_PASS'}

def installation():
    require(sys.version_info >= (3, 12) and not sys.flags.optimize, 'PYTHON_3_12_UNOPTIMIZED_REQUIRED')
    manifest = load(PREFIX / 'INSTALL.json')
    require(manifest['schema'] == 'rhook/controlled-alpha-install/0.1' and manifest['prefix'] == str(PREFIX), 'INSTALL_PREFIX_CHANGED')
    accepted_source(LIB)
    pins = artifact_pins(LIB)
    require(tree(LIB / 'developer') == manifest['developerFiles'], 'INSTALLER_CODE_DRIFT')
    require(sha(PREFIX / 'BUILD.json') == manifest['buildRecordSha256'], 'REGISTERED_BUILD_DRIFT')
    require(sha(PREFIX / 'bin/rhook') == manifest['launcherSha256'], 'LAUNCHER_DRIFT')
    for name, row in pins['files'].items():
        p = PREFIX / 'assets' / name
        require(sha(p) == row['sha256'] and p.stat().st_size == row['bytes'], 'ASSET_DRIFT: ' + name)
    dependencies(LIB / 'engine/adapters/hookr-case/node_modules')
    return pins

def environment():
    return {'PATH': str(PREFIX / 'assets') + ':/usr/bin:/bin', 'LANG': 'C', 'TZ': 'UTC', 'PYTHONDONTWRITEBYTECODE': '1'}

def engine_command(args):
    runner = 'import sys;sys.path.insert(0,sys.argv[1]);from case_sdk.cli import main;raise SystemExit(main(sys.argv[2:]))'
    return [sys.executable, '-I', '-B', '-c', runner, str(LIB / 'engine'), *args]

def ordinary(args):
    # -I intentionally removes inherited Python paths; the entry script's
    # own directory is restored in a tiny explicit module runner below.
    result = subprocess.run(engine_command(args), env=environment(), capture_output=True, timeout=45)
    require(result.returncode == 0 or result.stdout, 'ENGINE_CLI_FAILED')
    require(len(result.stdout) <= 65536 and len(result.stderr) <= 65536, 'CLI_OUTPUT_LIMIT')
    value = json.loads(result.stdout.decode('utf-8', errors='strict'))
    if result.returncode != 0:
        require(value.get('status') not in SUCCESS, 'CONTRADICTORY_ENGINE_EXIT')
    return value

def recorded(run, pins):
    run = no_links(run)
    expected = load(run / 'MANIFEST.json')['files']
    require(tree(run, omit=('MANIFEST.json',)) == expected, 'RECORDED_MANIFEST_DRIFT')
    b = load(run / 'proposal/AUTHORIZATION_BINDINGS.json')
    require(b['sourceCommitment'] == pins['sourceCommitment'] and b['binarySha256'] == pins['files']['worker']['sha256'], 'RECORDED_SOURCE_OR_WORKER')
    require(b['policySha256'] == pins['policySha256'] and b['sensorSha256'] == pins['files']['sensor']['sha256'], 'RECORDED_POLICY_OR_SENSOR')
    for relative, pin in [('artifacts/rhook-saved-pair', b['binarySha256']), ('artifacts/rhook-host-sensor', b['sensorSha256']), ('inputs/BLOCK_PACKAGE.json', b['packageSha256']), ('inputs/RUNTIME_PLAN.json', b['runtimePlanSha256'])]:
        require(sha(run / relative) == pin, 'RECORDED_STAGED_ARTIFACT')
    command = [str(PREFIX / 'assets/node'), '--import', str(LIB / 'engine/adapters/hookr-case/test/no-network.mjs'), str(LIB / 'engine/case_sdk/verify.mjs'), str(run / 'inputs/BLOCK_PACKAGE.json'), str(run / 'inputs/RUNTIME_PLAN.json'), str(run)]
    result = subprocess.run(command, env=environment(), capture_output=True, timeout=40)
    require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 2 << 20, 'RECORDED_VERIFICATION_FAILED')
    value = json.loads(result.stdout.decode('utf-8', errors='strict'))
    require(value['status'] == 'RECORDED_INTEGRITY_PASS' and value['mode'] == 'RECORDED_VERIFICATION', 'RECORDED_RESULT_REQUIRED')
    return value

def replay(workspace, plan, authority, began):
    # Import only the already reauthenticated engine modules. Nothing here
    # issues approval, samples host resources, or constructs an EVM.
    sys.path.insert(0, str(LIB / 'engine'))
    from case_sdk.contract import validate_approval
    from case_sdk.workspace import resolve_plan
    resolved = resolve_plan(no_links(workspace), plan)
    binding = resolved['binding']
    raw_authority = read(authority, 16383)
    validate_approval(binding, raw_authority, int(time.time()))
    require(time.monotonic() - began < 10, 'WORKFLOW_STARTUP_DEADLINE')
    controls = no_links(no_links(workspace) / 'workflows')
    controls.mkdir(exist_ok=True); sync(controls.parent)
    control = no_links(controls / plan)
    # The durable outer latch also forbids redispatch after a controller crash.
    control.mkdir(); sync(controls)
    with (control / 'AUTHORITY.json').open('xb') as f:
        f.write(raw_authority); f.flush(); os.fsync(f.fileno())
    save(control / 'DISPATCH_INTENT.json', {'operationCommitment': binding['operationCommitment'], 'authoritySha256': digest(raw_authority), 'oneDispatchOnly': True, 'automaticRetry': False})
    command = engine_command(['replay', '--workspace', str(no_links(workspace)), '--plan', plan, '--authority', str(control / 'AUTHORITY.json')])
    deadline, reaped, child, code, failure = False, False, None, None, None
    cleanup_failures = []
    def interrupted(signum, frame):
        raise InterruptedError('WORKFLOW_INTERRUPTED')
    old_handlers = {sig: signal.signal(sig, interrupted) for sig in [signal.SIGINT, signal.SIGTERM]}
    try:
        with (control / 'stdout.json').open('xb') as stdout, (control / 'stderr.txt').open('xb') as stderr:
            try:
                child = subprocess.Popen(command, env=environment(), stdout=stdout, stderr=stderr, start_new_session=True)
                save(control / 'PROCESS.json', {'pid': child.pid, 'executable': command[0], 'operationCommitment': binding['operationCommitment']})
                # Reserve two bounded cleanup waits plus one second for records.
                code = child.wait(timeout=max(0.001, 169 - (time.monotonic() - began)))
                reaped = True
            except BaseException as error:
                failure = type(error).__name__ + ': ' + str(error)[:240]
                deadline = isinstance(error, subprocess.TimeoutExpired)
                if child is not None:
                    # Only this owned SDK child is signalled. It receives one
                    # interruption and performs the preserved worker cleanup.
                    for sig in old_handlers: signal.signal(sig, signal.SIG_IGN)
                    try: child.terminate()
                    except OSError as cleanup_error:
                        cleanup_failures.append('terminate: ' + str(cleanup_error)[:160])
                    try:
                        code = child.wait(timeout=5); reaped = True
                    except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                        cleanup_failures.append('grace wait: ' + str(cleanup_error)[:160])
                        try: child.kill()
                        except OSError as kill_error:
                            cleanup_failures.append('kill: ' + str(kill_error)[:160])
                        try:
                            code = child.wait(timeout=5); reaped = True
                        except (OSError, subprocess.TimeoutExpired) as kill_error:
                            cleanup_failures.append('final wait: ' + str(kill_error)[:160])
                for stream in [stdout, stderr]:
                    stream.flush(); os.fsync(stream.fileno())
    finally:
        for sig, handler in old_handlers.items(): signal.signal(sig, handler)
    elapsed = time.monotonic() - began
    deadline = deadline or elapsed > 180
    try:
        value = load(control / 'stdout.json', 65536)
    except (ValueError, OSError):
        value = {'status': 'INTERRUPTED_UNVERIFIED', 'nativeInvocations': None}
    if failure or deadline or not reaped or code != 0 and value.get('status') in SUCCESS:
        value = {'status': 'INTERRUPTED_UNVERIFIED', 'nativeInvocations': None, 'rawEngineResult': value}
    value['outerWorkflow'] = {'seconds': elapsed, 'deadlineExceeded': deadline, 'cliExitCode': code, 'cliReaped': reaped, 'controllerFailure': failure, 'cleanupFailures': cleanup_failures, 'operationPermanentlyClosed': True, 'automaticRetry': False}
    value['mode'] = 'NATIVE_REPLAY'
    save(control / 'RESULT.json', value)
    return value

def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('inspect'); a.add_argument('--workspace', type=Path, required=True); a.add_argument('--package', type=Path)
    a = sub.add_parser('plan'); a.add_argument('--workspace', type=Path, required=True); a.add_argument('--lp-bps', required=True)
    a = sub.add_parser('replay'); a.add_argument('--workspace', type=Path, required=True); a.add_argument('--plan', required=True); a.add_argument('--authority', type=Path, required=True)
    a = sub.add_parser('verify'); a.add_argument('--run', type=Path, required=True)
    return p

def main(argv=None):
    began = time.monotonic()
    args = parser().parse_args(argv)
    try:
        pins = installation()
        if args.command == 'inspect':
            workspace = no_links(args.workspace)
            require(not workspace.is_relative_to(PREFIX), 'WORKSPACE_INSIDE_INSTALLATION')
            workspace.parent.mkdir(parents=True, exist_ok=True)
            value = ordinary(['inspect', '--workspace', str(no_links(args.workspace)), '--package', str(no_links(args.package or PREFIX / 'assets/BLOCK_PACKAGE.json')), '--build-record', str(PREFIX / 'BUILD.json')])
        elif args.command == 'plan':
            value = ordinary(['plan', '--workspace', str(no_links(args.workspace)), '--expected-old', '100', '--lp-bps', args.lp_bps])
        elif args.command == 'verify': value = recorded(args.run, pins)
        else: value = replay(args.workspace, args.plan, args.authority, began)
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        value = {'status': 'SETUP_OR_INPUT_STOP', 'causeCode': str(error)[:240], 'automaticRetry': False}
    print(json.dumps(value, ensure_ascii=True))
    return 0 if value.get('status') in SUCCESS else 1

if __name__ == '__main__': raise SystemExit(main())
