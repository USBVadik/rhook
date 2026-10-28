from pathlib import Path
import unittest
from unittest import mock
from rhook_alpha.cases.scenario import diagnostic


class DiagnosticBoundary(unittest.TestCase):
    def test_explicit_owner_and_workflow_precede_any_input_read(self):
        with mock.patch.object(diagnostic,'prepare',side_effect=AssertionError('must not load')):
            for options in ({},{'local_owner':True},{'mac_ready':True}):
                with self.assertRaisesRegex(ValueError,'EXPLICIT_DIAGNOSTIC'):
                    diagnostic.run(None,None,None,None,expected_operation=None,**options)
            with mock.patch.object(diagnostic,'active_group',return_value=None):
                with self.assertRaisesRegex(ValueError,'WORKFLOW_CONTEXT'):
                    diagnostic.run(None,None,None,None,expected_operation=None,local_owner=True,mac_ready=True)

    def test_wrong_operation_stops_before_helper_grant_or_output(self):
        with mock.patch.object(diagnostic,'active_group',return_value=123), \
             mock.patch.object(diagnostic,'prepare',return_value={'operationCommitment':'correct'}), \
             mock.patch.object(diagnostic.api,'_helper',side_effect=AssertionError('no helper')):
            with self.assertRaisesRegex(ValueError,'EXACT_DIAGNOSTIC'):
                diagnostic.run(None,None,None,None,expected_operation='wrong',local_owner=True,mac_ready=True)


if __name__=='__main__':unittest.main()
