"""Parameterized Execution workflow 0.2 tests (doctor, session-ready, session-run, session-result).

Synthetic inputs only. Every native entry point (registration, authentication, binding, run, verifier) is
replaced or must not be reached; nothing here is native or EVM evidence.
"""
from pathlib import Path
import hashlib, json, os, subprocess, sys, unittest
from unittest.mock import patch

from developer.files import canonical, load, tree
from rhook_alpha.execution import ExecutionSDK
from rhook_alpha.session import SessionError, hookr, workflow
from test_session import NoNativeNoNetwork, SDK
from test_session_plan import PlanTest, Forbidden, satisfied_report, READY

OP = 'ab' * 32
LP_RUNTIME = 'nitro-hookr-scenario/0.1'
READY_DOCTOR = dict(schema=workflow.DOCTOR_SCHEMA, status='READY', checks=[], registration={}, performed={})
BLOCKED_DOCTOR = dict(READY_DOCTOR, status='BLOCKED',
                      checks=[dict(check='processTelemetry', ok=False, detail=dict(error='PermissionError'), nextStep='Terminal')])


def comparison(run, base='1000', variant='1010'):
    """Shape of the existing scenario compare for this run; synthetic numbers."""
    return dict(status='VERIFIED_SCENARIO_COMPARISON', scenarioCommitment=load(Path(run) / 'RESULT.json', 65536)['scenarioCommitment'],
                worlds=[dict(world='SCENARIO_BASELINE', receiptStatus=1, gasUsed=100, outerSwapFeePips=[11000], actorTargetTokenTransferNetBaseUnits=base),
                        dict(world='SCENARIO_VARIANT', receiptStatus=1, gasUsed=98, outerSwapFeePips=[5960], actorTargetTokenTransferNetBaseUnits=variant)],
                targetTokenTransferNetDeltaBaseUnits=str(int(variant) - int(base)))


class WorkflowTest(PlanTest):
    def planned(self, lp=37, home='home'):
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()):
            out = self.plan(lp, home=home)
        self.assertEqual(out['status'], READY)
        sdk = self.sdk(home)
        return sdk, out['sessionId'], out

    def view(self, sdk, sid, lp=37):
        return next(v for v in sdk.open_session(sid).variants() if v['descriptor']['replacement'] == lp)

    def fake_run(self, sdk, sid, op=OP, lp=37):
        """A completed run directory in the place ExecutionSDK.run uses, with its manifest; synthetic."""
        session = sdk.open_session(sid)
        prepared = session.directory / self.view(sdk, sid, lp)['preparation']['preparedDirectory']
        run = sdk.home / 'scenarios/runs' / load(prepared / 'PREPARATION.json', 65536)['planId']
        raw = (prepared / 'SCENARIO.json').read_bytes(); spec = json.loads(raw)
        (run / 'inputs').mkdir(parents=True); (run / 'inputs/SCENARIO.json').write_bytes(raw)
        (run / 'BINDING.json').write_bytes(canonical(dict(profile='nitro-hookr-scenario/0.1', scenarioSha256=hashlib.sha256(raw).hexdigest(),
                                                          operationCommitment=op)))
        (run / 'RESULT.json').write_bytes(canonical(dict(status='SCENARIO_COMPLETED', operationCommitment=op, scenarioCommitment=spec['scenarioCommitment'])))
        (run / 'runtime/scenario').mkdir(parents=True)
        worlds = [dict(world=w, stateRoot='0x' + c * 64, receiptsRoot='0x' + d * 64, actorBalanceBefore='1000', actorBalanceAfter='990',
                       originalWitnessCommitment='d' * 64) for w, c, d in (('SCENARIO_BASELINE', '1', '2'), ('SCENARIO_VARIANT', '3', '4'))]
        (run / 'runtime/scenario/FINAL.json').write_bytes(canonical(dict(scenarioCommitment=spec['scenarioCommitment'], evidenceCommitment='e' * 64, worlds=worlds)))
        (run / 'MANIFEST.json').write_bytes(canonical(dict(files=tree(run, omit=('MANIFEST.json',)))))
        return run

    def verified(self, sdk, sid, lp=37):
        run = self.fake_run(sdk, sid, lp=lp)
        with patch.object(hookr.HookrScenarioAdapter, 'verify_run', side_effect=comparison):
            sdk.open_session(sid).verify_selected(self.view(sdk, sid, lp)['variantId'], run)
        return run

    def assert_nothing_consumed(self, sdk):
        for rel in ('scenarios/consents', 'scenarios/execution-attempts', 'scenarios/runs'):
            self.assertFalse((sdk.home / rel).exists(), rel)

    def manifest(self, name='RUNTIME.json', profile=LP_RUNTIME):
        """A runtime manifest file naming only its profile; registration itself is replaced in these tests."""
        path = self.root / name
        path.write_text(json.dumps(dict(profile=profile)))
        return path


class Doctor(WorkflowTest):
    def test_ps_row_must_be_exactly_the_owned_child(self):
        ok = workflow.parse_ps(0, ' 10    9   10   1200 /bin/sleep\n', 10, 9)
        self.assertEqual(ok, dict(pid=10, ppid=9, pgid=10, rssBytes=1200 * 1024, executable='/bin/sleep'))
        for code, out in ((0, '10 8 10 1200 /bin/sleep'), (0, '10 9 9 1200 /bin/sleep'), (0, '10 9 10 0 /bin/sleep'),
                          (1, '10 9 10 1200 /bin/sleep'), (0, ''), (0, '10 9 10 1 a\n11 9 11 1 b'), (0, '10 9 x 1 a')):
            with self.assertRaises(ValueError):
                workflow.parse_ps(code, out, 10, 9)

    def test_denied_ps_is_blocked_with_terminal_guidance_and_reaps_the_child(self):
        real = subprocess.run
        def run(args, *a, **k):
            if args[0] == '/bin/ps':
                raise PermissionError(1, 'Operation not permitted', '/bin/ps')
            return real(args, *a, **k)
        with patch.object(workflow.subprocess, 'run', side_effect=run), patch.object(workflow, 'power_and_lid', return_value=dict(onACPower=True, lidOpen=True)):
            out = self.sdk().doctor()
        self.assertEqual(out['status'], 'BLOCKED')
        tel = next(c for c in out['checks'] if c['check'] == 'processTelemetry')
        self.assertFalse(tel['ok']); self.assertIn('PermissionError', tel['detail']['error']); self.assertTrue(tel['detail']['childReaped'])
        self.assertIn('regular macOS Terminal', tel['nextStep'])
        self.assertEqual(out['performed'], dict(probeChild='/bin/sleep 5', nativeWorker=0, sensor=0, consent=0, attemptMarker=0, networkRequests=0))
        self.assertEqual(out['registration']['runtime'], 'NOT_REGISTERED')
        self.assert_nothing_consumed(self.sdk())

    def test_ready_needs_every_check(self):
        good = dict(ok=True, row=dict(pid=1), error=None, childReaped=True)
        def doctor(telemetry=good, power=True, machine=('darwin', 'arm64')):
            with patch.object(workflow, 'telemetry', return_value=telemetry), \
                 patch.object(workflow, 'power_and_lid', return_value=dict(onACPower=True, lidOpen=True)) if power else \
                 patch.object(workflow, 'power_and_lid', side_effect=ValueError('HOST_POWER_LID_NOT_READY')), \
                 patch.object(workflow.sys, 'platform', machine[0]), patch.object(workflow.platform, 'machine', return_value=machine[1]):
                return self.sdk().doctor()
        self.assertEqual(doctor()['status'], 'READY')
        self.assertEqual(doctor(telemetry=dict(good, ok=False, error='x'))['status'], 'BLOCKED')
        self.assertEqual(doctor(power=False)['status'], 'BLOCKED')
        self.assertEqual(doctor(machine=('linux', 'x86_64'))['status'], 'BLOCKED')


class Ready(WorkflowTest):
    def stage_b(self, sdk, out, *, auth=None):
        binding = dict(planId=out['prepared']['preparedDirectory'], binarySha256='b' * 64, sourceCommitment='c' * 64, policySha256='f' * 64,
                       profile='nitro-hookr-scenario/0.1', maximumInvocations=dict(SCENARIO_BASELINE=1, SCENARIO_VARIANT=1), RPC=0, WSS=0,
                       automaticRetry=False, externalDelivery='HOLD', hostAdmission=dict(profile='macos-host-admission-v4', policySha256='9' * 64))
        return [patch.object(ExecutionSDK, 'register_runtime', return_value=dict(status='RUNTIME_REGISTERED')),
                patch.object(ExecutionSDK, 'register_host', return_value=dict(status='HOST_REGISTERED')),
                patch.object(ExecutionSDK, 'authenticate', return_value=auth or dict(status='AUTHENTICATED_SCENARIO_INPUT',
                             scenarioCommitment=out['prepared']['scenarioCommitment'], nativeExecutions=0)),
                patch.object(ExecutionSDK, 'operation', return_value=dict(status='EXECUTION_OPERATION_PREPARED', binding=binding, operationCommitment=OP,
                             outputPath=str(sdk.home / 'scenarios/runs/c-test'))),
                patch.object(ExecutionSDK, 'run', side_effect=AssertionError('no run in Stage B')),
                patch.object(workflow, 'doctor', return_value=READY_DOCTOR)]

    def call(self, patches, fn):
        for p in patches:
            p.start()
        try:
            return fn()
        finally:
            for p in reversed(patches):
                p.stop()

    def test_ready_binds_the_exact_operation_once_and_creates_no_consent(self):
        sdk, sid, out = self.planned()
        patches = self.stage_b(sdk, out)
        value = self.call(patches, lambda: sdk.ready_lp_variant(sid, lp_bps=37, runtime=self.manifest(), sensor=self.root / 'sensor'))
        self.assertEqual(value['status'], 'RUN_READY')
        self.assertEqual((value['operationCommitment'], value['selectedLpBps'], value['baselineLpBps']), (OP, 37, 100))
        self.assertEqual(value['registration'], dict(runtime='REGISTERED_NOW', hostAdmission='REGISTERED_NOW'))
        self.assertEqual((value['consent'], value['attemptMarker'], value['evmExecutions']), ('NOT_CREATED', 'NOT_CREATED', 0))
        self.assertEqual(value['next']['command'][-6:], ['--lp-bps', '37', '--operation', OP, '--local-owner', '--mac-ready'])
        self.assertIn('session-run', value['next']['command'])
        self.assertEqual(value['scenarioCommitment'], out['prepared']['scenarioCommitment'])
        self.assert_nothing_consumed(sdk)

    def test_missing_registration_stops_before_any_native_process(self):
        sdk, sid, _ = self.planned()
        with NoNativeNoNetwork() as guard, Forbidden():
            self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=37), 'NATIVE_RUNTIME_MISSING')
            (sdk.home / 'scenarios').mkdir(exist_ok=True)
            (sdk.home / 'scenarios/RUNTIME.json').write_text(json.dumps(dict(runtime=dict(profile=LP_RUNTIME))))
            self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=37), 'HOST_ADMISSION_NOT_REGISTERED')
            other = self.root / 'other-runtime.json'; other.write_text(json.dumps(dict(profile='y')))
            self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=37, runtime=other), 'RUNTIME_REGISTRATION_DIFFERS')
        self.assertEqual(guard.launched, [])
        self.assert_nothing_consumed(sdk)

    def test_existing_registration_is_used_unchanged(self):
        sdk, sid, out = self.planned()
        (sdk.home / 'scenarios').mkdir(exist_ok=True)
        (sdk.home / 'scenarios/RUNTIME.json').write_text(json.dumps(dict(runtime=dict(profile=LP_RUNTIME))))
        (sdk.home / 'scenarios/HOST_V4.json').write_text(json.dumps(dict(sensor=dict(path=str(self.root / 'sensor')))))
        patches = self.stage_b(sdk, out)
        value = self.call(patches, lambda: sdk.ready_lp_variant(sid, lp_bps=37))
        self.assertEqual(value['registration'], dict(runtime='ALREADY_REGISTERED', hostAdmission='ALREADY_REGISTERED'))
        same = self.manifest('same.json')
        value = self.call(self.stage_b(sdk, out), lambda: sdk.ready_lp_variant(sid, lp_bps=37, runtime=same, sensor=self.root / 'sensor'))
        self.assertEqual(value['status'], 'RUN_READY')
        self.code(lambda: self.call(self.stage_b(sdk, out), lambda: sdk.ready_lp_variant(sid, lp_bps=37, sensor=self.root / 'other')),
                  'HOST_REGISTRATION_DIFFERS')

    def test_closed_operation_and_blocked_environment_are_reported(self):
        sdk, sid, out = self.planned()
        args = dict(runtime=self.manifest(), sensor=self.root / 'sensor')
        patches = self.stage_b(sdk, out)[:-1] + [patch.object(workflow, 'doctor', return_value=BLOCKED_DOCTOR)]
        value = self.call(patches, lambda: sdk.ready_lp_variant(sid, lp_bps=37, **args))
        self.assertEqual(value['status'], 'RUN_READY_ENVIRONMENT_BLOCKED')
        (sdk.home / 'scenarios/execution-attempts').mkdir(parents=True)
        (sdk.home / 'scenarios/execution-attempts' / f'{OP}.json').write_text('{}')
        value = self.call(self.stage_b(sdk, out), lambda: sdk.ready_lp_variant(sid, lp_bps=37, **args))
        self.assertEqual((value['status'], value['attemptMarker']), ('OPERATION_CLOSED', 'EXISTS'))
        self.assertNotIn('command', value['next'])

    def test_unauthenticated_input_is_not_bound(self):
        sdk, sid, out = self.planned()
        patches = self.stage_b(sdk, out, auth=dict(status='INPUT_STOP'))
        self.code(lambda: self.call(patches, lambda: sdk.ready_lp_variant(sid, lp_bps=37, runtime=self.manifest('r'), sensor=self.root / 's')),
                  'PREPARED_INPUT_NOT_AUTHENTICATED')

    def test_variant_selection(self):
        sdk, sid, out = self.planned()
        with Forbidden():
            self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=25), 'VARIANT_NOT_PLANNED')
            self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=100), 'BASELINE_LP100_IS_NOT_A_VARIANT')
            self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=37, variant_id=out['variantId']), 'VARIANT_SELECTION')
            self.code(lambda: sdk.ready_lp_variant(sid), 'VARIANT_SELECTION')
            self.code(lambda: sdk.ready_lp_variant(sid, variant_id='0' * 64), 'VARIANT_NOT_PLANNED')


class Run(WorkflowTest):
    def completed(self, sdk, sid, calls, status='EXECUTION_COMPLETED'):
        def run(self_, prepared, *, operation, evidence, local_owner, mac_ready, host_profile):
            calls.append(dict(operation=operation, evidence=str(evidence), local_owner=local_owner, mac_ready=mac_ready, host_profile=host_profile))
            Path(evidence).mkdir(parents=True)
            out = self.fake_run(sdk, sid, op=operation) if status == 'EXECUTION_COMPLETED' else None
            return dict(status=status, operationCommitment=operation, runDirectory=str(out) if out else None, cleanupConfirmed=out is not None,
                        causeCode=None if out else 'SUPERVISOR_STOP: SUPERVISION_FAILURE_PermissionError',
                        nativeResult=dict(status='SCENARIO_COMPLETED', producerInvocations=2, RPC=0, WSS=0, cleanupConfirmed=True) if out else None)
        return patch.object(ExecutionSDK, 'run', autospec=True, side_effect=run)

    def test_consent_and_operation_are_checked_before_anything_else(self):
        sdk, sid, _ = self.planned()
        with patch.object(workflow, 'doctor', side_effect=AssertionError('doctor before consent')), Forbidden():
            self.code(lambda: sdk.run_lp_variant(sid, lp_bps=37, operation=OP), 'EXACT_LOCAL_CONSENT_REQUIRED')
            self.code(lambda: sdk.run_lp_variant(sid, lp_bps=37, operation=OP, local_owner=True), 'EXACT_LOCAL_CONSENT_REQUIRED')
            self.code(lambda: sdk.run_lp_variant(sid, lp_bps=37, operation=OP.upper(), local_owner=True, mac_ready=True), 'OPERATION_COMMITMENT_REQUIRED')

    def test_blocked_environment_consumes_nothing(self):
        sdk, sid, _ = self.planned()
        with patch.object(workflow, 'doctor', return_value=BLOCKED_DOCTOR), Forbidden():
            value = sdk.run_lp_variant(sid, lp_bps=37, operation=OP, local_owner=True, mac_ready=True)
        self.assertEqual(value['status'], 'RUN_STOP_ENVIRONMENT_NOT_READY')
        self.assertEqual((value['operationPermanentlyClosed'], value['consumed']), (False, dict(consent=False, attemptMarker=False)))
        self.assert_nothing_consumed(sdk)
        self.assertFalse((self.root / 'home-evidence').exists())

    def test_completed_run_is_verified_once_and_produces_one_result(self):
        sdk, sid, _ = self.planned()
        calls = []
        with patch.object(workflow, 'doctor', return_value=READY_DOCTOR), self.completed(sdk, sid, calls), \
             patch.object(ExecutionSDK, 'verify', return_value=dict(status='SCENARIO_RECORDED_INTEGRITY_PASS', EVMReexecution=False)) as verify, \
             patch.object(hookr.HookrScenarioAdapter, 'verify_run', side_effect=comparison) as verifier:
            value = sdk.run_lp_variant(sid, lp_bps=37, operation=OP, local_owner=True, mac_ready=True)
        self.assertEqual(value['status'], 'RUN_VERIFIED')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], dict(operation=OP, evidence=str(self.root / 'home-evidence' / OP), local_owner=True, mac_ready=True,
                                        host_profile='macos-host-admission-v4'))
        verify.assert_called_once(); verifier.assert_called_once()
        self.assertEqual(value['verification']['sessionVerification'], 'RECORDED_RUN_VERIFIED')
        card = value['result']
        self.assertEqual((card['status'], card['difference']['targetTokenTransferNetBaseUnits'], card['difference']['gasUsed']), ('VERIFIED_RESULT', '10', -2))
        self.assertEqual(load(self.root / 'home-evidence' / OP / 'DEVELOPER_RUN.json', 1 << 20)['status'], 'RUN_VERIFIED')
        # The verified variant is not runnable again; nothing is retried.
        with patch.object(workflow, 'doctor', side_effect=AssertionError('no second doctor')), Forbidden():
            self.code(lambda: sdk.run_lp_variant(sid, lp_bps=37, operation=OP, local_owner=True, mac_ready=True), 'VARIANT_NOT_RUNNABLE')
            self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=37), 'VARIANT_NOT_RUNNABLE')

    def test_native_stop_is_reported_and_not_verified(self):
        sdk, sid, _ = self.planned()
        calls = []
        with patch.object(workflow, 'doctor', return_value=READY_DOCTOR), self.completed(sdk, sid, calls, status='EXECUTION_STOP'), \
             patch.object(ExecutionSDK, 'verify', side_effect=AssertionError('no verify after a stop')):
            value = sdk.run_lp_variant(sid, lp_bps=37, operation=OP, local_owner=True, mac_ready=True)
        self.assertEqual((value['status'], value['operationPermanentlyClosed'], value['automaticRetry']), ('RUN_STOP', True, False))
        self.assertIn('SUPERVISION_FAILURE', value['causeCode'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(load(Path(value['evidenceDirectory']) / 'DEVELOPER_RUN.json', 1 << 20)['status'], 'RUN_STOP')

    def test_failed_verification_after_a_completed_run_records_nothing(self):
        sdk, sid, out = self.planned()
        calls = []
        with patch.object(workflow, 'doctor', return_value=READY_DOCTOR), self.completed(sdk, sid, calls), \
             patch.object(ExecutionSDK, 'verify', return_value=dict(status='RECORDED_INTEGRITY_FAIL')):
            value = sdk.run_lp_variant(sid, lp_bps=37, operation=OP, local_owner=True, mac_ready=True, evidence=self.root / 'ev')
        self.assertEqual((value['status'], value['causeCode']), ('RUN_COMPLETED_VERIFICATION_STOP', 'RECORDED_INTEGRITY_NOT_PASSED'))
        self.assertEqual(len(calls), 1)
        self.assertFalse((sdk.home / 'sessions' / sid / 'variants' / out['variantId'] / 'VERIFICATION.json').exists())


class Result(WorkflowTest):
    def test_unverified_variant_has_no_result(self):
        sdk, sid, _ = self.planned()
        with NoNativeNoNetwork() as guard:
            self.code(lambda: sdk.lp_variant_result(sid, lp_bps=37), 'VARIANT_NOT_VERIFIED')
        self.assertEqual(guard.launched, [])

    def test_result_view_of_a_verified_variant(self):
        sdk, sid, out = self.planned()
        self.verified(sdk, sid)
        with NoNativeNoNetwork() as guard:
            card = sdk.lp_variant_result(sid, lp_bps=37)
        self.assertEqual(guard.launched, [])
        self.assertEqual(card['schema'], workflow.RESULT_SCHEMA)
        self.assertEqual((card['status'], card['parameter']), ('VERIFIED_RESULT', dict(field='RulesConfig.lpBps', baseline=100, variant=37)))
        b, v = card['worlds']
        self.assertEqual((b['world'], b['lpBps'], b['gasUsed'], b['outerSwapFeePips'], b['stateRoot']), ('SCENARIO_BASELINE', 100, 100, [11000], '0x' + '1' * 64))
        self.assertEqual((v['world'], v['lpBps'], v['actorTargetTokenTransferNetBaseUnits'], v['receiptsRoot']), ('SCENARIO_VARIANT', 37, '1010', '0x' + '4' * 64))
        self.assertEqual(card['difference'], dict(targetTokenTransferNetBaseUnits='10', relativeToBaselinePercent='+1.0000', gasUsed=-2))
        self.assertEqual((card['commitments']['operationCommitment'], card['commitments']['scenarioCommitment']), (OP, out['prepared']['scenarioCommitment']))
        self.assertEqual(card['verification']['runRecord'], 'MATCHES_MANIFEST_AND_VERIFICATION')
        self.assertEqual((card['verification']['economicAssurance'], card['verification']['qualifiedClaims']), ('UNRESOLVED', 0))
        self.assertIn('not profit', card['meaning'])
        text = workflow.render(card)
        for needle in ('VERIFIED_RESULT', 'baseline 100 -> variant 37', '+10 base units', '+1.0000%', 'gas -2', OP, 'economic assurance (UNRESOLVED)'):
            self.assertIn(needle, text)

    def test_changed_or_missing_run_record(self):
        sdk, sid, _ = self.planned()
        run = self.verified(sdk, sid)
        (run / 'runtime/scenario/FINAL.json').chmod(0o600)
        (run / 'runtime/scenario/FINAL.json').write_bytes(b'{}')
        self.code(lambda: sdk.lp_variant_result(sid, lp_bps=37), 'RUN_RECORD_DRIFT')
        moved = run.with_name('elsewhere'); run.rename(moved)
        card = sdk.lp_variant_result(sid, lp_bps=37)
        self.assertEqual(card['verification']['runRecord'], 'RUN_DIRECTORY_NOT_AVAILABLE')
        self.assertNotIn('stateRoot', card['worlds'][0])

    def test_test_only_verification_is_labelled(self):
        sdk, sid, _ = self.planned()
        run = self.fake_run(sdk, sid)
        sdk.open_session(sid).verify_selected(self.view(sdk, sid)['variantId'], run, test_only_backend=comparison)
        self.assertEqual(sdk.lp_variant_result(sid, lp_bps=37)['status'], 'TEST_ONLY_NOT_EVIDENCE')

    def test_percent_is_exact_and_signed(self):
        self.assertEqual(workflow.percent(375968768119907377829, 59085787608983877958575), '+0.6363')
        self.assertEqual((workflow.percent(-1, 3), workflow.percent(0, 7), workflow.percent(1, 0)), ('-33.3333', '+0.0000', None))


class Cli(WorkflowTest):
    def cli(self, home, *args):
        r = subprocess.run([sys.executable, '-B', '-m', 'rhook_alpha.cases', '--home', str(home), *args], cwd=SDK, capture_output=True, timeout=60)
        return r.returncode, r.stdout.decode(), r.stderr.decode()

    def test_cli_commands_and_exit_codes(self):
        sdk, sid, _ = self.planned()
        code, out, _ = self.cli(sdk.home, 'doctor')
        self.assertEqual(code, 0 if json.loads(out)['status'] == 'READY' else 1)
        code, out, _ = self.cli(sdk.home, 'session-ready', '--session', sid, '--lp-bps', '37')
        self.assertEqual((code, json.loads(out)['causeCode']), (1, 'NATIVE_RUNTIME_MISSING'))
        code, out, _ = self.cli(sdk.home, 'session-ready', '--session', sid, '--lp-bps', '037')
        self.assertEqual((code, json.loads(out)['causeCode']), (1, 'LP_BPS_INTEGER_REQUIRED'))
        code, _, err = self.cli(sdk.home, 'session-run', '--session', sid, '--lp-bps', '37', '--operation', OP)
        self.assertEqual(code, 2); self.assertIn('--local-owner', err)
        code, out, _ = self.cli(sdk.home, 'session-result', '--session', sid, '--lp-bps', '37')
        self.assertEqual((code, json.loads(out)['causeCode']), (1, 'VARIANT_NOT_VERIFIED'))
        self.verified(sdk, sid)
        code, out, _ = self.cli(sdk.home, 'session-result', '--session', sid, '--lp-bps', '37')
        self.assertEqual((code, json.loads(out)['status']), (0, 'VERIFIED_RESULT'))
        code, out, _ = self.cli(sdk.home, 'session-result', '--session', sid, '--lp-bps', '37', '--text')
        self.assertEqual(code, 0); self.assertIn('RHOOK parameterized result: VERIFIED_RESULT', out)
        self.assert_nothing_consumed_except_run(sdk)

    def example(self, *args):
        r = subprocess.run([sys.executable, '-B', str(SDK / 'examples/parameterized_execution.py'), *args], capture_output=True, timeout=60)
        return r.returncode, r.stdout.decode(), r.stderr.decode()

    def test_example_never_runs_without_all_three_run_arguments_and_reads_a_verified_result(self):
        sdk, sid, _ = self.planned()
        for extra in (['--operation', OP], ['--operation', OP, '--local-owner'], ['--local-owner', '--mac-ready']):
            code, _, err = self.example('--home', str(sdk.home), '--lp-bps', '37', '--session', sid, *extra)
            self.assertEqual(code, 2, err); self.assertIn('nothing is run', err)
        self.assert_nothing_consumed(sdk)
        self.verified(sdk, sid)
        code, out, err = self.example('--home', str(sdk.home), '--lp-bps', '37', '--session', sid, '--operation', OP, '--local-owner', '--mac-ready')
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)['result']['status'], 'VERIFIED_RESULT')
        self.assertIn('Already verified', err)
        self.assert_nothing_consumed_except_run(sdk)

    def assert_nothing_consumed_except_run(self, sdk):
        for rel in ('scenarios/consents', 'scenarios/execution-attempts'):
            self.assertFalse((sdk.home / rel).exists(), rel)


if __name__ == '__main__':
    unittest.main()
