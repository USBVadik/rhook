"""Synthetic Dynamic Fee input/SDK tests, no authority or producer."""
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from developer.files import canonical,digest,save
from rhook_alpha.execution import ExecutionSDK,ExecutionError,commit,_validate_spec,_profile
import test_execution as old
import test_interventions as cases

class DynamicFee(unittest.TestCase):
 def module(self):
  self.assertIsNotNone(importlib.util.find_spec('rhook_alpha.dynamic_fee'),'versioned native Dynamic Fee facade missing')
  return __import__('rhook_alpha.dynamic_fee',fromlist=['DynamicFeeExecutionSDK'])
 def data(self):
  m=self.module();_,_,d=cases.Interventions().prepared();e=dict(sourceSha256='1'*64,binarySha256='2'*64,policySha256=old.api.POLICY_SHA)
  return m,d,e,m.build_spec(old.fixture(),d,e)
 def test_new_domain_commits_exact_relation_and_preserves_fixed_inputs(self):
  m,d,e,s=self.data();m.validate_spec(s)
  self.assertEqual(s['schema'],m.DOMAIN);self.assertEqual(s['engine'],e)
  self.assertEqual(s['origin']['kind'],'AUTHENTICATED_CHECKPOINT_DYNAMIC_FEE_OFF')
  for k in ['actions','commonSetup','checkpoint','environment','parent','chainConfig','inventory','releaseManifestSha256']:self.assertEqual(s[k],old.fixture()[k])
  self.assertEqual(s['configurations']['baseline'],old.fixture()['configurations']['baseline'])
  self.assertEqual((int(s['configurations']['variant'][0],16)>>160)&65535,100)
  self.assertEqual(s['intervention']['planCommitment'],d['interventionCommitment'])
  self.assertEqual(s['intervention']['writes'][1]['after'][:4],'0x02')
 def test_rehashed_extra_write_changed_lp_root_and_config_fail_closed(self):
  m,d,e,s=self.data()
  for mutate in [lambda x:x['intervention']['writes'].append(x['intervention']['writes'][0]),lambda x:x['intervention']['writes'][1].update(after='0x'+'00'*32),lambda x:x['configurations']['variant'].__setitem__(0,'0x'+'00'*32),lambda x:x['origin'].update(kind='AUTHENTICATED_CHECKPOINT_SCENARIO')]:
   x=copy.deepcopy(s);mutate(x);x['intervention'].pop('interventionCommitment');x['intervention']['interventionCommitment']=commit(m.DOMAIN+'/transform',x['intervention']);x.pop('scenarioCommitment');x['scenarioCommitment']=commit(m.DOMAIN,x)
   with self.assertRaises((ExecutionError,ValueError)):m.validate_spec(x)
 def test_existing_lp_validator_does_not_silently_accept_new_domain(self):
  m,d,e,s=self.data()
  with self.assertRaises(ExecutionError):_validate_spec(s,_profile())
 def test_prepare_uses_registered_derivative_and_creates_no_grant(self):
  m,d,e,s=self.data()
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();source=root/'source.json';raw=canonical(old.fixture())+b'\n';source.write_bytes(raw);pin=digest(raw)
   from rhook_alpha.interventions import describe
   d=describe(old.fixture(),d['originalProjection'],kind=d['kind'],source_sha256=pin)
   sdk=m.DynamicFeeExecutionSDK(root/'home')
   r=dict(profile=m.PROFILE,sourceCommitment=e['sourceSha256'],files={'worker':dict(sha256=e['binarySha256'])},policySha256=e['policySha256'])
   with patch.object(sdk,'plan_intervention',return_value={'descriptor':d}),patch.object(old.api,'runtime',return_value=r):
    result=sdk.prepare_intervention(d,source,expected_sha256=pin,output=root/'prepared')
    self.assertEqual(result['profile'],m.PROFILE)
    sdk._prepared(root/'prepared')
    operation=sdk.operation(root/'prepared')
    self.assertEqual(operation['binding']['profile'],m.PROFILE)
    self.assertFalse(operation['executionAuthorized'])
   self.assertEqual(source.read_bytes(),raw)
   self.assertFalse((sdk.home/'scenarios/consents').exists())
   self.assertEqual(result['nativeExecutions'],0)
   self.assertFalse(result['executionAuthorized'])
 def test_old_runtime_cannot_prepare_dynamic_input(self):
  m,d,e,s=self.data()
  with tempfile.TemporaryDirectory() as t:
   r=Path(t).resolve();f=r/'source.json';raw=canonical(old.fixture())+b'\n';f.write_bytes(raw);pin=digest(raw)
   from rhook_alpha.interventions import describe
   d=describe(old.fixture(),d['originalProjection'],kind=d['kind'],source_sha256=pin);sdk=m.DynamicFeeExecutionSDK(r/'home')
   with patch.object(sdk,'plan_intervention',return_value={'descriptor':d}),patch.object(old.api,'runtime',return_value={'profile':old.api.PROFILE}):
    with self.assertRaisesRegex(ExecutionError,'DYNAMIC_DERIVATIVE_RUNTIME_REQUIRED'):sdk.prepare_intervention(d,f,expected_sha256=pin,output=r/'out')
   self.assertFalse((r/'out').exists())

 def test_dynamic_capabilities_and_run_require_direct_consent(self):
  m=self.module();sdk=m.DynamicFeeExecutionSDK('/private/tmp/unused-dynamic-home')
  self.assertEqual(sdk.profiles()[0]['backend'],m.PROFILE)
  with self.assertRaisesRegex(ExecutionError,'DYNAMIC_USE_INTERVENTION_API'):sdk.configure()
  with patch.object(sdk,'_prepared',side_effect=AssertionError('must not inspect before consent')):
   with self.assertRaisesRegex(ExecutionError,'EXACT_LOCAL_CONSENT_REQUIRED'):sdk.run('missing',operation='a'*64,evidence='missing')

 def test_valid_dynamic_witness_removes_inherited_missing_marker(self):
  m,d,e,s=self.data()
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();p=root/'SCENARIO.json';save(p,s);sdk=m.DynamicFeeExecutionSDK(root/'home')
   with patch.object(ExecutionSDK,'capabilities',return_value={'missing':[{'code':'PREPARED_WITNESS_MISSING'}]}):
    result=sdk.capabilities(witness=p)
   self.assertTrue(result['preparedWitness']['available']);self.assertTrue(result['staticDependenciesPresent'])
   self.assertFalse(any(x['code']=='PREPARED_WITNESS_MISSING' for x in result['missing']))

 def test_recorded_verify_binds_profile_schema_and_runtime_both_directions(self):
  from rhook_alpha.cases.api import CaseSDK
  m=self.module()
  for profile,schema,runtime_profile in [(old.api.PROFILE,m.DOMAIN,old.api.PROFILE),(m.PROFILE,'rhook/hookr-scenario/0.1',m.PROFILE),(m.PROFILE,m.DOMAIN,old.api.PROFILE)]:
   with tempfile.TemporaryDirectory() as t:
    root=Path(t).resolve();sdk=CaseSDK(root/'home');out=sdk.home/'scenarios/runs'/('c-'+'a'*32);(out/'inputs').mkdir(parents=True)
    save(out/'inputs/SCENARIO.json',{'schema':schema})
    b=dict(profile=profile,scenarioSha256=__import__('hashlib').sha256((out/'inputs/SCENARIO.json').read_bytes()).hexdigest())
    b['operationCommitment']=digest(b'rhook/scenario-operation/0.1\n'+canonical(b));save(out/'BINDING.json',b)
    save(out/'RESULT.json',dict(status='SCENARIO_COMPLETED',cleanupConfirmed=True,operationCommitment=b['operationCommitment'],scenarioCommitment='a'*64))
    save(out/'MANIFEST.json',dict(files={n:__import__('hashlib').sha256((out/n).read_bytes()).hexdigest() for n in ['inputs/SCENARIO.json','BINDING.json','RESULT.json']}))
    with patch.object(old.api,'runtime',return_value={'profile':runtime_profile}),patch.object(old.api,'_helper',return_value={'status':'SCENARIO_RECORDED_INTEGRITY_PASS'}) as helper:
     with self.assertRaisesRegex(ValueError,'SCENARIO_VERIFICATION_PROFILE'):old.api.verify(sdk,out)
     helper.assert_not_called()

 def test_candidate_preparation_never_registers_or_deploys_worker(self):
  m,d,e,s=self.data()
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();source=root/'source.json';raw=canonical(old.fixture())+b'\n';source.write_bytes(raw);pin=digest(raw)
   from rhook_alpha.interventions import describe
   d=describe(old.fixture(),d['originalProjection'],kind=d['kind'],source_sha256=pin);sdk=m.DynamicFeeExecutionSDK(root/'home')
   runtime=dict(profile=m.PROFILE,sourceCommitment=e['sourceSha256'],files={'worker':{'sha256':e['binarySha256']}},policySha256=e['policySha256']);manifest=root/'RUNTIME.json';save(manifest,runtime)
   with patch.object(sdk,'plan_intervention',return_value={'descriptor':d}),patch.object(old.api,'runtime',side_effect=AssertionError('unregistered runtime must not be assumed')),patch.object(old.api,'register',side_effect=AssertionError('no deployment')),patch.object(old.api,'_identity',return_value=runtime):
    result=sdk.prepare_intervention(d,source,expected_sha256=pin,output=root/'prepared',candidate_runtime=manifest)
   self.assertEqual(result['runtimeRegistration'],'PENDING')
   self.assertEqual(result['status'],'EXECUTION_CANDIDATE_PREPARED')
   self.assertFalse((sdk.home/'scenarios/RUNTIME.json').exists());self.assertFalse((sdk.home/'scenarios/.consent.key').exists())
   with self.assertRaisesRegex(ExecutionError,'NATIVE_RUNTIME_MISSING'):sdk.operation(root/'prepared')
