"""Unconditional consumer boundary tests; no private recorded bundle required."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.scenario import recorded


class PublicRecordedBoundary(unittest.TestCase):
    def test_missing_bundle_never_falls_back_to_an_execution_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk = CaseSDK(Path(tmp).resolve() / 'empty-home')
            with patch('subprocess.Popen', side_effect=AssertionError('no worker')):
                with self.assertRaisesRegex(ValueError, 'EVIDENCE_DIRECTORY_REQUIRED'):
                    sdk.verify_recorded_scenario(Path(tmp) / 'missing')
            self.assertFalse(sdk.home.exists())

    def test_descriptor_cannot_reanchor_arbitrary_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in recorded.RECORDS:
                (root / name).write_text('{}')
            (root / 'DEMO.json').write_text(json.dumps({'schema': 'synthetic-not-evidence'}))
            with self.assertRaisesRegex(ValueError, 'DESCRIPTOR_PIN_MISMATCH'):
                recorded.verify_recorded(root)

    def test_strict_json_rejects_duplicate_float_and_nonfinite_values(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":1.5}', b'{"x":NaN}'):
            with self.assertRaises(ValueError):
                recorded._parse(raw)

    def test_oversize_input_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'record.json'
            path.write_bytes(b' ' * (recorded.MAX_BYTES + 1))
            with self.assertRaisesRegex(ValueError, 'BOUNDED_REGULAR'):
                recorded._read(path)

    def test_scope_never_implies_evm_mpt_or_heterogeneous_verification(self):
        for field in ('MPTProofVerification', 'EVMReexecution', 'receiptTrieRecomputed',
                      'headerHashRecomputed', 'transactionSignatureRecovered'):
            self.assertFalse(recorded.SCOPE[field])
        self.assertEqual(recorded.SCOPE['qualifiedClaims'], 0)
        self.assertEqual(recorded.SCOPE['independentRustAgreement'], 'NOT_EVALUATED')
