from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from case_sdk import build

class BuildTest(unittest.TestCase):

    def test_stage_is_offline_exact_and_excludes_historical_tests(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            overlay = root / 'overlay'
            for suite in ['prestate', 'worker']:
                sub = overlay / 'native' / suite
                sub.mkdir(parents=True)
                (sub / ('plan.go' if suite == 'prestate' else 'main.go')).write_text('package ' + ('prestate' if suite == 'prestate' else 'main') + '\n')
                (sub / 'new_test.go').write_text('package ' + ('prestate' if suite == 'prestate' else 'main') + '\n')
            (overlay / 'case.json').write_bytes(b'{}')
            with patch.object(build, 'HERE', overlay), patch.object(build, 'verify_retained', return_value={}):
                result = build.stage(root, root / 'stage', 'worker')
            staged = root / 'stage'
            self.assertEqual((staged / 'worker/pair.go').read_bytes(), (build.ROOT / 'native/saved-pair/pair.go').read_bytes())
            self.assertFalse(list((staged / 'prestate').glob('*_test.go')))
            self.assertNotIn('TestPinnedSavedPackageAdmissionAndFreshNilSourceBridges', (staged / 'worker/synthetic_pair_test.go').read_text())
            self.assertIn('result[10], result[11] = 0, 0', (staged / 'prestate/lp_branch.go').read_text())
            self.assertFalse(result['productionWorkerLaunched'])
            with self.assertRaises(ValueError):
                build.stage(root, staged, 'worker')

    def test_build_drift_missing_tool_or_empty_test_selection_fails(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises((ValueError, FileNotFoundError)):
                build.verify_retained(Path(d))
        with self.assertRaises(ValueError):
            build.test_count('ok module [no tests to run]\n')
        self.assertEqual(build.test_count('--- PASS: TestSynthetic (0.00s)\nPASS\nok x'), 1)

    def test_compiler_closure_rejects_unlisted_retained_file(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            root = Path(d)
            retained = root / 'retained'
            retained.mkdir()
            output = root / 'output'
            output.mkdir()
            p = retained / 'unexpected.go'
            p.write_bytes(b'package main')
            with self.assertRaises(ValueError):
                build.compiler_input(p, retained, output, {})
            expected = {'unexpected.go': build.sha(p.read_bytes())}
            self.assertEqual(build.compiler_input(p, retained, output, expected), expected['unexpected.go'])
            p.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                build.compiler_input(p, retained, output, expected)
