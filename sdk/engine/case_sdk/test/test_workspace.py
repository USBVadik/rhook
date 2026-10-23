import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from case_sdk import common as c, workspace as ws
from case_sdk.test import test_workflow as helpers

class WorkspaceTest(unittest.TestCase):

    def register(self, root):
        old = root / 'mock'
        old.mkdir()
        _, _, buildp, _ = helpers.WorkflowTest().setup_case(old)
        build = c.strict(buildp.read_bytes())
        build['nodePath'] = os.environ['RHOOK_NODE']
        build['nodeSha256'] = c.sha(c.read(build['nodePath'], 256 << 20))
        buildp.write_bytes(c.canonical(build))
        case = root / 'case with spaces Ω'
        ws.initialize(case, Path(os.environ['RHOOK_PACKAGE']), buildp)
        return case

    def test_three_values_share_one_build_and_same_value_gets_new_ref(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            case = self.register(Path(d))
            results = [ws.plan_request(case, '100', n) for n in ['0', '50', '99', '50']]
            self.assertEqual(len({x['planId'] for x in results}), 4)
            self.assertEqual(len({x['runtimePlanSha256'] for x in results}), 3)
            self.assertEqual(results[1]['semanticPlanCommitment'], results[3]['semanticPlanCommitment'])
            bindings = [c.strict(c.read(x['bindingsPath'])) for x in results]
            self.assertEqual(len({x['binarySha256'] for x in bindings}), 1)
            for x in results:
                self.assertFalse(Path(x['runOutput']).exists())
            self.assertNotEqual(bindings[1]['operationCommitment'], bindings[3]['operationCommitment'])

    def test_missing_build_is_setup_error_not_implicit_build(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            case = Path(d) / 'unregistered'
            ws.initialize(case, Path(os.environ['RHOOK_PACKAGE']), None)
            with self.assertRaisesRegex(ValueError, 'BUILD_NOT_REGISTERED'):
                ws.plan_request(case, '100', '50')

    def test_ref_collision_and_traversal_cannot_overwrite(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            case = self.register(Path(d))
            with patch.object(ws.secrets, 'token_hex', return_value='0' * 32):
                result = ws.plan_request(case, '100', '50')
                original = c.read(result['bindingsPath'])
                with self.assertRaises((ValueError, FileExistsError)):
                    ws.plan_request(case, '100', '0')
            self.assertEqual(c.read(result['bindingsPath']), original)
            for ref in ['../escape', 'x' * 32, '0' * 31]:
                with self.assertRaises(ValueError):
                    ws.resolve_plan(case, ref)
