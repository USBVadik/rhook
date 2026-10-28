from pathlib import Path
import sys
import tempfile
import unittest
from rhook_alpha.cases import native

class ProcessLimits(unittest.TestCase):
    def test_output_is_cut_and_owned_child_reaped_on_overflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,out,err=native.capture([sys.executable,'-I','-B','-c','import os;os.write(1,b"x"*131072)'],Path(tmp).resolve()/'capture',5,1024,1024)
            self.assertLessEqual(len(out),1024)
            self.assertIsNotNone(result['stop'])
            self.assertTrue(result['ownedChildReaped'])
    def test_preexisting_timer_is_refused_before_plan_or_grant_access(self):
        from unittest import mock
        with mock.patch.object(native.signal,'getitimer',return_value=(1.0,0.0)):
            with self.assertRaisesRegex(ValueError,'CALLER_TIMER_ACTIVE'):
                native.replay(None,'c-'+'0'*32,'unused')

class ConsumedFailure(unittest.TestCase):
    def test_setup_failure_after_consumption_has_a_durable_result(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest import mock
        from developer.files import save,load
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();ref='c-'+'a'*32
            (root/'consents'/ref).mkdir(parents=True);(root/'runs').mkdir()
            grant=root/'consents'/ref/'GRANT.json'
            save(grant,{'body':{'binding':{'trustedCheckpoint':'checkpoint'}}})
            b={'planId':ref,'caseId':'case','capsuleId':'b'*64,'outputPath':str(root/'runs'/ref),'operationCommitment':'c'*64}
            sdk=SimpleNamespace(home=root,describe=lambda _: {'caseId':'case','capsuleId':'b'*64})
            with mock.patch.object(native,'binding',return_value=b),mock.patch.object(native,'runtime',return_value={}),mock.patch.object(native,'guards',return_value=(lambda _:nullcontext(),None,None,None)),mock.patch.object(native,'read_key',return_value=b'k'*32),mock.patch.object(native.authority,'consume',return_value={}) as consumed,mock.patch.object(native,'execute_consumed',side_effect=OSError('injected setup failure'),create=True):
                result=native.replay(sdk,ref,grant)
            consumed.assert_called_once()
            self.assertEqual(result['status'],'HOST_STOP')
            self.assertTrue(result['operationPermanentlyClosed'])
            self.assertEqual(load(grant.parent/'RESULT.json')['causeCode'],'OSError: injected setup failure')

class DurableCompletion(unittest.TestCase):
    def test_manifest_failure_cannot_leave_a_completed_result(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp).resolve()
            with mock.patch.object(native,'save',side_effect=OSError('manifest storage unavailable')):
                with self.assertRaises(OSError):native.seal_result(out,{'status':'COMPLETED'})
            self.assertFalse((out/'RESULT.json').exists())
    def test_completed_result_matches_the_sealed_inventory(self):
        from developer.files import load,tree
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp).resolve();(out/'evidence').write_text('synthetic')
            native.seal_result(out,{'status':'COMPLETED'})
            self.assertEqual(tree(out,omit=('MANIFEST.json',)),load(out/'MANIFEST.json')['files'])

class StagingBoundary(unittest.TestCase):
    def test_staging_uses_the_bound_plan_before_admission(self):
        from types import SimpleNamespace
        from unittest import mock
        from developer.files import save, sha
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); ref='c-'+'d'*32
            case=root/'case';case.mkdir();(root/'plans'/ref).mkdir(parents=True);(root/'runs').mkdir()
            plan={'planId':ref,'caseId':'synthetic-staging','capsuleId':'e'*64}
            save(case/'CAPSULE.json',{});save(case/'BLOCK_PACKAGE.json',{})
            save(root/'plans'/ref/'PLAN.json',plan)
            files={}
            for name in ('worker','sensor'):
                path=root/name;path.write_bytes(b'not executable: staging test only')
                files[name]={'path':str(path),'sha256':sha(path)}
            out=root/'runs'/ref
            binding={'outputPath':str(out),'operationCommitment':'f'*64}
            sdk=SimpleNamespace(home=root,registry=SimpleNamespace(resolve=lambda _: (case,{})))
            admission=mock.Mock(side_effect=ValueError('SYNTHETIC_ADMISSION_STOP'))
            supervise=mock.Mock(side_effect=AssertionError('must never execute'))
            result=native.execute_consumed(sdk,plan,binding,{'files':files},{},time.monotonic(),supervise,lambda *args:True,admission)
            self.assertEqual(result['status'],'HOST_STOP')
            self.assertEqual(result['causeCode'],'ValueError: SYNTHETIC_ADMISSION_STOP')
            self.assertEqual((out/'inputs/PLAN.json').read_bytes(),(root/'plans'/ref/'PLAN.json').read_bytes())
            self.assertEqual(result['nativeInvocations'],{'ACTUAL':0,'BRANCH':0,'B':0})
            admission.assert_called_once();supervise.assert_not_called()
