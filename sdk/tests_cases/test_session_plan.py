"""Parameterized LP Rewards plan 0.1 tests. Synthetic inputs only; nothing here is native or EVM evidence."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, unittest
from unittest.mock import patch

from developer.files import load
from rhook_alpha.execution import ExecutionSDK
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.session import SessionError, MAX_VARIANTS, hookr
from rhook_alpha.session.plan import lp_bps_text, PLAN_SCHEMA, BASELINE_LP_BPS
from test_execution import fixture as execution_fixture
from test_session import SessionTest, NoNativeNoNetwork, hash_linked_fixture, write, COVERAGE, REAL, SDK

VALID = [0, 1, 25, 37, 49, 50, 51, 75, 99]
READY = 'PLAN_READY_FOR_SEPARATELY_AUTHORIZED_NATIVE_RUN'
FORBIDDEN_CALLS = [(ExecutionSDK, 'operation'), (ExecutionSDK, 'authenticate'), (ExecutionSDK, 'run'), (ExecutionSDK, 'register_runtime'),
                   (ExecutionSDK, 'register_host'), (ExecutionSDK, 'verify'), (ExecutionSDK, 'compare'), (CaseSDK, 'acquire_scenario'),
                   (CaseSDK, 'prepare_scenario'), (CaseSDK, 'check_scenario'), (CaseSDK, 'run_scenario')]


def satisfied_report(preconditions='SATISFIED'):
    checks = [dict(id='A', status='SATISFIED'), dict(id='B', status=preconditions)]
    return dict(status='STATIC_DEPENDENCIES_COVERED', networkRequestsPerformed=0, unresolvedDependencies=0,
                preconditions=dict(status=preconditions, checks=checks))


class Forbidden:
    """Every Stage B/C entry point and every acquisition path raises if reached."""
    def __enter__(self):
        self.patches = [patch.object(cls, name, side_effect=AssertionError(f'{cls.__name__}.{name} must not run')) for cls, name in FORBIDDEN_CALLS]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


class PlanTest(SessionTest):
    def pinned(self, value=None, name='SCENARIO.json'):
        value = value or execution_fixture()
        src, pin = write(self.root, value, name)
        return value, src, pin

    def plan(self, lp, *, home='home', value=None, src=None, pin=None, **kwargs):
        if src is None:
            value, src, pin = self.pinned(value, f'{home}-SCENARIO.json')
        return self.sdk(home).plan_lp_variant(lp, source=src, expected_sha256=pin, checkpoint=value['checkpoint'], **kwargs)

    def assert_boundaries(self, out):
        self.assertEqual(out['schema'], PLAN_SCHEMA)
        self.assertEqual(out['operation']['status'], 'OPERATION_NOT_BOUND')
        def keys(v):
            if type(v) is dict:
                for k, x in v.items():
                    yield k
                    yield from keys(x)
            elif type(v) is list:
                for x in v:
                    yield from keys(x)
        self.assertFalse({'operationCommitment', 'consent', 'attempt', 'runDirectory'} & set(keys(out)))
        self.assertEqual((out['nativeExecutions'], out['networkRequests']), (0, 0))
        self.assertEqual(out['originalWitness']['acquisition'], 'NOT_PERFORMED_RETAINED_WITNESS_REUSED')
        self.assertEqual(out['checkpointCanonicality'], 'NOT_ESTABLISHED_REQUIRES_AN_INDEPENDENTLY_TRUSTED_BLOCK_HASH')
        self.assertEqual(out['limitations'], dict(nativeReexecution='NOT_PERFORMED', heterogeneousAgreement='NOT_EVALUATED',
                                                  economicAssurance='UNRESOLVED', qualifiedClaims=0))
        if out['status'] != 'PLAN_ALREADY_VERIFIED':
            self.assertEqual((out['dynamicCoverage'], out['nativeExecution']), ('UNKNOWN', 'NOT_PERFORMED'))

    def assert_no_native_traces(self, home):
        for rel in ('scenarios/runs', 'scenarios/consents', 'scenarios/execution-attempts', 'scenarios/RUNTIME.json', 'scenarios/helper-failures'):
            self.assertFalse((self.root / home / rel).exists(), rel)


class Input(PlanTest):
    """Validation happens before anything is written; no Node.js required."""
    def test_invalid_values_stop_before_any_write(self):
        value, src, pin = self.pinned()
        cases = [(BASELINE_LP_BPS, 'BASELINE_LP100_IS_NOT_A_VARIANT'), (101, 'LP_BPS_0_TO_99_REQUIRED'), (-1, 'LP_BPS_0_TO_99_REQUIRED'),
                 (37.5, 'LP_BPS_INTEGER_REQUIRED'), (37.0, 'LP_BPS_INTEGER_REQUIRED'), ('37', 'LP_BPS_INTEGER_REQUIRED'),
                 (True, 'LP_BPS_INTEGER_REQUIRED'), (False, 'LP_BPS_INTEGER_REQUIRED'), (None, 'LP_BPS_INTEGER_REQUIRED'),
                 ([37], 'LP_BPS_INTEGER_REQUIRED'), ({'lpBps': 37}, 'LP_BPS_INTEGER_REQUIRED')]
        for i, (lp, code) in enumerate(cases):
            home = f'invalid-{i}'
            self.code(lambda: self.sdk(home).plan_lp_variant(lp, source=src, expected_sha256=pin, checkpoint=value['checkpoint']), code)
            self.assertFalse((self.root / home).exists(), (lp, code))

    def test_cli_text_is_a_plain_decimal_integer(self):
        for text, lp in [('0', 0), ('1', 1), ('37', 37), ('99', 99)]:
            self.assertEqual(lp_bps_text(text), lp)
        for text in ['37.5', '37.0', '1e1', 'abc', '', '037', '+37', ' 37', '37 ', '0x25', '٣٧', None]:
            self.code(lambda: lp_bps_text(text), 'LP_BPS_INTEGER_REQUIRED')
        self.code(lambda: lp_bps_text('100'), 'BASELINE_LP100_IS_NOT_A_VARIANT')
        for text in ('-1', '101', '1000'):
            self.code(lambda: lp_bps_text(text), 'LP_BPS_0_TO_99_REQUIRED')

    def test_exactly_one_session_selection(self):
        value, src, pin = self.pinned()
        sdk = self.sdk()
        self.code(lambda: sdk.plan_lp_variant(37), 'SESSION_SELECTION')
        self.code(lambda: sdk.plan_lp_variant(37, session_id='0' * 64, source=src, expected_sha256=pin, checkpoint=value['checkpoint']), 'SESSION_SELECTION')
        self.code(lambda: sdk.plan_lp_variant(37, source=src, expected_sha256=pin), 'SESSION_SELECTION')
        self.code(lambda: sdk.plan_lp_variant(37, session_id='0' * 64), 'SESSION_MISSING_OR_INCOMPLETE')

    def test_incompatible_checkpoint_and_missing_or_changed_witness(self):
        value, src, pin = self.pinned()
        for field, other in [('blockHash', '0x' + '1' * 64), ('stateRoot', '0x' + '2' * 64), ('blockNumber', 1)]:
            e = self.code(lambda: self.sdk('cp').plan_lp_variant(37, source=src, expected_sha256=pin, checkpoint=dict(value['checkpoint'], **{field: other})),
                          'CHECKPOINT_MISMATCH')
            self.assertEqual(e.details['differingFields'], [field])
        self.code(lambda: self.sdk('missing').plan_lp_variant(37, source=self.root / 'absent.json', expected_sha256=pin, checkpoint=value['checkpoint']),
                  'PREPARED_WITNESS_MISSING')
        self.code(lambda: self.sdk('pin').plan_lp_variant(37, source=src, expected_sha256='0' * 64, checkpoint=value['checkpoint']),
                  'PREPARED_WITNESS_HASH_MISMATCH')
        for home in ('cp', 'missing', 'pin'):
            sessions = self.root / home / 'sessions'
            self.assertFalse(sessions.exists() and any(p.name[0] != '.' for p in sessions.iterdir()), home)


class Readiness(PlanTest):
    """Plan logic over a stored coverage report; the coverage helper is replaced, so no Node.js is required."""
    def test_satisfied_coverage_prepares_and_stops_before_stage_b(self):
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), NoNativeNoNetwork() as guard, Forbidden():
            out = self.plan(37)
        self.assertEqual(guard.launched, [])
        self.assertEqual((out['status'], out['readiness']['status'], out['readiness']['stops']), (READY, 'READY_FOR_STAGE_B', []))
        self.assertEqual([r['stage'] for r in out['readiness']['remaining']], ['B', 'B', 'B', 'C', 'C'])
        self.assertEqual((out['selectedLpBps'], out['descriptor']['replacement'], out['descriptor']['original']), (37, 37, 100))
        self.assertTrue(out['sessionCreated'])
        self.assertFalse(out['prepared']['alreadyPrepared'])
        self.assert_boundaries(out)
        self.assert_no_native_traces('home')
        prepared = load(self.root / 'home' / out['prepared']['preparedDirectory'] / 'SCENARIO.json', 8 << 20)
        self.assertEqual((int(prepared['configurations']['variant'][0], 16) >> 160) & 65535, 37)
        self.assertEqual(hashlib.sha256((self.root / 'home' / out['prepared']['preparedDirectory'] / 'SCENARIO.json').read_bytes()).hexdigest(),
                         out['prepared']['scenarioSha256'])

    def test_registered_runtime_files_do_not_lead_to_binding(self):
        value, src, pin = self.pinned()
        (self.root / 'home').mkdir(mode=0o700)
        scenarios = self.root / 'home/scenarios'
        scenarios.mkdir(mode=0o700)
        (scenarios / 'RUNTIME.json').write_text('{"runtime": {}}'); (scenarios / 'HOST_V4.json').write_text('{}')
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), NoNativeNoNetwork() as guard, Forbidden():
            out = self.plan(37, value=value, src=src, pin=pin)
        self.assertEqual(guard.launched, [])
        self.assertEqual(out['status'], READY)
        self.assert_boundaries(out)
        for rel in ('runs', 'consents', 'execution-attempts', 'helper-failures'):
            self.assertFalse((scenarios / rel).exists(), rel)

    def test_unsatisfied_or_unknown_preconditions_and_unevaluated_coverage_are_stop(self):
        cases = [(satisfied_report('NOT_SATISFIED'), 'PROFILE_PRECONDITIONS_NOT_SATISFIED'),
                 (satisfied_report('UNKNOWN'), 'PROFILE_PRECONDITIONS_UNKNOWN'),
                 (dict(status='NOT_EVALUATED', code='NODE_NOT_FOUND', nextStep='x'), 'STATIC_COVERAGE_NOT_EVALUATED'),
                 (dict(status='STOP', code='STATIC_PLAN_UNAVAILABLE'), 'STATIC_COVERAGE_STOP')]
        for i, (report, code) in enumerate(cases):
            with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=report), Forbidden():
                out = self.plan(37, home=f'h{i}')
            self.assertEqual((out['status'], out['readiness']['status']), ('PLAN_STOP', 'STOP'), code)
            self.assertEqual([s['code'] for s in out['readiness']['stops']], [code])
            self.assertIsNone(out['prepared'])
            self.assertFalse((self.root / f'h{i}/sessions' / out['sessionId'] / 'variants' / out['variantId'] / 'prepared').exists())
            self.assert_boundaries(out)

    def test_ninth_variant_is_a_stop_and_records_nothing(self):
        value, src, pin = self.pinned()
        with patch.object(hookr.HookrScenarioAdapter, 'coverage', return_value=satisfied_report()), Forbidden():
            outs = [self.plan(lp, value=value, src=src, pin=pin) for lp in VALID[:MAX_VARIANTS]]
            ninth = self.plan(VALID[MAX_VARIANTS], value=value, src=src, pin=pin)
        self.assertEqual({o['status'] for o in outs}, {READY})
        self.assertEqual(len({o['variantId'] for o in outs}), MAX_VARIANTS)
        self.assertEqual(len({o['prepared']['scenarioCommitment'] for o in outs}), MAX_VARIANTS)
        self.assertEqual(len({o['sessionId'] for o in outs}), 1)
        self.assertEqual(sum(o['sessionCreated'] for o in outs), 1)
        self.assertEqual((ninth['status'], ninth['variantId'], [s['code'] for s in ninth['readiness']['stops']]), ('PLAN_STOP', None, ['VARIANT_LIMIT']))
        variants = self.root / 'home/sessions' / outs[0]['sessionId'] / 'variants'
        self.assertEqual(len([p for p in variants.iterdir() if p.name[0] != '.']), MAX_VARIANTS)


@COVERAGE
class Coverage(PlanTest):
    """Real offline coverage helper over a hash-linked synthetic witness."""
    def test_valid_values_share_one_witness_and_keep_stable_identities(self):
        value, _ = hash_linked_fixture('complete')
        _, src, pin = self.pinned(value)
        source = load(src, 8 << 20)
        first = VALID[:MAX_VARIANTS]
        with NoNativeNoNetwork() as guard, Forbidden():
            a = {lp: self.plan(lp, value=value, src=src, pin=pin) for lp in first}
            b = {lp: self.plan(lp, home='second-home', value=value, src=src, pin=pin) for lp in (VALID[-1], 37)}
        self.assertTrue(all(Path(cmd[1]) == hookr.COVERAGE_HELPER for cmd in guard.launched))
        for out in [*a.values(), *b.values()]:
            self.assertEqual((out['status'], out['staticCoverage']['status'], out['profilePreconditions']), (READY, 'COVERED', 'SATISFIED'))
            self.assertEqual(out['staticCoverage']['networkRequestsPerformed'], 0)
            self.assert_boundaries(out)
        self.assertEqual(len({o['variantId'] for o in a.values()}), len(first))
        self.assertEqual(len({o['prepared']['scenarioCommitment'] for o in a.values()}), len(first))
        # Same source, checkpoint and value give the same identities in another home.
        self.assertEqual(b[37]['sessionId'], a[37]['sessionId'])
        for key in ('variantId',):
            self.assertEqual(b[37][key], a[37][key])
        for key in ('scenarioCommitment', 'scenarioSha256'):
            self.assertEqual(b[37]['prepared'][key], a[37]['prepared'][key])
        for home, outs in (('home', a), ('second-home', b)):
            for lp, out in outs.items():
                prepared = load(self.root / home / out['prepared']['preparedDirectory'] / 'SCENARIO.json', 8 << 20)
                self.assertEqual((int(prepared['configurations']['variant'][0], 16) >> 160) & 65535, lp)
                self.assertEqual(prepared['configurations']['baseline'], source['configurations']['baseline'])
                self.assertEqual(set(prepared), set(source))
                for key in set(source) - {'configurations', 'origin', 'scenarioCommitment'}:
                    self.assertEqual(prepared[key], source[key], key)
                self.assertEqual(prepared['inventory'], source['inventory'])
        # LP50 against an LP50 source reproduces the source bytes exactly.
        self.assertEqual(a[50]['prepared']['scenarioSha256'], pin)
        self.assertEqual(a[50]['prepared']['scenarioCommitment'], source['scenarioCommitment'])

    def test_repeat_plan_is_idempotent_and_writes_nothing_new(self):
        value, _ = hash_linked_fixture('complete')
        _, src, pin = self.pinned(value)
        first = self.plan(37, value=value, src=src, pin=pin)
        session_dir = self.root / 'home/sessions' / first['sessionId']
        snapshot = {p: p.read_bytes() for p in session_dir.rglob('*') if p.is_file()}
        again = self.plan(37, value=value, src=src, pin=pin)
        by_id = self.sdk().plan_lp_variant(37, session_id=first['sessionId'])
        for out in (again, by_id):
            self.assertEqual((out['alreadyRegistered'], out['prepared']['alreadyPrepared'], out['sessionCreated']), (True, True, False))
            for key in ('sessionId', 'variantId', 'staticCoverage', 'profilePreconditions', 'originalWitness', 'operation', 'readiness'):
                self.assertEqual(out[key], first[key], key)
            self.assertEqual({k: v for k, v in out['prepared'].items() if k != 'alreadyPrepared'},
                             {k: v for k, v in first['prepared'].items() if k != 'alreadyPrepared'})
        self.assertEqual({p: p.read_bytes() for p in session_dir.rglob('*') if p.is_file()}, snapshot)

    def test_missing_trie_node_is_stop_without_preparation(self):
        value, parts = hash_linked_fixture('unknown-sibling')
        with NoNativeNoNetwork(), Forbidden():
            out = self.plan(37, value=value)
        self.assertEqual((out['status'], out['staticCoverage']['status']), ('PLAN_STOP', 'MISSING'))
        self.assertGreater(out['staticCoverage']['unresolvedDependencies'], 0)
        self.assertEqual(out['readiness']['stops'][0]['code'], 'STATIC_COVERAGE_MISSING')
        self.assertTrue(out['readiness']['stops'][0]['nextStep'].startswith('NEEDS_AUTHENTICATED_STATE'))
        self.assertIsNone(out['prepared'])
        self.assert_boundaries(out)
        self.assert_no_native_traces('home')

    def test_failed_profile_precondition_is_stop(self):
        value, _ = hash_linked_fixture('config-differs')
        out = self.plan(37, value=value)
        self.assertEqual(out['status'], 'PLAN_STOP')
        stop = out['readiness']['stops'][0]
        self.assertEqual((stop['code'], stop['failed']), ('PROFILE_PRECONDITIONS_NOT_SATISFIED', ['ORIGINAL_CONFIGURATION_EQUALS_LP100_BASELINE']))
        self.assertIsNone(out['prepared'])

    def test_cli_plan_37_matches_the_api(self):
        value, _ = hash_linked_fixture('complete')
        _, src, pin = self.pinned(value)
        cp = self.root / 'checkpoint.json'; cp.write_text(json.dumps(value['checkpoint']))
        def cli(home, *args):
            r = subprocess.run([sys.executable, '-B', '-m', 'rhook_alpha.cases', '--home', str(self.root / home), *args],
                               cwd=SDK, capture_output=True, timeout=120)
            return r.returncode, json.loads(r.stdout)
        code, created = cli('cli', 'session-plan', '--lp-bps', '37', '--scenario', str(src), '--sha256', pin, '--checkpoint', str(cp))
        self.assertEqual((code, created['status']), (0, READY))
        api = self.plan(37, home='api', value=value, src=src, pin=pin)
        for key in ('sessionId', 'variantId', 'selectedLpBps', 'checkpoint', 'originalWitness', 'staticCoverage', 'profilePreconditions',
                    'dynamicCoverage', 'nativeExecution', 'operation', 'readiness'):
            self.assertEqual(created[key], api[key], key)
        self.assertEqual(created['prepared']['scenarioCommitment'], api['prepared']['scenarioCommitment'])
        self.assertNotIn(str(self.root), json.dumps(created))
        code, again = cli('cli', 'session-plan', '--lp-bps', '37', '--session', created['sessionId'])
        self.assertEqual((code, again['alreadyRegistered'], again['prepared']['alreadyPrepared']), (0, True, True))
        for text, cause in [('37.5', 'LP_BPS_INTEGER_REQUIRED'), ('100', 'BASELINE_LP100_IS_NOT_A_VARIANT'), ('101', 'LP_BPS_0_TO_99_REQUIRED'), ('-1', 'LP_BPS_0_TO_99_REQUIRED')]:
            code, bad = cli('cli', 'session-plan', '--lp-bps', text, '--session', created['sessionId'])
            self.assertEqual((code, bad['status'], bad['causeCode']), (1, 'SESSION_STOP', cause), text)
        code, stopped = cli('cli-missing', 'session-plan', '--lp-bps', '37', '--scenario', str(self.root / 'absent.json'), '--sha256', pin, '--checkpoint', str(cp))
        self.assertEqual((code, stopped['status']), (1, 'SESSION_STOP'))

    @unittest.skipUnless(REAL, 'RHOOK_SESSION_REAL_CAPTURE not set')
    def test_real_accepted_capture_reproduces_lp0_and_lp50_and_plans_37(self):
        source = Path(REAL) / 'SCENARIO.json'
        value = load(source, 8 << 20)
        pin = hashlib.sha256(source.read_bytes()).hexdigest()
        with NoNativeNoNetwork(), Forbidden():
            outs = {lp: self.sdk().plan_lp_variant(lp, source=source, expected_sha256=pin, checkpoint=value['checkpoint']) for lp in (0, 50, 37)}
        self.assertEqual(outs[0]['sessionId'], '3a6cbf813b0921651b2725624536cef361bf18c0c6a0c420e03c6ec022ce5dea')
        self.assertEqual(outs[0]['variantId'], '2da7594c58f21a3b37abb5d33d6cfcb47f21162e823e0ef05172dc0f82c8c08d')
        self.assertEqual(outs[0]['prepared']['scenarioCommitment'], '200a5012b29b129d4d4f6e43468094bd6f3d60aa2756538e6d13ec1be25ed8c0')
        self.assertEqual(outs[50]['variantId'], 'eade7409b1a1a9bba942493fbba6d5697db2253a0ff88b1f4f5cd74db0d3e580')
        self.assertEqual(outs[50]['prepared']['scenarioCommitment'], value['scenarioCommitment'])
        self.assertEqual(outs[50]['prepared']['scenarioSha256'], pin)
        for out in outs.values():
            self.assertEqual((out['status'], out['staticCoverage']['status'], out['profilePreconditions']), (READY, 'COVERED', 'SATISFIED'))
            self.assertEqual(out['staticCoverage']['summary']['dependencies'], 24)
            self.assertEqual((out['originalWitness']['nodes'], out['originalWitness']['codes']), (686, 14))
            self.assert_boundaries(out)


if __name__ == '__main__':
    unittest.main()
