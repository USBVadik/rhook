"""Counterfactual Session 0.1 tests. Synthetic inputs only; nothing here is native or EVM evidence."""
from pathlib import Path
import hashlib, json, os, shutil, socket, subprocess, sys, tempfile, unittest
from unittest.mock import patch

from developer.files import canonical, digest, load
from rhook_alpha.execution import ExecutionSDK
from rhook_alpha.session import SessionError, LIMITATIONS, MAX_VARIANTS
from rhook_alpha.session import hookr
from test_execution import fixture as execution_fixture, META

SDK = Path(__file__).resolve().parents[1]
FIXTURE_JS = SDK / 'tests_cases/session-fixture.mjs'
NODE = shutil.which('node')
DEPS = all((SDK / 'engine/adapters/hookr-case/node_modules' / n / 'package.json').is_file() for n in ('viem', 'hookr-sdk'))
COVERAGE = unittest.skipUnless(NODE and DEPS, 'Node.js and pinned adapter dependencies are required for coverage')
if os.environ.get('RHOOK_REQUIRE_SESSION_COVERAGE') == '1' and not (NODE and DEPS):
    raise RuntimeError('RHOOK_REQUIRE_SESSION_COVERAGE=1: Node.js or the pinned adapter dependencies are missing')
REAL = os.environ.get('RHOOK_SESSION_REAL_CAPTURE')


def recommit(v):
    v.pop('scenarioCommitment', None)
    v['scenarioCommitment'] = digest(b'rhook/hookr-scenario/0.1\n' + canonical(v))
    return v


def write(root, value, name='SCENARIO.json'):
    path = root / name
    path.write_bytes(canonical(value) + b'\n')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def hash_linked_fixture(mode='complete'):
    """Execution fixture whose parent header, checkpoint and inventory come from session-fixture.mjs."""
    parts = json.loads(subprocess.run([NODE, str(FIXTURE_JS), mode], capture_output=True, check=True, timeout=30).stdout)
    v = execution_fixture()
    cp = parts['checkpoint']
    v['checkpoint'] = cp
    v['parent'] = parts['parent']
    v['environment'] = dict(v['environment'], l2BlockNumber=cp['blockNumber'] + 1,
                            l2Timestamp=int(parts['parent']['timestamp'], 16) + 1, poster=parts['parent']['miner'])
    v['actions'][0]['deadline'] = v['environment']['l2Timestamp'] + 300
    body = dict(v['actions'][0]); body.pop('id')
    v['actions'][0]['id'] = digest(b'rhook/hookr-scenario/0.1/action\n' + canonical(body))
    v['inventory'] = parts['inventory']
    v['chainConfig'] = '0x' + '00' * 64
    intent = dict(schema='rhook/on-demand-hookr-intent/0.1', poolId=v['poolId'], lpBps=50)
    v['origin']['capsuleId'] = digest(b'rhook/scenario-checkpoint/0.1\n' + canonical(dict(checkpoint=cp, intent=intent)))
    return recommit(v), parts


class NoNativeNoNetwork:
    """Patch every process launch except the offline coverage helper, and every socket."""
    def __init__(self):
        self.launched = []
        real = subprocess.Popen
        def popen(args, *a, **k):
            self.launched.append(list(map(str, args)))
            if len(args) == 2 and Path(args[1]) in (hookr.COVERAGE_HELPER, FIXTURE_JS):
                return real(args, *a, **k)
            raise AssertionError(f'unexpected process {args}')
        self.patches = [patch('subprocess.Popen', side_effect=popen),
                        patch.object(socket, 'socket', side_effect=AssertionError('no network'))]

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)

    def sdk(self, name='home'):
        return ExecutionSDK(self.root / name)

    def session(self, value=None, *, name='home'):
        value = value or execution_fixture()
        src, pin = write(self.root, value, f'{name}-SCENARIO.json')
        return self.sdk(name).create_session(source=src, expected_sha256=pin, checkpoint=value['checkpoint']), src, pin

    def code(self, call, expected):
        with self.assertRaises(SessionError) as e:
            call()
        self.assertEqual(e.exception.code, expected, e.exception.details)
        self.assertTrue(e.exception.next_step)
        return e.exception


class Identity(SessionTest):
    def test_same_input_gives_same_semantic_identity_in_any_home(self):
        a, src, pin = self.session()
        again = self.sdk().create_session(source=src, expected_sha256=pin, checkpoint=META['checkpoint'])
        other, _, _ = self.session(name='second-home')
        self.assertEqual(a.id, again.id)
        self.assertEqual(a.id, other.id)
        self.assertEqual(a.header['limitations'], LIMITATIONS)
        self.assertEqual(a.header['checkpointTrust']['canonicality'], 'NOT_ESTABLISHED_REQUIRES_AN_INDEPENDENTLY_TRUSTED_BLOCK_HASH')

    def test_a_session_never_switches_checkpoint(self):
        v = execution_fixture()
        src, pin = write(self.root, v)
        for field, value in [('blockHash', '0x' + '1' * 64), ('stateRoot', '0x' + '2' * 64), ('chainId', 1), ('blockNumber', 1)]:
            e = self.code(lambda: self.sdk().create_session(source=src, expected_sha256=pin,
                                                            checkpoint=dict(v['checkpoint'], **{field: value})), 'CHECKPOINT_MISMATCH')
            self.assertEqual(e.details['differingFields'], [field])
        self.assertFalse((self.root / 'home/sessions').exists() and any((self.root / 'home/sessions').iterdir()))

    def test_source_pin_commitment_and_environment_are_enforced(self):
        v = execution_fixture()
        src, pin = write(self.root, v)
        self.code(lambda: self.sdk().create_session(source=src, expected_sha256='0' * 64, checkpoint=v['checkpoint']), 'PREPARED_WITNESS_HASH_MISMATCH')
        bad = dict(v, poolId=v['poolId'])
        bad['actions'] = [dict(v['actions'][0], gas=10000000)]
        bad['scenarioCommitment'] = '0' * 64
        src2, pin2 = write(self.root, bad, 'bad.json')
        self.code(lambda: self.sdk().create_session(source=src2, expected_sha256=pin2, checkpoint=v['checkpoint']), 'SCENARIO_COMMITMENT')
        moved = recommit(json.loads(json.dumps(v)))
        moved['environment']['poster'] = '0x' + '9' * 40
        src3, pin3 = write(self.root, recommit(moved), 'env.json')
        self.code(lambda: self.sdk().create_session(source=src3, expected_sha256=pin3, checkpoint=v['checkpoint']), 'CHECKPOINT_ENVIRONMENT_MISMATCH')

    def test_reopen_preserves_identities_offline(self):
        s, _, _ = self.session()
        v50 = s.add_variant({'lpBps': 50})['variantId']
        with NoNativeNoNetwork():
            again = self.sdk().open_session(s.id)
            self.assertEqual(again.header, s.header)
            self.assertEqual([v['variantId'] for v in again.variants()], [v50])

    def test_tampered_manifest_or_source_copy_is_drift(self):
        s, _, _ = self.session()
        manifest = s.directory / 'SESSION.json'
        original = manifest.read_bytes()
        value = json.loads(original)
        value['baseline']['lpBps'] = 99
        manifest.chmod(0o600); manifest.write_bytes(canonical(value) + b'\n')
        self.code(lambda: self.sdk().open_session(s.id), 'SESSION_MANIFEST_DRIFT')
        # Recomputing the file's own commitment does not help: identities are re-derived from the source.
        body = dict(value); body.pop('headerCommitment')
        value['headerCommitment'] = digest(b'rhook/counterfactual-session/0.1\n' + canonical(body))
        manifest.write_bytes(canonical(value) + b'\n')
        self.code(lambda: self.sdk().open_session(s.id), 'SESSION_MANIFEST_DRIFT')
        manifest.write_bytes(original)
        source = s.source_path
        source.chmod(0o600); source.write_bytes(source.read_bytes().replace(b'"nonce":0', b'"nonce":1', 1))
        self.code(lambda: self.sdk().open_session(s.id), 'PREPARED_WITNESS_HASH_MISMATCH')

    def test_unknown_profile_is_refused(self):
        from rhook_alpha import session
        self.code(lambda: session.adapter(self.root / 'home', 'arbitrary-evm/0.1'), 'UNSUPPORTED_PROFILE')


class Variants(SessionTest):
    def test_lp50_and_lp0_have_distinct_stable_ids_bound_to_one_checkpoint(self):
        s, _, _ = self.session()
        a = s.add_variant({'lpBps': 50}); b = s.add_variant({'lpBps': 0})
        self.assertNotEqual(a['variantId'], b['variantId'])
        other, _, _ = self.session(name='other')
        self.assertEqual(other.add_variant({'lpBps': 50})['variantId'], a['variantId'])
        self.assertEqual([v['descriptor']['replacement'] for v in s.variants()], [0, 50])
        for v in (a, b):
            record = s._load_variant(v['variantId'])
            self.assertEqual(record['bindings']['checkpoint'], s.header['checkpoint'])
            self.assertEqual(record['bindings']['baseline'], dict(lpBps=100, configurationWords=META['scenario']['configurations']['baseline']))
            self.assertEqual(record['bindings']['common']['actionId'], execution_fixture()['actions'][0]['id'])

    def test_unsupported_values_and_changes_are_refused(self):
        s, _, _ = self.session()
        for params, code in [({'lpBps': 100}, 'LP_BPS_0_TO_99_REQUIRED'), ({'lpBps': -1}, 'LP_BPS_0_TO_99_REQUIRED'),
                             ({'lpBps': True}, 'LP_BPS_0_TO_99_REQUIRED'), ({'lpBps': '50'}, 'LP_BPS_0_TO_99_REQUIRED'),
                             ({'lpBps': 50, 'amountInWei': '2'}, 'UNSUPPORTED_VARIANT'), ({'storage': {}}, 'UNSUPPORTED_VARIANT'), ([], 'UNSUPPORTED_VARIANT')]:
            self.code(lambda: s.add_variant(params), code)
        self.assertEqual(s.variants(), [])

    def test_duplicates_are_idempotent_and_count_is_bounded(self):
        s, _, _ = self.session()
        first = s.add_variant({'lpBps': 50}); again = s.add_variant({'lpBps': 50})
        self.assertFalse(first['alreadyRegistered']); self.assertTrue(again['alreadyRegistered'])
        for lp in range(1, MAX_VARIANTS):
            s.add_variant({'lpBps': lp})
        self.assertEqual(len(s.variants()), MAX_VARIANTS)
        self.code(lambda: s.add_variant({'lpBps': 90}), 'VARIANT_LIMIT')

    def test_tampered_variant_record_is_drift(self):
        s, _, _ = self.session()
        vid = s.add_variant({'lpBps': 50})['variantId']
        path = s.directory / 'variants' / vid / 'VARIANT.json'
        value = json.loads(path.read_bytes()); value['descriptor']['replacement'] = 49
        body = dict(value); body.pop('variantCommitment')
        value['variantCommitment'] = digest(b'rhook/counterfactual-session/0.1/variant\n' + canonical(body))
        path.chmod(0o600); path.write_bytes(canonical(value) + b'\n')
        self.code(lambda: s.variants(), 'VARIANT_RECORD_DRIFT')


class Preparation(SessionTest):
    def test_two_variants_prepare_offline_without_native_network_or_consent(self):
        s, _, _ = self.session()
        v50 = s.add_variant({'lpBps': 50})['variantId']; v0 = s.add_variant({'lpBps': 0})['variantId']
        with NoNativeNoNetwork() as guard:
            p50 = s.prepare_variant(v50)
            statuses = {v['variantId']: v['status'] for v in s.variants()}
            self.assertEqual(statuses, {v50: 'PREPARED_NOT_EXECUTED', v0: 'CONFIGURED'})
            p0 = s.prepare_variant(v0)
        self.assertEqual(guard.launched, [])
        home = s.adapter.home
        self.assertFalse((home / 'scenarios/consents').exists())
        self.assertFalse((home / 'scenarios/runs').exists())
        self.assertFalse((home / 'scenarios/execution-attempts').exists())
        self.assertNotEqual(p50['scenarioCommitment'], p0['scenarioCommitment'])
        for p in (p50, p0):
            self.assertEqual(p['nativeExecutions'], 0); self.assertEqual(p['witnessClosure'], 'NOT_EVALUATED')
            self.assertEqual(p['authentication'], 'PENDING_NATIVE_ADMISSION')
        a = load(s.directory / p50['preparedDirectory'] / 'SCENARIO.json', 8 << 20)
        b = load(s.directory / p0['preparedDirectory'] / 'SCENARIO.json', 8 << 20)
        for key in ('checkpoint', 'actions', 'environment', 'commonSetup', 'inventory', 'parent', 'engine'):
            self.assertEqual(a[key], b[key], key)
        self.assertEqual([(int(x['configurations']['variant'][0], 16) >> 160) & 65535 for x in (a, b)], [50, 0])
        before = (s.directory / p50['preparedDirectory'] / 'SCENARIO.json').read_bytes()
        self.assertTrue(s.prepare_variant(v50)['alreadyPrepared'])
        self.assertEqual((s.directory / p50['preparedDirectory'] / 'SCENARIO.json').read_bytes(), before)

    def test_incomplete_preparation_is_stop_and_does_not_affect_the_other_variant(self):
        s, _, _ = self.session()
        v50 = s.add_variant({'lpBps': 50})['variantId']; v0 = s.add_variant({'lpBps': 0})['variantId']
        s.prepare_variant(v50)
        broken = s.directory / 'variants' / v0 / 'prepared'
        broken.mkdir(); (broken / 'SCENARIO.json').write_text('{}')
        statuses = {v['variantId']: v for v in s.variants()}
        self.assertEqual(statuses[v0]['status'], 'STOP'); self.assertEqual(statuses[v0]['execution'], 'NOT_PERFORMED')
        self.assertEqual(statuses[v50]['status'], 'PREPARED_NOT_EXECUTED')
        with self.assertRaises((SessionError, ValueError)):
            s.prepare_variant(v0)

    def test_prepared_variant_cannot_be_swapped_for_another(self):
        s, _, _ = self.session()
        v50 = s.add_variant({'lpBps': 50})['variantId']; v0 = s.add_variant({'lpBps': 0})['variantId']
        s.prepare_variant(v50); s.prepare_variant(v0)
        a, b = (s.directory / 'variants' / v / 'prepared' for v in (v50, v0))
        tmp = s.directory / 'swap'; a.rename(tmp); b.rename(a); tmp.rename(b)
        self.assertEqual({v['status'] for v in s.variants()}, {'STOP'})


@COVERAGE
class Coverage(SessionTest):
    def test_complete_seed_covers_every_static_read_without_network(self):
        value, _ = hash_linked_fixture('complete')
        with NoNativeNoNetwork() as guard:
            s, _, _ = self.session(value)
            s.add_variant({'lpBps': 50}); s.add_variant({'lpBps': 0})
            report = s.coverage()
        self.assertEqual(report['status'], 'STATIC_DEPENDENCIES_COVERED', report.get('detail'))
        self.assertEqual(report['networkRequestsPerformed'], 0); self.assertEqual(report['networkRequestsRefused'], 0)
        self.assertEqual(report['nativeExecutions'], 0); self.assertEqual(report['dynamicClosure'], 'UNKNOWN')
        self.assertEqual(report['profile']['originalConfiguration'], 'AUTHENTICATED_EQUALS_BASELINE')
        self.assertEqual(report['profile']['simulationActor'], 'PROVEN_ABSENT')
        self.assertEqual(report['profile']['parentHeader'], 'HEADER_HASH_RECOMPUTED_EQUALS_CHECKPOINT')
        self.assertTrue(all(cmd[1] == str(hookr.COVERAGE_HELPER) for cmd in guard.launched))
        for v in s.variants():
            self.assertEqual((v['staticCoverage'], v['dynamicCoverage'], v['execution']), ('COVERED', 'UNKNOWN', 'NOT_PERFORMED'))
        self.assertEqual(s.coverage(), report)

    def test_unknown_original_state_is_reported_never_assumed(self):
        value, parts = hash_linked_fixture('unknown-sibling')
        s, _, _ = self.session(value)
        vid = s.add_variant({'lpBps': 0})['variantId']
        report = s.coverage()
        self.assertEqual(report['status'], 'STATIC_DEPENDENCIES_MISSING')
        self.assertGreater(report['summary']['accounts']['unknown'], 0)
        # Accounts under the Rules branch are genuinely proven absent; the rest stay UNKNOWN.
        self.assertGreater(report['summary']['accounts']['unknown'], report['summary']['accounts']['provenAbsent'])
        unknown = [d for d in report['dependencies'] if d['account'] == 'UNKNOWN']
        self.assertTrue(all(d['missingNodeHash'] == parts['missingNodeHash'] for d in unknown))
        self.assertTrue(all(s_['status'] == 'UNKNOWN' for d in unknown for s_ in d['storage']))
        self.assertGreater(report['networkRequestsRefused'], 0); self.assertEqual(report['networkRequestsPerformed'], 0)
        variant = next(v for v in s.variants() if v['variantId'] == vid)
        self.assertEqual(variant['staticCoverage'], 'MISSING'); self.assertTrue(variant['nextRequirement'].startswith('NEEDS_AUTHENTICATED_STATE'))

    def test_parent_header_that_cannot_be_authenticated_stops_coverage(self):
        # The execution fixture links the parent only by declared fields; its header cannot be hashed.
        s, _, _ = self.session()
        report = s.coverage()
        self.assertEqual((report['status'], report['code']), ('STOP', 'STATIC_PLAN_UNAVAILABLE'))
        s.add_variant({'lpBps': 50})
        self.assertEqual({v['staticCoverage'] for v in s.variants()}, {'STOP'})
        # A complete header that hashes to a different block is refused the same way.
        value, _ = hash_linked_fixture('complete')
        value['parent'] = dict(value['parent'], extraData='0x' + '00' * 32)
        s2, _, _ = self.session(recommit(value), name='other-parent')
        report = s2.coverage()
        self.assertEqual(report['status'], 'STOP'); self.assertIn('SEND_MERKLE_HEADER', report['detail'])

    def test_invalid_preimages_stop_coverage(self):
        value, _ = hash_linked_fixture('complete')
        value['inventory'] = dict(value['inventory'], nodes=value['inventory']['nodes'] + ['0x01'])
        s, _, _ = self.session(recommit(value))
        report = s.coverage()
        self.assertEqual((report['status'], report['code']), ('STOP', 'SEED_PREIMAGE_INVALID'))

    @unittest.skipUnless(REAL, 'RHOOK_SESSION_REAL_CAPTURE not set')
    def test_real_accepted_capture_parity(self):
        capture = Path(REAL)
        source = capture / 'SCENARIO.json'
        value = load(source, 8 << 20)
        s = self.sdk().create_session(source=source, expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), checkpoint=value['checkpoint'])
        report = s.coverage()
        self.assertEqual(report['status'], 'STATIC_DEPENDENCIES_COVERED')
        self.assertEqual(report['profile']['prefetchPlan']['groups'], load(capture / 'PREFETCH_PLAN.json', 1 << 20)['groups'])
        v50 = s.add_variant({'lpBps': 50})['variantId']
        self.assertEqual(s.prepare_variant(v50)['scenarioCommitment'], value['scenarioCommitment'])


class Verification(SessionTest):
    def prepared(self):
        s, _, _ = self.session()
        v50 = s.add_variant({'lpBps': 50})['variantId']; v0 = s.add_variant({'lpBps': 0})['variantId']
        s.prepare_variant(v50); s.prepare_variant(v0)
        return s, v50, v0

    def run_dir(self, s, vid, *, name='run', change=None, profile='nitro-hookr-scenario/0.1'):
        spec = load(s.directory / 'variants' / vid / 'prepared/SCENARIO.json', 8 << 20)
        if change:
            change(spec); recommit(spec)
        run = self.root / name
        (run / 'inputs').mkdir(parents=True)
        (run / 'inputs/SCENARIO.json').write_bytes(canonical(spec) + b'\n')
        sha = hashlib.sha256((run / 'inputs/SCENARIO.json').read_bytes()).hexdigest()
        op = digest(b'test-only operation ' + name.encode())
        (run / 'BINDING.json').write_bytes(canonical(dict(profile=profile, scenarioSha256=sha, operationCommitment=op)))
        (run / 'RESULT.json').write_bytes(canonical(dict(status='SCENARIO_COMPLETED', operationCommitment=op, scenarioCommitment=spec['scenarioCommitment'])))
        return run

    @staticmethod
    def backend(run):
        return dict(worlds=[dict(world='SCENARIO_BASELINE', receiptStatus=1, gasUsed=1, actorTargetTokenTransferNetBaseUnits='1000'),
                            dict(world='SCENARIO_VARIANT', receiptStatus=1, gasUsed=1, actorTargetTokenTransferNetBaseUnits='1010')],
                    targetTokenTransferNetDeltaBaseUnits='10')

    def test_unexecuted_session_has_nothing_to_compare(self):
        s, v50, v0 = self.prepared()
        result = s.compare_verified()
        self.assertEqual(result['status'], 'NO_VERIFIED_VARIANTS'); self.assertEqual(result['qualifiedClaims'], 0)
        self.assertEqual({v['execution'] for v in s.variants()}, {'NOT_PERFORMED'})

    def test_test_only_backend_never_becomes_native_verification(self):
        s, v50, v0 = self.prepared()
        record = s.verify_selected(v50, self.run_dir(s, v50), test_only_backend=self.backend)
        self.assertEqual(record['status'], 'TEST_ONLY_BINDING_CHECKED')
        self.assertEqual(record['assurance']['verification'], 'TEST_ONLY_NOT_EVIDENCE')
        self.assertEqual(record['assurance']['nativeExecution'], 'NOT_PERFORMED'); self.assertEqual(record['assurance']['qualifiedClaims'], 0)
        view = {v['variantId']: v for v in s.variants()}
        self.assertEqual(view[v50]['status'], 'TEST_ONLY_BINDING_CHECKED')
        self.assertEqual((view[v50]['execution'], view[v50]['dynamicCoverage']), ('NOT_PERFORMED', 'UNKNOWN'))
        self.assertEqual(view[v0]['status'], 'PREPARED_NOT_EXECUTED')
        comparison = s.compare_verified()
        self.assertEqual(comparison['status'], 'TEST_ONLY_COMPARISON_NOT_EVIDENCE')
        self.assertEqual([r['variantId'] for r in comparison['variants']], [v50])
        # Relabelling the stored record as production is detected even with a recomputed commitment.
        path = s.directory / 'variants' / v50 / 'VERIFICATION.json'
        value = json.loads(path.read_bytes()); value['status'] = 'RECORDED_RUN_VERIFIED'
        body = dict(value); body.pop('verificationCommitment')
        value['verificationCommitment'] = digest(b'rhook/counterfactual-session/0.1/verification\n' + canonical(body))
        path.chmod(0o600); path.write_bytes(canonical(value) + b'\n')
        self.code(lambda: s.compare_verified(), 'VERIFICATION_RECORD_DRIFT')

    def test_runs_must_belong_to_this_session_and_variant(self):
        s, v50, v0 = self.prepared()
        self.code(lambda: s.verify_selected(v50, self.run_dir(s, v0, name='lp0'), test_only_backend=self.backend), 'WRONG_VARIANT_RESULT')
        moved = lambda spec: spec['checkpoint'].update(blockNumber=1)
        self.code(lambda: s.verify_selected(v50, self.run_dir(s, v50, name='other-cp', change=moved), test_only_backend=self.backend), 'WRONG_SESSION_RESULT')
        env = lambda spec: spec['environment'].update(syntheticL1BaseFeeWei='2')
        self.code(lambda: s.verify_selected(v50, self.run_dir(s, v50, name='env', change=env), test_only_backend=self.backend), 'INCOMPATIBLE_RUN_COMMON')
        self.code(lambda: s.verify_selected(v50, self.run_dir(s, v50, name='dyn', profile='nitro-hookr-dynamic-fee-off/0.1'), test_only_backend=self.backend), 'WRONG_PROFILE_EVIDENCE')
        unprepared = s.add_variant({'lpBps': 1})['variantId']
        self.code(lambda: s.verify_selected(unprepared, self.run_dir(s, v50, name='x'), test_only_backend=self.backend), 'VARIANT_NOT_PREPARED')
        self.assertFalse(any((s.directory / 'variants' / v / 'VERIFICATION.json').exists() for v in (v50, v0, unprepared)))

    def test_production_verifier_without_registered_runtime_records_nothing(self):
        s, v50, _ = self.prepared()
        run = self.run_dir(s, v50)
        with NoNativeNoNetwork() as guard:
            with self.assertRaises(SessionError):
                s.verify_selected(v50, run)
        self.assertEqual(guard.launched, [])
        self.assertFalse((s.directory / 'variants' / v50 / 'VERIFICATION.json').exists())
        self.assertEqual(s.compare_verified()['status'], 'NO_VERIFIED_VARIANTS')


class Interfaces(SessionTest):
    def test_cli_and_example_use_the_same_offline_api(self):
        v = execution_fixture()
        src, pin = write(self.root, v)
        cp = self.root / 'checkpoint.json'; cp.write_text(json.dumps(v['checkpoint']))
        home = self.root / 'cli-home'
        def cli(*args):
            r = subprocess.run([sys.executable, '-B', '-m', 'rhook_alpha.cases', '--home', str(home), *args],
                               cwd=SDK, capture_output=True, timeout=60)
            return r.returncode, json.loads(r.stdout)
        code, created = cli('session-create', '--scenario', str(src), '--sha256', pin, '--checkpoint', str(cp))
        self.assertEqual((code, created['status']), (0, 'SESSION_INSPECTED'))
        sid = created['sessionId']
        code, v50 = cli('session-add-variant', '--session', sid, '--lp-bps', '50')
        self.assertEqual((code, v50['status'], v50['descriptor']['replacement']), (0, 'VARIANT_REGISTERED', 50))
        code, prep = cli('session-prepare', '--session', sid, '--variant', v50['variantId'])
        self.assertEqual((code, prep['status'], prep['nativeExecutions']), (0, 'VARIANT_PREPARED', 0))
        code, bad = cli('session-add-variant', '--session', sid, '--lp-bps', '100')
        self.assertEqual((code, bad['status'], bad['causeCode']), (1, 'SESSION_STOP', 'LP_BPS_0_TO_99_REQUIRED'))
        code, exported = cli('session-export', '--session', sid)
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), json.dumps(exported))
        code, compared = cli('session-compare', '--session', sid)
        self.assertEqual((code, compared['status']), (1, 'NO_VERIFIED_VARIANTS'))
        r = subprocess.run([sys.executable, '-B', str(SDK / 'examples/counterfactual_session.py'), '--home', str(self.root / 'example-home'),
                            '--scenario', str(src), '--sha256', pin, '--checkpoint', str(cp)], capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr.decode()[-800:])
        out = json.loads(r.stdout)
        self.assertEqual(out['sessionId'], sid)
        self.assertEqual(sorted(out['preparedScenarioCommitments']), ['0', '50'])
        self.assertEqual({v['execution'] for v in out['variants']}, {'NOT_PERFORMED'})


if __name__ == '__main__':
    unittest.main()
