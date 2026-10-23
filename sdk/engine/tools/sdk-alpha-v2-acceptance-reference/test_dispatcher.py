"""Exact dispatcher launch path + unchanged v2 guard; synthetic data only."""
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import dispatch_once as production
from staging import digest

HERE = Path(__file__).resolve().parent
SDK = HERE.parent/'rhook-developer-memory-profile-v2-01'


class DispatcherRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/private/tmp')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def spec(self, size=(64 << 20)+4096, bad_hash=False):
        source = self.root/'source.bin'
        with source.open('wb') as f:
            f.truncate(size)
        spec = self.root/'spec.json'
        spec.write_text(json.dumps({'inputs': [dict(name='worker', source=str(source),
            bytes=size, sha256='0'*64 if bad_hash else digest(source))]}))
        return spec, source

    def stage_cli(self, spec, destination):
        # Real production entry and its exact Popen/preexec path, not a substitute copy.
        return subprocess.run([sys.executable, str(HERE/'dispatch_once.py'), 'stage-only',
            '--spec', str(spec), '--destination', str(destination)],
            capture_output=True, text=True, timeout=35)

    def test_full_file_above_64_mib_stages_through_production_entry(self):
        spec, source = self.spec()
        target = self.root/'prepared'
        result = self.stage_cli(spec, target)
        self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
        self.assertEqual(json.loads(result.stdout)['status'], 'INPUTS_STAGED_NOT_AUTHORIZED_NOT_EXECUTED')
        self.assertEqual((target/'worker').stat().st_size, (64 << 20)+4096)
        self.assertEqual(digest(target/'worker'), digest(source))
        self.assertTrue((target/'READY.json').is_file())
        self.assertFalse(any(target.rglob('OPERATOR_CONSENT.json')))
        self.assertFalse(any(target.rglob('DISPATCH_STARTED.json')))

    def test_staging_hash_failure_is_stop_with_zero_native_and_no_ready(self):
        spec, _ = self.spec(100, bad_hash=True)
        target = self.root/'rejected'
        result = self.stage_cli(spec, target)
        self.assertNotEqual(result.returncode, 0)
        raw = json.loads(result.stdout)
        self.assertEqual(raw['status'], 'STAGING_STOP')
        self.assertEqual(raw['nativeInvocations'], dict(ACTUAL=0, BRANCH=0, B=0))
        self.assertFalse((target/'READY.json').exists())
        self.assertFalse(any(target.rglob('STARTED.json')))

    def test_unchanged_sdk_exact_copy_uses_production_caps_above_64_mib(self):
        # This is the actual SDK copy function that failed in the closed run.
        _, source = self.spec()
        harness = self.root/'copy-harness.py'
        harness.write_text('''import json,resource,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from sdk_alpha_v2.common import exact_copy
exact_copy(Path(sys.argv[2]),Path(sys.argv[3]),256<<20)
print(json.dumps({'status':'COPY_ONLY_PASS','fsize':resource.getrlimit(resource.RLIMIT_FSIZE),'ACTUAL':0,'BRANCH':0}))
''')
        target=self.root/'sdk-copy';out=self.root/'copy.stdout';err=self.root/'copy.stderr'
        with out.open('wb') as stdout,err.open('wb') as stderr:
            proc=production.spawn_trusted_cli([sys.executable,str(harness),str(SDK),str(source),str(target)],
                cwd=self.root,stdout=stdout,stderr=stderr)
            try: code=proc.wait(timeout=10)
            finally:
                if proc.poll() is None: os.killpg(proc.pid,9);proc.wait(timeout=1)
        self.assertEqual(code,0,err.read_text())
        self.assertEqual(json.loads(out.read_text())['fsize'],[256<<20,256<<20])
        self.assertEqual(digest(target),digest(source))
        self.assertEqual(target.stat().st_size,(64<<20)+4096)

    def test_used_staging_directory_is_not_retried(self):
        spec, _ = self.spec(100)
        target = self.root/'used'
        self.assertEqual(self.stage_cli(spec, target).returncode, 0)
        self.assertNotEqual(self.stage_cli(spec, target).returncode, 0)

    def test_symlink_input_rejected(self):
        spec, source = self.spec(100)
        linked = self.root/'link'; linked.symlink_to(source)
        raw = json.loads(spec.read_text()); raw['inputs'][0]['source'] = str(linked)
        spec.write_text(json.dumps(raw))
        self.assertNotEqual(self.stage_cli(spec, self.root/'rejected').returncode, 0)

    def test_no_fresh_approval_means_no_cli_or_run_creation(self):
        plan={'status':'SYNTHETIC_PROPOSAL_ONLY'}
        plan['planCommitment']=production.canonical(plan)
        path=self.root/'plan.json';path.write_text(json.dumps(plan))
        approval=self.root/'not-approved.json'
        approval.write_text(json.dumps(dict(approved=False,macReady=False,planCommitment=plan['planCommitment'])))
        with patch.object(production,'spawn_trusted_cli') as launch:
            with self.assertRaisesRegex(ValueError,'FRESH_EXACT_FOUNDER_APPROVAL_REQUIRED'):
                production.authenticate_plan(path,approval)
            launch.assert_not_called()
        self.assertFalse(any(self.root.rglob('DISPATCH_STARTED.json')))

    def test_original_or_snapshot_drift_is_rejected_before_consumption(self):
        spec, source = self.spec(100)
        target = self.root/'ready'
        self.assertEqual(self.stage_cli(spec, target).returncode, 0)
        plan = dict(preparedInputs=str(target), preparedReadySha256=digest(target/'READY.json'))
        production.verify_prepared_inputs(plan)
        source.write_bytes(b'x'*100)
        with self.assertRaisesRegex(ValueError, 'STAGED_OR_ORIGINAL_INPUT_DRIFT'):
            production.verify_prepared_inputs(plan)
        source.write_bytes(b'\0'*100)
        (target/'worker').chmod(0o600); (target/'worker').write_bytes(b'y'*100)
        with self.assertRaisesRegex(ValueError, 'STAGED_OR_ORIGINAL_INPUT_DRIFT'):
            production.verify_prepared_inputs(plan)

    def test_native_child_still_enforces_64_mib_inside_trusted_cli(self):
        # Python stub replaces the worker. No saved block, real sensor or EVM is used.
        fixture = self.root/'fixture'; (fixture/'runtime').mkdir(parents=True)
        (fixture/'artifacts').mkdir()
        worker = fixture/'artifacts/rhook-saved-pair'
        worker.write_text('#!'+sys.executable+'\n'+'''import errno,json,resource
soft,hard=resource.getrlimit(resource.RLIMIT_FSIZE)
try:
 with open('child-output.bin','wb',buffering=0) as f:
  for _ in range(65): f.write(b'x'*(1<<20))
except OSError as error:
 print(json.dumps(dict(soft=soft,hard=hard,errno=error.errno,cpu=resource.getrlimit(resource.RLIMIT_CPU)[0])))
else: raise SystemExit('Expected kernel file-size rejection')
''')
        worker.chmod(0o700)
        harness = self.root/'harness.py'
        harness.write_text('''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from sdk_alpha_v2.common import portable
root=Path(sys.argv[2]);g=portable.guards;g.ROOT=root
g.sample_owned=lambda proc:dict(pid=proc.pid,ppid=os.getpid(),pgid=proc.pid,executable='synthetic',rssBytes=1<<20)
result=g.monitored(b'{}',root/'runtime',portable.LIMITS)
print(json.dumps(result))
''')
        out=self.root/'harness.stdout';err=self.root/'harness.stderr'
        with out.open('wb') as stdout,err.open('wb') as stderr:
            proc=production.spawn_trusted_cli([sys.executable,str(harness),str(SDK),str(fixture)],
                cwd=self.root,stdout=stdout,stderr=stderr)
            try: code=proc.wait(timeout=10)
            finally:
                if proc.poll() is None: os.killpg(proc.pid,9);proc.wait(timeout=1)
        self.assertEqual(code,0,err.read_text())
        result=json.loads(out.read_text())
        raw=json.loads((fixture/'runtime/stdout.log').read_text())
        self.assertEqual((raw['soft'],raw['hard']),(64<<20,64<<20))
        self.assertEqual(raw['errno'],errno.EFBIG)
        self.assertEqual(raw['cpu'],120)
        self.assertEqual((fixture/'child-output.bin').stat().st_size,64<<20)
        self.assertTrue(result['workerReaped'])
        self.assertFalse((fixture/'runtime/NATIVE_COMPLETION.json').exists())

    def test_replay_failure_never_runs_verify_or_reports_workflow_pass(self):
        # Production orchestration, fake CLI outputs. No real SDK command is called.
        for code in (0,1):
            with self.subTest(code=code):
                cli=self.root/('fake-cli-'+str(code))
                cli.write_text('#!'+sys.executable+'\n'+'''import json,sys
name=sys.argv[1]
result={'doctor':{'status':'DOCTOR_PASS'},'prepare':{'status':'PREPARED_NATIVE_NOT_RUN'},'replay':{'terminal':'INTERRUPTED_UNVERIFIED','cause':'STAGING_FAILURE','nativeInvocations':{'ACTUAL':0,'BRANCH':0,'B':0}}}[name]
print(json.dumps(result))
sys.exit('''+str(code)+''' if name=='replay' else 0)
''');cli.chmod(0o700)
                archive=self.root/('archive-'+str(code));ws=self.root/('ws-'+str(code));ws.mkdir()
                approval=self.root/('approval-'+str(code));approval.write_text('{}')
                plan=dict(sourceCheckout=str(self.root),futureWorkspace=str(ws),archiveAfterOwnedWritersExit=str(archive),
                    planCommitment='SYNTHETIC',policySha256='SYNTHETIC',sourceCommitment='SYNTHETIC',
                    steps=[dict(step=i+1,command=[str(cli),name],requiredStatus=status) for i,(name,status) in enumerate([
                        ('doctor','DOCTOR_PASS'),('prepare','PREPARED_NATIVE_NOT_RUN'),('replay','DEVELOPER_PAIR03_REPLAY_PASS'),('verify','SAVED_DEVELOPER_RESULT_VERIFIED')])])
                with patch.object(production,'authenticate_plan',return_value=plan),patch.object(sys,'argv',[
                    'dispatch_once.py','acceptance','--plan','synthetic','--approval',str(approval)]),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(production.main(),1)
                saved=json.loads((archive/'WORKFLOW_RESULT.json').read_text())
                self.assertEqual(saved['terminal'],'STOP')
                self.assertEqual(saved['cause'],'REPLAY_FAILED')
                self.assertFalse((archive/'verify_DISPATCH.json').exists())


if __name__=='__main__':unittest.main()
