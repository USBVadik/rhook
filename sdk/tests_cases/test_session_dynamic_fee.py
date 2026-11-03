"""Dynamic Fee OFF as the second session intervention (SDK 0.3).

Synthetic inputs, except the real-capture test. Registration, authentication, binding, run, verifier and
MPT target authentication are replaced or must not be reached; nothing here is native or EVM evidence.
"""
from pathlib import Path
import hashlib, json, subprocess, sys, unittest
from unittest.mock import patch

from developer.files import canonical, load, tree
from rhook_alpha.execution import ExecutionSDK
from rhook_alpha.dynamic_fee import ACCEPTED_DERIVATIVE_ENGINE, DOMAIN as DF_DOMAIN, PROFILE as DF_PROFILE, DynamicFeeExecutionSDK
from rhook_alpha.interventions import DYNAMIC_OFF, describe
from rhook_alpha.session import hookr, workflow
from rhook_alpha.session.hookr import DYNAMIC_SUBHOME
import test_interventions as cases
from test_session import NoNativeNoNetwork, SDK, COVERAGE, REAL
from test_session_plan import Forbidden, satisfied_report, READY
from test_session_workflow import WorkflowTest, comparison, READY_DOCTOR, OP

ORIGINAL_CONFIG = '0x0000000007d0000000000064000000020000000000000000002cec0000000000'
OFF_CONFIG = '0x0000000007d0000000000064000000000000000000000000000bb80000000000'
ROOT_ON = '0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'
ROOT_OFF = '0x020101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'


def target_plan():
    """Replace the read-only MPT authenticator with the synthetic Root/Rules projection of test_interventions."""
    _, _, d0 = cases.Interventions().prepared()
    def plan(self_, witness, *, expected_sha256, kind, lp_bps=None, node=None):
        assert kind == DYNAMIC_OFF and lp_bps is None
        spec = load(witness, 8 << 20)
        return dict(status='TARGET_FIELDS_MPT_AUTHENTICATED_PLAN_ONLY',
                    descriptor=describe(spec, d0['originalProjection'], kind=DYNAMIC_OFF, source_sha256=expected_sha256))
    return patch.object(DynamicFeeExecutionSDK, 'plan_intervention', autospec=True, side_effect=plan)


class DynamicFeeTest(WorkflowTest):
    def planned_df(self, sdk_name='home', with_lp=False):
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), target_plan():
            lp = self.plan(37, home=sdk_name) if with_lp else None
            sdk = self.sdk(sdk_name)
            if lp is None:
                value, src, pin = self.pinned(None, f'{sdk_name}-SCENARIO.json')
                out = sdk.plan_dynamic_fee_variant('OFF', source=src, expected_sha256=pin, checkpoint=value['checkpoint'])
            else:
                out = sdk.plan_dynamic_fee_variant('OFF', session_id=lp['sessionId'])
        self.assertEqual(out['status'], READY, out['readiness'])
        return sdk, out['sessionId'], out, lp

    def df_view(self, sdk, sid):
        return next(v for v in sdk.open_session(sid).variants() if v['descriptor']['kind'] == hookr.DYNAMIC_KIND)

    def df_home(self, sdk):
        return sdk.home / DYNAMIC_SUBHOME

    def fake_df_run(self, sdk, sid, op=OP):
        session = sdk.open_session(sid)
        prepared = session.directory / self.df_view(sdk, sid)['preparation']['preparedDirectory']
        run = self.df_home(sdk) / 'scenarios/runs' / load(prepared / 'PREPARATION.json', 65536)['planId']
        raw = (prepared / 'SCENARIO.json').read_bytes(); spec = json.loads(raw)
        (run / 'inputs').mkdir(parents=True); (run / 'inputs/SCENARIO.json').write_bytes(raw)
        (run / 'BINDING.json').write_bytes(canonical(dict(profile=DF_PROFILE, scenarioSha256=hashlib.sha256(raw).hexdigest(), operationCommitment=op)))
        (run / 'RESULT.json').write_bytes(canonical(dict(status='SCENARIO_COMPLETED', operationCommitment=op, scenarioCommitment=spec['scenarioCommitment'])))
        (run / 'runtime/scenario').mkdir(parents=True)
        worlds = [dict(world=w, stateRoot='0x' + c * 64, receiptsRoot='0x' + c * 64, actorBalanceBefore='1000', actorBalanceAfter='990',
                       originalWitnessCommitment='d' * 64) for w, c in (('SCENARIO_BASELINE', '5'), ('SCENARIO_VARIANT', '6'))]
        (run / 'runtime/scenario/FINAL.json').write_bytes(canonical(dict(scenarioCommitment=spec['scenarioCommitment'], evidenceCommitment='e' * 64, worlds=worlds)))
        (run / 'MANIFEST.json').write_bytes(canonical(dict(files=tree(run, omit=('MANIFEST.json',)))))
        return run, spec


class Descriptor(DynamicFeeTest):
    def test_one_off_variant_with_stable_identity_and_unchanged_lp_descriptors(self):
        s, _, _ = self.session()
        first = s.add_variant({'dynamicFee': 'OFF'}); again = s.add_variant({'dynamicFee': 'OFF'})
        self.assertEqual((first['variantId'], again['alreadyRegistered']), (again['variantId'], True))
        self.assertEqual(first['descriptor'], dict(kind='HOOKR_DYNAMIC_FEE', field='DynamicFee', poolId=s.header['common']['poolId'],
                                                   original='ON', replacement='OFF', backendProfile=DF_PROFILE))
        lp = s.add_variant({'lpBps': 37})
        self.assertEqual(set(lp['descriptor']), {'kind', 'field', 'poolId', 'original', 'replacement'})
        self.assertEqual([v['descriptor']['kind'] for v in s.variants()], ['HOOKR_LP_REWARDS_BPS', 'HOOKR_DYNAMIC_FEE'])
        for parameters, code in (({'dynamicFee': 'ON'}, 'DYNAMIC_FEE_ON_IS_THE_BASELINE'), ({'dynamicFee': 'off'}, 'DYNAMIC_FEE_OFF_ONLY'),
                                 ({'dynamicFee': True}, 'DYNAMIC_FEE_OFF_ONLY'), ({'lpBps': 37, 'dynamicFee': 'OFF', 'maxFeePips': 3000}, 'UNSUPPORTED_VARIANT'),
                                 ({'lpBps': 37, 'backend': DF_PROFILE}, 'UNSUPPORTED_BACKEND'), ({'maxFeePips': 3000}, 'UNSUPPORTED_VARIANT')):
            self.code(lambda: s.add_variant(parameters), code)
        self.assertEqual(len(s.variants()), 2)


class Plan(DynamicFeeTest):
    def test_plan_prepares_for_the_derivative_and_runs_nothing(self):
        with NoNativeNoNetwork() as guard, Forbidden():
            sdk, sid, out, lp = self.planned_df(with_lp=True)
        self.assertEqual(guard.launched, [])
        self.assertEqual((out['dynamicFee'], out['baselineDynamicFee'], out['lpBps']), ('OFF', 'ON', 100))
        self.assertEqual(out['operation']['status'], 'OPERATION_NOT_BOUND')
        targets = out['interventionTargets']
        self.assertEqual(targets['authentication'], 'ORIGINAL_ROOT_MPT_AUTHENTICATED')
        self.assertEqual([(w['before'], w['after']) for w in targets['writes']], [(ORIGINAL_CONFIG, OFF_CONFIG), (ROOT_ON, ROOT_OFF)])
        self.assertEqual((targets['engine'], targets['backendProfile']), (ACCEPTED_DERIVATIVE_ENGINE, DF_PROFILE))
        self.assertEqual([r['stage'] for r in out['readiness']['remaining']], ['B', 'B', 'B', 'C', 'C'])
        self.assertIn('derivative', out['readiness']['remaining'][0]['step'])
        self.assertNotEqual(out['prepared']['scenarioCommitment'], lp['prepared']['scenarioCommitment'])
        spec = load(sdk.home / out['prepared']['preparedDirectory'] / 'SCENARIO.json', 8 << 20)
        self.assertEqual((spec['schema'], spec['engine'], spec['configurations']['variant'][0]), (DF_DOMAIN, ACCEPTED_DERIVATIVE_ENGINE, OFF_CONFIG))
        # Plans live in the derivative's own home; nothing native or authoritative exists anywhere.
        self.assertTrue((self.df_home(sdk) / 'scenarios/plans').is_dir())
        for home in (sdk.home, self.df_home(sdk)):
            for rel in ('scenarios/RUNTIME.json', 'scenarios/consents', 'scenarios/execution-attempts', 'scenarios/runs'):
                self.assertFalse((home / rel).exists(), (home, rel))
        # Planning again changes nothing; LP37 in the same session is unaffected.
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), target_plan(), Forbidden():
            again = sdk.plan_dynamic_fee_variant('OFF', session_id=sid)
            lp_again = sdk.plan_lp_variant(37, session_id=sid)
        self.assertEqual((again['alreadyRegistered'], again['prepared']['alreadyPrepared'], again['prepared']['scenarioCommitment']),
                         (True, True, out['prepared']['scenarioCommitment']))
        self.assertEqual(lp_again['prepared']['scenarioCommitment'], lp['prepared']['scenarioCommitment'])

    def test_failed_target_authentication_is_a_plan_stop(self):
        from rhook_alpha.execution import ExecutionError
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), \
             patch.object(DynamicFeeExecutionSDK, 'plan_intervention', side_effect=ExecutionError('HOOK_BLOCK_NOT_ACTIVE', 'Dynamic Fee must be active.')):
            value, src, pin = self.pinned()
            out = self.sdk().plan_dynamic_fee_variant('OFF', source=src, expected_sha256=pin, checkpoint=value['checkpoint'])
        self.assertEqual((out['status'], out['readiness']['stops'][0]['code'], out['prepared']), ('PLAN_STOP', 'HOOK_BLOCK_NOT_ACTIVE', None))


class Ready(DynamicFeeTest):
    def test_ready_registers_and_binds_in_the_derivative_home(self):
        sdk, sid, out, _ = self.planned_df()
        homes = []
        def record(name, value):
            def fn(self_, *a, **k):
                homes.append((name, self_.home)); return value
            return fn
        binding = dict(planId='c-test', binarySha256=ACCEPTED_DERIVATIVE_ENGINE['binarySha256'], sourceCommitment=ACCEPTED_DERIVATIVE_ENGINE['sourceSha256'],
                       policySha256='f' * 64, profile=DF_PROFILE, maximumInvocations={}, RPC=0, WSS=0, automaticRetry=False, externalDelivery='HOLD',
                       hostAdmission=dict(profile='macos-host-admission-v4', policySha256='9' * 64))
        auth = dict(status='AUTHENTICATED_SCENARIO_INPUT', scenarioCommitment=out['prepared']['scenarioCommitment'], nativeExecutions=0)
        with patch.object(ExecutionSDK, 'register_runtime', autospec=True, side_effect=record('runtime', {})), \
             patch.object(ExecutionSDK, 'register_host', autospec=True, side_effect=record('host', {})), \
             patch.object(ExecutionSDK, 'authenticate', autospec=True, side_effect=record('authenticate', auth)), \
             patch.object(ExecutionSDK, 'operation', autospec=True, side_effect=record('operation', dict(binding=binding, operationCommitment=OP,
                                                                                                       outputPath=str(self.df_home(sdk) / 'scenarios/runs/c-test')))), \
             patch.object(ExecutionSDK, 'run', side_effect=AssertionError('no run in Stage B')), \
             patch.object(workflow, 'doctor', return_value=READY_DOCTOR):
            self.code(lambda: sdk.ready_lp_variant(sid, dynamic_fee='OFF', runtime=self.manifest(), sensor=self.root / 'sensor'), 'RUNTIME_PROFILE_MISMATCH')
            self.assertEqual(homes, [])
            value = sdk.ready_lp_variant(sid, dynamic_fee='OFF', runtime=self.manifest('df.json', DF_PROFILE), sensor=self.root / 'sensor')
        self.assertEqual(value['status'], 'RUN_READY')
        self.assertEqual({h for _, h in homes}, {self.df_home(sdk)})
        self.assertEqual([n for n, _ in homes], ['runtime', 'host', 'authenticate', 'operation'])
        self.assertEqual((value['dynamicFee'], value['baselineDynamicFee'], value['operationCommitment']), ('OFF', 'ON', OP))
        self.assertEqual(value['next']['command'][-6:], ['--dynamic-fee', 'OFF', '--operation', OP, '--local-owner', '--mac-ready'])
        self.assertEqual(value['backendHome'], str(self.df_home(sdk)))


class Run(DynamicFeeTest):
    def test_run_verifies_in_the_derivative_home_and_reports_dynamic_fee_worlds(self):
        sdk, sid, out, _ = self.planned_df()
        calls, compares = [], []
        def run(self_, prepared, *, operation, evidence, local_owner, mac_ready, host_profile):
            calls.append(self_.home); Path(evidence).mkdir(parents=True)
            r, _ = self.fake_df_run(sdk, sid, op=operation)
            return dict(status='EXECUTION_COMPLETED', operationCommitment=operation, runDirectory=str(r), cleanupConfirmed=True,
                        nativeResult=dict(status='SCENARIO_COMPLETED', producerInvocations=2, RPC=0, WSS=0, cleanupConfirmed=True))
        def compare(self_, r):
            compares.append(self_.home); return comparison(r)
        with patch.object(workflow, 'doctor', return_value=READY_DOCTOR), patch.object(ExecutionSDK, 'run', autospec=True, side_effect=run), \
             patch.object(ExecutionSDK, 'verify', return_value=dict(status='SCENARIO_RECORDED_INTEGRITY_PASS')), \
             patch.object(ExecutionSDK, 'compare', autospec=True, side_effect=compare):
            value = sdk.run_lp_variant(sid, dynamic_fee='OFF', operation=OP, local_owner=True, mac_ready=True)
        self.assertEqual(value['status'], 'RUN_VERIFIED')
        self.assertEqual((calls, compares), ([self.df_home(sdk)], [self.df_home(sdk)]))
        self.assertEqual(value['evidenceDirectory'], str(self.root / 'home-evidence' / OP))
        card = value['result']
        self.assertEqual(card['parameter'], dict(field='DynamicFee', baseline='ON', variant='OFF'))
        self.assertEqual([(w['dynamicFee'], w['lpBps']) for w in card['worlds']], [('ON', 100), ('OFF', 100)])
        self.assertEqual(card['verification']['runRecord'], 'MATCHES_MANIFEST_AND_VERIFICATION')
        self.assertIn('Dynamic Fee OFF (variant)', workflow.render(card))
        self.assertEqual(sdk.lp_variant_result(sid, dynamic_fee='OFF')['status'], 'VERIFIED_RESULT')
        with Forbidden():
            self.code(lambda: sdk.run_lp_variant(sid, dynamic_fee='OFF', operation=OP, local_owner=True, mac_ready=True), 'VARIANT_NOT_RUNNABLE')

    def test_runs_must_match_the_variant_backend(self):
        sdk, sid, out, lp = self.planned_df(with_lp=True)
        s = sdk.open_session(sid); vid = self.df_view(sdk, sid)['variantId']
        lp_run = self.fake_run(sdk, sid)
        self.code(lambda: s.verify_selected(vid, lp_run, test_only_backend=comparison), 'WRONG_VARIANT_RESULT')
        df_run, spec = self.fake_df_run(sdk, sid)
        mixed = json.loads((df_run / 'BINDING.json').read_bytes()); mixed['profile'] = 'nitro-hookr-scenario/0.1'
        (df_run / 'BINDING.json').write_bytes(canonical(mixed))
        self.code(lambda: s.verify_selected(vid, df_run, test_only_backend=comparison), 'WRONG_PROFILE_EVIDENCE')
        self.assertFalse((s.directory / 'variants' / vid / 'VERIFICATION.json').exists())


class Cli(DynamicFeeTest):
    def cli(self, home, *args):
        r = subprocess.run([sys.executable, '-B', '-m', 'rhook_alpha.cases', '--home', str(home), *args], cwd=SDK, capture_output=True, timeout=60)
        return r.returncode, r.stdout.decode(), r.stderr.decode()

    def test_cli_selection(self):
        value, src, pin = self.pinned()
        cp = self.root / 'cp.json'; cp.write_text(json.dumps(value['checkpoint']))
        home = self.root / 'cli-home'
        code, out, _ = self.cli(home, 'session-plan', '--dynamic-fee', 'ON', '--scenario', str(src), '--sha256', pin, '--checkpoint', str(cp))
        self.assertEqual((code, json.loads(out)['causeCode']), (1, 'DYNAMIC_FEE_ON_IS_THE_BASELINE'))
        self.assertFalse((home / 'sessions').exists())
        # SDK 0.4: both settings together plan the combined config-overlay variant; no setting at all is refused before writing.
        code, out, _ = self.cli(home, 'session-plan', '--config-overlay', '--scenario', str(src), '--sha256', pin, '--checkpoint', str(cp))
        self.assertEqual((code, json.loads(out)['causeCode']), (1, 'VARIANT_SETTING_REQUIRED'))
        self.assertFalse((home / 'sessions').exists())
        sdk, sid, _ = self.planned()
        code, out, _ = self.cli(sdk.home, 'session-ready', '--session', sid, '--dynamic-fee', 'OFF')
        self.assertEqual((code, json.loads(out)['causeCode']), (1, 'VARIANT_NOT_PLANNED'))
        code, out, _ = self.cli(sdk.home, 'session-result', '--session', sid, '--lp-bps', '37')
        self.assertEqual((code, json.loads(out)['causeCode']), (1, 'VARIANT_NOT_VERIFIED'))


@COVERAGE
class RealCapture(DynamicFeeTest):
    @unittest.skipUnless(REAL, 'RHOOK_SESSION_REAL_CAPTURE not set')
    def test_real_capture_plans_lp37_and_dynamic_fee_off_in_one_session(self):
        source = Path(REAL) / 'SCENARIO.json'
        raw = source.read_bytes(); pin = hashlib.sha256(raw).hexdigest(); spec = json.loads(raw)
        sdk = self.sdk('real')
        lp = sdk.plan_lp_variant(37, source=source, expected_sha256=pin, checkpoint=spec['checkpoint'])
        df = sdk.plan_dynamic_fee_variant('OFF', session_id=lp['sessionId'])
        self.assertEqual((lp['status'], df['status']), (READY, READY))
        self.assertEqual(lp['variantId'], 'a55efba370137c39d36cf219008f3891eb357aa9e6d30e9b7b7a6e6828f7283a')
        self.assertEqual(lp['prepared']['scenarioCommitment'], 'c5c5f9fc7382818641255aa266a6eb11472df78eb1cb23b8e6170433ffdaa435')
        self.assertEqual([(w['before'], w['after']) for w in df['interventionTargets']['writes']], [(ORIGINAL_CONFIG, OFF_CONFIG), (ROOT_ON, ROOT_OFF)])
        self.assertEqual((df['staticCoverage']['status'], df['profilePreconditions']), ('COVERED', 'SATISFIED'))
        self.assertEqual(df['prepared']['scenarioSha256'], '90b72e52bd1a8844ec84368ae56f52e4f0272a7737f521765a5b1fe2188c5722')


if __name__ == '__main__':
    unittest.main()
