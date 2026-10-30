"""Installed closure owns its existing workflow; producer calls are test doubles."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from developer.files import canonical, save
from rhook_alpha.cases.scenario import closure


class ClosureWorkflow(unittest.TestCase):
    operation = 'a' * 64

    def arguments(self, root):
        return dict(sdk=SimpleNamespace(home=root / 'home'), ref='c-' + 'b' * 32,
                    output=root / 'result', credential_file=root / 'never-read-key',
                    account_assertions=root / 'account.json', expected_operation=self.operation,
                    local_owner=True, mac_ready=True)

    def completed(self):
        return dict(status='SCENARIO_WITNESS_CLOSURE_COMPLETED', operationCommitment=self.operation,
                    cleanupConfirmed=True, finalSource='NIL', completedOfflineWorlds=2,
                    nativeProducerEntries=dict(discovery=2, finalOffline=2))

    def capture(self, root, child, *, linked=True, group_gone=True, exit_code=0, wrong_binding=False):
        def fake(command, directory, timeout, stdout_limit, stderr_limit):
            self.assertEqual(timeout, 180)
            self.assertEqual((stdout_limit, stderr_limit), (1 << 20, 1 << 20))
            self.assertIn('scenario-close', command)
            self.assertNotIn('scenario-run', command)
            self.assertEqual(command[command.index('--operation') + 1], self.operation)
            self.assertEqual(command[command.index('--credential-file') + 1], str(root / 'never-read-key'))
            if linked:
                out = root / 'result'; out.mkdir()
                save(out / 'RESULT.json', child)
                save(out / 'BINDING.json', dict(operationCommitment='0' * 64 if wrong_binding else self.operation))
            process = dict(ownedChildReaped=True, workflowGroupGone=group_gone,
                           cleanupError=None, exitCode=exit_code, stop=None)
            return process, canonical(child), b''
        return fake

    def test_missing_consent_never_dispatches_or_creates_evidence(self):
        with tempfile.TemporaryDirectory(prefix='rhc-') as directory:
            root = Path(directory).resolve(); args = self.arguments(root); args['local_owner'] = False
            with patch.object(closure.native, 'capture_workflow', side_effect=AssertionError('no dispatch')):
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_CLOSURE_OWNER'):
                    closure.run_owned(**args)
            self.assertEqual(list(root.iterdir()), [])

    def test_existing_owned_launcher_preserves_the_original_run_path(self):
        with tempfile.TemporaryDirectory(prefix='rhc-') as directory:
            args = self.arguments(Path(directory).resolve()); child = self.completed()
            with patch.object(closure, 'active_group', return_value=123), \
                 patch.object(closure, 'run', return_value=child) as run, \
                 patch.object(closure.native, 'capture_workflow', side_effect=AssertionError('no nested workflow')):
                self.assertEqual(closure.run_owned(**args), child)
                run.assert_called_once_with(args['sdk'], args['ref'], args['output'],
                    credential_file=args['credential_file'], account_assertions=args['account_assertions'],
                    expected_operation=self.operation, local_owner=True, mac_ready=True)

    def test_linked_completed_result_is_returned_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='rhc-') as directory:
            root = Path(directory).resolve(); child = self.completed()
            with patch.object(closure, 'active_group', return_value=None), \
                 patch.object(closure.native, 'capture_workflow', side_effect=self.capture(root, child)) as capture:
                self.assertEqual(closure.run_owned(**self.arguments(root)), child)
                capture.assert_called_once()
            self.assertEqual(json.loads((root / 'result/RESULT.json').read_bytes()), child)
            self.assertEqual(json.loads((root / 'result.workflow/SDK_RESULT.json').read_bytes()), child)
            self.assertFalse((root / 'never-read-key').exists())

    def test_unlinked_stdout_cannot_become_completed_execution(self):
        with tempfile.TemporaryDirectory(prefix='rhc-') as directory:
            root = Path(directory).resolve(); child = self.completed()
            with patch.object(closure, 'active_group', return_value=None), \
                 patch.object(closure.native, 'capture_workflow', side_effect=self.capture(root, child, linked=False)):
                result = closure.run_owned(**self.arguments(root))
            self.assertEqual(result['status'], 'SCENARIO_CLOSURE_STOP')
            self.assertFalse(result['cleanupConfirmed'])
            self.assertEqual(result['childDiagnosticsScope'], 'UNLINKED_STDOUT_NOT_NATIVE_EXECUTION_EVIDENCE')

    def test_wrong_binding_or_unclean_group_or_wrong_counts_never_pass(self):
        for change in ('binding', 'cleanup', 'counts'):
            with self.subTest(change=change), tempfile.TemporaryDirectory(prefix='rhc-') as directory:
                root = Path(directory).resolve(); child = self.completed()
                if change == 'counts': child['nativeProducerEntries']['finalOffline'] = 1
                with patch.object(closure, 'active_group', return_value=None), \
                     patch.object(closure.native, 'capture_workflow', side_effect=self.capture(root, child,
                         wrong_binding=change == 'binding', group_gone=change != 'cleanup')):
                    result = closure.run_owned(**self.arguments(root))
                self.assertEqual(result['status'], 'SCENARIO_CLOSURE_STOP')
                self.assertTrue(result['operationPermanentlyClosed'])
                self.assertFalse(result['automaticRetry'])

    def test_linked_missing_state_retains_precise_stop(self):
        with tempfile.TemporaryDirectory(prefix='rhc-') as directory:
            root = Path(directory).resolve()
            child = dict(status='SCENARIO_CLOSURE_STOP', operationCommitment=self.operation,
                         causeCode='HOST_STOP_MISSING_STATE', primaryStop={'kind': 'TRIE_UPDATE_PREIMAGE_UNAVAILABLE'},
                         cleanupConfirmed=True, operationPermanentlyClosed=True, automaticRetry=False)
            with patch.object(closure, 'active_group', return_value=None), \
                 patch.object(closure.native, 'capture_workflow', side_effect=self.capture(root, child, exit_code=1)):
                result = closure.run_owned(**self.arguments(root))
            self.assertEqual(result['causeCode'], child['causeCode'])
            self.assertEqual(result['primaryStop'], child['primaryStop'])
            self.assertTrue(result['cleanupConfirmed'])

    def test_dispatch_failure_retains_attempt_and_forbids_reuse(self):
        with tempfile.TemporaryDirectory(prefix='rhc-') as directory:
            root = Path(directory).resolve()
            with patch.object(closure, 'active_group', return_value=None), \
                 patch.object(closure.native, 'capture_workflow', side_effect=RuntimeError('synthetic capture failure')) as capture:
                result = closure.run_owned(**self.arguments(root))
                self.assertEqual(result['status'], 'SCENARIO_CLOSURE_STOP')
                self.assertIn('synthetic capture failure', result['causeCode'])
                with self.assertRaisesRegex(ValueError, 'FRESH_CLOSURE_WORKFLOW_EVIDENCE_REQUIRED'):
                    closure.run_owned(**self.arguments(root))
                capture.assert_called_once()

    def test_installed_cli_owns_workflow_before_account_gate_without_native(self):
        sdk_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='rhc-', dir='/tmp') as directory:
            root = Path(directory).resolve(); prefix = root / 'install'
            env = dict(PATH='/usr/bin:/bin', HOME=str(root), TMPDIR=str(root), LANG='C', TZ='UTC')
            installed = subprocess.run([sys.executable, '-I', '-S', '-B', str(sdk_root / 'install_cases.py'),
                                       '--prefix', str(prefix)], env=env, capture_output=True, timeout=20)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            account = root / 'account.json'
            account.write_text(json.dumps(dict(schema='rhook/scenario-account-assertions/0.1', freePlan=False)))
            args = self.arguments(root)
            command = [str(prefix / 'bin/rhook-cases'), '--home', str(args['sdk'].home), 'scenario-close',
                       '--plan', args['ref'], '--output', str(args['output']),
                       '--credential-file', str(args['credential_file']), '--account-assertions', str(account),
                       '--operation', self.operation, '--local-owner', '--mac-ready']
            result = subprocess.run(command, env=env, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 1, result.stderr)
            reported = json.loads(result.stdout)
            self.assertEqual(reported['causeCode'], 'CONFIRMED_FREE_ACCOUNT_REQUIRED')
            process = json.loads((root / 'result.workflow/process/FINAL_PROCESS_RESULT.json').read_bytes())
            self.assertTrue(process['ownedChildReaped'])
            self.assertTrue(process['workflowGroupGone'])
            self.assertFalse(args['sdk'].home.exists())
            self.assertFalse(args['credential_file'].exists())


if __name__ == '__main__':
    unittest.main()
