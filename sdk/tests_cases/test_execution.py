"""Developer API tests. Synthetic input is never represented as MPT/EVM validated."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from developer.files import canonical,digest,save
from rhook_alpha.cases.scenario import api
SDK=Path(__file__).resolve().parents[1]
from synthetic_scenario import metadata
META=metadata()  # Public source-only fixture, not an accepted native record.


def fixture():
    p=json.loads((api.HERE/'native/profile.json').read_text());m=META;s=m['scenario'];cp=m['checkpoint']
    a=dict(nonce=0,gas=10000000,gasPriceWei='1000000000',amountInWei='1000000000000000',minimumOutputBaseUnits='1',sqrtPriceLimitX96='4295128740',deadline=s['environment']['l2Timestamp']+300,signedTransaction='0xdead')
    a['id']=digest(b'rhook/hookr-scenario/0.1/action\n'+canonical(a))
    v=dict(schema='rhook/hookr-scenario/0.1',origin=dict(kind='AUTHENTICATED_CHECKPOINT_SCENARIO',capsuleId=digest(b'rhook/scenario-checkpoint/0.1\n'+canonical(dict(checkpoint=cp,intent=dict(schema='rhook/on-demand-hookr-intent/0.1',poolId=p['poolId'],lpBps=50))))),checkpoint=cp,
           parent=dict(hash=cp['blockHash'],stateRoot=cp['stateRoot'],number=hex(cp['blockNumber']),timestamp=hex(m['checkpointTimestamp']),miner=s['environment']['poster'],baseFeePerGas='0x1'),chainConfig='0x01',inventory=dict(nodes=['0x01'],codes=['0x02']),
           releaseManifestSha256=digest(b'rhook/hookr-scenario/0.1/release\n'+canonical(p['manifest'])),poolId=p['poolId'],configurations=s['configurations'],commonSetup=s['commonSetup'],actions=[a],environment=s['environment'],engine=dict(sourceSha256='c8712d12e59299524431db239134ea7fbf7124d30d441b289d69d5b8ab5a4453',binarySha256=m['source']['workerSha256'],policySha256=api.POLICY_SHA),limits=dict(nativeWallSeconds=120,nativeCPUSeconds=120,workerRSSBytes=1<<30,stageWallSeconds=140,workflowWallSeconds=180,outputBytes=64<<20,rpc=0,worlds=2))
    v['scenarioCommitment']=digest(b'rhook/hookr-scenario/0.1\n'+canonical(v));return v


class ExecutionInterface(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('rhook_alpha.execution'),'developer ExecutionSDK missing')
        return __import__('rhook_alpha.execution',fromlist=['ExecutionSDK'])

    def setup_input(self,root,change=None):
        v=fixture()
        if change:change(v);v.pop('scenarioCommitment');v['scenarioCommitment']=digest(b'rhook/hookr-scenario/0.1\n'+canonical(v))
        p=root/'SCENARIO.json';p.write_bytes(canonical(v)+b'\n');return p,hashlib.sha256(p.read_bytes()).hexdigest()

    def test_configure_and_capabilities_need_no_runtime_process_or_home(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();home=root/'home';sdk=m.ExecutionSDK(home)
            with patch('subprocess.Popen',side_effect=AssertionError('no process during planning')):
                cfg=sdk.configure(lp_bps=50,checkpoint=META['checkpoint']);cap=sdk.capabilities()
            self.assertEqual(cfg['lpBps'],50);self.assertFalse(cfg['executionAuthorized']);self.assertFalse(cap['nativeExecutionReady'])
            self.assertTrue(cap['recordedEvidenceVerifier']['available']);self.assertIn('NATIVE_RUNTIME_MISSING',[v['code'] for v in cap['missing']]);self.assertFalse(home.exists())
            self.assertEqual(sdk.profiles()[0]['poolId'],META['scenario']['poolId'])

    def test_unsupported_profile_chain_transaction_and_lp_are_explicit(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            sdk=m.ExecutionSDK(Path(t).resolve()/'home')
            for options,code in [({'profile':'arbitrary-pool'},'UNSUPPORTED_PROFILE'),({'lp_bps':100},'LP_BPS_0_TO_99_REQUIRED'),({'lp_bps':True},'LP_BPS_0_TO_99_REQUIRED'),({'checkpoint':dict(META['checkpoint'],chainId=1)},'UNSUPPORTED_CHAIN'),({'transaction':{'amountInWei':'1','gas':10000000,'fundingWei':'1000000000000000000'}},'UNSUPPORTED_TRANSACTION')]:
                with self.assertRaises(m.ExecutionError) as e:sdk.configure(**options)
                self.assertEqual(e.exception.code,code);self.assertTrue(e.exception.next_step)

    def test_prepare_imports_without_old_home_or_grant_and_preserves_source(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();src,pin=self.setup_input(root);raw=src.read_bytes();sdk=m.ExecutionSDK(root/'new-home');cfg=sdk.configure(checkpoint=META['checkpoint']);out=root/'prepared'
            with patch.object(api,'runtime',side_effect=AssertionError('prepare must be runtime-free')):result=sdk.prepare(cfg,src,expected_sha256=pin,output=out)
            self.assertEqual(result['status'],'EXECUTION_PREPARED');self.assertEqual(result['authentication'],'PENDING_NATIVE_ADMISSION');self.assertEqual(result['witnessClosure'],'NOT_EVALUATED');self.assertEqual(result['nativeExecutions'],0)
            self.assertEqual(src.read_bytes(),raw);self.assertEqual(api._input(sdk._sdk(),out)[3],fixture());self.assertFalse((sdk.home/'scenarios/consents').exists())

    def test_changed_intervention_derives_only_variant_and_commitments(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            r=Path(t).resolve();src,pin=self.setup_input(r);sdk=m.ExecutionSDK(r/'home');result=sdk.prepare(sdk.configure(lp_bps=49),src,expected_sha256=pin,output=r/'new')
            v=json.loads((r/'new/SCENARIO.json').read_text());old=fixture()
            self.assertEqual((int(v['configurations']['variant'][0],16)>>160)&65535,49);self.assertEqual(v['actions'],old['actions']);self.assertEqual(v['checkpoint'],old['checkpoint']);self.assertEqual(v['inventory'],old['inventory']);self.assertNotEqual(v['scenarioCommitment'],old['scenarioCommitment']);self.assertEqual(result['witnessClosure'],'NOT_EVALUATED')

    def test_hash_drift_and_checkpoint_mismatch_create_no_prepared_output(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            r=Path(t).resolve();src,pin=self.setup_input(r);sdk=m.ExecutionSDK(r/'home')
            for cfg,h,code in [(sdk.configure(),'1'*64,'PREPARED_WITNESS_HASH_MISMATCH'),(sdk.configure(checkpoint=dict(META['checkpoint'],blockNumber=1)),pin,'CHECKPOINT_MISMATCH')]:
                with self.assertRaises(m.ExecutionError) as e:sdk.prepare(cfg,src,expected_sha256=h,output=r/'out')
                self.assertEqual(e.exception.code,code);self.assertFalse((r/'out').exists())

    def test_missing_material_and_action_mismatch_are_not_faked(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            r=Path(t).resolve();sdk=m.ExecutionSDK(r/'home')
            for change,code in [(lambda v:v['inventory'].update(nodes=[]),'MISSING_WITNESS_MATERIAL'),(lambda v:v['actions'][0].update(gas=5000000),'UNSUPPORTED_TRANSACTION')]:
                src,pin=self.setup_input(r,change)
                with self.assertRaises(m.ExecutionError) as e:sdk.prepare(sdk.configure(),src,expected_sha256=pin,output=r/'out')
                self.assertEqual(e.exception.code,code);self.assertFalse((r/'out').exists())

    def test_config_and_input_commitment_tamper_rejected(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            r=Path(t).resolve();src,pin=self.setup_input(r);sdk=m.ExecutionSDK(r/'home');cfg=sdk.configure();cfg['lpBps']=0
            with self.assertRaisesRegex(m.ExecutionError,'CONFIGURATION_DRIFT'):sdk.prepare(cfg,src,expected_sha256=pin,output=r/'out')
            v=json.loads(src.read_text());v['actions'][0]['gas']=1;src.write_bytes(canonical(v)+b'\n')
            with self.assertRaisesRegex(m.ExecutionError,'SCENARIO_COMMITMENT'):sdk.prepare(sdk.configure(),src,expected_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),output=r/'out')

    def test_prepared_output_cannot_replace_source_or_existing_directory(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            r=Path(t).resolve();src,pin=self.setup_input(r);sdk=m.ExecutionSDK(r/'home');cfg=sdk.configure();out=r/'existing';out.mkdir();(out/'keep').write_text('keep')
            with self.assertRaisesRegex(m.ExecutionError,'FRESH_PREPARED_OUTPUT_REQUIRED'):sdk.prepare(cfg,src,expected_sha256=pin,output=out)
            self.assertEqual((out/'keep').read_text(),'keep')

    def test_malformed_profile_is_an_actionable_capability_error(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            sdk=m.ExecutionSDK(Path(t).resolve()/'home')
            for invalid in ([],None,{'schema':'rhook/hookr-scenario-profile/0.1'}):
                with patch.object(m,'load',return_value=invalid):
                    with self.assertRaises(m.ExecutionError) as error:sdk.profiles()
                    self.assertEqual(error.exception.code,'CHAIN_PROFILE_MISSING_OR_INVALID')
                    cap=sdk.capabilities();self.assertIn('CHAIN_PROFILE_MISSING_OR_INVALID',[x['code'] for x in cap['missing']])

    def test_capabilities_distinguish_v2_and_opt_in_v3_without_observing_resources(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            r=Path(t).resolve();sdk=m.ExecutionSDK(r/'home')
            cap=sdk.capabilities();self.assertFalse(cap['host']['admissionProfiles']['macos-host-admission-v3']['registered'])
            sensor=r/'sensor';sensor.write_bytes(b'test-sensor-not-executed');sensor.chmod(0o700)
            api.register_host(sdk._sdk(),sensor)
            with patch('subprocess.Popen',side_effect=AssertionError('capability probe must not execute sensor')):
                cap=sdk.capabilities()
            self.assertTrue(cap['host']['admissionProfiles']['macos-host-admission-v3']['registered'])
            self.assertEqual(cap['host']['resourceAdmission'],'NOT_RUN')

    def test_capability_report_unsupported_native_host_is_truthful(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as t:
            sdk=m.ExecutionSDK(Path(t).resolve()/'home')
            with patch('sys.platform','linux'),patch('platform.machine',return_value='x86_64'):
                c=sdk.capabilities()
            self.assertFalse(c['host']['supported']);self.assertFalse(c['nativeExecutionReady']);self.assertIn('UNSUPPORTED_NATIVE_HOST',[v['code'] for v in c['missing']])

if __name__=='__main__':unittest.main()
