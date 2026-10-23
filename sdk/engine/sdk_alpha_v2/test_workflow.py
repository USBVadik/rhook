"""No real host readings or historical package/EVM in these workflow tests."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sdk_alpha import common as old_common
from sdk_alpha import resources as old_resources
from sdk_alpha import kit as old_kit
from sdk_alpha_v2 import common,resources,kit,build
from sdk_alpha_v2 import __main__ as cli
from sdk_alpha_v2._frozen import source,BASE_COMMIT
from sdk_alpha_v2.test_policy import sample


class V2WorkflowTests(unittest.TestCase):
    def fixture(self,root):
        package=root/'package';package.write_bytes(b'synthetic input')
        worker=root/'worker';worker.write_bytes(b'not an engine')
        sensor=root/'sensor';sensor.write_bytes(b'not a sensor')
        record_path=root/'build.json';record_path.write_text('{}')
        record=dict(worker=str(worker),workerSha256=common.sha(worker),sensor=str(sensor),sensorSha256=common.sha(sensor))
        return package,record_path,record

    def test_v1_source_tree_is_byte_identical_to_checkpoint(self):
        rows=subprocess.check_output(['git','ls-tree','-rz',BASE_COMMIT],cwd=common.REPO).split(b'\0');count=0
        for row in rows:
            if not row:continue
            metadata,name=row.split(b'\t',1)
            expected=subprocess.check_output(['git','cat-file','blob',metadata.split()[2].decode()],cwd=common.REPO)
            self.assertEqual((common.REPO/name.decode()).read_bytes(),expected,name)
            count+=1
        self.assertEqual(count,113)

    def test_v1_globals_limits_and_source_closure_are_not_modified(self):
        self.assertEqual(old_resources.POLICY['profile'],'developer-darwin-arm64/1')
        self.assertEqual(old_resources.POLICY['workerRssBytes'],4<<30)
        self.assertEqual(old_common.portable.LIMITS['workerSampledRssBytes'],4<<30)
        self.assertEqual(common.portable.LIMITS['workerSampledRssBytes'],1<<30)
        self.assertIsNot(common.portable.guards,old_common.portable.guards)
        self.assertIsNot(kit._operator_mutex,old_kit._operator_mutex)
        self.assertFalse(any(p.startswith('sdk_alpha_v2/') or p=='rhook-v2' for p in old_common.sources()))
        self.assertTrue(any(p.startswith('sdk_alpha_v2/') for p in common.sources()))

    def test_frozen_loader_rejects_unreviewed_paths_bad_hashes_and_edit_drift(self):
        with self.assertRaisesRegex(ValueError,'UNREVIEWED'):source('runtime/anything.py')
        with self.assertRaisesRegex(ValueError,'BOUNDARY_DRIFT'):
            source('sdk_alpha/kit.py',[('not present','x',1)])
        with patch.object(Path,'read_bytes',return_value=b'arbitrary replacement'):
            with self.assertRaisesRegex(ValueError,'SOURCE_DRIFT'):source('sdk_alpha/kit.py')

    def test_policy_and_help_do_not_start_subprocesses(self):
        with patch.object(subprocess,'Popen',side_effect=AssertionError('No child permitted')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['policy']),0)

    def test_v1_workspace_is_rejected_before_readiness(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp);(root/'KIT.json').write_text(json.dumps(dict(format='rhook/developer-kit/1',profile='developer-darwin-arm64/1')))
            with patch.object(kit,'admission') as sensor:
                with self.assertRaisesRegex(ValueError,'KIT_PROFILE'):kit.doctor(root,'synthetic')
                sensor.assert_not_called()

    def test_preparation_has_v2_limits_domain_and_no_execution(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp);package,record_path,record=self.fixture(root)
            with patch.object(kit,'verify_build',return_value=record), \
                 patch.object(common.portable,'validate_package',return_value={'packageSha256':common.sha(package)}), \
                 patch.object(kit,'admission') as sensor,patch.object(kit,'supervise') as worker:
                out=root/'kit';kit.initialize(out,package,record_path)
                binding=kit.prepare(out,'synthetic')
                self.assertEqual(binding['profile'],'developer-darwin-arm64/2')
                self.assertEqual(binding['limits']['workerSampledRssBytes'],1<<30)
                self.assertEqual(binding['limits']['GOMEMLIMIT_advisoryBytes'],512<<20)
                consent=json.loads(kit.operator_consent(binding,True,True,1000))
                self.assertEqual(consent['domain'],'DEVELOPER_SAVED_PAIR03_V2')
                self.assertEqual(consent['maximumInvocations'],{'ACTUAL':1,'BRANCH':1,'B':0})
                self.assertEqual(consent['RPC'],0);self.assertEqual(consent['WSS'],0)
                self.assertFalse((out/'runs/synthetic').exists())
                sensor.assert_not_called();worker.assert_not_called()

    def test_admission_failure_has_known_zero_counts_without_worker_dispatch(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp);package,record_path,record=self.fixture(root)
            with patch.object(kit,'verify_build',return_value=record), \
                 patch.object(common.portable,'validate_package',return_value={'packageSha256':common.sha(package)}), \
                 patch.object(kit,'admission',side_effect=ValueError('INSUFFICIENT_FREE_HEADROOM')), \
                 patch.object(kit,'supervise') as worker:
                out=root/'kit';kit.initialize(out,package,record_path)
                result=kit.replay(out,'synthetic',confirm_native=True,mac_ready=True)
                self.assertEqual(result['terminal'],'HOST_STOP')
                self.assertEqual(result['nativeInvocations'],{'ACTUAL':0,'BRANCH':0,'B':0})
                self.assertFalse(result['workerDispatchAttempted'])
                worker.assert_not_called()
                with self.assertRaisesRegex(ValueError,'OUTPUT_ALREADY_USED'):
                    kit.replay(out,'synthetic',confirm_native=True,mac_ready=True)

    def test_before_dispatch_interrupt_and_after_dispatch_incomplete_cleanup(self):
        for after in [False,True]:
            with self.subTest(after=after),tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
                root=Path(tmp);package,record_path,record=self.fixture(root)
                with patch.object(kit,'verify_build',return_value=record), \
                     patch.object(common.portable,'validate_package',return_value={'packageSha256':common.sha(package)}), \
                     patch.object(kit,'admission',return_value=({'status':'PASS'},[sample(),sample(2)])) as host, \
                     patch.object(kit,'supervise',side_effect=RuntimeError('REAP_UNCONFIRMED')):
                    if not after:host.side_effect=KeyboardInterrupt('OPERATOR_SIGNAL_15')
                    out=root/'kit';kit.initialize(out,package,record_path)
                    result=kit.replay(out,'synthetic',confirm_native=True,mac_ready=True)
                    self.assertEqual(result['terminal'],'INTERRUPTED_UNVERIFIED')
                    self.assertEqual(result['workerDispatchAttempted'],after)
                    self.assertEqual(result['nativeInvocations'],None if after else {'ACTUAL':0,'BRANCH':0,'B':0})
                    self.assertEqual((out/'runs/synthetic/MANIFEST.json').exists(),not after)

    def test_existing_cpu_wall_output_storage_limits_are_preserved(self):
        for key,value in old_common.portable.LIMITS.items():
            if key in ['workerSampledRssBytes','GOMEMLIMIT_advisoryBytes']:continue
            self.assertEqual(common.portable.LIMITS[key],value,key)

    def test_generated_go_admission_is_distinct_and_pair_engine_unchanged(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp);module=root/'v2/pair';build.stage(root,module)
            self.assertEqual((module/'pair.go').read_bytes(),(common.REPO/'native/saved-pair/pair.go').read_bytes())
            main=(module/'main.go').read_text();profile=(module/'developer_profile.go').read_text()
            self.assertIn('DEVELOPER_SAVED_PAIR03_V2',main)
            self.assertIn('developer-darwin-arm64/2',profile)
            self.assertIn('ORIGINAL_RULES_ACCOUNT_CODE_FULL_WORD_REQUIRED',main)
            self.assertNotIn('TestPinnedSavedPackageAdmissionAndFreshNilSourceBridges',(module/'synthetic_pair_test.go').read_text())


if __name__=='__main__':unittest.main()
