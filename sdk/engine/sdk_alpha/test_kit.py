import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sdk_alpha import kit
from sdk_alpha import __main__ as cli
from sdk_alpha.build import DOMAIN, POLICY_HASH, overlay, stage
from sdk_alpha.common import REPO, sources, sha, store, portable
from sdk_alpha.resources import POLICY
from sdk_alpha.test_resources import sample


class KitTests(unittest.TestCase):
    def test_run_names_cannot_traverse_or_inject_options(self):
        for name in ['../x', '/x', 'A', '-x', 'a/b', '', 'x'*65]:
            with self.assertRaises(ValueError): kit.identifier(name)

    def test_no_confirmation_cannot_even_touch_workspace_or_sensor(self):
        for flags in [{}, {'confirm_native': True}, {'mac_ready': True}]:
            with patch.object(kit, 'workspace') as workspace, patch.object(kit, 'admission') as sensor:
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_NATIVE'): kit.replay('/nonexistent', 'x', **flags)
                workspace.assert_not_called(); sensor.assert_not_called()

    def test_operator_consent_is_new_domain_and_never_claims_founder_science(self):
        b = dict(operationCommitment='op', binarySha256='bin', packagePath='/input', outputPath='/out',
                 executionContext='local-terminal', profile=POLICY['profile'], policySha256=POLICY_HASH,
                 maximumInvocations=POLICY['maximumInvocations'], RPC=0, WSS=0)
        a = json.loads(kit.operator_consent(b, True, True, 1000))
        self.assertEqual(a['domain'], DOMAIN)
        self.assertTrue(a['operatorApproved'])
        self.assertNotIn('founderApproved', a)
        self.assertEqual(a['expiresUnix']-a['notBeforeUnix'], 300)

    def test_overlay_rejects_upstream_drift(self):
        with self.assertRaisesRegex(ValueError, 'OVERLAY_BOUNDARY'): overlay('package main')

    def test_staging_preserves_engine_and_removes_historical_test(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root = Path(tmp); module = root/'developer/pair'
            stage(root, module)
            self.assertEqual((module/'pair.go').read_bytes(), (REPO/'native/saved-pair/pair.go').read_bytes())
            self.assertNotIn('TestPinnedSavedPackageAdmissionAndFreshNilSourceBridges', (module/'synthetic_pair_test.go').read_text())
            text = (module/'main.go').read_text()
            self.assertIn('operatorApproved', text)
            self.assertNotIn('founderApproved', text)
            self.assertIn('developerPolicyHash', text)
            self.assertNotIn('=> /', (module/'go.mod').read_text())

    def test_policy_command_has_no_resources_or_native_side_effect(self):
        with patch.object(kit, 'admission') as host, patch.object(kit, 'supervise') as worker, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['policy']), 0)
            host.assert_not_called(); worker.assert_not_called()

    def test_setup_rejects_bad_package_before_build_or_network(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root = Path(tmp); package = root/'package.json'; package.write_text('{}')
            with patch.object(cli, 'compile_developer') as build:
                with self.assertRaisesRegex(ValueError, 'PACKAGE_SHA256'):
                    cli.main(['setup', '--workspace', str(root/'kit'), '--package', str(package), '--build-root', str(root/'build'), '--bootstrap'])
                build.assert_not_called(); self.assertFalse((root/'kit').exists())

    def test_initialize_and_prepare_do_not_sample_or_run_and_cannot_reuse(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); package=root/'package'; package.write_bytes(b'input')
            worker=root/'worker'; worker.write_bytes(b'not a native executable')
            sensor=root/'sensor'; sensor.write_bytes(b'not a sensor')
            record_path=root/'build.json'; record_path.write_text('{}')
            record={'worker':str(worker),'workerSha256':sha(worker),'sensor':str(sensor),'sensorSha256':sha(sensor)}
            with patch.object(kit, 'verify_build', return_value=record), \
                 patch.object(portable, 'validate_package', return_value={'packageSha256':sha(package)}), \
                 patch.object(kit, 'admission') as host, patch.object(kit, 'supervise') as run:
                path=root/'kit'; kit.initialize(path, package, record_path)
                b=kit.prepare(path, 'first')
                self.assertEqual(b['sourceFiles'], sources())
                self.assertEqual((path/'inputs/BLOCK_PACKAGE.json').read_bytes(), b'input')
                self.assertFalse((path/'runs/first').exists())
                with self.assertRaisesRegex(ValueError, 'OUTPUT_ALREADY_USED'): kit.prepare(path, 'first')
                with self.assertRaisesRegex(ValueError, 'OUTPUT_ALREADY_USED'): kit.initialize(path, package, record_path)
                host.assert_not_called(); run.assert_not_called()

    def fixture(self, root):
        package=root/'package'; package.write_bytes(b'input')
        worker=root/'worker'; worker.write_bytes(b'not a native executable')
        sensor=root/'sensor'; sensor.write_bytes(b'not a sensor')
        record_path=root/'build.json'; record_path.write_text('{}')
        record={'worker':str(worker),'workerSha256':sha(worker),'sensor':str(sensor),'sensorSha256':sha(sensor)}
        return package, record_path, record

    def test_host_failure_records_stop_zero_counts_and_never_dispatches(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); package, record_path, record=self.fixture(root)
            with patch.object(kit, 'verify_build', return_value=record), \
                 patch.object(portable, 'validate_package', return_value={'packageSha256':sha(package)}), \
                 patch.object(kit, 'admission', side_effect=ValueError('INSUFFICIENT_FREE_HEADROOM')), \
                 patch.object(kit, 'supervise') as run:
                path=root/'kit'; kit.initialize(path, package, record_path)
                result=kit.replay(path, 'first', confirm_native=True, mac_ready=True)
                self.assertEqual(result['terminal'], 'HOST_STOP')
                self.assertEqual(result['nativeInvocations'], {'ACTUAL':0,'BRANCH':0,'B':0})
                self.assertTrue((path/'runs/first/MANIFEST.json').is_file())
                run.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'OUTPUT_ALREADY_USED'):
                    kit.replay(path, 'first', confirm_native=True, mac_ready=True)

    def test_unconfirmed_worker_cleanup_never_gets_a_manifest(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); package, record_path, record=self.fixture(root)
            with patch.object(kit, 'verify_build', return_value=record), \
                 patch.object(portable, 'validate_package', return_value={'packageSha256':sha(package)}), \
                 patch.object(kit, 'admission', return_value=({'status':'PASS'},[sample(),sample(2)])), \
                 patch.object(kit, 'supervise', side_effect=RuntimeError('REAP_UNCONFIRMED')):
                path=root/'kit'; kit.initialize(path, package, record_path)
                result=kit.replay(path, 'first', confirm_native=True, mac_ready=True)
                self.assertEqual(result['terminal'], 'INTERRUPTED_UNVERIFIED')
                self.assertIsNone(result['nativeInvocations'])
                self.assertFalse((path/'runs/first/MANIFEST.json').exists())

    def test_manifest_detects_extra_file_and_drift(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); (root/'data').write_bytes(b'original')
            manifest=kit.file_manifest(root)
            store(root/'MANIFEST.json', {'files':manifest})
            self.assertEqual(kit.file_manifest(root), manifest)
            (root/'data').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): kit.verify_run(root)
            (root/'data').write_bytes(b'original'); (root/'extra').write_bytes(b'new')
            with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): kit.verify_run(root)

    def test_verify_does_not_promote_host_stop_to_success(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); (root/'runtime').mkdir()
            store(root/'runtime/FINAL_RESULT.json', {'profile':POLICY['profile'],'policySha256':POLICY_HASH,'terminal':'HOST_STOP'})
            store(root/'MANIFEST.json', {'files':kit.file_manifest(root)})
            with self.assertRaisesRegex(ValueError, 'RUN_NOT_SUCCESSFUL'): kit.verify_run(root)

    def test_old_scientific_files_equal_base_git_tree(self):
        import subprocess
        files=subprocess.run(['git','diff','7c828cb99a16f8461f357b5726410f6b8463aa67','--name-only','--','native','supervisor','repro'],
                             cwd=REPO, check=True, capture_output=True, text=True).stdout
        self.assertEqual(files, '')

    def test_operator_lock_rejects_api_overlap_and_releases_on_error(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); (root/'KIT.json').write_text('{}')
            with kit.operator_lock(root):
                with self.assertRaisesRegex(ValueError, 'ALREADY_ACTIVE'):
                    with kit.operator_lock(root): pass
            with self.assertRaises(RuntimeError):
                with kit.operator_lock(root): raise RuntimeError('controlled failure')
            with kit.operator_lock(root): pass

    def test_pre_admission_sigterm_unwinds_and_restores_handler_and_lock(self):
        import signal
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); (root/'KIT.json').write_text('{}')
            original=signal.getsignal(signal.SIGTERM)
            with self.assertRaisesRegex(KeyboardInterrupt, 'OPERATOR_SIGNAL_15'):
                with kit.operator_lock(root):
                    handler=signal.getsignal(signal.SIGTERM)
                    self.assertTrue(callable(handler), 'SIGTERM must unwind bounded capture, not abruptly exit Python')
                    handler(signal.SIGTERM,None)
            self.assertEqual(signal.getsignal(signal.SIGTERM),original)
            with kit.operator_lock(root): pass

    def test_interruption_before_dispatch_preserves_known_zero_native_counts(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); package,record_path,record=self.fixture(root)
            with patch.object(kit,'verify_build',return_value=record), \
                 patch.object(portable,'validate_package',return_value={'packageSha256':sha(package)}), \
                 patch.object(kit,'admission',side_effect=KeyboardInterrupt('OPERATOR_SIGNAL_15')), \
                 patch.object(kit,'supervise') as worker:
                path=root/'kit';kit.initialize(path,package,record_path)
                result=kit.replay(path,'interrupted',confirm_native=True,mac_ready=True)
                self.assertEqual(result['terminal'],'INTERRUPTED_UNVERIFIED')
                self.assertEqual(result['nativeInvocations'],{'ACTUAL':0,'BRANCH':0,'B':0})
                self.assertFalse(result['workerDispatchAttempted'])
                worker.assert_not_called()

    def test_interruption_after_dispatch_is_not_a_pre_admission_host_stop(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp);package,record_path,record=self.fixture(root)
            measured=dict(stop='EXTERNAL_SIGNAL',exitCode=-9,workerReaped=True,resourcesReliable=True)
            def interrupted(raw,out,sensor,previous):
                store(out/'runtime/PROCESS_COMPLETION.json',measured)
                return measured
            with patch.object(kit,'verify_build',return_value=record), \
                 patch.object(portable,'validate_package',return_value={'packageSha256':sha(package)}), \
                 patch.object(kit,'admission',return_value=({'status':'PASS'},[sample(),sample(2)])), \
                 patch.object(kit,'supervise',side_effect=interrupted):
                path=root/'kit';kit.initialize(path,package,record_path)
                result=kit.replay(path,'interrupted',confirm_native=True,mac_ready=True)
                self.assertEqual(result['terminal'],'INTERRUPTED_UNVERIFIED')
                self.assertEqual(result['cause'],'EXTERNAL_SIGNAL')
                self.assertTrue(result['workerDispatchAttempted'])
                self.assertIsNone(result['nativeInvocations'])

    def test_only_confirmed_exit_can_relax_vanished_ps_row(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            runtime=Path(tmp); proc=Mock(pid=123)
            proc.poll.return_value=0
            sensor=Mock(); original=Mock(side_effect=AssertionError('row vanished'))
            self.assertIsNone(kit.sample_developer(proc,original,sensor,runtime))
            sensor.poll.assert_not_called()
            proc.poll.return_value=None
            with self.assertRaises(AssertionError): kit.sample_developer(proc,original,sensor,runtime)
            self.assertTrue((runtime/'WORKER_OBSERVER_STOP.json').is_file())

    def test_workspace_cannot_put_input_or_runtime_in_source_tree(self):
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_SOURCE_CHECKOUT'):
            kit.initialize(REPO/'forbidden-kit', '/not-read', '/not-read')
        self.assertFalse((REPO/'forbidden-kit').exists())

    def test_nonregular_lock_is_rejected_without_blocking(self):
        import os
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); (root/'KIT.json').write_text('{}'); os.mkfifo(root/'.OPERATOR_LOCK')
            with self.assertRaisesRegex(ValueError, 'REGULAR_OPERATOR_LOCK'):
                with kit.operator_lock(root): pass

    def test_diagnostic_surfaces_rejected_sample_without_new_measurements(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp);(root/'host/sample-0').mkdir(parents=True)
            store(root/'RESULT.json',dict(status='HOST_STOP',profile=POLICY['profile'],policySha256=POLICY_HASH,cause='MEMORY_PRESSURE'))
            raw=sample(free=1);raw['pressureBefore']=raw['pressureAfter']=2
            (root/'host/sample-0/stdout.bin').write_text(json.dumps(raw))
            with patch.object(kit,'admission') as sensor,patch.object(kit,'supervise') as worker:
                result=kit.diagnostic(root)
                self.assertEqual(result['observed'][0]['freeMiB'],1024)
                self.assertEqual(result['observed'][0]['pressureAfter'],2)
                self.assertEqual(result['newMeasurements'],0)
                sensor.assert_not_called();worker.assert_not_called()

    def test_saved_result_verification_checks_consent_link_and_raw_sensor_records(self):
        # Pure fabricated fixture; baseline checker is mocked, no historical
        # package or real execution record is opened by this test.
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp)
            for name in ['runtime/HOST', 'runtime/HOST_RUNTIME', 'proposal', 'inputs', 'artifacts']:
                (root/name).mkdir(parents=True,exist_ok=True)
            for name in ['artifacts/rhook-saved-pair','artifacts/rhook-host-sensor','inputs/BLOCK_PACKAGE.json']:
                (root/name).write_bytes(b'fabricated fixture')
            binding=dict(profile=POLICY['profile'],policySha256=POLICY_HASH,resourcePolicy=POLICY,
                limits=portable.LIMITS,binarySha256=sha(root/'artifacts/rhook-saved-pair'),
                sensorSha256=sha(root/'artifacts/rhook-host-sensor'),packageSha256=sha(root/'inputs/BLOCK_PACKAGE.json'),
                packagePath='/fixture/input',outputPath=str(root),executionContext='local-terminal',
                maximumInvocations=POLICY['maximumInvocations'],RPC=0,WSS=0)
            binding['operationCommitment']=kit.commitment(binding)
            store(root/'proposal/AUTHORIZATION_BINDINGS.json',binding)
            raw=kit.operator_consent(binding,True,True,1000)
            (root/'runtime/OPERATOR_CONSENT.json').write_bytes(raw)
            store(root/'runtime/STARTED.json',dict(operationCommitment=binding['operationCommitment'],
                  authoritySha256=sha(root/'runtime/OPERATOR_CONSENT.json')))
            measured=dict(stop=None,workerReaped=True,resourcesReliable=True,exitCode=0,
                          wallSeconds=1,workerAndObserverCpuSeconds=0.1,sampledPeakWorkerRSS=1024)
            store(root/'runtime/PROCESS_COMPLETION.json',measured)
            store(root/'runtime/NATIVE_COMPLETION.json',dict(operationCommitment=binding['operationCommitment'],
                  result=dict(nativeInvocations=POLICY['maximumInvocations'],canonicalActualValid=True)))
            samples=[sample(),sample(2)]
            from sdk_alpha.resources import assess
            store(root/'runtime/HOST/SAMPLES.json',samples)
            store(root/'runtime/HOST_ADMISSION.json',dict(accepted=True,profile=POLICY['profile'],
                  policySha256=POLICY_HASH,decision=assess(samples)))
            for folder,value in [('HOST/sample-0',samples[0]),('HOST/sample-1',samples[1]),('HOST_RUNTIME/0',sample(3))]:
                p=root/'runtime'/folder;p.mkdir()
                store(p/'RESULT.json',dict(exitCode=0,stop=None,ownedChildReaped=True,truncated={'stdout':False,'stderr':False}))
                (p/'stdout.bin').write_text(json.dumps(value));(p/'stderr.bin').write_bytes(b'')
            compared=dict(status='PASS',worlds={'ACTUAL':True,'BRANCH':True})
            final=dict(profile=POLICY['profile'],policySha256=POLICY_HASH,terminal='DEVELOPER_PAIR03_REPLAY_PASS',
                       operationCommitment=binding['operationCommitment'],baselineComparison=compared,
                       resources=measured,elapsedSeconds=3,nativeInvocations=POLICY['maximumInvocations'])
            store(root/'runtime/FINAL_RESULT.json',final)
            def seal(): (root/'MANIFEST.json').write_text(json.dumps({'files':kit.file_manifest(root)}))
            seal()
            with patch.object(portable,'compare_baseline',return_value=compared):
                self.assertEqual(kit.verify_run(root)['status'],'SAVED_DEVELOPER_RESULT_VERIFIED')
                started=json.loads((root/'runtime/STARTED.json').read_text());started['authoritySha256']='wrong'
                (root/'runtime/STARTED.json').write_text(json.dumps(started));seal()
                with self.assertRaisesRegex(ValueError,'CONSENT_LINK'): kit.verify_run(root)
                started['authoritySha256']=sha(root/'runtime/OPERATOR_CONSENT.json')
                (root/'runtime/STARTED.json').write_text(json.dumps(started))
                value=sample(3);value['pressureAfter']=2
                (root/'runtime/HOST_RUNTIME/0/stdout.bin').write_text(json.dumps(value));seal()
                with self.assertRaisesRegex(ValueError,'PRESSURE'): kit.verify_run(root)


if __name__ == '__main__': unittest.main()
