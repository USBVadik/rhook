import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rhook_alpha import LpBps, SDK
from rhook_alpha import consent
from developer.files import canonical, digest, save


class TypedIntervention(unittest.TestCase):
    def test_supported_values(self):
        for value in [0, 50, 99]:
            self.assertEqual(LpBps(value).value, value)

    def test_malformed_noop_and_unsupported_values(self):
        for value in [True, -1, 100, 101, 50.0, '50', None]:
            with self.subTest(value=value), self.assertRaises(ValueError): LpBps(value)

    def test_only_fixed_case_and_typed_rule(self):
        sdk = SDK('/private/tmp/synthetic-rhook-home')
        with self.assertRaises(ValueError): sdk.inspect('other-pool')
        with self.assertRaises(ValueError): sdk.plan('hookr-pair03', {'lpBps': 50})


class LocalConsent(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.key = b'x' * 32
        self.context = {'installationId': 'synthetic-install-not-native', 'ownerUid': 501,
                        'host': 'synthetic-host', 'platform': 'darwin', 'machine': 'arm64'}
        self.binding = {'profile': 'hookr-case-darwin-arm64/0.1', 'domain': 'HOOKR_UNIFIED_PLAN_NATIVE_0_1',
                        'operationCommitment': 'a'*64, 'planId': 'b'*32, 'workspace': str(self.root),
                        'policySha256': 'c'*64, 'runtimePlanSha256': 'd'*64,
                        'maximumInvocations': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0},
                        'RPC': 0, 'WSS': 0, 'workflowSeconds': 180, 'nativeStageSeconds': 140,
                        'executionContext': 'require_escalated'}
    def tearDown(self): self.temporary.cleanup()

    def issue(self, **kwargs):
        return consent.issue(self.root, self.binding, self.context, self.key,
                             local_owner=True, mac_ready=True, now=1000, **kwargs)

    def test_explicit_owner_and_mac_attestation_required(self):
        for owner, ready in [(False, True), (True, False)]:
            with self.assertRaises(ValueError):
                consent.issue(self.root, self.binding, self.context, self.key,
                              local_owner=owner, mac_ready=ready, now=1000)

    def test_exact_grant_and_one_shot_consumption(self):
        path = self.issue()
        authority = consent.consume(path, self.root, self.binding, self.context, self.key, now=1001)
        body = json.loads(authority.read_text())
        self.assertTrue(body['founderApproved'])  # Legacy local bridge, not remote consent.
        self.assertEqual(body['operationCommitment'], self.binding['operationCommitment'])
        with self.assertRaises(FileExistsError):
            consent.consume(path, self.root, self.binding, self.context, self.key, now=1001)
        with self.assertRaises(FileExistsError): self.issue()

    def test_foreign_install_key_context_plan_and_expiry_rejected(self):
        path = self.issue()
        for kind in ['key', 'context', 'binding', 'expired', 'short-window']:
            binding, context, key, now = dict(self.binding), dict(self.context), self.key, 1001
            if kind == 'key': key = b'z' * 32
            if kind == 'context': context['installationId'] = 'another-install'
            if kind == 'binding': binding['operationCommitment'] = 'e'*64
            if kind == 'expired': now = 1600
            if kind == 'short-window': now = 1500
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                consent.consume(path, self.root, binding, context, key, now=now)
        self.assertFalse((path.parent / 'CONSUMED.json').exists())

    def test_remote_or_linux_scope_cannot_be_issued(self):
        binding = dict(self.binding, profile='hookr-case-linux-cgroup-v2/0.3-psi-experimental')
        with self.assertRaises(ValueError):
            consent.issue(self.root, binding, self.context, self.key, local_owner=True, mac_ready=True, now=1000)

    def test_tampering_and_symlink_are_rejected(self):
        path = self.issue(); original = path.read_bytes();value = json.loads(original)
        value['body']['expiresUnix'] += 1;path.write_bytes(canonical(value)+b'\n')
        with self.assertRaises(ValueError): consent.consume(path, self.root, self.binding, self.context, self.key, now=1001)
        path.write_bytes(original);other = self.root/'link';other.symlink_to(path)
        with self.assertRaises(ValueError): consent.consume(other, self.root, self.binding, self.context, self.key, now=1001)

    def test_crash_after_consumption_cannot_reopen_the_operation(self):
        path = self.issue()
        original = consent.save
        def fail_engine_bridge(destination, value):
            if destination.name == 'ENGINE_AUTHORITY.json': raise OSError('synthetic disk failure')
            return original(destination, value)
        with patch.object(consent, 'save', side_effect=fail_engine_bridge), self.assertRaises(OSError):
            consent.consume(path, self.root, self.binding, self.context, self.key, now=1001)
        self.assertTrue((path.parent/'CONSUMED.json').is_file())
        with self.assertRaises(FileExistsError):
            consent.consume(path, self.root, self.binding, self.context, self.key, now=1001)

    def test_concurrent_consent_issuance_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        def attempt(_):
            try: return self.issue()
            except FileExistsError: return None
        with ThreadPoolExecutor(max_workers=2) as pool: outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(value is not None for value in outcomes), 1)


class DispatchBoundary(unittest.TestCase):
    def test_planning_only_value_cannot_authorize_replay(self):
        sdk = SDK('/private/tmp/synthetic-rhook-home')
        with patch.object(sdk, '_resolve', return_value=({'newValue':'99'}, {}, ({}, {}, b'x'*32))), self.assertRaisesRegex(ValueError, 'PLANNING_ONLY'):
            sdk.authorize('b'*32, local_owner=True, mac_ready=True)

    def test_compare_always_uses_verifier_and_no_saved_economic_constants(self):
        sdk = SDK('/private/tmp/synthetic-rhook-home')
        value = {'status':'RECORDED_INTEGRITY_PASS','worlds':{
            'ACTUAL':{'buyerRhookTransferNetBaseUnits':'10','subjectGasUsed':'5','outerSwap':{'feePips':'2'},'hookFeeEvents':[]},
            'BRANCH':{'buyerRhookTransferNetBaseUnits':'13','subjectGasUsed':'6','outerSwap':{'feePips':'1'},'hookFeeEvents':[]}},
            'buyerRhookTransferNetDeltaBaseUnits':'3','subjectGasDelta':'1', 'qualifiedClaims':0}
        with patch.object(sdk, 'verify', return_value=value) as verify:
            result = sdk.compare('/tmp/synthetic-run');verify.assert_called_once()
            self.assertEqual(result['buyerTransferNetDeltaBaseUnits'], '3')
            self.assertEqual(result['buyerTransferNetIncreasePercent'], '30')


if __name__ == '__main__': unittest.main(verbosity=2)
