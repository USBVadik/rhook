"""Offline tests: no real host sensors, worker, subprocess, or provider calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from plan_native import core, launch, resources


class Boundary(unittest.TestCase):
    def setUp(self):
        self.plan, self.policy = core.inputs()
        self.b = dict(launch.pins('reviewed-source'), operationCommitment='operation',
                      binarySha256='binary', packagePath='/original-package', outputPath='/fresh')
        self.a = dict(launch.pins('reviewed-source'), domain=core.DOMAIN, operationCommitment='operation',
                      binarySha256='binary', packagePath='/original-package', outputPath='/fresh',
                      founderApproved=True, noRetry=True, macOnPowerOpenLid=True, executionContext='require_escalated',
                      maximumInvocations={'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, RPC=0, WSS=0,
                      notBeforeUnix=1000, expiresUnix=1300)

    def test_exact_reviewed_commitments(self):
        self.assertEqual(core.sha(core.read(core.HERE / 'plan.json')), core.PLAN_SHA)
        self.assertEqual(self.plan['intervention']['newWord'][22:26], '0032')
        self.assertEqual(self.plan['checkpoint']['blockNumber'], 93251802)
        self.assertEqual(len(self.plan['arrivals']), 7)

    def test_authority_rejects_every_changed_field(self):
        launch.authority(self.b, core.canonical(self.a), 1100)
        for key in self.a:
            with self.subTest(key=key):
                bad = dict(self.a); bad[key] = None
                with self.assertRaises((ValueError, TypeError)):
                    launch.authority(self.b, core.canonical(bad), 1100)

    def test_old_authority_and_unknown_field_rejected(self):
        for key, value in [('domain', 'DEVELOPER_SAVED_PAIR03_V2'), ('extra', 'override'), ('founderApproved', False)]:
            bad = dict(self.a); bad[key] = value
            with self.assertRaises(ValueError): launch.authority(self.b, core.canonical(bad), 1100)

    def test_window_and_duplicate_fields(self):
        for now in [999, 1300]:
            with self.assertRaises(ValueError): launch.authority(self.b, core.canonical(self.a), now)
        with self.assertRaises(ValueError): core.strict(b'{"approved":false,"approved":true}')

    def test_missing_authority_precedes_all_side_effects(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            b = Path(d) / 'bindings'; b.write_bytes(core.canonical(self.b))
            with patch.object(launch, 'admission') as sensor, patch.object(launch, 'supervise') as native:
                with self.assertRaises(ValueError): launch.execute(b, Path(d) / 'absent', 'unused', 'unused')
                sensor.assert_not_called(); native.assert_not_called()

    def test_numerical_policy_is_unchanged(self):
        original = core.strict(core.read(core.ROOT / 'sdk_alpha_v2/policy.json'))
        new = copy.deepcopy(self.policy); new['profile'] = original['profile']; new['workload'] = original['workload']
        self.assertEqual(new, original)
        self.assertEqual(resources.POLICY, self.policy)

    def test_original_source_pins_not_current_recomputed_approval(self):
        files = core.source_files()
        self.assertEqual(files['native/prestate/lp_branch.go'], '341f27d85edf31aa4193ec2aca4ce01c1b57378934d8e5548573eb730d229bb9')
        self.assertEqual(len(core.source_commitment()), 64)

    def test_transform_is_exact_and_rejects_drift(self):
        raw = core.read(core.ROOT / 'native/prestate/lp_branch.go')
        modified = core.replacement(raw)
        self.assertEqual(modified.replace(b'result[10], result[11] = 0, 50', b'result[10], result[11] = 0, 0'), raw)
        with self.assertRaises(ValueError): core.replacement(raw + b'\n')

    def test_consumption_parent_is_synced(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            out = Path(d) / 'one-shot'
            from unittest.mock import Mock
            sync = Mock(wraps=launch.portable.sync_directory)
            with patch.dict(launch.portable.consume_output.__globals__, sync_directory=sync):
                launch.portable.consume_output(out)
            self.assertEqual([call.args[0] for call in sync.call_args_list], [out.parent, out])
            with self.assertRaises(FileExistsError): launch.portable.consume_output(out)

    def test_resource_fail_closed_on_pressure_or_low_ram(self):
        from sdk_alpha_v2.test_policy import sample
        a, b = sample(), sample(t=2)
        self.assertEqual(resources.assess([a, b])['status'], 'PASS')
        # The numerical predicates are reused, while the resulting profile is new.
        for key, value in [('pressureAfter', 2), ('freePages', 0), ('swapUsedBytes', 10**12)]:
            bad = dict(b); bad[key] = value
            with self.assertRaises(ValueError): resources.assess([a, bad])


if __name__ == '__main__': unittest.main()
