"""One bounded acquisition/discovery, followed by a fresh offline scenario pair.

The private socket separates provider credentials from the native worker. This
module does not retry missing dependencies or treat discovery receipts as an
accepted counterfactual result. All execution belongs to one explicit consent.
"""
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time

from developer.files import canonical, digest, load, no_links, read, require, save, sha, sync
from .. import authority, native
from ..workflow import active_group, PROFILE as WORKFLOW_PROFILE
from . import api, host_v3, outcome, power

PROFILE = 'rhook/scenario-witness-discovery/0.1'
BUDGET = dict(requests=64, wallMs=30000, bytes=8 << 20, estimatedCU=1280,
              discoveryBaseline=1, discoveryVariant=1, offlineBaseline=1, offlineVariant=1, finalHeaderRequests=1)


def prepare(sdk, ref, output):
    plan = api.describe(sdk, ref)
    require(plan.get('assumptions',{}).get('gas')==10000000,'STALE_SCENARIO_PLAN_GAS')
    r = api.runtime(sdk)
    host = api.select_host(sdk, host_v3.PROFILE)
    output = no_links(output)
    require(len(str(output / 'broker.sock').encode()) <= 103, 'SHORT_PRIVATE_SOCKET_PATH_REQUIRED')
    b = dict(schema=PROFILE, planId=ref, planCommitment=plan['planCommitment'], intent=plan['intent'],
             outputPath=str(output), runtime=r, hostAdmission=host,
             sdkFilesCommitment=digest(canonical(host_v3.sdk_files())),
             budget=BUDGET, workflowCaptureProfile=WORKFLOW_PROFILE,
             retries=0, WSS=0, onchain=0, externalDelivery='HOLD')
    b['operationCommitment'] = digest((PROFILE + '\n').encode() + canonical(b))
    return b


def account(path):
    value = load(no_links(path), 65536)
    now = int(time.time() * 1000)
    require(value.get('schema') == 'rhook/scenario-account-assertions/0.1'
            and value.get('freePlan') is True and value.get('paidUsageDisabled') is True
            and value.get('chainId') == 4663, 'CONFIRMED_FREE_ACCOUNT_REQUIRED')
    require(type(value.get('remainingCU')) is int and value['remainingCU'] >= 2000
            and type(value.get('throughputCUPerSecond')) is int and value['throughputCUPerSecond'] >= 200,
            'ACCOUNT_BUDGET_REQUIRED')
    require(type(value.get('observedUnixMs')) is int and 0 <= now - value['observedUnixMs'] <= 600000,
            'FRESH_ACCOUNT_OBSERVATION_REQUIRED')
    return value


def _discover_once(sdk, spec_path, out, r, host, macro, key, previous, broker):
    """Discovery uses the same OS fence, with its own explicit source binding."""
    out.mkdir(mode=0o700)
    sync(out.parent)
    for name in ('runtime', 'inputs', 'artifacts'):
        (out / name).mkdir(mode=0o700)
    shutil.copyfile(spec_path, out / 'inputs/SCENARIO.json')
    spec = load(spec_path, 8 << 20)
    for name, src in [('rhook-saved-pair', r['files']['worker']), ('rhook-host-sensor', host['sensor'])]:
        shutil.copyfile(src['path'], out / 'artifacts' / name)
        require(sha(out / 'artifacts' / name) == src['sha256'], 'CLOSURE_STAGING_DRIFT')
        (out / 'artifacts' / name).chmod(0o700)
    b = dict(schema='rhook/scenario-operation/0.1', profile=api.PROFILE, planId=macro['planId'],
             scenarioCommitment=spec['scenarioCommitment'], scenarioSha256=sha(spec_path),
             binarySha256=r['files']['worker']['sha256'], sourceCommitment=r['sourceCommitment'],
             policySha256=api.POLICY_SHA, outputPath=str(out),
             parentOperation=macro['operationCommitment'], hostAdmission=host,
             sdkFilesCommitment=macro['sdkFilesCommitment'],
             maximumInvocations={'SCENARIO_BASELINE': 1, 'SCENARIO_VARIANT': 1},
             RPC=0, WSS=0, automaticRetry=False, externalDelivery='HOLD')
    b.update(discoveryProfile=PROFILE, discoverySocket=str(out.parent / 'broker.sock'),
             network='BROKER_ONLY_SHARED_MACRO_BUDGET')
    b['operationCommitment'] = digest(b'rhook/scenario-operation/0.1\n' + canonical(b))
    grants = sdk.home / 'scenarios/discovery-consents'
    grant = authority.issue(grants, b, key)
    body = authority.consume(grant, grants, b, key)
    raw = canonical(body) + b'\n'
    save(out / 'BINDING.json', b)
    save(out / 'runtime/STARTED.json', dict(operationCommitment=b['operationCommitment'], authoritySha256=digest(raw)))
    save(out / 'runtime/HOST_ADMISSION.json', dict(accepted=True, profile=api.PROFILE, policySha256=api.POLICY_SHA,
                                                 hostAdmission=host, parentAdmission=str(out.parent / 'HOST')))
    # Fresh macro admission immediately precedes capture/discovery; final gets
    # its own fresh admission after acquisition has closed.
    supervise = host_v3.supervise
    native.guards()
    from case_sdk.common import portable
    old_sample = portable.guards.sample_owned
    broker_samples = []
    def sample(proc):
        if broker is not None:
            require(broker.poll() in (None, 0), 'DISCOVERY_BROKER_EXITED')
            row = sample_broker(broker)
            if row:
                require(row['rssBytes'] <= 256 << 20, 'BROKER_SAMPLED_RSS_LIMIT')
                broker_samples.append(dict(row, elapsedSeconds=time.monotonic()))
        return old_sample(proc)
    try:
        portable.guards.sample_owned = sample
        measured = supervise(raw, out, Path(host['sensor']['path']), previous)
    finally:
        portable.guards.sample_owned = old_sample
        save(out / 'runtime/BROKER_SAMPLES.json', broker_samples)
    completion = outcome.require_stage(out / 'runtime', b['operationCommitment'], measured)
    require(completion['operationCommitment'] == b['operationCommitment'], 'CLOSURE_COMPLETION_LINK')
    require(measured['exitCode'] == 0 and measured['stop'] is None and measured['resourcesReliable'], 'CLOSURE_NATIVE_STOP')
    result = completion['result']
    require(result['status'] == 'SCENARIO_DISCOVERY_COMPLETED' and completion['producerEntries'] == 2
            and result['ownedBridgesClosed'] is True and result.get('discoveryOnly') is True,
            'CLOSURE_WORLD_COMPLETION_REQUIRED')
    return result, measured


def compare_worlds(discovered, final):
    fields = ('stateRoot', 'receiptsRoot', 'producedSyntheticHeader', 'systemTransactionHash',
              'actionMapping', 'receipts', 'actorBalanceBefore', 'actorBalanceAfter', 'actorNonceAfter', 'overlay')
    require(len(discovered['worlds']) == len(final['worlds']) == 2, 'TWO_COMPLETED_WORLDS_REQUIRED')
    for a, b in zip(discovered['worlds'], final['worlds']):
        require(a['world'] == b['world'] and all(a[k] == b[k] for k in fields), 'DISCOVERY_OFFLINE_DIVERGENCE')
    return dict(status='DISCOVERY_OFFLINE_DETERMINISTIC_RESULTS_MATCH', compared=list(fields),
                independentOriginalCopies=True, finalSource='NIL', qualifiedClaims=0)


def confirmed_acquisition(acquired, discovered):
    require(discovered.get('discoveryOnly') is True and discovered.get('producerInvocations') == 2
            and len(discovered.get('worlds', [])) == 2
            and discovered.get('status') == 'SCENARIO_DISCOVERY_COMPLETED', 'DISCOVERY_COUNT_UNCONFIRMED')
    return dict(acquired, nativeExecutions=discovered['producerInvocations'],
                nativeExecutionAccounting='CONFIRMED_DISCOVERY_NATIVE_COMPLETION')


def run(sdk, ref, output, *, credential_file, account_assertions, expected_operation,
        local_owner=False, mac_ready=False):
    require(local_owner is True and mac_ready is True, 'EXPLICIT_CLOSURE_OWNER_AND_READY_REQUIRED')
    require(active_group() is not None, 'OWNED_WORKFLOW_CONTEXT_REQUIRED')
    account(account_assertions)
    b = prepare(sdk, ref, output)
    require(b['operationCommitment'] == expected_operation, 'EXACT_CLOSURE_OPERATION_REQUIRED')
    out = no_links(output)
    require(not out.exists(), 'FRESH_CLOSURE_OUTPUT_REQUIRED')
    r, host = b['runtime'], b['hostAdmission']
    key = read(sdk.home / 'scenarios/.consent.key', 32)
    lock, _, _, _ = native.guards()
    began = time.monotonic()
    child = None
    result = dict(status='SCENARIO_CLOSURE_STOP', operationCommitment=expected_operation,
                  operationPermanentlyClosed=True, automaticRetry=False, externalDelivery='HOLD')
    with lock(sdk.home):
        # Permanent operation marker survives a failed admission; never retry.
        grant = authority.issue(sdk.home / 'scenarios/closure-consents', b, key)
        authority.consume(grant, sdk.home / 'scenarios/closure-consents', b, key)
        out.mkdir(mode=0o700)
        sync(out.parent)
        save(out / 'BINDING.json', b)
        try:
            power.observe(out / 'POWER')
            decision, samples = host_v3.admission(Path(host['sensor']['path']), out / 'HOST')
            save(out / 'HOST_ADMISSION.json', decision)
            require(b == prepare(sdk, ref, output), 'CLOSURE_PREFLIGHT_DRIFT')
            capture = out / 'capture'
            capture.mkdir(mode=0o700)
            config = dict(profile=PROFILE, readOnlyApproved=True, discoveryApproved=True,
                          intent=b['intent'], engine={'sourceSha256': r['sourceCommitment'],
                          'binarySha256': r['files']['worker']['sha256'], 'policySha256': r['policySha256']},
                          output=str(capture), socket=str(out / 'broker.sock'),
                          credentialFile=str(no_links(credential_file)), accountAssertions=str(no_links(account_assertions)))
            save(out / 'BROKER_CONFIG.json', config)
            def caps():
                resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
                resource.setrlimit(resource.RLIMIT_FSIZE, (16 << 20, 16 << 20))
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            with (out / 'broker.stdout').open('xb') as stdout, (out / 'broker.stderr').open('xb') as stderr:
                child = subprocess.Popen([r['files']['node']['path'], str(api.HERE / 'closure-main.mjs'), str(out / 'BROKER_CONFIG.json')],
                    stdout=stdout, stderr=stderr, cwd=out, env=dict(PATH='/usr/bin:/bin:/usr/sbin:/sbin', LANG='C', TZ='UTC'), preexec_fn=caps)
                save(out / 'BROKER_PROCESS.json', dict(pid=child.pid, pgid=os.getpgrp(), cpuSeconds=10, sampledRSSLimitBytes=256 << 20))
                guard = host_v3.RuntimeGuard(Path(host['sensor']['path']), out / 'WAIT_HOST', samples[-1])
                deadline = time.monotonic() + 30
                while not (capture / 'DISCOVERY_READY.json').exists():
                    require(child.poll() is None and time.monotonic() < deadline, 'CLOSURE_ACQUISITION_STOP')
                    guard.poll()
                    row = sample_broker(child)
                    require(row is None or row['rssBytes'] <= 256 << 20, 'BROKER_SAMPLED_RSS_LIMIT')
                    time.sleep(0.05)
                discovered, result['discoveryResources'] = _discover_once(sdk, capture / 'PROVISIONAL_SCENARIO.json', out / 'discovery',
                    r, host, b, key, guard.previous, child)
                require(child.wait(timeout=max(.01, deadline - time.monotonic())) == 0, 'CLOSURE_BROKER_STOP')
                stdout.flush();stderr.flush();os.fsync(stdout.fileno());os.fsync(stderr.fileno())
            acquired = confirmed_acquisition(load(capture / 'ACQUISITION_RESULT.json', 65536), discovered)
            result['acquisition'] = acquired
            require(acquired['status'] == 'AUTHENTICATED_SCENARIO_CAPTURED', 'CLOSURE_ACQUISITION_STOP')
            # Acquired data is frozen before any final nil-Source execution.
            save(capture / 'SDK_RESULT.json', dict(acquired, planId=ref, planCommitment=b['planCommitment'],
                 cleanupConfirmed=True, scenarioSha256=sha(capture / 'SCENARIO.json')))
            api.check(sdk, capture)
            power.observe(out / 'FINAL_POWER')
            final_binding = api.prepare(sdk, capture, host_profile=host_v3.PROFILE)
            final_out = Path(final_binding['outputPath'])
            final_out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            final_grant = authority.issue(sdk.home / 'scenarios/consents', final_binding, key)
            final_body = authority.consume(final_grant, sdk.home / 'scenarios/consents', final_binding, key)
            final_runtime = dict(r, files=dict(r['files'], sensor=host['sensor']))
            executed = api._execute(sdk, capture, final_out, final_binding, final_runtime, final_body,
                time.monotonic(), host_v3.supervise, native.guards()[2], host_v3.admission, out / 'FINAL_POWER')
            result['offlineResult'] = executed
            if executed.get('primaryStop'):
                outcome.require_stage(final_out / 'runtime', final_binding['operationCommitment'], executed.get('resources'))
            require(executed['status'] == 'SCENARIO_COMPLETED' and executed['cleanupConfirmed'], 'FINAL_OFFLINE_SCENARIO_STOP')
            final = load(final_out / 'runtime/scenario/FINAL.json', 8 << 20)
            verified = api.verify(sdk, final_out)
            save(out / 'VERIFIED.json', verified)
            save(out / 'COMPARISON.json', api.compare(sdk, final_out))
            save(out / 'DETERMINISTIC_COMPARISON.json', compare_worlds(discovered, final))
            require(time.monotonic() - began <= 180, 'CLOSURE_WORKFLOW_DEADLINE')
            result.update(status='SCENARIO_WITNESS_CLOSURE_COMPLETED', finalSource='NIL', completedOfflineWorlds=2,
                          checkpoint=acquired['checkpoint'], verified=verified, qualifiedClaims=0,
                          nativeProducerEntries={'discovery':discovered['producerInvocations'],
                                                 'finalOffline':executed['producerInvocations']})
        except BaseException as error:
            outcome.apply_failure(result, error)
        finally:
            try:
                if child is not None and child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
            except BaseException as cleanup_error:
                result['brokerCleanupError'] = type(cleanup_error).__name__ + ': ' + str(cleanup_error)[:400]
            result.update(brokerReaped=child is None or child.returncode is not None,
                          elapsedSeconds=time.monotonic() - began)
            discovery_clean, diagnostics = outcome.discovery_cleanup(out / 'discovery')
            result['discoveryDiagnostics'] = diagnostics
            final_clean = result.get('offlineResult', {}).get('cleanupConfirmed', True)
            result['cleanupConfirmed'] = result['brokerReaped'] and not result.get('brokerCleanupError') and discovery_clean and final_clean is True
            save(out / 'RESULT.json', result)
    return result


def sample_broker(proc):
    """Inspect only this exact owned Node PID, with no argv/environment dump."""
    observed = subprocess.run(['/bin/ps', '-p', str(proc.pid), '-o', 'pid=,ppid=,pgid=,rss=,comm='],
                              capture_output=True, text=True, timeout=1)
    if proc.poll() is not None:
        return None
    rows = observed.stdout.strip().splitlines()
    require(observed.returncode == 0 and len(rows) == 1, 'BROKER_TELEMETRY_MISSING')
    pid, parent, group, rss, executable = rows[0].split(None, 4)
    require(int(pid) == proc.pid and int(parent) == os.getpid() and int(group) == active_group()
            and Path(executable).name == Path(proc.args[0]).name, 'BROKER_PROCESS_IDENTITY')
    return dict(pid=int(pid), ppid=int(parent), pgid=int(group), rssBytes=int(rss) * 1024, executable=executable)
