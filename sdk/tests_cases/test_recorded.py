"""Optional retained-record consumer tests; source-only CI uses boundary tests separately."""
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(os.environ.get('RHOOK_RECORDED_TEST_BUNDLE', ROOT / 'examples/on-demand-hookr-demo/evidence'))
MODULE = 'rhook_alpha.cases.scenario.recorded'


@unittest.skipUnless(BUNDLE.is_dir(), 'optional retained records not distributed; set RHOOK_RECORDED_TEST_BUNDLE explicitly')
class RecordedScenario(unittest.TestCase):
    def consumer(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'worker-free recorded consumer is missing')
        return importlib.import_module(MODULE)

    def test_receipt_math_and_explicit_verification_limits(self):
        result = self.consumer().compare_recorded(BUNDLE)
        self.assertEqual(result['status'], 'SCENARIO_EVIDENCE_COMPARISON_PASS')
        self.assertEqual(result['tokenOutputDeltaBaseUnits'], '264493944266048824899')
        self.assertEqual(result['gasDelta'], 0)
        self.assertEqual([w['gasUsed'] for w in result['worlds']], [1655206, 1655206])
        self.assertEqual([w['swapFeePips'] for w in result['worlds']], [[11000], [7000]])
        self.assertTrue(result['tokenOutputGainPercent'].startswith('0.5049116567607209698'))
        self.assertFalse(result['scope']['EVMReexecution'])
        self.assertFalse(result['scope']['MPTProofVerification'])
        self.assertFalse(result['scope']['receiptTrieRecomputed'])
        self.assertFalse(result['scope']['transactionSignatureRecovered'])

    def test_inspect_preserves_hypothetical_and_synthetic_context(self):
        result = self.consumer().inspect_recorded(BUNDLE)
        self.assertEqual(result['executionMode'], 'HYPOTHETICAL_SCENARIO')
        self.assertEqual(result['checkpoint']['blockNumber'], 99236464)
        self.assertEqual(result['scenario']['configurationAccount'], '0x4a71c270b1520f94064268102aebd744b0de7942')
        self.assertEqual(result['scenario']['action']['amountInWei'], '1000000000000000')
        self.assertEqual(result['scenario']['commonSetup']['fundingWei'], '1000000000000000000')
        self.assertEqual(result['scenario']['action']['minimumOutputBaseUnits'], '1')

    def test_stage_commitments_can_differ_while_checked_world_fields_match(self):
        result = self.consumer().verify_recorded(BUNDLE)
        self.assertEqual(result['status'], 'SCENARIO_EVIDENCE_INTEGRITY_PASS')
        self.assertTrue(result['checks']['evidenceCommitments'])
        self.assertTrue(result['checks']['discoveryOfflineMatch'])
        self.assertEqual(result['qualifiedClaims'], 0)

    def test_plain_record_tamper_is_rejected(self):
        m = self.consumer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'evidence'
            shutil.copytree(BUNDLE, root)
            p = root / 'OFFLINE_FINAL.json'
            p.write_bytes(p.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'FILE_HASH_MISMATCH'):
                m.verify_recorded(root)

    def test_editable_descriptor_cannot_reanchor_tampered_records(self):
        m = self.consumer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'evidence'
            shutil.copytree(BUNDLE, root)
            p = root / 'OFFLINE_FINAL.json'
            p.write_bytes(p.read_bytes() + b' ')
            meta = json.loads((root / 'DEMO.json').read_text())
            meta['files']['OFFLINE_FINAL.json'] = hashlib.sha256(p.read_bytes()).hexdigest()
            (root / 'DEMO.json').write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError, 'DESCRIPTOR_PIN_MISMATCH'):
                m.verify_recorded(root)

    def trusted_mutation(self, change):
        """Trust a synthetic fixture deliberately, so invariant checks are exercised."""
        m = self.consumer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'evidence'
            shutil.copytree(BUNDLE, root)
            final = json.loads((root / 'OFFLINE_FINAL.json').read_text())
            change(final)
            unsigned = dict(final)
            unsigned.pop('evidenceCommitment')
            payload = json.dumps(unsigned, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
            final['evidenceCommitment'] = hashlib.sha256(b'rhook/hookr-scenario/0.1/evidence\n' + payload).hexdigest()
            p = root / 'OFFLINE_FINAL.json'
            p.write_text(json.dumps(final, sort_keys=True, separators=(',', ':')) + '\n')
            meta = json.loads((root / 'DEMO.json').read_text())
            meta['files']['OFFLINE_FINAL.json'] = hashlib.sha256(p.read_bytes()).hexdigest()
            p = root / 'DEMO.json'
            p.write_text(json.dumps(meta, sort_keys=True, indent=2) + '\n')
            with patch.object(m, 'DESCRIPTOR_SHA256', hashlib.sha256(p.read_bytes()).hexdigest()):
                m.verify_recorded(root)

    def test_recommitted_unrelated_lp_word_change_is_rejected(self):
        def change(v):
            o = v['worlds'][1]['overlay']
            o['initialWord'] = '0x' + (int(o['initialWord'], 16) ^ 1).to_bytes(32, 'big').hex()
        with self.assertRaisesRegex(ValueError, 'LP_INTERVENTION'):
            self.trusted_mutation(change)

    def test_recommitted_transaction_identity_change_is_rejected(self):
        def change(v):
            v['worlds'][1]['actionMapping'][0]['transactionHash'] = '0x' + '11' * 32
        with self.assertRaisesRegex(ValueError, 'TRANSACTION_IDENTITY'):
            self.trusted_mutation(change)

    def test_recommitted_log_identity_change_is_rejected(self):
        def change(v):
            v['worlds'][1]['receipts'][1]['logs'][-1]['removed'] = True
        with self.assertRaisesRegex(ValueError, 'LOG_IDENTITY'):
            self.trusted_mutation(change)

    def test_symlink_input_rejected(self):
        m = self.consumer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'evidence'
            shutil.copytree(BUNDLE, root)
            (root / 'OFFLINE_FINAL.json').unlink()
            (root / 'OFFLINE_FINAL.json').symlink_to(BUNDLE / 'OFFLINE_FINAL.json')
            with self.assertRaises(ValueError):
                m.verify_recorded(root)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO unavailable')
    def test_fifo_input_rejected_without_opening_stream(self):
        m = self.consumer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'evidence'
            shutil.copytree(BUNDLE, root)
            (root / 'OFFLINE_FINAL.json').unlink()
            os.mkfifo(root / 'OFFLINE_FINAL.json')
            with self.assertRaises(ValueError):
                m.verify_recorded(root)

    def test_evidence_verification_needs_no_process_or_network(self):
        m = self.consumer()
        with patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')), patch('subprocess.Popen', side_effect=AssertionError('PROCESS_FORBIDDEN')):
            self.assertEqual(m.compare_recorded(BUNDLE)['status'], 'SCENARIO_EVIDENCE_COMPARISON_PASS')

    def test_sdk_api_does_not_register_or_require_a_runtime(self):
        from rhook_alpha.cases.api import CaseSDK
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / 'empty-home'
            sdk = CaseSDK(home)
            fn = getattr(sdk, 'verify_recorded_scenario', None)
            self.assertTrue(callable(fn), 'SDK recorded API is missing')
            with patch('subprocess.Popen', side_effect=AssertionError('NATIVE_PROCESS_FORBIDDEN')):
                self.assertEqual(fn(BUNDLE)['status'], 'SCENARIO_EVIDENCE_INTEGRITY_PASS')
            self.assertFalse(home.exists())

    def test_cli_verifies_with_an_empty_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / 'empty-home'
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            p = subprocess.run([sys.executable, '-B', '-m', 'rhook_alpha.cases', '--home', str(home),
                                'scenario-evidence-verify', '--bundle', str(BUNDLE)],
                               capture_output=True, text=True, env=env, timeout=5)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)['status'], 'SCENARIO_EVIDENCE_INTEGRITY_PASS')
            self.assertFalse(home.exists())

    def test_oversized_record_is_rejected_before_parsing(self):
        m = self.consumer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'evidence'
            shutil.copytree(BUNDLE, root)
            (root / 'OFFLINE_FINAL.json').write_bytes(b' ' * ((2 << 20) + 1))
            with self.assertRaisesRegex(ValueError, 'BOUNDED_REGULAR'):
                m.verify_recorded(root)

    def test_strict_json_rejects_duplicate_and_float_in_a_trusted_descriptor(self):
        m = self.consumer()
        for raw in [b'{"x":1,"x":2}', b'{"x":1.5}', b'{"x":NaN}']:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'evidence'
                shutil.copytree(BUNDLE, root)
                (root / 'DEMO.json').write_bytes(raw)
                with patch.object(m, 'DESCRIPTOR_SHA256', hashlib.sha256(raw).hexdigest()):
                    with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY|NON_INTEGER_OR_NONFINITE_JSON'):
                        m.verify_recorded(root)


if __name__ == '__main__':
    unittest.main()
