"""Exercise real consent consumption with the native process boundary stubbed."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rhook_alpha import SDK, consent
from rhook_alpha.api import engine
import test_alpha as fixtures


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LocalConsent(); self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.sdk = SDK(self.fixture.root); self.sdk.workspace = self.fixture.root
        self.binding = dict(self.fixture.binding, outputPath=str(self.fixture.root/'synthetic-run'))
        self.resolve = patch.object(self.sdk, '_resolve', return_value=({'newValue':'50'}, self.binding, ({}, self.fixture.context, self.fixture.key)))
        self.context = patch.object(self.sdk, '_context', side_effect=AssertionError('duplicate authentication after resolve'))
        self.resolve.start(); self.context.start()
        self.addCleanup(self.resolve.stop); self.addCleanup(self.context.stop)

    def test_real_grant_consumed_before_single_dispatch_and_stop_remains_closed(self):
        grant = self.sdk.authorize(self.binding['planId'], local_owner=True, mac_ready=True)
        def stop(workspace, plan, authority, began):
            self.assertTrue((grant.parent/'CONSUMED.json').is_file())
            self.assertEqual(json.loads(authority.read_bytes())['operationCommitment'], self.binding['operationCommitment'])
            return {'status':'HOST_STOP', 'nativeInvocations':{'ACTUAL':0,'BRANCH':0,'B':0}}
        with patch.object(engine, 'replay', side_effect=stop) as dispatch:
            result = self.sdk.replay(self.binding['planId'], grant)
            self.assertEqual(result['status'], 'HOST_STOP')
            with self.assertRaises(FileExistsError): self.sdk.replay(self.binding['planId'], grant)
            self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(json.loads((grant.parent/'RESULT.json').read_bytes())['status'], 'HOST_STOP')

    def test_interrupted_dispatch_preserves_unknown_counts_and_consumed_grant(self):
        grant = self.sdk.authorize(self.binding['planId'], local_owner=True, mac_ready=True)
        with patch.object(engine, 'replay', side_effect=InterruptedError('synthetic, no worker')):
            with self.assertRaises(InterruptedError): self.sdk.replay(self.binding['planId'], grant)
        result = json.loads((grant.parent/'RESULT.json').read_bytes())
        self.assertEqual(result['status'], 'INTERRUPTED_UNVERIFIED')
        self.assertIsNone(result['nativeInvocations'])
        self.assertTrue(result['operationPermanentlyClosed'])

    def test_rejected_grant_never_reaches_dispatch(self):
        grant = self.sdk.authorize(self.binding['planId'], local_owner=True, mac_ready=True)
        grant.write_text('{}')
        with patch.object(engine, 'replay') as dispatch, self.assertRaises(ValueError):
            self.sdk.replay(self.binding['planId'], grant)
        dispatch.assert_not_called()


if __name__ == '__main__': unittest.main(verbosity=2)
