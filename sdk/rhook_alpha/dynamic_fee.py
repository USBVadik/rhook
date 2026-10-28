"""Versioned Dynamic Fee OFF prepared-witness API. No automatic live capture."""
import copy
from pathlib import Path
from developer.files import canonical,digest,load,no_links,save,sha,sync
from .execution import ExecutionSDK,ExecutionError,check,commit,_input,_profile,_validate_spec,DOMAIN as LP_DOMAIN
from .interventions import DYNAMIC_OFF,describe,validate,_writes

DOMAIN='rhook/hookr-dynamic-fee-off/0.1'
PROFILE='nitro-hookr-dynamic-fee-off/0.1'
KIND='AUTHENTICATED_CHECKPOINT_DYNAMIC_FEE_OFF'
ROOT_ON='0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'
ROOT_OFF='0x020101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'


def intent(pool):
 return dict(schema=DOMAIN+'/intent',poolId=pool,dynamicFee='OFF',lpBps=100)


def transform(spec,plan_pin):
 from .interventions import _pin
 _pin(plan_pin);p=_profile()
 contracts={r:next(c for c in p['manifest']['contracts'] if c['role']==r) for r in ['root','rules']}
 projection=dict(schema='rhook/intervention-target-state/0.1',checkpoint=spec['checkpoint'],accounts={
  'root':dict(address=contracts['root']['address'],codeHash=contracts['root']['runtimeHash'],storage={p['rootRecordSlot']:ROOT_ON}),
  'rules':dict(address=contracts['rules']['address'],codeHash=contracts['rules']['runtimeHash'],storage={'0x'+format(int(p['configSlot'],16)+i,'064x'):w for i,w in enumerate(p['baselineConfigWords'])})})
 writes=[{k:v for k,v in row.items() if k!='mask'} for row in _writes(projection,DYNAMIC_OFF,None)]
 body=dict(schema=DOMAIN+'/transform',originalStateRoot=spec['checkpoint']['stateRoot'],poolId=p['poolId'],rootCodeHash=contracts['root']['runtimeHash'],rulesCodeHash=contracts['rules']['runtimeHash'],planCommitment=plan_pin,writes=writes)
 return dict(body,interventionCommitment=commit(DOMAIN+'/transform',body))


def build_spec(original,descriptor,engine):
 d=validate(descriptor);check(d['kind']==DYNAMIC_OFF,'DYNAMIC_OFF_ONLY','Use the exact Dynamic Fee OFF descriptor.')
 check(describe(original,d['originalProjection'],kind=DYNAMIC_OFF,source_sha256=d['sourceInputSha256'])==d,
       'INTERVENTION_PLAN_MISMATCH','Keep all original input, code and projection bindings.')
 s=copy.deepcopy(original);s.pop('scenarioCommitment')
 s.update(schema=DOMAIN,origin=dict(kind=KIND,capsuleId=commit(DOMAIN+'/checkpoint',dict(checkpoint=s['checkpoint'],intent=intent(s['poolId'])))),engine=copy.deepcopy(engine))
 s['intervention']=transform(s,d['interventionCommitment'])
 s['configurations']['variant']=copy.deepcopy(s['configurations']['baseline']);s['configurations']['variant'][0]=s['intervention']['writes'][0]['after']
 s['scenarioCommitment']=commit(DOMAIN,s);validate_spec(s);return s


def validate_spec(spec):
 try:
  s=copy.deepcopy(spec);pin=s.pop('scenarioCommitment')
  check(s.get('schema')==DOMAIN and pin==commit(DOMAIN,s),'DYNAMIC_SPEC_COMMITMENT','Restore the versioned Dynamic Fee input.')
  t=s.pop('intervention');check(t==transform(s,t['planCommitment']),'DYNAMIC_EXACT_TRANSFORM','Require exactly the two committed writes, identities and original root.')
  p=_profile();expected=copy.deepcopy(p['baselineConfigWords']);expected[0]=t['writes'][0]['after']
  check(s['configurations']==dict(baseline=p['baselineConfigWords'],variant=expected),'DYNAMIC_CONFIG_OFF_ONLY','LP100 and all other config words must remain unchanged.')
  check(s['origin']==dict(kind=KIND,capsuleId=commit(DOMAIN+'/checkpoint',dict(checkpoint=s['checkpoint'],intent=intent(s['poolId'])))),
        'DYNAMIC_ORIGIN','Keep the exact Dynamic Fee OFF intent/checkpoint binding.')
  # Reuse existing common input checks through an explicit validation-only LP
  # view. This is never written, executed, or represented as an actual LP run.
  s['schema']=LP_DOMAIN;s['configurations']['variant']=copy.deepcopy(p['baselineConfigWords'])
  old=int(s['configurations']['baseline'][0],16);s['configurations']['variant'][0]='0x'+format((old&~(65535<<160))|(50<<160),'064x')
  lp_intent=dict(schema='rhook/on-demand-hookr-intent/0.1',poolId=s['poolId'],lpBps=50)
  s['origin']=dict(kind='AUTHENTICATED_CHECKPOINT_SCENARIO',capsuleId=commit('rhook/scenario-checkpoint/0.1',dict(checkpoint=s['checkpoint'],intent=lp_intent)))
  s['scenarioCommitment']=commit(LP_DOMAIN,s);_validate_spec(s,p)
  check(set(spec)==set(s)|{'intervention'},'DYNAMIC_SPEC_FIELDS','Unknown Dynamic Fee input fields are unsupported.')
  return spec
 except ExecutionError:raise
 except (KeyError,ValueError,TypeError,AttributeError) as error:
  raise ExecutionError('DYNAMIC_SPEC_FIELDS','Supply the complete supported versioned input.') from error


class DynamicFeeExecutionSDK(ExecutionSDK):
 """Prepared Dynamic Fee OFF workflow using separately registered derivative.

 Inherits the existing exact operation/run/verify/compare and host supervision.
 LP configuration methods are not this profile's preparation interface.
 """
 def profiles(self):
  p=_profile()
  return [dict(id=PROFILE,backend=PROFILE,chainId=4663,poolId=p['poolId'],intervention=DYNAMIC_OFF,lpBps=100,arbRecapture='RETAINED',nativeHost='darwin-arm64',livePreparation='UNSUPPORTED',witnessCoverage='ONLY_ESTABLISHED_BY_COMPLETED_NATIVE_EXECUTION')]

 def configure(self,**kwargs):
  raise ExecutionError('DYNAMIC_USE_INTERVENTION_API','Use plan_intervention(kind=hookr.dynamic-fee-off/0.1) and prepare_intervention with the separately registered derivative.')

 def prepare(self,*args,**kwargs):
  raise ExecutionError('DYNAMIC_USE_INTERVENTION_API','Prepare the exact committed intervention through prepare_intervention; LP preparation uses ExecutionSDK.')

 def capabilities(self,*,witness=None):
  value=super().capabilities()
  runtime=self.home/'scenarios/RUNTIME.json'
  if runtime.exists():
   try:
    check(load(runtime,2<<20)['runtime']['profile']==PROFILE,'DYNAMIC_DERIVATIVE_RUNTIME_REQUIRED','Register the separately pinned derivative in a fresh SDK home.')
   except (OSError,ValueError,KeyError,TypeError) as error:
    value['missing'].append(dict(code='DYNAMIC_DERIVATIVE_RUNTIME_REQUIRED',nextStep='Register the separately pinned derivative in a fresh home.'))
  if witness is not None:
   try:
    path=no_links(witness);spec=load(path/'SCENARIO.json' if path.is_dir() else path,8<<20);validate_spec(spec)
    value['preparedWitness']=dict(available=True,checkpoint=spec['checkpoint'],authentication='PENDING_NATIVE_ADMISSION',witnessClosure='NOT_EVALUATED')
    value['missing']=[x for x in value['missing'] if x['code']!='PREPARED_WITNESS_MISSING']
   except (ExecutionError,OSError,ValueError):
    value['missing'].append(dict(code='DYNAMIC_PREPARED_WITNESS_MISSING_OR_INVALID',nextStep='Use the prepared Dynamic Fee OFF input.'))
  value['staticDependenciesPresent']=not value['missing'];return value

 def prepare_intervention(self,descriptor,witness,*,expected_sha256,output,node=None,candidate_runtime=None):
  from .cases.scenario import api
  d=validate(descriptor);check(d['kind']==DYNAMIC_OFF and d['sourceInputSha256']==expected_sha256,
        'INTERVENTION_SOURCE_PIN','Use the original pinned witness and Dynamic Fee descriptor.')
  fresh=self.plan_intervention(witness,expected_sha256=expected_sha256,kind=DYNAMIC_OFF,node=node)
  check(fresh['descriptor']==d,'INTERVENTION_PLAN_MISMATCH','Reauthenticate and preserve the complete saved plan.')
  raw,original=_input(witness,expected_sha256);sdk=self._sdk()
  r=api.runtime(sdk) if candidate_runtime is None else api._identity(load(no_links(candidate_runtime),65536))
  check(r['profile']==PROFILE,'DYNAMIC_DERIVATIVE_RUNTIME_REQUIRED','Register the separately pinned Dynamic Fee derivative in a fresh SDK home; accepted LP worker is incompatible.')
  out=no_links(output);check(not out.exists(),'FRESH_PREPARED_OUTPUT_REQUIRED','Choose a fresh prepared directory.')
  engine=dict(sourceSha256=r['sourceCommitment'],binarySha256=r['files']['worker']['sha256'],policySha256=r['policySha256'])
  spec=build_spec(original,d,engine)
  plan=api.configure(sdk,pool_id=spec['poolId'],lp_bps=100,profile=PROFILE)
  out.mkdir(mode=0o700,parents=True);sync(out.parent);save(out/'SCENARIO.json',spec);save(out/'INTERVENTION.json',d)
  save(out/'SDK_RESULT.json',dict(status='PREPARED_SCENARIO_INPUT',authentication='PENDING_NATIVE_ADMISSION',nativeExecutions=0,cleanupConfirmed=True,planId=plan['planId'],planCommitment=plan['planCommitment'],scenarioSha256=sha(out/'SCENARIO.json'),scenarioCommitment=spec['scenarioCommitment']))
  result=dict(status='EXECUTION_PREPARED' if candidate_runtime is None else 'EXECUTION_CANDIDATE_PREPARED',runtimeRegistration='REGISTERED' if candidate_runtime is None else 'PENDING',schema=DOMAIN+'/prepared',profile=PROFILE,prepared=str(out),planId=plan['planId'],checkpoint=spec['checkpoint'],scenarioSha256=sha(out/'SCENARIO.json'),scenarioCommitment=spec['scenarioCommitment'],interventionCommitment=spec['intervention']['interventionCommitment'],descriptorCommitment=d['interventionCommitment'],sourceWitnessSha256=digest(raw),nativeRunDirectory=str(sdk.home/'scenarios/runs'/plan['planId']),authentication='PENDING_NATIVE_ADMISSION',witnessClosure='NOT_EVALUATED',nativeExecutions=0,executionAuthorized=False)
  save(out/'PREPARATION.json',result);return result

 def _prepared(self,prepared):
  from .cases.scenario import api
  path=no_links(prepared)
  try:
   meta=load(path/'PREPARATION.json',65536);d=validate(load(path/'INTERVENTION.json',65536))
   _,capture,plan,spec=api._input(self._sdk(),path);validate_spec(spec)
   check(d['kind']==DYNAMIC_OFF and meta['schema']==DOMAIN+'/prepared' and meta['profile']==PROFILE and plan['profile']==PROFILE and meta['scenarioSha256']==capture['scenarioSha256'] and meta['scenarioCommitment']==spec['scenarioCommitment'] and meta['planId']==plan['planId'] and meta['checkpoint']==spec['checkpoint'] and meta['interventionCommitment']==spec['intervention']['interventionCommitment'] and meta['descriptorCommitment']==d['interventionCommitment']==spec['intervention']['planCommitment'] and meta['sourceWitnessSha256']==d['sourceInputSha256'],
         'DYNAMIC_PREPARATION_DRIFT','Use the exact prepared input, descriptor, new home and derivative runtime.')
   check(d['checkpoint']==spec['checkpoint'] and d['fixedInputs']=={k:spec[k] for k in d['fixedInputs']},'DYNAMIC_FIXED_INPUTS','Preserve original signed action, common setup and environment.')
   return path,meta
  except ExecutionError:raise
  except (OSError,ValueError,KeyError,TypeError) as error:raise ExecutionError('DYNAMIC_PREPARATION_DRIFT','Restore the exact prepared input and descriptor.') from error
