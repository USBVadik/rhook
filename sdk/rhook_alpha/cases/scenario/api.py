"""Checkpoint scenarios with explicit assumptions, separate from historical cases."""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import time
from developer.files import canonical,digest,load,no_links,read,require,save,sha,sync
from .. import authority,native,forge
PROFILE='nitro-hookr-scenario/0.1'
DYNAMIC_PROFILE='nitro-hookr-dynamic-fee-off/0.1'
DYNAMIC_DOMAIN='rhook/hookr-dynamic-fee-off/0.1'
OVERLAY_PROFILE='nitro-hookr-config-overlay/0.1'
OVERLAY_DOMAIN='rhook/hookr-config-overlay/0.1'
# SDK 0.6: descriptor-driven overlays. An operation binding needs a descriptor the catalogue admits for
# NATIVE_EXECUTION, kinds reviewed for it and the reviewed engine identity (profile_descriptor.native_operation_ref).
# That identity authorizes nothing: run() also requires the owner's per-operation authorization record below.
PROFILE_OVERLAY_PROFILE='nitro-hook-profile-overlay/0.1'
PROFILE_OVERLAY_DOMAIN='rhook/hookr-profile-overlay/0.1'
PROFILE_AUTHORIZATION_SCHEMA='rhook/profile-native-authorization/0.1'
PROFILE_AUTHORIZATIONS='scenarios/profile-native-authorizations'
PROFILE_HOST='macos-host-admission-v4'
PROFILE_AUTHORIZATION_SECONDS=86400
# Minimum remaining authorization lifetime when run() opens the attempt (a full 600 s grant plus 60 s), and in the
# ProfileOverlayExecutionSDK launcher (advisory: it writes no marker; a later refusal by run() consumes nothing).
# The consent grant of a profile-overlay operation never expires after the authorization (authority.issue not_after).
PROFILE_RUN_MARGIN_SECONDS=660
PROFILE_LAUNCH_MARGIN_SECONDS=900
# Every runtime profile this backend binds, runs and verifies; each one is a separately pinned worker.
PROFILES=(PROFILE,DYNAMIC_PROFILE,OVERLAY_PROFILE,PROFILE_OVERLAY_PROFILE)
DOMAINS={PROFILE:'rhook/hookr-scenario/0.1',DYNAMIC_PROFILE:DYNAMIC_DOMAIN,OVERLAY_PROFILE:OVERLAY_DOMAIN,PROFILE_OVERLAY_PROFILE:PROFILE_OVERLAY_DOMAIN}
_DEFAULT_LP_BPS=object()
HERE=Path(__file__).resolve().parent
POLICY_SHA=sha(HERE/'policy.json')


class ScenarioHelperStop(ValueError):
    """Retain exact bounded helper diagnostics while preserving ValueError API."""
    def __init__(self, status, stdout, stderr, evidence):
        self.report=dict(helperStatus=status,stdout=stdout.decode(errors='replace')[:4096],
                         stderr=stderr.decode(errors='replace')[:4096],evidencePath=str(evidence),
                         stdoutSha256=digest(stdout),stderrSha256=digest(stderr))
        super().__init__('SCENARIO_HELPER_STOP: '+str(status['stop'])+': '+str(status.get('captureError'))+
                         '; exit='+str(status['exitCode'])+'; evidence='+str(evidence))


def select_pool(pool_id=None):
    p=load(HERE/'native/profile.json',65536)
    require(pool_id is None or pool_id==p['poolId'],'SUPPORTED_HOOKR_POOL_REQUIRED')
    return {'status':'SUPPORTED_SCENARIO_POOL','poolId':p['poolId'],'poolKey':p['poolKey'],
            'contracts':{r['role']:{'address':r['address'],'runtimeHash':r['runtimeHash']} for r in p['manifest']['contracts'] if r['role'] in ['root','rules','router','poolManager']},
            'profile':PROFILE,'amountInWei':'1000000000000000','mode':'HYPOTHETICAL_NOT_HISTORICAL_REPLAY'}


def configure(sdk,*,pool_id=None,lp_bps=_DEFAULT_LP_BPS,profile=PROFILE,interventions=None,descriptor=None):
    p=select_pool(pool_id)
    require(descriptor is None or profile==PROFILE_OVERLAY_PROFILE,'DESCRIPTOR_ONLY_FOR_PROFILE_OVERLAY')
    if profile==PROFILE_OVERLAY_PROFILE:
        # The descriptor states every word; an LP value outside its intervention set is refused, not ignored.
        from ...profile_descriptor import load_accepted,intent as profile_intent
        require(lp_bps is _DEFAULT_LP_BPS and type(descriptor) is str and interventions is not None,'PROFILE_OVERLAY_DESCRIPTOR_AND_INTERVENTIONS_REQUIRED')
        _,raw,_=load_accepted(descriptor,'OFFLINE_PREPARATION')
        value=profile_intent(raw,p['poolId'],interventions)
        require(value['interventions']==interventions,'PROFILE_CANONICAL_SET_REQUIRED')
        return _save_plan(sdk,PROFILE_OVERLAY_PROFILE,value)
    if lp_bps is _DEFAULT_LP_BPS:lp_bps=50
    if profile==OVERLAY_PROFILE:
        from ...config_overlay import canonical_interventions,intent as overlay_intent
        require(interventions is not None and interventions==canonical_interventions(interventions),'CONFIG_OVERLAY_CANONICAL_SET_REQUIRED')
        lp_bps=overlay_intent(p['poolId'],interventions)['lpBps']
    else:require(interventions is None,'INTERVENTIONS_ONLY_FOR_CONFIG_OVERLAY')
    require((profile==PROFILE and type(lp_bps) is int and 0<=lp_bps<=99) or (profile in (DYNAMIC_PROFILE,OVERLAY_PROFILE) and type(lp_bps) is int and 0<=lp_bps<=100),'LP_BPS_0_TO_99_REQUIRED')
    require(profile!=DYNAMIC_PROFILE or lp_bps==100,'LP_BPS_0_TO_99_REQUIRED')
    sdk.registry._prepare();ref='c-'+secrets.token_hex(16)
    directory=sdk.home/'scenarios/plans'/ref;directory.mkdir(mode=0o700,parents=True);sync(directory.parent)
    value={'schema':'rhook/scenario-plan/0.1','planId':ref,'profile':PROFILE,'intent':{'schema':'rhook/on-demand-hookr-intent/0.1','poolId':p['poolId'],'lpBps':lp_bps},
           'assumptions':{'simulatedBuyWei':'1000000000000000','commonFundingMintWei':'1000000000000000000','caller':'PUBLIC_SIMULATION_SIGNER_NEVER_FUND_OR_BROADCAST','nonce':0,'gas':10000000,'syntheticL1BaseFeeWei':'1000000000','independentWorlds':True,'canonicalActualComparison':'NOT_APPLICABLE'}}
    if profile==DYNAMIC_PROFILE:
        from ...dynamic_fee import intent
        value.update(profile=profile,intent=intent(p['poolId']))
    if profile==OVERLAY_PROFILE:
        value.update(profile=profile,intent=overlay_intent(p['poolId'],interventions))
    value['planCommitment']=digest(canonical(value));save(directory/'PLAN.json',value)
    return dict(value,status='SCENARIO_PLANNED',executionAuthorized=False,results=None)


def _save_plan(sdk,profile,intent):
    sdk.registry._prepare();ref='c-'+secrets.token_hex(16)
    directory=sdk.home/'scenarios/plans'/ref;directory.mkdir(mode=0o700,parents=True);sync(directory.parent)
    value={'schema':'rhook/scenario-plan/0.1','planId':ref,'profile':profile,'intent':intent,
           'assumptions':{'simulatedBuyWei':'1000000000000000','commonFundingMintWei':'1000000000000000000','caller':'PUBLIC_SIMULATION_SIGNER_NEVER_FUND_OR_BROADCAST','nonce':0,'gas':10000000,'syntheticL1BaseFeeWei':'1000000000','independentWorlds':True,'canonicalActualComparison':'NOT_APPLICABLE'}}
    value['planCommitment']=digest(canonical(value));save(directory/'PLAN.json',value)
    return dict(value,status='SCENARIO_PLANNED',executionAuthorized=False,results=None)


def describe(sdk,ref):
    require(type(ref) is str and re.fullmatch('c-[0-9a-f]{32}',ref),'SCENARIO_PLAN_ID')
    value=load(sdk.home/'scenarios/plans'/ref/'PLAN.json',65536);body=dict(value);pin=body.pop('planCommitment')
    require(pin==digest(canonical(body)) and value['planId']==ref and value['profile'] in PROFILES and value['schema']=='rhook/scenario-plan/0.1','SCENARIO_PLAN_DRIFT')
    select_pool(value['intent']['poolId'])
    if value['profile']==DYNAMIC_PROFILE:
        from ...dynamic_fee import intent
        require(value['intent']==intent(value['intent']['poolId']),'DYNAMIC_PLAN_INTENT')
    elif value['profile']==OVERLAY_PROFILE:
        from ...config_overlay import canonical_interventions,intent
        items=value['intent']['interventions'];require(items==canonical_interventions(items) and value['intent']==intent(value['intent']['poolId'],items),'CONFIG_OVERLAY_PLAN_INTENT')
    elif value['profile']==PROFILE_OVERLAY_PROFILE:
        from ...profile_descriptor import load_for_intent
        load_for_intent(value['intent'],'OFFLINE_PREPARATION')
    else:require(type(value['intent']['lpBps']) is int and 0<=value['intent']['lpBps']<=99,'LP_BPS_DOMAIN')
    return value


def _identity(runtime):
    native.python_required()
    require(type(runtime) is dict and set(runtime)=={'schema','profile','sourceCommitment','policySha256','files'},'SCENARIO_RUNTIME_FIELDS')
    require(runtime['schema']=='rhook/scenario-runtime/0.1' and runtime['profile'] in PROFILES and runtime['policySha256']==POLICY_SHA,'SCENARIO_RUNTIME_PROFILE')
    require(re.fullmatch('[0-9a-f]{64}',runtime['sourceCommitment']) and set(runtime['files'])=={'worker','node','sensor'},'SCENARIO_RUNTIME_ARTIFACTS')
    for row in runtime['files'].values():require(set(row)=={'path','sha256'} and sha(no_links(row['path']))==row['sha256'],'SCENARIO_RUNTIME_ARTIFACT_DRIFT')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='rhook-scenario-identity-') as tmp:
        result,out,err=native.capture([runtime['files']['worker']['path'],'--identity'],Path(tmp)/'capture',5,4096,4096)
    require(result['ownedChildReaped'] and result['exitCode']==0 and not result['stop'] and not err,'SCENARIO_WORKER_IDENTITY')
    require(json.loads(out)=={k:runtime[k] for k in ['profile','sourceCommitment','policySha256']},'SCENARIO_LINKED_IDENTITY')
    return runtime


def register(sdk,path):
    r=_identity(load(path,65536));sdk.registry._prepare()
    directory=sdk.home/'scenarios';directory.mkdir(mode=0o700,exist_ok=True);sync(directory.parent)
    save(directory/'RUNTIME.json',{'runtime':r,'sdkFiles':native.code_files()})
    key=directory/'.consent.key'
    with key.open('xb') as stream:stream.write(os.urandom(32));stream.flush();os.fsync(stream.fileno())
    key.chmod(0o600);sync(directory)
    return {'status':'SCENARIO_RUNTIME_REGISTERED','profile':r['profile'],'nativeExecutions':0}


def runtime(sdk):
    value=load(sdk.home/'scenarios/RUNTIME.json',2<<20);require(value['sdkFiles']==native.code_files(),'SCENARIO_SDK_CODE_DRIFT')
    from developer.files import dependencies
    dependencies(native.SDK_ROOT/'engine/adapters/hookr-case/node_modules')
    return _identity(value['runtime'])


def acquire(sdk,ref,output,*,credential_file,account_assertions,read_only=False):
    require(read_only is True,'EXPLICIT_READ_ONLY_REQUIRED');plan=describe(sdk,ref)
    require(plan['profile']==PROFILE,'DYNAMIC_OFFLINE_ONLY')
    require(plan.get('assumptions',{}).get('gas')==10000000,'STALE_SCENARIO_PLAN_GAS')
    r=runtime(sdk);output=no_links(output);output.mkdir(mode=0o700);sync(output.parent)
    config={'output':str(output),'readOnlyApproved':True,'intent':plan['intent'],'engine':{'sourceSha256':r['sourceCommitment'],'binarySha256':r['files']['worker']['sha256'],'policySha256':r['policySha256']},
            'credentialFile':str(no_links(credential_file)),'accountAssertions':str(no_links(account_assertions))}
    save(output/'STARTED.json',{'planId':ref,'planCommitment':plan['planCommitment'],'profile':PROFILE})
    import tempfile
    with tempfile.TemporaryDirectory(prefix='.scenario-config-',dir=sdk.home) as tmp:
        path=Path(tmp)/'CONFIG.json';save(path,config)
        status,out,err=forge.capture_helper([r['files']['node']['path'],str(HERE/'main.mjs'),str(path)],output/'CHILD',40,65536,65536)
    require(status['ownedChildReaped'],'SCENARIO_ACQUISITION_CLEANUP_UNCONFIRMED')
    if status['stop'] or status['exitCode'] not in (0,1):
        value={'status':'SCENARIO_ACQUISITION_STOP','causeCode':status['stop'] or 'CHILD_EXIT_'+str(status['exitCode']),'nativeExecutions':0}
    else:
        value=load(output/'ACQUISITION_RESULT.json',65536);require(value==json.loads(out),'SCENARIO_ACQUISITION_RESULT_LINK')
    value.update(planId=ref,planCommitment=plan['planCommitment'],cleanupConfirmed=True,output=str(output),externalDelivery='HOLD')
    if value['status']=='AUTHENTICATED_SCENARIO_CAPTURED':
        value['scenarioSha256']=sha(output/'SCENARIO.json')
    save(output/'SDK_RESULT.json',value);return value


def _input(sdk,capture):
    capture=no_links(capture);v=load(capture/'SDK_RESULT.json',65536)
    imported=(v.get('status')=='PREPARED_SCENARIO_INPUT' and v.get('authentication')=='PENDING_NATIVE_ADMISSION' and type(v.get('nativeExecutions')) is int and v['nativeExecutions']==0)
    require((v['status']=='AUTHENTICATED_SCENARIO_CAPTURED' or imported) and v['cleanupConfirmed'] is True,'AUTHENTICATED_SCENARIO_CAPTURE_REQUIRED')
    plan=describe(sdk,v['planId']);require(v['planCommitment']==plan['planCommitment'] and sha(capture/'SCENARIO.json')==v['scenarioSha256'],'SCENARIO_CAPTURE_DRIFT')
    spec=load(capture/'SCENARIO.json',8<<20);body=dict(spec);pin=body.pop('scenarioCommitment')
    require(type(spec.get('actions')) is list and len(spec['actions'])==1,'ON_DEMAND_SINGLE_ACTION_REQUIRED')
    domain=DOMAINS[plan['profile']]
    require(spec['schema']==domain and pin==digest((domain+'\n').encode()+canonical(body)) and pin==v['scenarioCommitment'],'SCENARIO_SPEC_COMMITMENT')
    if plan['profile']==DYNAMIC_PROFILE:
        from ...dynamic_fee import validate_spec
        validate_spec(spec)
    if plan['profile']==OVERLAY_PROFILE:
        from ...config_overlay import validate_spec as validate_overlay
        validate_overlay(spec);require(spec['configOverlay']['interventions']==plan['intent']['interventions'],'SCENARIO_PLAN_LINK')
    if plan['profile']==PROFILE_OVERLAY_PROFILE:
        # The plan names the descriptor and the interventions; the input must be exactly their derivation.
        from ...profile_descriptor import load_for_intent,validate_input
        _,raw,_=load_for_intent(plan['intent'],'OFFLINE_PREPARATION');validate_input(spec,raw)
        require(spec['poolId']==plan['intent']['poolId'] and spec['profileOverlay']['interventions']==plan['intent']['interventions']
                and spec['profileOverlay']['descriptor']['sha256']==plan['intent']['profile']['sha256'],'SCENARIO_PLAN_LINK')
    else:require(spec['poolId']==plan['intent']['poolId'] and (int(spec['configurations']['variant'][0],16)>>160)&65535==plan['intent']['lpBps'],'SCENARIO_PLAN_LINK')
    require(spec['actions'][0].get('gas')==plan.get('assumptions',{}).get('gas'),'SCENARIO_PLAN_GAS_LINK')
    return capture,v,plan,spec


def _helper(sdk,args,timeout=12):
    r=runtime(sdk);import tempfile
    with tempfile.TemporaryDirectory(prefix='.scenario-helper-',dir=sdk.home) as tmp:
        status,out,err=forge.capture_helper([r['files']['worker']['path'],*map(str,args)],Path(tmp)/'capture',timeout,65536,65536)
        if not (status['ownedChildReaped'] and not status['stop'] and status['exitCode']==0):
            failures=sdk.home/'scenarios/helper-failures';failures.mkdir(mode=0o700,parents=True,exist_ok=True)
            sync(failures.parent);sync(sdk.home)
            retained=failures/secrets.token_hex(16);os.rename(Path(tmp)/'capture',retained)
            sync(retained);sync(failures);sync(Path(tmp))
            raise ScenarioHelperStop(status,out,err,retained)
    return json.loads(out)


def check(sdk,capture):
    capture,v,plan,spec=_input(sdk,capture);r=runtime(sdk)
    require(r['profile']==plan['profile'],'SCENARIO_CAPTURE_RUNTIME_PROFILE')
    require(spec['engine']=={'sourceSha256':r['sourceCommitment'],'binarySha256':r['files']['worker']['sha256'],'policySha256':r['policySha256']},'SCENARIO_CAPTURE_RUNTIME_DRIFT')
    result=_helper(sdk,['--authenticate',capture/'SCENARIO.json'])
    require(result['status']=='AUTHENTICATED_SCENARIO_INPUT' and result['scenarioCommitment']==v['scenarioCommitment'] and result['nativeExecutions']==0,'SCENARIO_INPUT_ADMISSION_LINK')
    return result


def host_profile_module(profile):
    """Opt-in host admission profiles and their registration records; v2 has neither."""
    from . import host_v3, host_v4
    profiles={host_v3.PROFILE:(host_v3,'HOST_V3.json'),host_v4.PROFILE:(host_v4,host_v4.RECORD)}
    require(profile in profiles,'UNSUPPORTED_HOST_PROFILE')
    return profiles[profile]


def register_host(sdk,sensor,*,profile='macos-host-admission-v3'):
    host,record=host_profile_module(profile)
    sensor=no_links(sensor)
    sdk.registry._prepare();directory=sdk.home/'scenarios';directory.mkdir(mode=0o700,exist_ok=True)
    value={'profile':host.PROFILE,'policySha256':host.POLICY_SHA,
           'sensor':{'path':str(sensor),'sha256':sha(sensor)},
           'sdkFilesCommitment':digest(canonical(host.sdk_files()))}
    save(directory/record,value)
    return dict(value,status='HOST_PROFILE_REGISTERED',executionAuthorized=False)


def select_host(sdk,profile):
    if profile=='v2':return {'profile':'v2'}
    host,record=host_profile_module(profile)
    value=load(sdk.home/'scenarios'/record,65536)
    require(set(value)=={'profile','policySha256','sensor','sdkFilesCommitment'} and value['profile']==profile
            and value['policySha256']==host.POLICY_SHA
            and value['sdkFilesCommitment']==digest(canonical(host.sdk_files())),'HOST_RUNTIME_DRIFT')
    require(set(value['sensor'])=={'path','sha256'}
            and sha(no_links(value['sensor']['path']))==value['sensor']['sha256'],'HOST_RUNTIME_DRIFT')
    return value


def prepare(sdk,capture,*,host_profile='v2'):
    host=select_host(sdk,host_profile)
    capture,v,plan,spec=_input(sdk,capture);r=runtime(sdk)
    require(r['profile']==plan['profile'],'SCENARIO_CAPTURE_RUNTIME_PROFILE')
    return operation_binding(sdk,plan,v,r,host,host_profile=host_profile)


def operation_binding(sdk,plan,v,r,host,*,host_profile='v2'):
    """Pure proposal identity, not runtime registration/admission or authority."""
    require(plan['profile'] in PROFILES and r['profile']==plan['profile'],'SCENARIO_CAPTURE_RUNTIME_PROFILE')
    ref=plan['planId'];out=sdk.home/'scenarios/runs'/ref
    b={'schema':'rhook/scenario-operation/0.1','profile':plan['profile'],'planId':ref,'scenarioCommitment':v['scenarioCommitment'],'scenarioSha256':v['scenarioSha256'],
       'binarySha256':r['files']['worker']['sha256'],'sourceCommitment':r['sourceCommitment'],'policySha256':POLICY_SHA,'outputPath':str(out),'ownerUid':os.getuid(),'host':os.uname().nodename,
       'maximumInvocations':{'SCENARIO_BASELINE':1,'SCENARIO_VARIANT':1},'RPC':0,'WSS':0,'automaticRetry':False,'externalDelivery':'HOLD'}
    if host_profile!='v2':
        from ..workflow import PROFILE as WORKFLOW_PROFILE
        b.update(hostAdmission=host,sdkFilesCommitment=host['sdkFilesCommitment'],workflowCaptureProfile=WORKFLOW_PROFILE)
    if plan['profile']==PROFILE_OVERLAY_PROFILE:
        # The worker refuses a profile operation without this exact descriptor binding (PROFILE_OPERATION_BINDING).
        from ...profile_descriptor import native_operation_ref
        # The engine is the identity this operation binds (source, binary, policy), compared exactly with the accepted one.
        b['profileDescriptor']=native_operation_ref(plan['intent'],{'sourceSha256':b['sourceCommitment'],'binarySha256':b['binarySha256'],'policySha256':b['policySha256']})
    b['operationCommitment']=digest(b'rhook/scenario-operation/0.1\n'+canonical(b))
    return b


# ----- profile-overlay native gate (SDK 0.6, G5) -------------------------------------------------
# Three separate things: the G4B build verification (records outside the SDK), the reviewed engine identity
# (profile_descriptor.PROFILE_ENGINE_RECORD; it makes an operation bindable) and the owner's authorization of
# one exact operation (this record). Without the record no profile-overlay authority is issued. The record is
# data in the SDK home, so authorizing a reviewed operation needs no code change (which would alter the SDK
# files commitment inside every operation binding).

def _profile_authorization_fields(b):
    from ...profile_descriptor import PROFILE_ENGINE_RECORD
    return {'schema':PROFILE_AUTHORIZATION_SCHEMA,'profile':PROFILE_OVERLAY_PROFILE,'operationCommitment':b['operationCommitment'],
            'planId':b['planId'],'scenarioCommitment':b['scenarioCommitment'],'scenarioSha256':b['scenarioSha256'],
            'engine':{'sourceSha256':b['sourceCommitment'],'binarySha256':b['binarySha256'],'policySha256':b['policySha256']},
            'profileDescriptor':b['profileDescriptor'],'catalogueSha256':PROFILE_ENGINE_RECORD['catalogueSha256'],
            'hostAdmissionProfile':PROFILE_HOST,'maximumRuns':1,'automaticRetry':False,'localOwnerConfirmed':True}


def _profile_scope(b,host_profile):
    require(b.get('profile')==PROFILE_OVERLAY_PROFILE and type(b.get('profileDescriptor')) is dict,'PROFILE_NATIVE_AUTHORIZATION_SCOPE')
    require(host_profile==PROFILE_HOST and type(b.get('hostAdmission')) is dict and b['hostAdmission'].get('profile')==PROFILE_HOST,'PROFILE_NATIVE_HOST_V4_REQUIRED')


def profile_authorization_path(sdk,b):
    require(type(b.get('operationCommitment')) is str and re.fullmatch('[0-9a-f]{64}',b['operationCommitment']),'OPERATION_COMMITMENT_REQUIRED')
    return sdk.home/PROFILE_AUTHORIZATIONS/(b['operationCommitment']+'.json')


def require_profile_authorization(sdk,b,host_profile,*,now=None,remaining=PROFILE_RUN_MARGIN_SECONDS):
    """Fail closed unless the owner authorized exactly this operation: a private record whose every field equals
    the binding's and that stays valid for at least `remaining` more seconds. run() checks it before any worker
    check, consent key or authority, and again under the operation lock immediately before authority; the margin
    there exceeds the consent grant's lifetime, so the grant cannot outlive the authorization."""
    _profile_scope(b,host_profile)
    path=profile_authorization_path(sdk,b)
    try:info=os.lstat(no_links(path))
    except FileNotFoundError:
        raise ValueError('PROFILE_NATIVE_AUTHORIZATION_REQUIRED: no owner authorization for operation '+b['operationCommitment']) from None
    import stat
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_mode&0o077==0,'PROFILE_NATIVE_AUTHORIZATION_REQUIRED')
    value=load(path,65536);expected=_profile_authorization_fields(b)
    now=int(time.time()) if now is None else now
    require(type(value) is dict and set(value)==set(expected)|{'notBeforeUnix','expiresUnix'}
            and {k:value[k] for k in expected}==expected,'PROFILE_NATIVE_AUTHORIZATION_REQUIRED')
    begin,end=value['notBeforeUnix'],value['expiresUnix']
    require(type(now) is int and type(begin) is int and type(end) is int and type(remaining) is int and remaining>=0
            and begin<=now<end and end-now>=remaining and 0<end-begin<=PROFILE_AUTHORIZATION_SECONDS,'PROFILE_NATIVE_AUTHORIZATION_EXPIRED')
    return value


def _open_profile_attempt(sdk,b,authorization):
    """The one-shot attempt of a profile-overlay operation, opened by run() itself under the operation lock right
    after the authoritative authorization check and before any host observation, consent or worker: an
    authorization refusal never consumes the attempt, and everything after this marker closes the operation."""
    attempts=sdk.home/'scenarios/execution-attempts';attempts.mkdir(mode=0o700,exist_ok=True);sync(attempts.parent)
    marker=attempts/(b['operationCommitment']+'.json')
    try:save(marker,{'operationCommitment':b['operationCommitment'],'status':'ATTEMPT_STARTED','openedBy':'cases.scenario.api.run','automaticRetry':False,
                     'profileAuthorizationSha256':digest(canonical(authorization)),'profileAuthorizationExpiresUnix':authorization['expiresUnix']})
    except FileExistsError:
        raise ValueError('OPERATION_ALREADY_ATTEMPTED') from None
    return marker


def authorize_profile(sdk,capture,*,expected_operation,local_owner=False,now=None):
    """The owner's authorization of one exact profile-overlay operation, written once. It runs the worker's
    identity and input checks (no EVM) and creates no consent, attempt marker or run directory."""
    require(local_owner is True,'EXPLICIT_LOCAL_OWNER_REQUIRED')
    require(type(expected_operation) is str and re.fullmatch('[0-9a-f]{64}',expected_operation),'OPERATION_COMMITMENT_REQUIRED')
    b=prepare(sdk,capture,host_profile=PROFILE_HOST)
    _profile_scope(b,PROFILE_HOST)
    require(expected_operation==b['operationCommitment'],'EXACT_PROFILE_OPERATION_REQUIRED')
    checked=check(sdk,capture)
    closed=[Path(b['outputPath']).exists(),(sdk.home/'scenarios/consents'/b['planId']).exists(),
            (sdk.home/'scenarios/execution-attempts'/(expected_operation+'.json')).exists()]
    require(not any(closed),'OPERATION_ALREADY_CLOSED_OR_STARTED')
    now=int(time.time()) if now is None else now
    value=dict(_profile_authorization_fields(b),notBeforeUnix=now,expiresUnix=now+PROFILE_AUTHORIZATION_SECONDS)
    sdk.registry._prepare();directory=sdk.home/PROFILE_AUTHORIZATIONS
    directory.mkdir(mode=0o700,parents=True,exist_ok=True);sync(directory.parent)
    require(directory.stat().st_mode&0o077==0,'PRIVATE_AUTHORIZATION_DIRECTORY_REQUIRED')
    path=profile_authorization_path(sdk,b)
    try:save(path,value)
    except FileExistsError:
        raise ValueError('PROFILE_NATIVE_AUTHORIZATION_EXISTS') from None
    path.chmod(0o600);sync(directory)
    return {'status':'PROFILE_NATIVE_AUTHORIZATION_RECORDED','operationCommitment':expected_operation,'scenarioCommitment':b['scenarioCommitment'],
            'authorization':str(path),'notBeforeUnix':value['notBeforeUnix'],'expiresUnix':value['expiresUnix'],'inputAuthentication':checked['status'],
            'scope':'ONE_RUN_OF_THIS_OPERATION','consent':'NOT_CREATED','attemptMarker':'NOT_CREATED','nativeExecutions':0}


def run(sdk,capture,*,local_owner=False,mac_ready=False,host_profile='v2',expected_operation=None):
    require(local_owner is True and mac_ready is True,'EXPLICIT_LOCAL_OWNER_AND_READY_MAC_REQUIRED')
    import platform,sys
    require(sys.platform=='darwin' and platform.machine()=='arm64','SUPPORTED_SCENARIO_HOST')
    if host_profile!='v2':
        from ..workflow import active_group
        require(active_group() is not None,'OWNED_WORKFLOW_CONTEXT_REQUIRED')
    b=prepare(sdk,capture,host_profile=host_profile)
    if host_profile!='v2':require(expected_operation==b['operationCommitment'],'EXACT_V3_OPERATION_REQUIRED')
    elif expected_operation is not None:require(expected_operation==b['operationCommitment'],'EXACT_V2_OPERATION_REQUIRED')
    profile_gate=b['profile']==PROFILE_OVERLAY_PROFILE
    if profile_gate:require_profile_authorization(sdk,b,host_profile)
    capture,v,plan,spec=_input(sdk,capture);r=runtime(sdk);check(sdk,capture)
    out=Path(b['outputPath']);out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    key_path=sdk.home/'scenarios/.consent.key';require(key_path.stat().st_uid==os.getuid() and key_path.stat().st_mode&0o077==0,'PRIVATE_SCENARIO_KEY_REQUIRED');key=read(key_path,32);require(len(key)==32,'SCENARIO_KEY_SIZE')
    lock,supervise,cleanup,admission=native.guards();began=time.monotonic()
    with lock(sdk.home):
        if profile_gate:
            # Authoritative check, then the attempt marker, before anything else under the lock.
            authorization=require_profile_authorization(sdk,b,host_profile)
            _open_profile_attempt(sdk,b,authorization)
        from . import power
        preflight=sdk.home/'scenarios/preflight';preflight.mkdir(mode=0o700,exist_ok=True)
        power_dir=preflight/plan['planId'];power.observe(power_dir)
        # Reauthenticate after prerequisite checks and before consuming authority.
        require(b==prepare(sdk,capture,host_profile=host_profile),'SCENARIO_PREFLIGHT_DRIFT')
        if host_profile!='v2':
            host=host_profile_module(host_profile)[0]
            admission,supervise=host.admission,host.supervise
            r=dict(r,files=dict(r['files'],sensor=b['hostAdmission']['sensor']))
        if profile_gate:
            # The same record, still valid; the grant cannot outlive it.
            require(require_profile_authorization(sdk,b,host_profile,remaining=180)==authorization,'PROFILE_NATIVE_AUTHORIZATION_CHANGED')
            grant=authority.issue(sdk.home/'scenarios/consents',b,key,not_after=authorization['expiresUnix'])
        else:grant=authority.issue(sdk.home/'scenarios/consents',b,key)
        body=authority.consume(grant,sdk.home/'scenarios/consents',b,key)
        return _execute(sdk,capture,out,b,r,body,began,supervise,cleanup,admission,power_dir)


def _execute(sdk,capture,out,b,r,body,began,supervise,cleanup,admission,power_dir=None):
    out.mkdir(mode=0o700);sync(out.parent);rt=out/'runtime';rt.mkdir(mode=0o700)
    raw=canonical(body)+b'\n';save(rt/'STARTED.json',{'operationCommitment':b['operationCommitment'],'authoritySha256':digest(raw),'authorityConsumed':True})
    result={'status':'INTERRUPTED_UNVERIFIED','profile':b['profile'],'hostAdmissionProfile':b.get('hostAdmission',{'profile':'v2'})['profile'],'operationCommitment':b['operationCommitment'],'scenarioCommitment':b['scenarioCommitment'],'producerInvocations':0,'RPC':0,'WSS':0,'operationPermanentlyClosed':True,'externalDelivery':'HOLD'}
    dispatched=False;measured=None;admission_started=False
    def interrupt(signum,frame):raise InterruptedError('SCENARIO_WORKFLOW_INTERRUPTED')
    require(signal.getitimer(signal.ITIMER_REAL)[0]==0,'CALLER_TIMER_ACTIVE');old={s:signal.signal(s,interrupt) for s in [signal.SIGALRM,signal.SIGINT,signal.SIGTERM]};signal.setitimer(signal.ITIMER_REAL,max(.001,135-(time.monotonic()-began)))
    try:
        for name in ['inputs','artifacts']:(out/name).mkdir(mode=0o700)
        shutil.copyfile(capture/'SCENARIO.json',out/'inputs/SCENARIO.json');require(sha(out/'inputs/SCENARIO.json')==b['scenarioSha256'],'SCENARIO_STAGING_DRIFT')
        for name,target in [('worker','rhook-saved-pair'),('sensor','rhook-host-sensor')]:
            shutil.copyfile(r['files'][name]['path'],out/'artifacts'/target);require(sha(out/'artifacts'/target)==r['files'][name]['sha256'],'SCENARIO_ARTIFACT_STAGING_DRIFT');(out/'artifacts'/target).chmod(0o700)
        save(out/'BINDING.json',b);save(rt/'AUTHORITY.json',body)
        if power_dir is not None:shutil.copytree(power_dir,rt/'POWER')
        admission_started=True;decision,samples=admission(out/'artifacts/rhook-host-sensor',rt/'HOST')
        if 'hostAdmission' in b:
            require(decision['profile']==b['hostAdmission']['profile']
                    and sha(out/'artifacts/rhook-host-sensor')==b['hostAdmission']['sensor']['sha256'],'HOST_ADMISSION_PROFILE_DRIFT')
        save(rt/'HOST_ADMISSION.json',{'accepted':True,'profile':b['profile'],'policySha256':POLICY_SHA,'decision':decision,
                                     'hostAdmission':b.get('hostAdmission',{'profile':'v2'})})
        require(time.monotonic()-began<10,'SCENARIO_PREPARATION_ADMISSION_DEADLINE');save(rt/'DISPATCH_INTENT.json',{'operationCommitment':b['operationCommitment']})
        dispatched=True;result['producerInvocations']=None;measured=supervise(raw,out,out/'artifacts/rhook-host-sensor',samples[-1]);result['resources']=measured
        from . import outcome
        completion=outcome.require_stage(rt,b['operationCommitment'],measured)
        require(completion['operationCommitment']==b['operationCommitment'] and completion['RPC']==0 and completion['WSS']==0,'SCENARIO_COMPLETION_LINK')
        value=completion['result'];count=completion['producerEntries'];require(type(count) is int and 0<=count<=2 and value['producerInvocations']==count,'SCENARIO_INVOCATION_COUNTS')
        result.update(producerInvocations=count,rawTerminal=value['status'],failure=value.get('failure'))
        require(measured['workerReaped'] and measured['exitCode']==0 and measured['stop'] is None and measured['resourcesReliable'] and measured['wallSeconds']<=120 and measured['workerAndObserverCpuSeconds']<=120 and measured['sampledPeakWorkerRSS']<=1<<30,'SCENARIO_NATIVE_OR_RESOURCE_STOP')
        require(value['status']=='SCENARIO_EXECUTED_UNQUALIFIED' and count==2 and value['ownedBridgesClosed'] is True and len(value['worlds'])==2,'SCENARIO_PAIR_COMPLETION_REQUIRED')
        require(time.monotonic()-began<=140,'SCENARIO_NATIVE_STAGE_DEADLINE');signal.setitimer(signal.ITIMER_REAL,0)
        checked=_helper(sdk,['--verify',out/'inputs/SCENARIO.json',rt/'scenario/FINAL.json'],min(45,max(.001,180-(time.monotonic()-began))))
        require(checked['status']=='SCENARIO_RECORDED_INTEGRITY_PASS','SCENARIO_VERIFICATION_FAILED');save(rt/'VERIFIED.json',checked)
        require(time.monotonic()-began<=180,'SCENARIO_WORKFLOW_DEADLINE');result['status']='SCENARIO_COMPLETED'
    except BaseException as error:
        from . import outcome
        outcome.apply_failure(result,error);result['status']='HOST_STOP' if not dispatched else 'SCENARIO_STOP'
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        for s,h in old.items():signal.signal(s,h)
    try:clean=cleanup(out,dispatched,measured,admission_started)
    except BaseException as error:
        clean=False;result['cleanupError']=type(error).__name__+': '+str(error)[:400]
    if dispatched:
        from . import outcome
        diagnostics=outcome.inspect_stage(rt,b['operationCommitment'],measured).diagnostics
        result['nativeDiagnostics']=diagnostics
        clean=clean and diagnostics['processTermination']==diagnostics['engineBridgeClosure']=='CONFIRMED'
    result.update(cleanupConfirmed=clean,workerDispatchAttempted=dispatched,elapsedSeconds=time.monotonic()-began,runDirectory=str(out))
    if not clean:result['status']='INTERRUPTED_UNVERIFIED'
    native.seal_result(out,result);return result


def verify(sdk,run):
    out=no_links(run);require(out.parent==sdk.home/'scenarios/runs','SCENARIO_RUN_HOME')
    result=load(out/'RESULT.json',65536);require(result['status']=='SCENARIO_COMPLETED' and result['cleanupConfirmed'] is True,'COMPLETED_SCENARIO_REQUIRED')
    manifest=load(out/'MANIFEST.json',1<<20)['files']
    for name,pin in manifest.items():require(sha(out/name)==pin,'SCENARIO_RUN_INTEGRITY')
    b=load(out/'BINDING.json',65536);require(b['profile'] in PROFILES and b['operationCommitment']==result['operationCommitment'] and b['scenarioSha256']==sha(out/'inputs/SCENARIO.json'),'SCENARIO_RUN_BINDING')
    body=dict(b);pin=body.pop('operationCommitment')
    require(pin==digest(b'rhook/scenario-operation/0.1\n'+canonical(body)),'SCENARIO_OPERATION_DRIFT')
    if 'hostAdmission' in b:
        require(b['hostAdmission']==select_host(sdk,b['hostAdmission']['profile'])
                and b['sdkFilesCommitment']==b['hostAdmission']['sdkFilesCommitment'],'SCENARIO_HOST_BINDING_DRIFT')
        require(sha(out/'artifacts/rhook-host-sensor')==b['hostAdmission']['sensor']['sha256'],'SCENARIO_HOST_SENSOR_DRIFT')
    spec=load(out/'inputs/SCENARIO.json',8<<20);registered=runtime(sdk)
    domain=DOMAINS[b['profile']]
    require(spec.get('schema')==domain and registered['profile']==b['profile'],'SCENARIO_VERIFICATION_PROFILE')
    checked=_helper(sdk,['--verify',out/'inputs/SCENARIO.json',out/'runtime/scenario/FINAL.json'],45)
    return dict(checked,runDirectory=str(out),scenarioCommitment=result['scenarioCommitment'],executionMode='HYPOTHETICAL_SCENARIO',canonicalActualComparison='NOT_APPLICABLE',hostAdmission=b.get('hostAdmission',{'profile':'v2'}))


def compare(sdk,run):
    verified=verify(sdk,run);out=no_links(run);spec=load(out/'inputs/SCENARIO.json',8<<20);value=load(out/'runtime/scenario/FINAL.json',8<<20)
    token=select_pool()['poolKey']['currency1'];actor=spec['commonSetup']['actor'];actor_topic='0x'+actor[2:].rjust(64,'0');transfer='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
    projections=[]
    for world in value['worlds']:
        receipt=world['receipts'][1];net=0;fees=[]
        for log in receipt['logs']:
            if log['address']==token and len(log['topics'])==3 and log['topics'][0]==transfer and len(log['data'])==66:
                amount=int(log['data'],16)
                if log['topics'][2]==actor_topic:net+=amount
                if log['topics'][1]==actor_topic:net-=amount
            # Uniswap v4 Swap(uint24 fee) is the sixth non-indexed ABI word.
            if log['address']==select_pool()['contracts']['poolManager']['address'] and len(log['topics'])==3 and log['topics'][0]=='0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f' and log['topics'][1]==select_pool()['poolId'] and len(log['data'])==386:
                fees.append(int(log['data'][-64:],16))
        projections.append({'world':world['world'],'receiptStatus':int(receipt['status'],16),'gasUsed':int(receipt['gasUsed'],16),'actorRhookTransferNetBaseUnits':str(net),'outerSwapFeePips':fees,'stateRoot':world['stateRoot'],'receiptsRoot':world['receiptsRoot'],'actorBalanceAfterWei':world['actorBalanceAfter']})
    return {'status':'VERIFIED_SCENARIO_COMPARISON','scenarioCommitment':verified['scenarioCommitment'],'hostAdmissionProfile':verified['hostAdmission']['profile'],'worlds':projections,'rhookTransferNetDeltaBaseUnits':str(int(projections[1]['actorRhookTransferNetBaseUnits'])-int(projections[0]['actorRhookTransferNetBaseUnits'])),'gasDelta':projections[1]['gasUsed']-projections[0]['gasUsed'],'canonicalActualComparison':'NOT_APPLICABLE','verification':'RECORDED_INTEGRITY_NO_INDEPENDENT_EVM_REEXECUTION','qualifiedClaims':0}
