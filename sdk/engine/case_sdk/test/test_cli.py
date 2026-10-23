import contextlib
import io
import json
import unittest
from unittest.mock import patch
from case_sdk import cli

class CliTest(unittest.TestCase):

    def test_cli_uses_recorded_status_for_exit_code(self):
        for status, expected in [('COMPLETED', 0), ('MISSING_WITNESS', 1), ('HOST_STOP', 1), ('INTERRUPTED_UNVERIFIED', 1)]:
            with patch.object(cli, 'execute', return_value={'status': status}), patch.object(cli, 'replay_paths', return_value=('b', 'a', 'c')), contextlib.redirect_stdout(io.StringIO()) as out:
                code = cli.main(['replay', '--workspace', 'unused', '--plan', '0' * 32, '--authority', 'unused'])
            self.assertEqual(code, expected)
            self.assertEqual(json.loads(out.getvalue())['status'], status)

    def test_missing_approval_stops_before_resolution(self):
        with patch.object(cli, 'replay_paths', side_effect=AssertionError('unexpected resolution')), contextlib.redirect_stdout(io.StringIO()) as out:
            code = cli.main(['replay', '--workspace', 'unused', '--plan', '0' * 32])
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['status'], 'NOT_AUTHORIZED')

    def test_invalid_lp_request_is_not_a_host_failure(self):
        import tempfile
        from pathlib import Path
        from case_sdk.test import test_workspace as helpers
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            case = helpers.WorkspaceTest().register(Path(d))
            for value in ['100', '-1', '101', '1e1']:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    code = cli.main(['plan', '--workspace', str(case), '--expected-old', '100', '--lp-bps', value])
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(out.getvalue())['status'], 'INVALID_PLAN')
            self.assertEqual(list((case / 'plans').iterdir()), [])
