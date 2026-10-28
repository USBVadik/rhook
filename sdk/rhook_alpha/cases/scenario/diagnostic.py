"""Single-world, nil-Source diagnostics over a separately pinned saved scenario."""
import json
import os
from pathlib import Path
import shutil
import time

from developer.files import canonical, digest, load, no_links, read, require, save, sha, sync
from .. import authority, native
from ..workflow import active_group, PROFILE as WORKFLOW_PROFILE
from . import api, host_v3, outcome, power

PROFILE = 'rhook/scenario-result-diagnostic/0.1'


def prepare(sdk, ref, scenario, output):
    plan = api.describe(sdk, ref)
    scenario = no_links(scenario)
    spec = load(scenario, 8 << 20)
    body = dict(spec)
    pin = body.pop('scenarioCommitment')
    require(pin == digest(b'rhook/hookr-scenario/0.1\n' + canonical(body)), 'DIAGNOSTIC_INPUT_COMMITMENT')
    r = api.runtime(sdk)
    host = api.select_host(sdk, host_v3.PROFILE)
    b = dict(schema=PROFILE, profile=api.PROFILE, planId=plan['planId'], diagnosticProfile=PROFILE,
             diagnosticOf=pin, maximumProducerEntries=1, maximumInvocations={'SCENARIO_BASELINE': 1, 'SCENARIO_VARIANT': 0},
             scenarioPath=str(scenario), scenarioSha256=sha(scenario), scenarioCommitment=pin,
             referenceEngine=spec['engine'], binarySha256=r['files']['worker']['sha256'],
             sourceCommitment=r['sourceCommitment'], policySha256=r['policySha256'],
             hostAdmission=host, sdkFilesCommitment=digest(canonical(host_v3.sdk_files())),
             workflowCaptureProfile=WORKFLOW_PROFILE, outputPath=str(no_links(output)),
             RPC=0, WSS=0, Source='NIL', automaticRetry=False, externalDelivery='HOLD')
    b['operationCommitment'] = digest((PROFILE+'\n').encode()+canonical(b))
    return b


def run(sdk, ref, scenario, output, *, expected_operation, local_owner=False, mac_ready=False):
    require(local_owner is True and mac_ready is True, 'EXPLICIT_DIAGNOSTIC_OWNER_AND_READY_REQUIRED')
    require(active_group() is not None, 'OWNED_WORKFLOW_CONTEXT_REQUIRED')
    b = prepare(sdk, ref, scenario, output)
    require(b['operationCommitment'] == expected_operation, 'EXACT_DIAGNOSTIC_OPERATION_REQUIRED')
    api._helper(sdk, ['--authenticate', b['scenarioPath']])
    out = no_links(output)
    require(not out.exists(), 'FRESH_DIAGNOSTIC_OUTPUT_REQUIRED')
    r = api.runtime(sdk)
    lock, _, cleanup, _ = native.guards()
    key = read(sdk.home/'scenarios/.consent.key', 32)
    began = time.monotonic()
    dispatched = admission_started = False
    measured = None
    result = dict(status='DIAGNOSTIC_STOP', operationCommitment=expected_operation,
                  diagnosticOf=b['diagnosticOf'], operationPermanentlyClosed=True,
                  RPC=0, WSS=0, Source='NIL', qualifiedClaims=0, automaticRetry=False, externalDelivery='HOLD')
    with lock(sdk.home):
        grant = authority.issue(sdk.home/'scenarios/diagnostic-consents', b, key)
        body = authority.consume(grant, sdk.home/'scenarios/diagnostic-consents', b, key)
        raw = canonical(body)+b'\n'
        out.mkdir(mode=0o700)
        sync(out.parent)
        rt = out/'runtime'; rt.mkdir(mode=0o700)
        save(rt/'STARTED.json', dict(operationCommitment=expected_operation, authoritySha256=digest(raw)))
        try:
            power.observe(rt/'POWER')
            require(b == prepare(sdk, ref, scenario, output), 'DIAGNOSTIC_PREFLIGHT_DRIFT')
            (out/'inputs').mkdir(mode=0o700); (out/'artifacts').mkdir(mode=0o700)
            shutil.copyfile(b['scenarioPath'], out/'inputs/SCENARIO.json')
            require(sha(out/'inputs/SCENARIO.json') == b['scenarioSha256'], 'DIAGNOSTIC_INPUT_DRIFT')
            for name, asset in [('rhook-saved-pair', r['files']['worker']), ('rhook-host-sensor', b['hostAdmission']['sensor'])]:
                shutil.copyfile(asset['path'], out/'artifacts'/name)
                require(sha(out/'artifacts'/name) == asset['sha256'], 'DIAGNOSTIC_ARTIFACT_DRIFT')
                (out/'artifacts'/name).chmod(0o700)
            save(out/'BINDING.json', b); save(rt/'AUTHORITY.json', body)
            admission_started = True
            decision, samples = host_v3.admission(out/'artifacts/rhook-host-sensor', rt/'HOST')
            save(rt/'HOST_ADMISSION.json', dict(accepted=True, profile=api.PROFILE, policySha256=api.POLICY_SHA,
                 hostAdmission=b['hostAdmission'], decision=decision))
            require(time.monotonic()-began < 10, 'DIAGNOSTIC_PREPARATION_DEADLINE')
            save(rt/'DISPATCH_INTENT.json', dict(operationCommitment=expected_operation))
            dispatched = True
            measured = host_v3.supervise(raw, out, out/'artifacts/rhook-host-sensor', samples[-1])
            completion = outcome.require_stage(rt, expected_operation, measured)
            value = completion['result']
            result.update(producerEntries=completion['producerEntries'], rawStatus=value['status'], failure=value.get('failure'), resources=measured)
            require(measured['workerReaped'] and measured['exitCode'] == 0 and measured['stop'] is None
                    and measured['resourcesReliable'], 'DIAGNOSTIC_NATIVE_STOP')
            require(completion['operationCommitment'] == expected_operation and completion['diagnosticOnly'] is True
                    and completion['producerEntries'] == 1 and value['diagnosticOnly'] is True
                    and value['status'] == 'SCENARIO_DIAGNOSTIC_COMPLETED' and len(value['worlds']) == 1
                    and value['ownedBridgesClosed'] is True, 'DIAGNOSTIC_COMPLETION_SCOPE')
            require(time.monotonic()-began <= 140, 'DIAGNOSTIC_STAGE_DEADLINE')
            result.update(status='DIAGNOSTIC_COMPLETED', diagnosticPath=str(rt/'scenario/DIAGNOSTIC.json'))
        except BaseException as error:
            outcome.apply_failure(result, error)
        try:
            clean = cleanup(out, dispatched, measured, admission_started)
        except BaseException as error:
            clean = False
            result['cleanupError'] = type(error).__name__ + ': ' + str(error)[:400]
        if dispatched:
            diagnostics = outcome.inspect_stage(rt, expected_operation, measured).diagnostics
            result['nativeDiagnostics'] = diagnostics
            clean = clean and diagnostics['processTermination'] == diagnostics['engineBridgeClosure'] == 'CONFIRMED'
        result['cleanupConfirmed'] = clean
        if not clean:
            result['status'] = 'DIAGNOSTIC_STOP'
        result['elapsedSeconds'] = time.monotonic()-began
        native.seal_result(out, result)
    return result
