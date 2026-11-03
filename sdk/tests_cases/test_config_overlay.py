"""Parameterized Config Overlay Engine 0.1 (SDK 0.4).

Pure composition, spec and session tests on synthetic inputs, plus the real-capture plan. Registration,
authentication, binding, run, verifier and MPT target authentication are replaced or must not be reached;
nothing here is native or EVM evidence. The worker's own checks are tested in native/overlay_test.go.
"""
from pathlib import Path
import copy, hashlib, json, subprocess, sys, unittest
from unittest.mock import patch

from developer.files import canonical, load, tree
from rhook_alpha import config_overlay as co
from rhook_alpha import dynamic_fee
from rhook_alpha.execution import ExecutionError, ExecutionSDK, _validate_spec, _profile, commit
from rhook_alpha.session import hookr, workflow
from rhook_alpha.session.hookr import OVERLAY_KIND, OVERLAY_SUBHOME
import test_interventions as cases
from test_session import NoNativeNoNetwork, SDK, COVERAGE, REAL
from test_session_plan import Forbidden, satisfied_report, READY
from test_session_workflow import WorkflowTest, comparison, READY_DOCTOR, OP

# Written out, not recomputed: the same vectors as native/overlay_test.go and the SDK 0.4 blocker analysis.
ORIGINAL = '0x0000000007d0000000000064000000020000000000000000002cec0000000000'
LP23 = '0x0000000007d0000000000017000000020000000000000000002cec0000000000'
DF_OFF = '0x0000000007d0000000000064000000000000000000000000000bb80000000000'
MERGED = '0x0000000007d0000000000017000000000000000000000000000bb80000000000'
ROOT_ON, ROOT_OFF = co.ROOT_ON, co.ROOT_OFF
LP = lambda v: dict(kind=co.LP_REWARDS, lpBps=v)
OFF = dict(kind=co.DYNAMIC_FEE, dynamicFee='OFF')
OVERLAY_PROFILE = co.PROFILE


def projection():
    _, _, d = cases.Interventions().prepared()
    return d['originalProjection']


def descriptor(items, spec=None):
    return co.describe(spec or cases.fixture(), projection(), items, source_sha256='a' * 64)


class Composition(unittest.TestCase):
    def code(self, call, expected):
        with self.assertRaises(ExecutionError) as e:
            call()
        self.assertEqual(e.exception.code, expected, e.exception.details)

    def compose(self, items, rules=ORIGINAL, root=ROOT_ON, **kw):
        return co.compose(items, rules, root, _profile(), **kw)

    def test_lp_dynamic_and_combined_words_fields_and_writes(self):
        p = _profile()
        rules_address = next(c['address'] for c in p['manifest']['contracts'] if c['role'] == 'rules')
        for items, word, root, n, f in (([LP(23)], LP23, ROOT_ON, 1, (23, 11500, 2, 3)), ([OFF], DF_OFF, ROOT_OFF, 2, (100, 3000, 0, 2)),
                                        ([OFF, LP(23)], MERGED, ROOT_OFF, 2, (23, 3000, 0, 2))):
            c = self.compose(items)
            self.assertEqual((c['rules'], c['root'], len(c['writes'])), (word, root, n))
            self.assertEqual(tuple(c['fields'][k] for k in ('lpBps', 'maxFeePips', 'sensitivity', 'rootMode')), f)
            self.assertEqual(c['writes'][0], dict(address=rules_address, slot=p['configSlot'], before=ORIGINAL, after=word))
            if n == 2:
                self.assertEqual(c['writes'][1], dict(address=p['poolKey']['hooks'], slot=p['rootRecordSlot'], before=ROOT_ON, after=ROOT_OFF))
        # The Dynamic-only overlay is the existing Dynamic Fee OFF relation; the existing full word would reset LP to 100.
        _, _, d = cases.Interventions().prepared()
        self.assertEqual([(w['before'], w['after']) for w in self.compose([OFF])['writes']], [(w['before'], w['after']) for w in d['writes']])
        self.assertEqual(co.fields(DF_OFF, ROOT_OFF)['lpBps'], 100)
        self.assertEqual(self.compose([LP(0)])['fields']['lpBps'], 0)

    def test_order_independence_and_canonical_set(self):
        self.assertEqual(co.canonical_interventions([LP(23), OFF]), co.canonical_interventions([OFF, LP(23)]))
        self.assertEqual(co.canonical_interventions([LP(23), OFF]), [OFF, LP(23)])
        self.assertEqual(self.compose([LP(23), OFF]), self.compose([OFF, LP(23)]))

    def test_rejects_unknown_duplicate_and_invalid_parameters(self):
        for items, code in (([], 'CONFIG_OVERLAY_INTERVENTION_COUNT'), ([OFF, LP(1), LP(2)], 'CONFIG_OVERLAY_INTERVENTION_COUNT'),
                            ('LP23', 'CONFIG_OVERLAY_INTERVENTION_COUNT'), ([['LP_REWARDS_BPS']], 'CONFIG_OVERLAY_DESCRIPTOR'),
                            ([dict(kind='STORAGE_WRITE', slot='0x0', value='0x1')], 'CONFIG_OVERLAY_UNKNOWN_INTERVENTION'),
                            ([LP(23), LP(37)], 'CONFIG_OVERLAY_DUPLICATE_KIND'), ([OFF, OFF], 'CONFIG_OVERLAY_DUPLICATE_KIND'),
                            ([LP(100)], 'CONFIG_OVERLAY_LP_PARAMETER'), ([LP(-1)], 'CONFIG_OVERLAY_LP_PARAMETER'), ([LP(True)], 'CONFIG_OVERLAY_LP_PARAMETER'),
                            ([LP('23')], 'CONFIG_OVERLAY_LP_PARAMETER'), ([LP(23.0)], 'CONFIG_OVERLAY_LP_PARAMETER'), ([dict(kind=co.LP_REWARDS)], 'CONFIG_OVERLAY_LP_PARAMETER'),
                            ([dict(LP(23), dynamicFee='OFF')], 'CONFIG_OVERLAY_LP_PARAMETER'), ([dict(OFF, dynamicFee='ON')], 'CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER'),
                            ([dict(kind=co.DYNAMIC_FEE)], 'CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER'), ([dict(OFF, lpBps=23)], 'CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER'),
                            ([dict(OFF, maxFeePips=0)], 'CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER')):
            self.code(lambda: self.compose(items), code)

    def test_mask_conflicts_preconditions_and_width(self):
        overlapping = dict(co.REGISTRY, LP_HIGH_BYTE=lambda item, p: [('lpBps', lambda x: True, 1)])
        self.code(lambda: self.compose([LP(23), dict(kind='LP_HIGH_BYTE')], registry=overlapping), 'CONFIG_OVERLAY_MASK_CONFLICT')
        wide = dict(WIDE=lambda item, p: [('rootMode', lambda x: True, 256)])
        self.code(lambda: self.compose([dict(kind='WIDE')], registry=wide), 'CONFIG_OVERLAY_VALUE_WIDTH')
        lp99 = '0x' + format((int(ORIGINAL, 16) & ~co._mask('lpBps')) | (99 << 160), '064x')
        self.code(lambda: self.compose([LP(23)], rules=lp99), 'CONFIG_OVERLAY_ORIGINAL_PRECONDITION')
        self.code(lambda: self.compose([OFF], root=ROOT_OFF), 'CONFIG_OVERLAY_ORIGINAL_PRECONDITION')
        self.code(lambda: self.compose([OFF], rules=DF_OFF), 'CONFIG_OVERLAY_ORIGINAL_PRECONDITION')

    def test_every_non_target_bit_is_preserved(self):
        target = co._mask('lpBps') | co._mask('maxFeePips') | co._mask('sensitivity')
        ones = (1 << 256) - 1
        seed = int('5a5aa5a5c3c33c3c0ff0f00f12345678deadbeef0badf00d13579bdf2468ace0', 16)
        for noise in (ones, 0, seed, ones ^ seed):
            rules = (noise & ~target) | (int(ORIGINAL, 16) & target)
            root = (noise & ~co._mask('rootMode')) | (3 << 248)
            c = self.compose([OFF, LP(23)], rules=co._hex(rules), root=co._hex(root))
            self.assertEqual(int(c['rules'], 16) & ~target & ones, rules & ~target & ones)
            self.assertEqual(int(c['root'], 16) & ~co._mask('rootMode') & ones, root & ~co._mask('rootMode') & ones)
            self.assertEqual(c['fields'], dict(lpBps=23, maxFeePips=3000, sensitivity=0, rootMode=2))


class Spec(unittest.TestCase):
    def code(self, call, expected):
        with self.assertRaises(ExecutionError) as e:
            call()
        self.assertEqual(e.exception.code, expected, e.exception.details)

    def built(self, items=(OFF, LP(23))):
        original = cases.fixture()
        return original, co.build_spec(original, descriptor(list(items), original), co.ACCEPTED_OVERLAY_ENGINE)

    def test_descriptor_is_plan_only_and_tamper_evident(self):
        d = descriptor([LP(23), OFF])
        self.assertEqual(co.validate_descriptor(d), d)
        self.assertEqual((d['status'], d['witnessClosureEstablished'], d['interventions']), ('INTERVENTION_PLAN_ONLY', False, [OFF, LP(23)]))
        self.assertEqual(d['fields'], dict(baseline=dict(lpBps=100, maxFeePips=11500, sensitivity=2, rootMode=3),
                                           variant=dict(lpBps=23, maxFeePips=3000, sensitivity=0, rootMode=2)))
        for change, code in ((lambda x: x['writes'][0].update(after=LP23), 'INTERVENTION_WRITES'),
                             (lambda x: x['writes'].append(copy.deepcopy(x['writes'][0])), 'INTERVENTION_WRITES'),
                             (lambda x: x['fields']['variant'].update(lpBps=24), 'INTERVENTION_WRITES'),
                             (lambda x: x.update(interventions=[LP(23), OFF]), 'CONFIG_OVERLAY_CANONICAL_ORDER'),
                             (lambda x: x.update(interventions=[OFF, LP(24)]), 'INTERVENTION_WRITES'),
                             (lambda x: x.update(extra=1), 'CONFIG_OVERLAY_DESCRIPTOR'),
                             (lambda x: x.update(witnessClosureEstablished=True), 'CONFIG_OVERLAY_DESCRIPTOR')):
            x = copy.deepcopy(d); x.pop('interventionCommitment'); change(x)
            x['interventionCommitment'] = commit(co.PLAN_DOMAIN, x)
            self.code(lambda: co.validate_descriptor(x), code)
        x = copy.deepcopy(d); x['writes'][0]['after'] = LP23
        self.code(lambda: co.validate_descriptor(x), 'INTERVENTION_COMMITMENT')

    def test_spec_carries_the_derived_overlay_and_validates(self):
        original, s = self.built()
        self.assertEqual(co.validate_spec(s), s)
        self.assertEqual((s['schema'], s['engine'], s['configurations']['variant'][0]), (co.DOMAIN, co.ACCEPTED_OVERLAY_ENGINE, MERGED))
        self.assertEqual(s['configurations']['variant'][1:], original['configurations']['baseline'][1:])
        self.assertEqual(set(s), set(original) | {'configOverlay'})
        self.assertEqual([(w['before'], w['after']) for w in s['configOverlay']['writes']], [(ORIGINAL, MERGED), (ROOT_ON, ROOT_OFF)])
        self.assertEqual(s['origin'], dict(kind=co.KIND, capsuleId=co.capsule(s)))
        # Same set in any order -> one commitment; another set -> another commitment.
        _, again = self.built((LP(23), OFF))
        _, other = self.built((LP(24), OFF))
        self.assertEqual(again['scenarioCommitment'], s['scenarioCommitment'])
        self.assertNotEqual(other['scenarioCommitment'], s['scenarioCommitment'])

    def test_tampered_specs_are_refused_with_fresh_commitments(self):
        _, s = self.built()
        def overlay(change):
            def fn(x):
                change(x['configOverlay']); o = x['configOverlay']; o.pop('interventionCommitment')
                o['interventionCommitment'] = commit(co.DOMAIN + '/transform', o)
            return fn
        for change, code in ((lambda x: x['configurations']['variant'].__setitem__(0, LP23), 'CONFIG_OVERLAY_VARIANT_WORD'),
                             (lambda x: x['configurations']['variant'].__setitem__(2, ORIGINAL), 'CONFIG_OVERLAY_VARIANT_WORD'),
                             (overlay(lambda o: o['writes'][0].update(after=DF_OFF)), 'CONFIG_OVERLAY_DERIVED_WRITES'),
                             (overlay(lambda o: o['writes'].pop()), 'CONFIG_OVERLAY_DERIVED_WRITES'),
                             (overlay(lambda o: o.update(interventions=[LP(23), OFF])), 'CONFIG_OVERLAY_CANONICAL_ORDER'),
                             (lambda x: x['origin'].update(kind=dynamic_fee.KIND), 'CONFIG_OVERLAY_ORIGIN'),
                             (lambda x: x.update(intervention={}), 'CONFIG_OVERLAY_BINDING'),
                             (lambda x: x.update(unexpected=1), 'UNSUPPORTED_SCENARIO_SHAPE')):
            x = copy.deepcopy(s); x.pop('scenarioCommitment'); change(x)
            x['scenarioCommitment'] = commit(co.DOMAIN, x)
            self.code(lambda: co.validate_spec(x), code)
        x = copy.deepcopy(s); x['configurations']['variant'][0] = LP23
        self.code(lambda: co.validate_spec(x), 'CONFIG_OVERLAY_SPEC_COMMITMENT')

    def test_profiles_do_not_accept_each_others_inputs(self):
        original, s = self.built()
        self.assertEqual(_validate_spec(original, _profile()), 50)
        for call in (lambda: _validate_spec(s, _profile()), lambda: dynamic_fee.validate_spec(s), lambda: co.validate_spec(original)):
            with self.assertRaises(ExecutionError):
                call()
        _, _, d = cases.Interventions().prepared()
        df = dynamic_fee.build_spec(original, d, dynamic_fee.ACCEPTED_DERIVATIVE_ENGINE)
        with self.assertRaises(ExecutionError):
            co.validate_spec(df)

    def test_offline_preparation_binds_only_the_accepted_engine(self):
        self.assertEqual(set(co.ACCEPTED_OVERLAY_ENGINE), {'sourceSha256', 'binarySha256', 'policySha256'})
        self.assertNotEqual(co.ACCEPTED_OVERLAY_ENGINE, dynamic_fee.ACCEPTED_DERIVATIVE_ENGINE)
        sdk = co.ConfigOverlayExecutionSDK(Path('/nonexistent-rhook-home'))
        with self.assertRaises(ExecutionError) as e:
            sdk.prepare_overlay(descriptor([OFF]), '/nonexistent', expected_sha256='a' * 64, output='/nonexistent-out',
                                engine=dynamic_fee.ACCEPTED_DERIVATIVE_ENGINE)
        self.assertEqual(e.exception.code, 'CONFIG_OVERLAY_ENGINE_PIN')
        for name in ('configure', 'prepare'):
            with self.assertRaises(ExecutionError) as e:
                getattr(sdk, name)()
            self.assertEqual(e.exception.code, 'CONFIG_OVERLAY_USE_OVERLAY_API')


def target_plan():
    """Replace the read-only MPT authenticator with the synthetic Root/Rules projection of test_interventions."""
    def plan(self_, witness, *, expected_sha256, interventions, node=None):
        spec = load(witness, 8 << 20)
        return dict(status='TARGET_FIELDS_MPT_AUTHENTICATED_PLAN_ONLY',
                    descriptor=co.describe(spec, projection(), interventions, source_sha256=expected_sha256))
    return patch.object(co.ConfigOverlayExecutionSDK, 'plan_overlay', autospec=True, side_effect=plan)


class OverlaySessionTest(WorkflowTest):
    def planned_overlay(self, lp=23, dynamic='OFF', home='home', with_lp=False):
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), target_plan():
            first = self.plan(37, home=home) if with_lp else None
            sdk = self.sdk(home)
            if first is None:
                value, src, pin = self.pinned(None, f'{home}-SCENARIO.json')
                out = sdk.plan_config_overlay_variant(lp_bps=lp, dynamic_fee=dynamic, source=src, expected_sha256=pin, checkpoint=value['checkpoint'])
            else:
                out = sdk.plan_config_overlay_variant(lp_bps=lp, dynamic_fee=dynamic, session_id=first['sessionId'])
        self.assertEqual(out['status'], READY, out['readiness'])
        return sdk, out['sessionId'], out, first

    def overlay_view(self, sdk, sid):
        return next(v for v in sdk.open_session(sid).variants() if v['descriptor']['kind'] == OVERLAY_KIND)

    def home_of(self, sdk):
        return sdk.home / OVERLAY_SUBHOME

    def fake_overlay_run(self, sdk, sid, op=OP):
        session = sdk.open_session(sid)
        prepared = session.directory / self.overlay_view(sdk, sid)['preparation']['preparedDirectory']
        run = self.home_of(sdk) / 'scenarios/runs' / load(prepared / 'PREPARATION.json', 65536)['planId']
        raw = (prepared / 'SCENARIO.json').read_bytes(); spec = json.loads(raw)
        (run / 'inputs').mkdir(parents=True); (run / 'inputs/SCENARIO.json').write_bytes(raw)
        (run / 'BINDING.json').write_bytes(canonical(dict(profile=OVERLAY_PROFILE, scenarioSha256=hashlib.sha256(raw).hexdigest(), operationCommitment=op)))
        (run / 'RESULT.json').write_bytes(canonical(dict(status='SCENARIO_COMPLETED', operationCommitment=op, scenarioCommitment=spec['scenarioCommitment'])))
        (run / 'runtime/scenario').mkdir(parents=True)
        worlds = [dict(world=w, stateRoot='0x' + c * 64, receiptsRoot='0x' + c * 64, actorBalanceBefore='1000', actorBalanceAfter='990',
                       originalWitnessCommitment='d' * 64) for w, c in (('SCENARIO_BASELINE', '7'), ('SCENARIO_VARIANT', '8'))]
        (run / 'runtime/scenario/FINAL.json').write_bytes(canonical(dict(scenarioCommitment=spec['scenarioCommitment'], evidenceCommitment='e' * 64, worlds=worlds)))
        (run / 'MANIFEST.json').write_bytes(canonical(dict(files=tree(run, omit=('MANIFEST.json',)))))
        return run, spec


class SessionDescriptor(OverlaySessionTest):
    def test_combined_and_explicit_overlay_variants_with_stable_identities(self):
        s, _, _ = self.session()
        both = s.add_variant({'lpBps': 23, 'dynamicFee': 'OFF'})
        self.assertEqual(both['descriptor'], dict(kind=OVERLAY_KIND, field='RulesConfig+RootRecord', poolId=s.header['common']['poolId'],
                                                  original=dict(lpBps=100, dynamicFee='ON'), replacement=dict(lpBps=23, dynamicFee='OFF'),
                                                  interventions=[OFF, LP(23)], backendProfile=OVERLAY_PROFILE))
        again = s.add_variant({'dynamicFee': 'OFF', 'lpBps': 23, 'backend': OVERLAY_PROFILE})
        self.assertEqual((again['variantId'], again['alreadyRegistered']), (both['variantId'], True))
        # A single setting on the overlay worker is a distinct variant; without backend it keeps its legacy descriptor.
        lp_overlay = s.add_variant({'lpBps': 23, 'backend': OVERLAY_PROFILE})
        lp_legacy = s.add_variant({'lpBps': 23})
        df_legacy = s.add_variant({'dynamicFee': 'OFF'})
        self.assertEqual(lp_overlay['descriptor']['interventions'], [LP(23)])
        self.assertEqual(set(lp_legacy['descriptor']), {'kind', 'field', 'poolId', 'original', 'replacement'})
        self.assertEqual(df_legacy['descriptor']['kind'], hookr.DYNAMIC_KIND)
        self.assertEqual(len({both['variantId'], lp_overlay['variantId'], lp_legacy['variantId'], df_legacy['variantId']}), 4)
        adapter = s.adapter
        for v in s.variants():
            self.assertEqual(adapter.variant_descriptor(adapter.parameters(v['descriptor']), s.header), v['descriptor'])
        self.assertEqual([v['descriptor']['kind'] for v in s.variants()], ['HOOKR_LP_REWARDS_BPS', 'HOOKR_DYNAMIC_FEE', OVERLAY_KIND, OVERLAY_KIND])
        for parameters, code in (({'lpBps': 23, 'dynamicFee': 'ON'}, 'DYNAMIC_FEE_ON_IS_THE_BASELINE'), ({'lpBps': 100, 'dynamicFee': 'OFF'}, 'LP_BPS_0_TO_99_REQUIRED'),
                                 ({'backend': OVERLAY_PROFILE}, 'UNSUPPORTED_VARIANT'), ({'lpBps': 23, 'backend': 'nitro-hookr-scenario/0.1'}, 'UNSUPPORTED_BACKEND'),
                                 ({'lpBps': 23, 'dynamicFee': 'OFF', 'sensitivity': 0}, 'UNSUPPORTED_VARIANT')):
            self.code(lambda: s.add_variant(parameters), code)
        self.assertEqual(len(s.variants()), 4)


class SessionPlan(OverlaySessionTest):
    def test_plan_prepares_for_the_overlay_worker_and_runs_nothing(self):
        with NoNativeNoNetwork() as guard, Forbidden():
            sdk, sid, out, lp = self.planned_overlay(with_lp=True)
        self.assertEqual(guard.launched, [])
        self.assertEqual((out['lpBps'], out['dynamicFee'], out['interventions'], out['backendProfile']), (23, 'OFF', [OFF, LP(23)], OVERLAY_PROFILE))
        self.assertEqual(out['operation']['status'], 'OPERATION_NOT_BOUND')
        targets = out['interventionTargets']
        self.assertEqual([(w['before'], w['after']) for w in targets['writes']], [(ORIGINAL, MERGED), (ROOT_ON, ROOT_OFF)])
        self.assertEqual(targets['fields']['variant'], dict(lpBps=23, maxFeePips=3000, sensitivity=0, rootMode=2))
        self.assertEqual((targets['engine'], targets['backendProfile']), (co.ACCEPTED_OVERLAY_ENGINE, OVERLAY_PROFILE))
        self.assertIn('config-overlay', out['readiness']['remaining'][0]['step'])
        spec = load(sdk.home / out['prepared']['preparedDirectory'] / 'SCENARIO.json', 8 << 20)
        self.assertEqual((spec['schema'], spec['configurations']['variant'][0]), (co.DOMAIN, MERGED))
        self.assertEqual(co.validate_spec(spec), spec)
        self.assertTrue((self.home_of(sdk) / 'scenarios/plans').is_dir())
        for home in (sdk.home, self.home_of(sdk)):
            for rel in ('scenarios/RUNTIME.json', 'scenarios/consents', 'scenarios/execution-attempts', 'scenarios/runs'):
                self.assertFalse((home / rel).exists(), (home, rel))
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), target_plan(), Forbidden():
            again = sdk.plan_config_overlay_variant(dynamic_fee='OFF', lp_bps=23, session_id=sid)
            lp_again = sdk.plan_lp_variant(37, session_id=sid)
        self.assertEqual((again['alreadyRegistered'], again['prepared']['alreadyPrepared'], again['prepared']['scenarioCommitment']),
                         (True, True, out['prepared']['scenarioCommitment']))
        self.assertEqual(lp_again['prepared']['scenarioCommitment'], lp['prepared']['scenarioCommitment'])

    def test_single_settings_on_the_overlay_worker(self):
        sdk, sid, df, _ = self.planned_overlay(lp=None)
        self.assertEqual([(w['before'], w['after']) for w in df['interventionTargets']['writes']], [(ORIGINAL, DF_OFF), (ROOT_ON, ROOT_OFF)])
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), target_plan():
            lp = sdk.plan_config_overlay_variant(lp_bps=0, session_id=sid)
        self.assertEqual(lp['status'], READY)
        self.assertEqual([(w['before'], w['after']) for w in lp['interventionTargets']['writes']],
                         [(ORIGINAL, '0x0000000007d0000000000000000000020000000000000000002cec0000000000')])
        self.code(lambda: sdk.plan_config_overlay_variant(session_id=sid), 'CONFIG_OVERLAY_SETTING_REQUIRED')


class SessionReadyRun(OverlaySessionTest):
    def test_ready_binds_in_the_overlay_home_with_the_overlay_runtime(self):
        sdk, sid, out, _ = self.planned_overlay()
        homes = []
        def record(name, value):
            def fn(self_, *a, **k):
                homes.append((name, self_.home)); return value
            return fn
        binding = dict(planId='c-test', binarySha256=co.ACCEPTED_OVERLAY_ENGINE['binarySha256'], sourceCommitment=co.ACCEPTED_OVERLAY_ENGINE['sourceSha256'],
                       policySha256='f' * 64, profile=OVERLAY_PROFILE, maximumInvocations={}, RPC=0, WSS=0, automaticRetry=False, externalDelivery='HOLD',
                       hostAdmission=dict(profile='macos-host-admission-v4', policySha256='9' * 64))
        auth = dict(status='AUTHENTICATED_SCENARIO_INPUT', scenarioCommitment=out['prepared']['scenarioCommitment'], nativeExecutions=0)
        with patch.object(ExecutionSDK, 'register_runtime', autospec=True, side_effect=record('runtime', {})), \
             patch.object(ExecutionSDK, 'register_host', autospec=True, side_effect=record('host', {})), \
             patch.object(ExecutionSDK, 'authenticate', autospec=True, side_effect=record('authenticate', auth)), \
             patch.object(ExecutionSDK, 'operation', autospec=True, side_effect=record('operation', dict(binding=binding, operationCommitment=OP,
                                                                                                       outputPath=str(self.home_of(sdk) / 'scenarios/runs/c-test')))), \
             patch.object(ExecutionSDK, 'run', side_effect=AssertionError('no run in Stage B')), \
             patch.object(workflow, 'doctor', return_value=READY_DOCTOR):
            for runtime_profile in ('nitro-hookr-scenario/0.1', dynamic_fee.PROFILE):
                self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=23, dynamic_fee='OFF', runtime=self.manifest(runtime_profile.replace('/', '-') + '.json', runtime_profile),
                                                       sensor=self.root / 'sensor'), 'RUNTIME_PROFILE_MISMATCH')
            self.assertEqual(homes, [])
            self.code(lambda: sdk.ready_lp_variant(sid, lp_bps=23), 'VARIANT_NOT_PLANNED')
            value = sdk.ready_lp_variant(sid, lp_bps=23, dynamic_fee='OFF', runtime=self.manifest('overlay.json', OVERLAY_PROFILE), sensor=self.root / 'sensor')
        self.assertEqual(value['status'], 'RUN_READY')
        self.assertEqual({h for _, h in homes}, {self.home_of(sdk)})
        self.assertEqual([n for n, _ in homes], ['runtime', 'host', 'authenticate', 'operation'])
        self.assertEqual((value['lpBps'], value['dynamicFee'], value['interventions'], value['operationCommitment']), (23, 'OFF', [OFF, LP(23)], OP))
        self.assertEqual(value['next']['command'][-6:], ['--variant', value['variantId'], '--operation', OP, '--local-owner', '--mac-ready'])
        self.assertEqual(value['backendHome'], str(self.home_of(sdk)))

    def test_run_verifies_in_the_overlay_home_and_reports_both_settings(self):
        sdk, sid, out, _ = self.planned_overlay()
        calls, compares = [], []
        def run(self_, prepared, *, operation, evidence, local_owner, mac_ready, host_profile):
            calls.append(self_.home); Path(evidence).mkdir(parents=True)
            r, _ = self.fake_overlay_run(sdk, sid, op=operation)
            return dict(status='EXECUTION_COMPLETED', operationCommitment=operation, runDirectory=str(r), cleanupConfirmed=True,
                        nativeResult=dict(status='SCENARIO_COMPLETED', producerInvocations=2, RPC=0, WSS=0, cleanupConfirmed=True))
        def compare(self_, r):
            compares.append(self_.home); return comparison(r)
        vid = self.overlay_view(sdk, sid)['variantId']
        with patch.object(workflow, 'doctor', return_value=READY_DOCTOR), patch.object(ExecutionSDK, 'run', autospec=True, side_effect=run), \
             patch.object(ExecutionSDK, 'verify', return_value=dict(status='SCENARIO_RECORDED_INTEGRITY_PASS')), \
             patch.object(ExecutionSDK, 'compare', autospec=True, side_effect=compare):
            value = sdk.run_lp_variant(sid, variant_id=vid, operation=OP, local_owner=True, mac_ready=True)
        self.assertEqual(value['status'], 'RUN_VERIFIED', value)
        self.assertEqual((calls, compares), ([self.home_of(sdk)], [self.home_of(sdk)]))
        card = value['result']
        self.assertEqual(card['parameter'], dict(field='RulesConfig+RootRecord', baseline=dict(lpBps=100, dynamicFee='ON'), variant=dict(lpBps=23, dynamicFee='OFF')))
        self.assertEqual([(w['lpBps'], w['dynamicFee']) for w in card['worlds']], [(100, 'ON'), (23, 'OFF')])
        self.assertIn('LP23 + DF OFF (variant)', workflow.render(card))
        self.assertEqual(sdk.lp_variant_result(sid, lp_bps=23, dynamic_fee='OFF')['status'], 'VERIFIED_RESULT')

    def test_runs_must_match_the_variant_backend(self):
        sdk, sid, out, lp = self.planned_overlay(with_lp=True)
        s = sdk.open_session(sid); vid = self.overlay_view(sdk, sid)['variantId']
        run, spec = self.fake_overlay_run(sdk, sid)
        for profile in ('nitro-hookr-scenario/0.1', dynamic_fee.PROFILE):
            mixed = json.loads((run / 'BINDING.json').read_bytes()); mixed['profile'] = profile
            (run / 'BINDING.json').write_bytes(canonical(mixed))
            self.code(lambda: s.verify_selected(vid, run, test_only_backend=comparison), 'WRONG_PROFILE_EVIDENCE')
        lp_run = self.fake_run(sdk, sid)
        self.code(lambda: s.verify_selected(vid, lp_run, test_only_backend=comparison), 'WRONG_VARIANT_RESULT')
        self.assertFalse((s.directory / 'variants' / vid / 'VERIFICATION.json').exists())


class Cli(OverlaySessionTest):
    def cli(self, home, *args):
        r = subprocess.run([sys.executable, '-B', '-m', 'rhook_alpha.cases', '--home', str(home), *args], cwd=SDK, capture_output=True, timeout=120)
        return r.returncode, r.stdout.decode(), r.stderr.decode()

    def test_cli_routes_both_settings_to_the_overlay_worker(self):
        value, src, pin = self.pinned()
        cp = self.root / 'cp.json'; cp.write_text(json.dumps(value['checkpoint']))
        home = self.root / 'cli-home'
        code, out, _ = self.cli(home, 'session-plan', '--lp-bps', '23', '--dynamic-fee', 'OFF', '--scenario', str(src), '--sha256', pin, '--checkpoint', str(cp))
        plan = json.loads(out)
        self.assertEqual((plan['descriptor']['kind'], plan['descriptor']['interventions']), (OVERLAY_KIND, [OFF, LP(23)]))
        self.assertEqual(plan['operation']['status'], 'OPERATION_NOT_BOUND')
        code, out, _ = self.cli(home, 'session-plan', '--lp-bps', '23', '--config-overlay', '--session', plan['sessionId'])
        self.assertEqual(json.loads(out)['descriptor']['interventions'], [LP(23)])
        code, out, _ = self.cli(home, 'session-ready', '--session', plan['sessionId'], '--variant', plan['variantId'], '--lp-bps', '23')
        self.assertEqual((code, json.loads(out)['causeCode']), (1, 'VARIANT_SELECTION'))
        self.assertFalse((home / OVERLAY_SUBHOME / 'scenarios/RUNTIME.json').exists())


@COVERAGE
class RealCapture(OverlaySessionTest):
    @unittest.skipUnless(REAL, 'RHOOK_SESSION_REAL_CAPTURE not set')
    def test_real_capture_plans_the_combined_variant_next_to_lp37_and_dynamic_fee_off(self):
        source = Path(REAL) / 'SCENARIO.json'
        raw = source.read_bytes(); pin = hashlib.sha256(raw).hexdigest(); spec = json.loads(raw)
        sdk = self.sdk('real')
        lp = sdk.plan_lp_variant(37, source=source, expected_sha256=pin, checkpoint=spec['checkpoint'])
        df = sdk.plan_dynamic_fee_variant('OFF', session_id=lp['sessionId'])
        both = sdk.plan_config_overlay_variant(lp_bps=23, dynamic_fee='OFF', session_id=lp['sessionId'])
        self.assertEqual((lp['status'], df['status'], both['status']), (READY, READY, READY))
        # Existing identities are unchanged next to the new profile.
        self.assertEqual(lp['variantId'], 'a55efba370137c39d36cf219008f3891eb357aa9e6d30e9b7b7a6e6828f7283a')
        self.assertEqual(lp['prepared']['scenarioCommitment'], 'c5c5f9fc7382818641255aa266a6eb11472df78eb1cb23b8e6170433ffdaa435')
        self.assertEqual(df['prepared']['scenarioSha256'], '90b72e52bd1a8844ec84368ae56f52e4f0272a7737f521765a5b1fe2188c5722')
        self.assertEqual((both['staticCoverage']['status'], both['profilePreconditions']), ('COVERED', 'SATISFIED'))
        self.assertEqual(both['interventionTargets']['authentication'], 'ORIGINAL_ROOT_MPT_AUTHENTICATED')
        self.assertEqual([(w['before'], w['after']) for w in both['interventionTargets']['writes']], [(ORIGINAL, MERGED), (ROOT_ON, ROOT_OFF)])
        self.assertEqual(both['prepared']['scenarioCommitment'], 'fc70c8fad7006c1a77de8bcee00142673df0eb39bdfaf167d51a1af9d2319295')


if __name__ == '__main__':
    unittest.main()
