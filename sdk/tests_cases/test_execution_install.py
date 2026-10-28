"""Clean source installation; no worker, credentials, grant or EVM required."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,unittest
from developer.files import canonical
from test_execution import fixture,SDK

EXAMPLE=SDK/'examples/execute_prepared_hookr.py'
class ExecutionInstallation(unittest.TestCase):
    def install(self,root):
        self.assertTrue(EXAMPLE.is_file(),'supported execution example is missing')
        prefix=root/'installed';p=subprocess.run([sys.executable,'-B',str(SDK/'install_cases.py'),'--prefix',str(prefix)],capture_output=True,text=True,timeout=10);self.assertEqual(p.returncode,0,p.stderr);return prefix

    def call(self,prefix,home,*args):
        return subprocess.run([sys.executable,'-I',str(prefix/'bin/rhook-cases'),'--home',str(home),*args],capture_output=True,text=True,timeout=10)

    def test_clean_install_reports_missing_private_components_then_prepares_locally(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();prefix=self.install(root);home=root/'home'
            p=self.call(prefix,home,'execution-capabilities');self.assertEqual(p.returncode,0,p.stderr);v=json.loads(p.stdout);self.assertFalse(v['nativeExecutionReady']);self.assertFalse(v['runtime']['configured']);self.assertFalse(home.exists())
            p=self.call(prefix,home,'execution-configure','--lp-bps','50');self.assertEqual(p.returncode,0,p.stderr);config=root/'config.json';config.write_text(p.stdout)
            source=root/'SCENARIO.json';source.write_bytes(canonical(fixture())+b'\n');pin=hashlib.sha256(source.read_bytes()).hexdigest();prepared=root/'prepared'
            p=self.call(prefix,home,'execution-prepare','--configuration',str(config),'--witness',str(source),'--witness-sha256',pin,'--output',str(prepared));self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['authentication'],'PENDING_NATIVE_ADMISSION')
            p=self.call(prefix,home,'execution-operation','--prepared',str(prepared));self.assertEqual(p.returncode,1);v=json.loads(p.stdout);self.assertEqual(v['causeCode'],'NATIVE_RUNTIME_MISSING');self.assertTrue(v['nextStep'])
            self.assertFalse((home/'scenarios/consents').exists())

    def test_supported_example_uses_selected_install_and_never_autoruns(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();prefix=self.install(root);home=root/'home';p=subprocess.run([sys.executable,'-I',str(EXAMPLE),'--sdk-root',str(prefix/'lib'),'--home',str(home)],capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['status'],'EXECUTION_CAPABILITIES');self.assertFalse(home.exists())
            source=root/'input.json';source.write_bytes(canonical(fixture())+b'\n');pin=hashlib.sha256(source.read_bytes()).hexdigest()
            p=subprocess.run([sys.executable,'-I',str(EXAMPLE),'--sdk-root',str(prefix/'lib'),'--home',str(home),'--witness',str(source),'--witness-sha256',pin,'--prepared',str(root/'prepared')],capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['status'],'EXECUTION_PREPARED');self.assertFalse((home/'scenarios/consents').exists())

    def test_cli_file_and_home_failures_are_structured(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();prefix=self.install(root)
            p=self.call(prefix,root/'home','execution-prepare','--configuration',str(root/'missing.json'),'--witness',str(root/'no'),'--witness-sha256','a'*64,'--output',str(root/'prepared'))
            self.assertEqual(p.returncode,1);self.assertTrue(json.loads(p.stdout)['nextStep']);self.assertFalse((root/'prepared').exists())
            (root/'linked').symlink_to(root,target_is_directory=True)
            p=self.call(prefix,root/'linked/home','execution-capabilities');self.assertEqual(p.returncode,1);self.assertTrue(json.loads(p.stdout)['nextStep'])

    def test_example_execution_without_exact_consent_is_not_a_replay(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();prefix=self.install(root)
            p=subprocess.run([sys.executable,'-I',str(EXAMPLE),'--sdk-root',str(prefix/'lib'),'--home',str(root/'home'),'--prepared',str(root/'missing'),'--execute'],capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,1);self.assertEqual(json.loads(p.stdout)['causeCode'],'EXACT_LOCAL_CONSENT_REQUIRED');self.assertFalse((root/'home').exists())

    def test_example_retains_completed_native_result_when_read_only_verify_fails(self):
        import contextlib,importlib.util,io
        from unittest.mock import patch,Mock
        from rhook_alpha.execution import ExecutionError
        self.assertTrue(EXAMPLE.exists());spec=importlib.util.spec_from_file_location('build12_example',EXAMPLE);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        fake=Mock();fake.run.return_value={'status':'EXECUTION_COMPLETED','runDirectory':'/new-run'}
        fake.verify.side_effect=ExecutionError('VERIFIER_STOP','Inspect retained verification evidence.')
        out=io.StringIO()
        with patch('rhook_alpha.execution.ExecutionSDK',return_value=fake),contextlib.redirect_stdout(out):
            code=module.main(['--home','/new-home','--prepared','/prepared','--execute','--operation','a'*64,'--evidence','/fresh-evidence','--local-owner','--mac-ready'])
        result=json.loads(out.getvalue());self.assertEqual(code,1)
        self.assertEqual(result['nativeExecution']['status'],'EXECUTION_COMPLETED');self.assertEqual(result['failedStage'],'READ_ONLY_VERIFICATION')
        fake.compare.assert_not_called()

if __name__=='__main__':unittest.main()
