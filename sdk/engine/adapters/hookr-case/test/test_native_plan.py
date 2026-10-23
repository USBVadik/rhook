"""Native request admission without a native dispatcher or executable."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import native_plan
import validate_plan


class NativePlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(os.environ['RHOOK_PAIR03_PACKAGE'])
        cls.raw = cls.package.read_bytes()
        cls.plans = {}
        for value in ['0', '50']:
            completed = subprocess.run([os.environ.get('RHOOK_NODE', 'node'), '--import',
                str(HERE / 'test/no-network.mjs'), str(HERE / 'cli.ts'), 'plan',
                '--package', str(cls.package), '--expected-old', '100', '--new-value', value],
                capture_output=True, check=True, timeout=10)
            cls.plans[value] = json.loads(completed.stdout)

    def fresh(self):
        return json.loads(json.dumps(self.plans['50']))

    def test_exact_50_is_admitted_only_for_review(self):
        self.assertEqual(self.plans['50']['planCommitment'],
                         'e8a0e1d0a8158ec073ea076507864bb9b828a96fd81cdd22732ab902345b6cd7')
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('NO DISPATCH')):
            x = native_plan.prepare_native_plan(self.raw, self.plans['50'])
        self.assertEqual(x['status'], 'ADMITTED_FOR_REVIEW_NOT_EXECUTABLE')
        self.assertFalse(x['canExecuteNow'])
        self.assertFalse(x['executionAuthorized'])
        self.assertEqual(x['nativeInvocations'], {'ACTUAL': 0, 'BRANCH': 0, 'B': 0})
        self.assertEqual(x['additionalBranchStateCoverage'], 'NOT_EVALUATED')

    def test_zero_runtime_plan_is_byte_compatible_with_saved_plan(self):
        x = native_plan.prepare_native_plan(self.raw, self.plans['0'])
        original = (native_plan.REPO / 'repro/portable/plan.json').read_bytes()
        self.assertEqual(x['runtimePlanSha256'], hashlib.sha256(original).hexdigest())
        self.assertTrue(x['legacyInterventionCompatible'])

    def test_50_preserves_all_inputs_and_actual_gate(self):
        x = native_plan.prepare_native_plan(self.raw, self.plans['50'])
        before = json.loads((native_plan.REPO / 'repro/portable/plan.json').read_bytes())
        after = json.loads(json.dumps(x['runtimePlan']))
        after['intervention'] = before['intervention']
        self.assertEqual(before, after)
        self.assertEqual(x['canonicalActualGate'], ['stateRoot', 'receiptsRoot', 'blockHash'])
        self.assertEqual(x['worldConstruction'], 'INDEPENDENT_ORIGINAL_PARENT_NIL_SOURCE')
        self.assertIn('NEW_SCOPED_WORKER_AND_PROFILE', x['executionPrerequisites'])

    def test_changed_expected_word_checkpoint_or_input_override_is_rejected(self):
        for key, value in [('expectedOldWord', '0x00'), ('checkpoint', {}), ('slot', '0x00')]:
            plan = self.fresh(); plan['intervention'][key] = value
            body = {k: v for k, v in plan.items() if k != 'planCommitment'}
            plan['planCommitment'] = validate_plan.commitment('rhook/hookr-plan/0.1', body)
            with self.subTest(key=key), self.assertRaises(ValueError):
                native_plan.prepare_native_plan(self.raw, plan)
        plan = self.fresh(); plan['transactions'] = []
        with self.assertRaises(ValueError):
            native_plan.prepare_native_plan(self.raw, plan)

    def test_missing_original_state_or_code_fails_admission(self):
        packet = json.loads(self.raw)
        for kind in ['state', 'codes']:
            material = {k: list(packet[k]) for k in ['state', 'codes']}
            material[kind].pop()
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'MATERIAL_MISSING'):
                native_plan.prepare_native_plan(self.raw, self.plans['50'], available_material=material)

    def test_changed_or_synthesized_material_cannot_replace_original_witness(self):
        packet = json.loads(self.raw)
        material = {k: list(packet[k]) for k in ['state', 'codes']}
        material['state'][0] = '0xdeadbeef'
        with self.assertRaises(ValueError):
            native_plan.prepare_native_plan(self.raw, self.plans['50'], available_material=material)

    def test_request_is_deterministic_and_commitment_binds_all_bytes(self):
        a = native_plan.prepare_native_plan(self.raw, self.plans['50'])
        self.assertEqual(a, native_plan.prepare_native_plan(self.raw, self.plans['50']))
        body = dict(a); body.pop('requestCommitment')
        self.assertEqual(a['requestCommitment'],
                         validate_plan.commitment('rhook/native-plan-request/0.1', body))

    def test_approval_field_cannot_turn_a_plan_into_an_execution(self):
        plan = self.fresh(); plan['executionAuthorized'] = True
        with self.assertRaises(ValueError):
            native_plan.prepare_native_plan(self.raw, plan)

    def test_execute_flag_is_not_an_entry_point(self):
        result = subprocess.run([sys.executable, '-B', str(HERE / 'native_plan.py'), '--execute'],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')

    def test_regular_file_guard_is_rechecked_on_the_open_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / 'replaced-input'
            os.mkfifo(fifo)
            # Simulate a file that changed after the existing path checks.
            with patch.object(validate_plan.saved_package, 'local_file', return_value=fifo):
                with self.assertRaisesRegex(ValueError, 'INPUT_FILE_TYPE'):
                    validate_plan.read_input(fifo, 16384)
