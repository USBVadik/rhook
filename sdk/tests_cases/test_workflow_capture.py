"""Nested limits are exercised with tiny Python children, never EVM execution."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from rhook_alpha.cases import native
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.scenario import api

NESTED = r'''
import json,resource,subprocess,sys
def child(cpu,size,files):
    def caps():
        resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE,(size,size))
        resource.setrlimit(resource.RLIMIT_NOFILE,(files,files))
    command=[sys.executable,'-I','-c','import json,resource;print(json.dumps([resource.getrlimit(x) for x in (resource.RLIMIT_CPU,resource.RLIMIT_FSIZE,resource.RLIMIT_NOFILE)]))']
    return json.loads(subprocess.check_output(command,preexec_fn=caps))
parent=[resource.getrlimit(x) for x in (resource.RLIMIT_CPU,resource.RLIMIT_FSIZE,resource.RLIMIT_NOFILE)]
print(json.dumps({'parent':parent,'helper':child(3,8<<20,64),'supervisor':child(120,64<<20,256)}))
'''


class WorkflowCapture(unittest.TestCase):
    def test_small_diagnostic_profile_reproduces_inherited_limit_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,out,err=native.capture([sys.executable,'-I','-c',NESTED],Path(tmp).resolve()/'capture',5)
            self.assertNotEqual(result['exitCode'],0)
            self.assertIn(b'Exception occurred in preexec_fn',err)
            self.assertTrue(result['ownedChildReaped'])

    def workflow(self):
        self.assertTrue(hasattr(native,'capture_workflow'),'workflow capture is not implemented')
        return native.capture_workflow

    def test_whole_workflow_admits_helper_and_native_sibling_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp).resolve()/'capture'
            result,out,err=self.workflow()([sys.executable,'-I','-c',NESTED],directory,5)
            self.assertEqual((result['exitCode'],result['stop'],err),(0,None,b''))
            values=json.loads(out)
            self.assertEqual(values['parent'],[[120,120],[67108864,67108864],[256,256]])
            self.assertEqual(values['helper'],[[3,3],[8388608,8388608],[64,64]])
            self.assertEqual(values['supervisor'],[[120,120],[67108864,67108864],[256,256]])
            self.assertTrue(result['ownedChildReaped'])
            self.assertEqual(json.loads((directory/'PROCESS.json').read_text())['cpuSecondsPerChild'],120)

    def test_timeout_reaps_only_owned_benign_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,_,_=self.workflow()([sys.executable,'-I','-c','import time;time.sleep(10)'],Path(tmp).resolve()/'capture',0.15)
            self.assertEqual(result['stop'],'WALL_TIME_LIMIT')
            self.assertTrue(result['ownedChildReaped'])
            self.assertTrue(result['ownedProcessGroupKilled'])

    def test_stdout_overflow_stays_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,out,_=self.workflow()([sys.executable,'-I','-c','import os;os.write(1,b"x"*131072)'],Path(tmp).resolve()/'capture',5,1024,1024)
            self.assertLessEqual(len(out),1024)
            self.assertIsNotNone(result['stop'])
            self.assertTrue(result['ownedChildReaped'])

    def test_excessive_deadline_is_rejected_before_process_or_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp).resolve()/'capture'
            with self.assertRaisesRegex(ValueError,'WORKFLOW_CAPTURE_LIMIT'):
                self.workflow()([sys.executable,'-I','-c','print(1)'],target,181)
            self.assertFalse(target.exists())

    def test_timeout_cleans_nested_sdk_helper_session(self):
        self.nested_timeout('helper')

    def test_timeout_cleans_nested_sdk_supervisor_worker(self):
        self.nested_timeout('worker')

    def test_early_cli_exit_cleans_remaining_sdk_helper(self):
        self.nested_timeout('early-exit')

    def nested_timeout(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();pid_file=root/'nested.json'
            leaf='import os,json,time;from pathlib import Path;Path('+repr(str(pid_file))+').write_text(json.dumps([os.getpid(),os.getpgrp()]));time.sleep(10)'
            code='import sys;from pathlib import Path;sys.path.insert(0,'+repr(str(native.SDK_ROOT))+');from rhook_alpha.cases import native;root=Path('+repr(str(root))+');'
            if mode in ('helper','early-exit'):
                call='native.capture([sys.executable,"-I","-c",'+repr(leaf)+'],root/"helper",10)'
                if mode=='early-exit':
                    code+='import threading,time,os;threading.Thread(target=lambda:'+call+',daemon=True).start();'
                    code+='\nwhile not (root/"nested.json").exists():time.sleep(.01)\nos._exit(0)'
                else:code+=call
            else:
                worker=root/'artifacts/rhook-saved-pair';worker.parent.mkdir()
                worker.write_text('#!'+sys.executable+' -I\n'+leaf+'\n');worker.chmod(0o700)
                (root/'runtime').mkdir()
                code+='native.guards();from case_sdk.common import portable;portable.guards.ROOT=root;portable.guards.sample_owned=lambda proc:None;portable.guards.monitored(b"{}",root/"runtime",portable.LIMITS)'
            pid=None
            try:
                result,_,_=self.workflow()([sys.executable,'-I','-B','-c',code],root/'outer',0.8)
                self.assertTrue(pid_file.exists(),'nested benign process did not start')
                pid,pgid=json.loads(pid_file.read_text())
                owner=json.loads((root/'outer/PROCESS.json').read_text())['pid']
                self.assertEqual(pgid,owner,'SDK descendant escaped owned workflow group')
                self.assertTrue(result.get('workflowGroupGone'),'whole workflow cleanup is unconfirmed')
                self.assertEqual(result['stop'],'WORKFLOW_DESCENDANTS_REMAINED' if mode=='early-exit' else 'WALL_TIME_LIMIT')
            finally:
                if pid is None and pid_file.exists():pid=json.loads(pid_file.read_text())[0]
                if pid is not None:
                    try:os.kill(pid,9)
                    except ProcessLookupError:pass


class HelperEvidence(unittest.TestCase):
    def test_unmanaged_v3_run_stops_before_loading_state_or_issuing_authority(self):
        with patch('sys.platform','darwin'),patch('platform.machine',return_value='arm64'),\
             patch.object(api,'_input',side_effect=AssertionError('must not read state')):
            with self.assertRaisesRegex(ValueError,'OWNED_WORKFLOW_CONTEXT_REQUIRED'):
                api.run(None,'unused',local_owner=True,mac_ready=True,host_profile='macos-host-admission-v3')

    def test_failed_helper_diagnostics_survive_temporary_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk=CaseSDK(root/'home');sdk.registry._prepare()
            helper=root/'helper'
            helper.write_text('#!'+sys.executable+' -I\nimport sys\nprint("saved stdout")\nprint("saved stderr",file=sys.stderr)\nsys.exit(7)\n')
            helper.chmod(0o700)
            with patch.object(api,'runtime',return_value={'files':{'worker':{'path':str(helper)}}}):
                with self.assertRaisesRegex(ValueError,'SCENARIO_HELPER_STOP'):
                    api._helper(sdk,['--authenticate','unused'])
            directories=list((sdk.home/'scenarios/helper-failures').glob('*'))
            self.assertEqual(len(directories),1,'failed capture was discarded with TemporaryDirectory')
            self.assertEqual((directories[0]/'stdout.bin').read_bytes(),b'saved stdout\n')
            self.assertEqual((directories[0]/'stderr.bin').read_bytes(),b'saved stderr\n')
            result=json.loads((directories[0]/'RESULT.json').read_text())
            self.assertEqual(result['exitCode'],7)
            self.assertTrue(result['ownedChildReaped'])


if __name__=='__main__':unittest.main()
