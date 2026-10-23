"""Cross-language planning only; real history is never executed."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hookr_plan_boundary', HERE / 'validate_plan.py')
boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boundary)


class Boundary(unittest.TestCase):
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

    def test_existing_and_new_plan_pass_independent_python_reconstruction(self):
        for value, plan in self.plans.items():
            result = boundary.validate_plan(self.raw, plan)
            self.assertEqual(result['status'], 'INTERVENTION_VALIDATED_NOT_AUTHORIZED')
            self.assertEqual(result['nativeInvocations'], 0)
            self.assertFalse(result['executionAuthorized'])

    def test_changed_slot_mask_account_checkpoint_or_other_bits_are_rejected_even_if_rehashed(self):
        for key in ['slot', 'mask', 'account', 'newWord', 'checkpoint']:
            plan = self.fresh()
            plan['intervention'][key] = 'arbitrary'
            body = {k: v for k, v in plan.items() if k != 'planCommitment'}
            plan['planCommitment'] = boundary.commitment('rhook/hookr-plan/0.1', body)
            with self.subTest(key=key), self.assertRaises(ValueError):
                boundary.validate_plan(self.raw, plan)

    def test_injected_result_authority_identity_or_extra_field_is_rejected(self):
        for key, value in [('branchResult', {'output': 'invented'}), ('executionAuthorized', True),
                           ('caseId', 'other'), ('ruleId', 'other'), ('rpcUrl', 'not allowed'),
                           ('status', 'EXECUTED'), ('planCommitment', 'wrong')]:
            plan = self.fresh(); plan[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                boundary.validate_plan(self.raw, plan)

    def test_changed_original_package_is_rejected(self):
        with self.assertRaises(Exception):
            boundary.validate_plan(self.raw + b' ', self.fresh())

    def test_bad_values_types_and_unrequested_noop_are_rejected(self):
        for value in [True, 50, '01', '-1', '101', '100', '1000', '５０', '9' * 200]:
            plan = self.fresh(); plan['newValue'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                boundary.validate_plan(self.raw, plan)

    def test_boolean_is_not_accepted_as_a_numeric_checkpoint(self):
        plan = self.fresh(); plan['intervention']['checkpoint']['chainId'] = True
        with self.assertRaises(ValueError):
            boundary.validate_plan(self.raw, plan)

    def test_duplicate_json_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            boundary.strict_json('{"newValue":"50","newValue":"0"}')


if __name__ == '__main__':
    unittest.main()
