"""Review/consent integration with mock runtime identity; no producer or grants."""
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from unittest import mock
from developer.files import save
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases import native
from rhook_alpha.cases.__main__ import main
from test_plans import hookr


def fake_runtime(sdk):
    profile, policy, _ = native._settings(sdk)
    return dict(schema='rhook/case-runtime/0.1', profile=profile,
                policySha256=policy, sourceCommitment='a' * 64,
                files={name: dict(path='/offline-test/' + name, sha256=pin * 64)
                       for name, pin in [('worker', '1'), ('sensor', '2'), ('node', '3')]})


@contextmanager
def planned():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        capsule, raw = hookr()
        bundle = root / 'bundle'
        bundle.mkdir()
        save(bundle / 'CAPSULE.json', capsule)
        (bundle / 'BLOCK_PACKAGE.json').write_bytes(raw)
        sdk = CaseSDK(root / 'home')
        sdk.import_case(bundle)
        plan = sdk.plan(capsule['caseId'], {'rule': 'lpBps', 'value': 50})
        yield sdk, plan['planId'], capsule['checkpoint']['blockHash']


class OperationReview(unittest.TestCase):
    def test_preview_is_stable_and_does_not_issue_consent_or_execute(self):
        with planned() as (sdk, ref, trust), mock.patch.object(native, 'runtime', side_effect=fake_runtime), \
                mock.patch.object(native.authority, 'issue', side_effect=AssertionError('no consent')), \
                mock.patch.object(native, 'capture', side_effect=AssertionError('no helper')):
            a = sdk.operation(ref, trusted_checkpoint=trust)
            self.assertEqual(a, sdk.operation(ref, trusted_checkpoint=trust))
            self.assertEqual(a['planId'], ref)
            self.assertEqual(a['trustedCheckpoint'], trust)
            self.assertEqual(a['maximumInvocations'], {'ACTUAL': 1, 'BRANCH': 1, 'B': 0})
            self.assertEqual(list((sdk.home / 'consents').iterdir()), [])
            self.assertEqual(list((sdk.home / 'runs').iterdir()), [])
            self.assertFalse((sdk.home / '.case-consent.key').exists())

    def test_wrong_or_implicit_trust_stops_before_runtime(self):
        with planned() as (sdk, ref, trust), mock.patch.object(native, 'runtime', side_effect=AssertionError('no helper')):
            for wrong in [None, '0x' + 'ff' * 32]:
                with self.subTest(trust=wrong), self.assertRaisesRegex(ValueError, 'EXPLICIT_TRUSTED_CHECKPOINT_REQUIRED'):
                    sdk.operation(ref, trusted_checkpoint=wrong)

    def test_missing_runtime_cannot_fabricate_a_preview_or_consent(self):
        with planned() as (sdk, ref, trust), mock.patch.object(native, 'capture', side_effect=AssertionError('no helper')):
            with self.assertRaises(FileNotFoundError):
                sdk.operation(ref, trusted_checkpoint=trust)
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(['--home', str(sdk.home), 'operation', '--plan', ref, '--trust-checkpoint', trust])
            value = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(value['status'], 'INPUT_OR_RUNTIME_STOP')
            self.assertIn('RUNTIME.json', value['causeCode'])
            self.assertNotIn('operationCommitment', value)
            self.assertEqual(list((sdk.home / 'consents').iterdir()), [])

    def test_cli_operation_returns_the_same_exact_binding(self):
        with planned() as (sdk, ref, trust), mock.patch.object(native, 'runtime', side_effect=fake_runtime):
            expected = sdk.operation(ref, trusted_checkpoint=trust)
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(['--home', str(sdk.home), 'operation', '--plan', ref, '--trust-checkpoint', trust])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue()), expected)

    def test_changed_runtime_refuses_reviewed_consent_before_authentication_or_key_access(self):
        with planned() as (sdk, ref, trust), mock.patch.object(native, 'runtime', side_effect=fake_runtime):
            reviewed = sdk.operation(ref, trusted_checkpoint=trust)
            changed = fake_runtime(sdk)
            changed['files']['worker']['sha256'] = '4' * 64
            with mock.patch.object(native, 'runtime', return_value=changed), \
                    mock.patch.object(native, 'authenticate') as authenticate, \
                    mock.patch.object(native, 'read_key') as key, \
                    mock.patch.object(native.authority, 'issue') as issue, \
                    mock.patch.object(native.sys, 'platform', 'darwin'), \
                    mock.patch.object(native.platform, 'machine', return_value='arm64'):
                with self.assertRaisesRegex(ValueError, 'REVIEWED_OPERATION_MISMATCH'):
                    sdk.authorize(ref, local_owner=True, mac_ready=True, trusted_checkpoint=trust,
                                  expected_operation=reviewed['operationCommitment'])
                authenticate.assert_not_called()
                key.assert_not_called()
                issue.assert_not_called()

    def test_review_cannot_be_applied_to_a_different_intervention_plan(self):
        with planned() as (sdk, ref, trust), mock.patch.object(native, 'runtime', side_effect=fake_runtime):
            reviewed = sdk.operation(ref, trusted_checkpoint=trust)
            other = sdk.plan('hookr-one', {'rule': 'lpBps', 'value': 49})['planId']
            with mock.patch.object(native, 'authenticate') as authenticate, \
                    mock.patch.object(native.authority, 'issue') as issue, \
                    mock.patch.object(native.sys, 'platform', 'darwin'), \
                    mock.patch.object(native.platform, 'machine', return_value='arm64'):
                with self.assertRaisesRegex(ValueError, 'REVIEWED_OPERATION_MISMATCH'):
                    sdk.authorize(other, local_owner=True, mac_ready=True, trusted_checkpoint=trust,
                                  expected_operation=reviewed['operationCommitment'])
                authenticate.assert_not_called()
                issue.assert_not_called()

    def test_exact_review_and_legacy_authorization_both_use_existing_issuer(self):
        with planned() as (sdk, ref, trust), mock.patch.object(native, 'runtime', side_effect=fake_runtime), \
                mock.patch.object(native, 'authenticate'), mock.patch.object(native, 'read_key', return_value=b't' * 32), \
                mock.patch.object(native.authority, 'issue', return_value=Path('/offline-test/GRANT.json')) as issue, \
                mock.patch.object(native.sys, 'platform', 'darwin'), \
                mock.patch.object(native.platform, 'machine', return_value='arm64'):
            reviewed = sdk.operation(ref, trusted_checkpoint=trust)
            for options in [{}, {'expected_operation': reviewed['operationCommitment']}]:
                result = sdk.authorize(ref, local_owner=True, mac_ready=True, trusted_checkpoint=trust, **options)
                self.assertEqual(result, Path('/offline-test/GRANT.json'))
                self.assertEqual(issue.call_args.args[1], reviewed)
            self.assertEqual(issue.call_count, 2)
            self.assertEqual(list((sdk.home / 'consents').iterdir()), [])

    def test_cli_authorize_forwards_exact_review_without_issuing_real_consent(self):
        with planned() as (sdk, ref, trust), mock.patch.object(CaseSDK, 'authorize', return_value=Path('/offline-test/GRANT.json')) as authorize:
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(['--home', str(sdk.home), 'authorize', '--plan', ref,
                             '--trust-checkpoint', trust, '--operation', 'a' * 64, '--local-owner', '--mac-ready'])
            self.assertEqual(code, 0)
            self.assertEqual(authorize.call_args.kwargs['expected_operation'], 'a' * 64)

    def test_clean_installed_cli_reports_missing_runtime_without_opening_consent(self):
        import install_cases
        with planned() as (sdk, ref, trust), tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp).resolve() / 'sdk'
            command = install_cases.install(prefix)
            env = {'PATH': os.defpath, 'LANG': 'C', 'TZ': 'UTC'}
            result = subprocess.run([str(command), '--home', str(sdk.home), 'operation',
                                     '--plan', ref, '--trust-checkpoint', trust],
                                    capture_output=True, text=True, env=env, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stderr, '')
            value = json.loads(result.stdout)
            self.assertEqual(value['status'], 'INPUT_OR_RUNTIME_STOP')
            self.assertIn('RUNTIME.json', value['causeCode'])
            self.assertFalse((sdk.home / '.case-consent.key').exists())
            self.assertEqual(list((sdk.home / 'consents').iterdir()), [])
            self.assertEqual(list((sdk.home / 'runs').iterdir()), [])

    @unittest.skipUnless(os.environ.get('RHOOK_HISTORICAL_TEST_PACKAGE'), 'explicit retained fixture required')
    def test_real_historical_import_plan_preview_uses_scoped_backend_without_a_producer(self):
        from rhook_alpha.cases.historical import ADAPTER, PROFILE
        from rhook_alpha.cases.historical.adapter import profile
        p = profile()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            sdk = CaseSDK(root / 'home')
            sdk.package_case(Path(os.environ['RHOOK_HISTORICAL_TEST_PACKAGE']), root / 'bundle',
                             case_id='historical-review', adapter=ADAPTER, subject_index=3,
                             input_commitment=p['inputCommitment'], witness_commitment=p['witnessCommitment'])
            sdk.import_case(root / 'bundle')
            ref = sdk.plan('historical-review', {'rule': 'dynamicFee', 'value': 'OFF'})['planId']
            with mock.patch.object(native, 'runtime', side_effect=fake_runtime), \
                    mock.patch.object(native.authority, 'issue', side_effect=AssertionError('no grant')), \
                    mock.patch.object(native, 'capture', side_effect=AssertionError('no helper')):
                binding = sdk.operation(ref, trusted_checkpoint=p['checkpoint']['blockHash'])
            self.assertEqual(binding['profile'], PROFILE)
            self.assertEqual(binding['packageSha256'], p['packageSha256'])
            self.assertEqual(binding['maximumInvocations'], {'ACTUAL': 1, 'BRANCH': 1, 'B': 0})
            self.assertEqual(list((sdk.home / 'consents').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
