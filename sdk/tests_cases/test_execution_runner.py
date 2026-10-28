"""Native dispatch contracts use explicit test doubles; they do not prove EVM execution."""
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
import json,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from developer.files import canonical,load,save
from rhook_alpha.execution import ExecutionSDK,ExecutionError
from rhook_alpha import execution as execution_module
from rhook_alpha.cases.scenario import api
from rhook_alpha.cases import native
from test_execution import fixture,SDK

@contextmanager
def supported_mock_host():
    # Only the facade's module bindings change, never the process-wide platform.
    # Real dispatch stays replaced by each test's explicit capture/backend double.
    host_sys=SimpleNamespace(platform='darwin',executable=sys.executable)
    host_platform=SimpleNamespace(machine=lambda:'arm64')
    with patch.object(execution_module,'sys',host_sys),patch.object(execution_module,'platform',host_platform):
        yield

class ExecutionRunner(unittest.TestCase):
    def prepared(self,root):
        import hashlib
        p=root/'source.json';p.write_bytes(canonical(fixture())+b'\n');sdk=ExecutionSDK(root/'home');result=sdk.prepare(sdk.configure(),p,expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),output=root/'prepared');return sdk,Path(result['prepared']),result

    def binding(self,prepared):
        return dict(operationCommitment='a'*64,outputPath=prepared['nativeRunDirectory'])

    def test_exact_consent_and_supported_host_before_any_dispatch(self):
        sdk=ExecutionSDK(Path('/private/tmp/uncreated-build12-home'))
        fn=getattr(sdk,'run',None);self.assertTrue(callable(fn),'native developer run missing')
        with patch.object(sdk,'operation',side_effect=AssertionError('operation touched without consent')):
            for flags in ({},{'local_owner':True},{'mac_ready':True}):
                with self.assertRaisesRegex(ExecutionError,'EXACT_LOCAL_CONSENT_REQUIRED'):fn('not-read',operation='a'*64,evidence='not-written',**flags)
            with patch('sys.platform','linux'),patch('platform.machine',return_value='x86_64'):
                with self.assertRaisesRegex(ExecutionError,'UNSUPPORTED_NATIVE_HOST'):fn('not-read',operation='a'*64,evidence='not-written',local_owner=True,mac_ready=True)

    def test_wrong_operation_never_enters_outer_capture(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();sdk,prepared,result=self.prepared(root)
            self.assertTrue(callable(getattr(sdk,'run',None)),'native run missing')
            with supported_mock_host(),patch.object(sdk,'operation',return_value=self.binding(result)),patch.object(native,'capture_workflow',side_effect=AssertionError('dispatch forbidden')):
                with self.assertRaisesRegex(ExecutionError,'OPERATION_MISMATCH'):sdk.run(prepared,operation='b'*64,evidence=root/'workflow',local_owner=True,mac_ready=True)
            self.assertFalse((root/'workflow').exists())

    def fake_capture(self,root,result,*,stop=None,group_gone=True,child_status='SCENARIO_COMPLETED'):
        def capture(command,directory,timeout,stdout_limit,stderr_limit):
            self.assertEqual(timeout,180);self.assertIn('scenario-run',command);self.assertIn('--operation',command);self.assertNotIn('scenario-close',command)
            self.assertNotIn('credential',str(command));self.assertIn(str(SDK),command)
            Path(directory).mkdir();out=Path(result['nativeRunDirectory']);out.mkdir(parents=True)
            value=dict(status=child_status,operationCommitment='a'*64,cleanupConfirmed=True,producerInvocations=2,
                       runDirectory=str(out),operationPermanentlyClosed=True,RPC=0,WSS=0)
            if child_status!='SCENARIO_COMPLETED':value.update(primaryStop=dict(kind='NATIVE_STOP',code='TRIE_UPDATE_PREIMAGE_UNAVAILABLE',evidencePath='runtime/NATIVE_COMPLETION.json'),failure=dict(world='SCENARIO_VARIANT',missingNode='0x'+'12'*32))
            save(out/'RESULT.json',value);save(out/'BINDING.json',dict(operationCommitment='a'*64))
            process=dict(ownedChildReaped=True,workflowGroupGone=group_gone,stop=stop,exitCode=0 if child_status=='SCENARIO_COMPLETED' else 1,cleanupError=None)
            return process,canonical(value)+b'\n',b''
        return capture

    def test_dispatches_existing_cli_in_owned_workflow_and_closes_attempt(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();sdk,prepared,result=self.prepared(root)
            self.assertTrue(callable(getattr(sdk,'run',None)),'native run missing')
            with supported_mock_host(),patch.object(sdk,'operation',return_value=self.binding(result)),patch.object(native,'capture_workflow',side_effect=self.fake_capture(root,result)) as capture:
                answer=sdk.run(prepared,operation='a'*64,evidence=root/'evidence',local_owner=True,mac_ready=True)
                self.assertEqual(answer['status'],'EXECUTION_COMPLETED');self.assertEqual(answer['nativeResult']['producerInvocations'],2);self.assertTrue(answer['cleanupConfirmed']);capture.assert_called_once()
                with self.assertRaisesRegex(ExecutionError,'OPERATION_ALREADY_ATTEMPTED'):sdk.run(prepared,operation='a'*64,evidence=root/'other-evidence',local_owner=True,mac_ready=True)
            self.assertTrue((root/'evidence/EXECUTION_RESULT.json').is_file())

    def test_cleanup_uncertainty_is_never_completed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();sdk,prepared,result=self.prepared(root)
            self.assertTrue(callable(getattr(sdk,'run',None)),'native run missing')
            with supported_mock_host(),patch.object(sdk,'operation',return_value=self.binding(result)),patch.object(native,'capture_workflow',side_effect=self.fake_capture(root,result,group_gone=False)):
                answer=sdk.run(prepared,operation='a'*64,evidence=root/'evidence',local_owner=True,mac_ready=True)
            self.assertEqual(answer['status'],'EXECUTION_STOP');self.assertFalse(answer['cleanupConfirmed']);self.assertFalse(answer['automaticRetry'])

    def test_native_missing_dependency_and_failed_world_are_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();sdk,prepared,result=self.prepared(root)
            self.assertTrue(callable(getattr(sdk,'run',None)),'native run missing')
            with supported_mock_host(),patch.object(sdk,'operation',return_value=self.binding(result)),patch.object(native,'capture_workflow',side_effect=self.fake_capture(root,result,child_status='SCENARIO_STOP')):
                answer=sdk.run(prepared,operation='a'*64,evidence=root/'evidence',local_owner=True,mac_ready=True)
            self.assertEqual(answer['status'],'EXECUTION_STOP');self.assertEqual(answer['nativeResult']['failure']['world'],'SCENARIO_VARIANT');self.assertEqual(answer['primaryStop']['code'],'TRIE_UPDATE_PREIMAGE_UNAVAILABLE')

    def test_authenticate_and_native_compare_delegate_without_recorded_fallback(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();sdk,prepared,result=self.prepared(root)
            self.assertTrue(callable(getattr(sdk,'authenticate',None)),'native authenticate missing')
            with supported_mock_host(),patch.object(api,'check',return_value=dict(status='AUTHENTICATED_SCENARIO_INPUT',nativeExecutions=0,coverage='KNOWN_PREREQUISITES_ONLY')) as checked:
                answer=sdk.authenticate(prepared);self.assertEqual(answer['coverage'],'KNOWN_PREREQUISITES_ONLY');checked.assert_called_once()
            with supported_mock_host(),patch.object(api,'compare',return_value=dict(status='VERIFIED_SCENARIO_COMPARISON',worlds=[{'actorRhookTransferNetBaseUnits':'10'},{'actorRhookTransferNetBaseUnits':'12'}],rhookTransferNetDeltaBaseUnits='2',qualifiedClaims=0)) as compare:
                answer=sdk.compare(Path(result['nativeRunDirectory']));self.assertEqual(answer['targetTokenTransferNetDeltaBaseUnits'],'2');compare.assert_called_once()

    def test_v2_child_rechecks_exact_operation_before_authentication_or_authority(self):
        with tempfile.TemporaryDirectory() as t:
            sdk=ExecutionSDK(Path(t).resolve()/'home')._sdk()
            with patch('sys.platform','darwin'),patch('platform.machine',return_value='arm64'),patch.object(api,'prepare',return_value={'operationCommitment':'b'*64}),patch.object(api,'_input',side_effect=AssertionError('must stop before any input/helper/authority')):
                with self.assertRaisesRegex(ValueError,'EXACT_V2_OPERATION_REQUIRED'):
                    api.run(sdk,'not-read',local_owner=True,mac_ready=True,host_profile='v2',expected_operation='a'*64)

    def test_operation_preserves_the_original_hashable_binding_as_nested_data(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();sdk,prepared,result=self.prepared(root);binding=self.binding(result)
            with patch.object(api,'prepare',return_value=binding):answer=sdk.operation(prepared)
            self.assertEqual(answer['binding'],binding)
            self.assertEqual(answer['operationCommitment'],binding['operationCommitment'])
            self.assertFalse(answer['executionAuthorized'])

    def test_pre_native_child_failure_is_preserved_without_native_completion_claim(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();sdk,prepared,result=self.prepared(root)
            def failed(command,directory,*args):
                Path(directory).mkdir()
                child=dict(status='INPUT_OR_RUNTIME_STOP',causeCode='SCENARIO_CAPTURE_RUNTIME_DRIFT',
                           details={'stderr':'ACCOUNT_PREIMAGE_UNAVAILABLE: 0x'+'12'*32},nextStep='Inspect input.',automaticRetry=False)
                return dict(ownedChildReaped=True,workflowGroupGone=True,cleanupError=None,exitCode=1,stop=None),canonical(child),b''
            with supported_mock_host(),patch.object(sdk,'operation',return_value=self.binding(result)),patch.object(native,'capture_workflow',side_effect=failed):
                answer=sdk.run(prepared,operation='a'*64,evidence=root/'evidence',local_owner=True,mac_ready=True)
            self.assertEqual(answer['causeCode'],'SCENARIO_CAPTURE_RUNTIME_DRIFT')
            self.assertIn('ACCOUNT_PREIMAGE_UNAVAILABLE',answer['childDiagnostics']['details']['stderr'])
            self.assertIsNone(answer['nativeResult']);self.assertFalse(answer['cleanupConfirmed']);self.assertEqual(answer['status'],'EXECUTION_STOP')

    def test_legacy_child_cli_serializes_structured_helper_failure(self):
        import contextlib,io
        from rhook_alpha.cases.__main__ import main
        with tempfile.TemporaryDirectory() as t:
            out=io.StringIO();error=api.ScenarioHelperStop(dict(stop=None,exitCode=1,captureError=None),b'',b'CODE_PREIMAGE_UNAVAILABLE: 0x1234',Path(t)/'retained')
            with patch.object(api,'run',side_effect=error),contextlib.redirect_stdout(out):
                code=main(['--home',str(Path(t).resolve()/'home'),'scenario-run','not-read','--local-owner','--mac-ready'])
            value=json.loads(out.getvalue());self.assertEqual(code,1);self.assertEqual(value['details']['stderr'],'CODE_PREIMAGE_UNAVAILABLE: 0x1234')
            self.assertTrue(value['nextStep'])

    def test_helper_failure_keeps_exact_stderr_and_raw_files(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();home=root/'home';home.mkdir();sdk=ExecutionSDK(home)._sdk();message=b'ACCOUNT_PREIMAGE_UNAVAILABLE: missing trie node 0x'+b'12'*32
            def failure(command,directory,*args):
                directory.mkdir();(directory/'stdout.bin').write_bytes(b'');(directory/'stderr.bin').write_bytes(message)
                return dict(ownedChildReaped=True,stop=None,exitCode=1),b'',message
            with patch.object(api,'runtime',return_value={'files':{'worker':{'path':'/never-executed'}}}),patch.object(api.forge,'capture_helper',side_effect=failure):
                with self.assertRaises(ValueError) as error:api._helper(sdk,['--authenticate','not-executed'])
            report=getattr(error.exception,'report',None);self.assertIsNotNone(report,'structured helper failure missing');self.assertEqual(report['stderr'],message.decode());self.assertEqual((Path(report['evidencePath'])/'stderr.bin').read_bytes(),message)

    def test_cli_capability_and_validation_errors_are_actionable(self):
        with tempfile.TemporaryDirectory() as t:
            home=Path(t).resolve()/'home';env=dict(__import__('os').environ,PYTHONPATH=str(SDK))
            def cli(*args):return subprocess.run([sys.executable,'-B','-m','rhook_alpha.cases','--home',str(home),*args],env=env,capture_output=True,text=True,timeout=10)
            p=cli('execution-capabilities');self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['status'],'EXECUTION_CAPABILITIES');self.assertFalse(home.exists())
            p=cli('execution-configure','--lp-bps','100');self.assertEqual(p.returncode,1);v=json.loads(p.stdout);self.assertEqual(v['causeCode'],'LP_BPS_0_TO_99_REQUIRED');self.assertTrue(v['nextStep'])

if __name__=='__main__':unittest.main()
