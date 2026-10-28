from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from rhook_alpha.cases import forge
from rhook_alpha.cases.api import CaseSDK


class AcquisitionBoundary(unittest.TestCase):
    def test_network_is_opt_in_before_any_runtime_or_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk=CaseSDK(root/'home')
            with mock.patch.object(forge.native,'runtime',side_effect=AssertionError('must not touch runtime')):
                with self.assertRaisesRegex(ValueError,'EXPLICIT_READ_ONLY'):
                    sdk.capture_case(root/'out',block=123,case_id='new-case',subject_index=1)
            self.assertFalse((root/'out').exists())

    def test_wrong_chain_and_ambiguous_block_fail_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home')
            with mock.patch.object(forge.native,'runtime',side_effect=AssertionError('must not touch runtime')):
                for block,chain in [(0,4663),(True,4663),('latest',4663),(123,1)]:
                    with self.assertRaises(ValueError):
                        sdk.capture_case(Path(tmp)/'out',block=block,chain=chain,case_id='new-case',subject_index=1,read_only=True)

    def test_recent_capture_never_substitutes_an_arbitrary_case_after_no_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();out=root/'out';out.mkdir();sdk=CaseSDK(root/'home')
            stop={'status':'ACQUISITION_STOP','causeCode':'NO_SUPPORTED_POOL_EVENT_IN_BOUNDED_WINDOW','nativeExecutions':0}
            with mock.patch.object(forge,'run',return_value=stop),mock.patch.object(forge,'create',side_effect=AssertionError('no case may be created')):
                value=sdk.capture_recent_case(out,read_only=True)
            self.assertEqual(value['status'],'ACQUISITION_STOP');self.assertNotIn('capsule',value)

    def test_near_head_no_event_does_not_forge_or_authorize_a_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk=CaseSDK(root/'home');output=root/'out';output.mkdir()
            with mock.patch.object(forge,'run',return_value={'status':'NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW'}) as helper, mock.patch.object(forge,'create',side_effect=AssertionError('no case without event')):
                value=sdk.capture_recent_case(output,read_only=True)
            self.assertEqual(value['status'],'NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW')
            self.assertEqual(helper.call_args.kwargs['action'],'capture-recent')
            self.assertNotIn('capsule',value)

    def test_fresh_root_qualification_requires_explicit_read_only_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home')
            with mock.patch.object(forge.native,'runtime',side_effect=AssertionError('must not touch runtime')):
                with self.assertRaisesRegex(ValueError,'EXPLICIT_READ_ONLY'):
                    sdk.qualify_root(Path(tmp)/'out')

    def test_capture_helper_can_write_a_package_larger_than_one_mib(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();file=root/'package'
            result,out,err=forge.capture_helper([sys.executable,'-I','-B','-c',
                'import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(b"x"*(2<<20))',str(file)],root/'capture',5)
            self.assertEqual(result['exitCode'],0,err)
            self.assertTrue(result['ownedChildReaped'])
            self.assertEqual(file.stat().st_size,2<<20)

    def test_helper_file_and_pipe_limits_remain_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();file=root/'too-large'
            result,_,_=forge.capture_helper([sys.executable,'-I','-B','-c',
                'import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(b"x"*(9<<20))',str(file)],root/'file',5)
            self.assertNotEqual(result['exitCode'],0)
            self.assertTrue(result['ownedChildReaped'])
            self.assertLessEqual(file.stat().st_size,8<<20)
            result,out,_=forge.capture_helper([sys.executable,'-I','-B','-c',
                'import os;os.write(1,b"x"*131072)'],root/'pipe',5,1024,1024)
            self.assertIsNotNone(result['stop']);self.assertTrue(result['ownedChildReaped']);self.assertLessEqual(len(out),1024)

    def test_negative_subject_net_is_not_reported_as_a_buyer_gain(self):
        from rhook_alpha.cases.adapters import HookrLP
        world={'buyerRhookTransferNetBaseUnits':'-100','subjectGasUsed':'7','outerSwap':None}
        value=HookrLP().compare({'worlds':{'ACTUAL':world,'BRANCH':world}})
        self.assertEqual(value['subjectRhookTransferNetActualBaseUnits'],'-100')
        self.assertEqual(value['subjectRhookTransferNetDeltaBaseUnits'],'0')
        self.assertIsNone(value['buyerTransferNetIncreasePercent'])


class WatchBoundary(unittest.TestCase):
    def test_watch_requires_read_only_before_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home')
            with mock.patch.object(forge.native,'runtime',side_effect=AssertionError('must not touch runtime')):
                with self.assertRaisesRegex(ValueError,'EXPLICIT_READ_ONLY'):
                    sdk.watch_case(Path(tmp)/'out',account_assertions=Path(tmp)/'account')
            self.assertFalse((Path(tmp)/'out').exists())

    def test_no_event_never_creates_a_capsule_or_native_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();output=root/'out';output.mkdir();sdk=CaseSDK(root/'home')
            with mock.patch.object(forge,'run',return_value={'status':'NO_ELIGIBLE_EVENT_OBSERVED','nativeExecutions':0}) as helper, mock.patch.object(forge,'create',side_effect=AssertionError('no case without event')):
                value=sdk.watch_case(output,account_assertions=root/'account',read_only=True)
            self.assertEqual(value['status'],'NO_ELIGIBLE_EVENT_OBSERVED')
            self.assertEqual(helper.call_args.kwargs['action'],'watch')
            self.assertIsNone(helper.call_args.kwargs['credential_file'])
            self.assertNotIn('capsule',value)


if __name__=='__main__':unittest.main()
