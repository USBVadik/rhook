from pathlib import Path
import tempfile
import unittest
from unittest import mock
from test_plans import hookr
from developer.files import save
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases import native

class NativeBoundary(unittest.TestCase):

    def test_authorization_requires_owner_without_loading_a_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk = CaseSDK(Path(tmp).resolve() / 'home')
            with mock.patch.object(native, 'runtime', side_effect=AssertionError('must not load')):
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_LOCAL_OWNER'):
                    sdk.authorize('c-' + '0' * 32)

    def test_wrong_trusted_checkpoint_rejects_before_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src = root / 'src'
            src.mkdir()
            d, p = hookr()
            save(src / 'CAPSULE.json', d)
            (src / 'BLOCK_PACKAGE.json').write_bytes(p)
            sdk = CaseSDK(root / 'home')
            sdk.import_case(src)
            with mock.patch.object(native, 'runtime', side_effect=AssertionError('must not load')):
                with self.assertRaisesRegex(ValueError, 'TRUSTED_CHECKPOINT_MISMATCH'):
                    sdk.authenticate(d['caseId'], trusted_checkpoint='0x' + '00' * 32)

    def test_plan_tamper_fails_before_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src = root / 'src'
            src.mkdir()
            d, p = hookr()
            save(src / 'CAPSULE.json', d)
            (src / 'BLOCK_PACKAGE.json').write_bytes(p)
            sdk = CaseSDK(root / 'home')
            sdk.import_case(src)
            plan = sdk.plan(d['caseId'], {'rule': 'lpBps', 'value': 50})
            path = sdk.home / 'plans' / plan['planId'] / 'PLAN.json'
            path.write_text('{}')
            with self.assertRaises((ValueError, KeyError)):
                sdk.describe(plan['planId'])
            self.assertFalse(any((sdk.home / 'consents').iterdir()))

    def test_runtime_always_authenticates_verifier_dependencies(self):
        with mock.patch.object(native, 'dependencies', side_effect=ValueError('DEPENDENCY_CLOSURE_MISMATCH')):
            with self.assertRaisesRegex(ValueError, 'DEPENDENCY_CLOSURE_MISMATCH'):
                native._check_runtime({})

    def test_missing_runtime_stops_before_a_child_or_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src = root / 'src'
            src.mkdir()
            d, p = hookr()
            save(src / 'CAPSULE.json', d)
            (src / 'BLOCK_PACKAGE.json').write_bytes(p)
            sdk = CaseSDK(root / 'home')
            sdk.import_case(src)
            with mock.patch.object(native, 'capture', side_effect=AssertionError('must not launch')):
                with self.assertRaises(FileNotFoundError):
                    sdk.authenticate(d['caseId'])
            self.assertFalse(any((sdk.home / 'consents').iterdir()))

class CompletionEvidence(unittest.TestCase):

    def test_unverified_counts_are_not_accepted(self):
        valid = {'operationCommitment': 'a' * 64, 'result': {'nativeInvocations': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, 'canonicalActualValid': True, 'RPC': 0, 'WSS': 0, 'terminal': 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED'}}
        self.assertEqual(native.validate_completion(valid, 'a' * 64), valid)
        import copy
        for counts in ({'ACTUAL': True, 'BRANCH': 1, 'B': 0}, {'ACTUAL': 0, 'BRANCH': 1, 'B': 0}, {'ACTUAL': 2, 'BRANCH': 1, 'B': 0}, None):
            bad = copy.deepcopy(valid)
            bad['result']['nativeInvocations'] = counts
            with self.assertRaises(ValueError):
                native.validate_completion(bad, 'a' * 64)
        with self.assertRaises(ValueError):
            native.validate_completion(valid, 'b' * 64)

class PrivateKeyBoundary(unittest.TestCase):

    def test_world_readable_or_wrong_size_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            key = root / '.case-consent.key'
            key.write_bytes(b'x' * 32)
            key.chmod(420)
            with self.assertRaisesRegex(ValueError, 'PRIVATE_CONSENT_KEY'):
                native.read_key(root)
            key.chmod(384)
            self.assertEqual(native.read_key(root), b'x' * 32)
            key.write_bytes(b'x' * 31)
            with self.assertRaises(ValueError):
                native.read_key(root)

    def test_malformed_failure_cannot_claim_missing_witness(self):
        base = {'operationCommitment': 'a' * 64, 'result': {'nativeInvocations': {'ACTUAL': 1, 'BRANCH': 0, 'B': 0}, 'canonicalActualValid': False, 'RPC': 0, 'WSS': 0, 'terminal': 'HOST_STOP'}}
        for detail in (['bad'], {'phase': 'ACTUAL', 'code': 'NOT_A_MISSING_STATE_CODE', 'classification': 'HOST_STOP_MISSING_STATE'}):
            with self.assertRaises(ValueError):
                native.validate_completion(dict(base, failureDetail=detail), 'a' * 64)

class PythonModeBoundary(unittest.TestCase):

    def test_optimized_replay_is_refused_before_plan_or_grant_access(self):
        import subprocess, sys
        root = Path(__file__).resolve().parents[1]
        script = 'import sys;sys.path.insert(0,sys.argv[1]);from rhook_alpha.cases import native\ntry:\n native.replay(None,"c-"+"0"*32,"unused")\nexcept ValueError as e:\n print(str(e))\n'
        p = subprocess.run([sys.executable, '-O', '-B', '-c', script, str(root)], capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('PYTHON_3_12_UNOPTIMIZED_REQUIRED', p.stdout)
if __name__ == '__main__':
    unittest.main()
