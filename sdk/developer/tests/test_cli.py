import contextlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from developer import cli
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'engine'))
from case_sdk import contract, workspace

class SyntheticChild:
    """No subprocess or engine is started by these dispatch-path tests."""
    pid = 42
    def __init__(self, command, *, env, stdout, stderr, start_new_session):
        self.terminated = False; self.killed = False; self.waits = 0
        self.mode = SyntheticReplayTests.mode
        self.assert_session = start_new_session
        stdout.write(json.dumps({'status': 'COMPLETED', 'nativeInvocations': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}}).encode())
    def wait(self, timeout):
        self.waits += 1
        if self.mode == 'cleanup-hang': raise subprocess.TimeoutExpired('synthetic cleanup', timeout)
        if self.waits == 1 and self.mode == 'timeout': raise subprocess.TimeoutExpired('synthetic', timeout)
        if self.waits == 1 and self.mode == 'interrupt': raise InterruptedError('synthetic')
        return 1 if self.mode == 'bad-exit' else 0
    def terminate(self):
        self.terminated = True
        if self.mode == 'signal-error': raise OSError('synthetic signal failure')
    def kill(self): self.killed = True

class SyntheticReplayTests(unittest.TestCase):
    mode = 'normal'
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.authority = self.root / 'synthetic.json'
        self.authority.write_text('{"syntheticFixtureNotAnAuthority":true}')
        self.case = self.root / 'case'; self.case.mkdir()
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(contract, 'validate_approval', return_value=None))
        self.stack.enter_context(patch.object(workspace, 'resolve_plan', return_value={'binding': {'operationCommitment': 'SYNTHETIC_NOT_AN_EXECUTION_OPERATION'}}))
        self.popen = self.stack.enter_context(patch.object(cli.subprocess, 'Popen', side_effect=SyntheticChild))
    def tearDown(self):
        self.stack.close(); self.directory.cleanup(); type(self).mode = 'normal'
    def run_fixture(self):
        return cli.replay(self.case, '0' * 32, self.authority, time.monotonic())
    def test_timeout_cannot_promote_completed_fixture(self):
        type(self).mode = 'timeout'
        result = self.run_fixture()
        self.assertEqual(result['status'], 'INTERRUPTED_UNVERIFIED')
        self.assertIsNone(result['nativeInvocations'])
        self.assertTrue(result['outerWorkflow']['deadlineExceeded'])
    def test_nonzero_exit_cannot_promote_completed_fixture(self):
        type(self).mode = 'bad-exit'
        self.assertEqual(self.run_fixture()['status'], 'INTERRUPTED_UNVERIFIED')
    def test_cleanup_timeout_retains_unverified_result_and_closed_latch(self):
        type(self).mode = 'cleanup-hang'
        result = self.run_fixture()
        self.assertEqual(result['status'], 'INTERRUPTED_UNVERIFIED')
        self.assertFalse(result['outerWorkflow']['cliReaped'])
        self.assertIsNone(result['nativeInvocations'])
        self.assertTrue(result['outerWorkflow']['cleanupFailures'])
        self.assertTrue((self.case / 'workflows' / ('0' * 32) / 'RESULT.json').exists())
    def test_signal_error_does_not_erase_original_timeout(self):
        type(self).mode = 'signal-error'
        with patch.object(SyntheticChild, 'wait', side_effect=[subprocess.TimeoutExpired('synthetic', 1), 0]):
            result = self.run_fixture()
        self.assertEqual(result['status'], 'INTERRUPTED_UNVERIFIED')
        self.assertIn('TimeoutExpired', result['outerWorkflow']['controllerFailure'])
        self.assertTrue(result['outerWorkflow']['cleanupFailures'])
    def test_controller_reserves_time_for_cleanup_inside_workflow_limit(self):
        waits = []
        def wait(child, timeout): waits.append(timeout); return 0
        with patch.object(SyntheticChild, 'wait', wait): self.run_fixture()
        self.assertLessEqual(waits[0], 169)
    def test_interruption_is_preserved(self):
        type(self).mode = 'interrupt'
        result = self.run_fixture()
        self.assertEqual(result['status'], 'INTERRUPTED_UNVERIFIED')
        self.assertIn('InterruptedError', result['outerWorkflow']['controllerFailure'])
    def test_one_shot_outer_latch_blocks_redispatch(self):
        self.run_fixture()
        with self.assertRaises(FileExistsError): self.run_fixture()
        self.assertEqual(self.popen.call_count, 1)
    def test_launch_error_is_durable_and_closed(self):
        self.popen.side_effect = OSError('synthetic launch failure')
        result = self.run_fixture()
        self.assertEqual(result['status'], 'INTERRUPTED_UNVERIFIED')
        self.assertTrue(result['outerWorkflow']['operationPermanentlyClosed'])
        self.assertTrue((self.case / 'workflows' / ('0' * 32) / 'RESULT.json').exists())
    def test_rejected_approval_does_not_dispatch_or_create_latch(self):
        with patch.object(contract, 'validate_approval', side_effect=ValueError('NOT_AUTHORIZED')):
            with self.assertRaises(ValueError): self.run_fixture()
        self.popen.assert_not_called()
        self.assertFalse((self.case / 'workflows').exists())
    def test_symlink_control_directory_stops_before_authority_copy(self):
        outside = self.root / 'outside'; outside.mkdir()
        (self.case / 'workflows').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): self.run_fixture()
        self.assertEqual(list(outside.iterdir()), [])

class CliBoundaryTests(unittest.TestCase):
    def test_python_runner_is_isolated_and_arguments_are_data(self):
        args = ['plan', '--workspace', '/tmp/spaces Ω $(false)', '--lp-bps', '50']
        command = cli.engine_command(args)
        self.assertEqual(command[1:4], ['-I', '-B', '-c'])
        self.assertEqual(command[-len(args):], args)
    def test_replay_requires_external_authority_argument(self):
        with contextlib.redirect_stderr(__import__('io').StringIO()):
            with self.assertRaises(SystemExit): cli.parser().parse_args(['replay', '--workspace', '/tmp/case', '--plan', '0' * 32])
    def test_recorded_manifest_corruption_stops_before_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'MANIFEST.json').write_text('{"files":{}}')
            (root / 'unexpected').write_text('tamper')
            with patch.object(cli.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'RECORDED_MANIFEST_DRIFT'): cli.recorded(root, {})
                run.assert_not_called()
