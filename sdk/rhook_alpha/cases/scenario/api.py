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


def configure(sdk,*,pool_id=None,lp_bps=50,profile=PROFILE):
    p=select_pool(pool_id)
    require((profile==PROFILE and type(lp_bps) is int and 0<=lp_bps<=99) or (profile==DYNAMIC_PROFILE and type(lp_bps) is int and lp_bps==100),'LP_BPS_0_TO_99_REQUIRED')
    sdk.registry._prepare();ref='c-'+secrets.token_hex(16)
    directory=sdk.home/'scenarios/plans'/ref;directory.mkdir(mode=0o700,parents=True);sync(directory.parent)
    value={'schema':'rhook/scenario-plan/0.1','planId':ref,'profile':PROFILE,'intent':{'schema':'rhook/on-demand-hookr-intent/0.1','poolId':p['poolId'],'lpBps':lp_bps},
           'assumptions':{'simulatedBuyWei':'1000000000000000','commonFundingMintWei':'1000000000000000000','caller':'PUBLIC_SIMULATION_SIGNER_NEVER_FUND_OR_BROADCAST','nonce':0,'gas':10000000,'syntheticL1BaseFeeWei':'1000000000','independentWorlds':True,'canonicalActualComparison':'NOT_APPLICABLE'}}
    if profile==DYNAMIC_PROFILE:
        from ...dynamic_fee import intent
        value.update(profile=profile,intent=intent(p['poolId']))
    value['planCommitment']=digest(canonical(value));save(directory/'PLAN.json',value)
    return dict(value,status='SCENARIO_PLANNED',executionAuthorized=False,results=None)


def describe(sdk,ref):
    require(type(ref) is str and re.fullmatch('c-[0-9a-f]{32}',ref),'SCENARIO_PLAN_ID')
    value=load(sdk.home/'scenarios/plans'/ref/'PLAN.json',65536);body=dict(value);pin=body.pop('planCommitment')
    require(pin==digest(canonical(body)) and value['planId']==ref and value['profile'] in (PROFILE,DYNAMIC_PROFILE) and value['schema']=='rhook/scenario-plan/0.1','SCENARIO_PLAN_DRIFT')
    select_pool(value['intent']['poolId'])
    if value['profile']==DYNAMIC_PROFILE:
        from ...dynamic_fee import intent
        require(value['intent']==intent(value['intent']['poolId']),'DYNAMIC_PLAN_INTENT')
    else:require(type(value['intent']['lpBps']) is int and 0<=value['intent']['lpBps']<=99,'LP_BPS_DOMAIN')
    return value


def _identity(runtime):
    native.python_required()
    require(type(runtime) is dict and set(runtime)=={'schema','profile','sourceCommitment','policySha256','files'},'SCENARIO_RUNTIME_FIELDS')
    require(runtime['schema']=='rhook/scenario-runtime/0.1' and runtime['profile'] in (PROFILE,DYNAMIC_PROFILE) and runtime['policySha256']==POLICY_SHA,'SCENARIO_RUNTIME_PROFILE')
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
    domain=DYNAMIC_DOMAIN if plan['profile']==DYNAMIC_PROFILE else 'rhook/hookr-scenario/0.1'
    require(spec['schema']==domain and pin==digest((domain+'\n').encode()+canonical(body)) and pin==v['scenarioCommitment'],'SCENARIO_SPEC_COMMITMENT')
    if plan['profile']==DYNAMIC_PROFILE:
        from ...dynamic_fee import validate_spec
        validate_spec(spec)
    require(spec['poolId']==plan['intent']['poolId'] and (int(spec['configurations']['variant'][0],16)>>160)&65535==plan['intent']['lpBps'],'SCENARIO_PLAN_LINK')
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


def register_host(sdk,sensor):
    from . import host_v3
    sensor=no_links(sensor)
    sdk.registry._prepare();directory=sdk.home/'scenarios';directory.mkdir(mode=0o700,exist_ok=True)
    value={'profile':host_v3.PROFILE,'policySha256':host_v3.POLICY_SHA,
           'sensor':{'path':str(sensor),'sha256':sha(sensor)},
           'sdkFilesCommitment':digest(canonical(host_v3.sdk_files()))}
    save(directory/'HOST_V3.json',value)
    return dict(value,status='HOST_PROFILE_REGISTERED',executionAuthorized=False)


def select_host(sdk,profile):
    if profile=='v2':return {'profile':'v2'}
    from . import host_v3
    require(profile==host_v3.PROFILE,'UNSUPPORTED_HOST_PROFILE')
    value=load(sdk.home/'scenarios/HOST_V3.json',65536)
    require(set(value)=={'profile','policySha256','sensor','sdkFilesCommitment'} and value['profile']==profile
            and value['policySha256']==host_v3.POLICY_SHA
            and value['sdkFilesCommitment']==digest(canonical(host_v3.sdk_files())),'HOST_RUNTIME_DRIFT')
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
    require(plan['profile'] in (PROFILE,DYNAMIC_PROFILE) and r['profile']==plan['profile'],'SCENARIO_CAPTURE_RUNTIME_PROFILE')
    ref=plan['planId'];out=sdk.home/'scenarios/runs'/ref
    b={'schema':'rhook/scenario-operation/0.1','profile':plan['profile'],'planId':ref,'scenarioCommitment':v['scenarioCommitment'],'scenarioSha256':v['scenarioSha256'],
       'binarySha256':r['files']['worker']['sha256'],'sourceCommitment':r['sourceCommitment'],'policySha256':POLICY_SHA,'outputPath':str(out),'ownerUid':os.getuid(),'host':os.uname().nodename,
       'maximumInvocations':{'SCENARIO_BASELINE':1,'SCENARIO_VARIANT':1},'RPC':0,'WSS':0,'automaticRetry':False,'externalDelivery':'HOLD'}
    if host_profile!='v2':
        from ..workflow import PROFILE as WORKFLOW_PROFILE
        b.update(hostAdmission=host,sdkFilesCommitment=host['sdkFilesCommitment'],workflowCaptureProfile=WORKFLOW_PROFILE)
    b['operationCommitment']=digest(b'rhook/scenario-operation/0.1\n'+canonical(b))
    return b


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
    capture,v,plan,spec=_input(sdk,capture);r=runtime(sdk);check(sdk,capture)
    out=Path(b['outputPath']);out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    key_path=sdk.home/'scenarios/.consent.key';require(key_path.stat().st_uid==os.getuid() and key_path.stat().st_mode&0o077==0,'PRIVATE_SCENARIO_KEY_REQUIRED');key=read(key_path,32);require(len(key)==32,'SCENARIO_KEY_SIZE')
    lock,supervise,cleanup,admission=native.guards();began=time.monotonic()
    with lock(sdk.home):
        from . import power
        preflight=sdk.home/'scenarios/preflight';preflight.mkdir(mode=0o700,exist_ok=True)
        power_dir=preflight/plan['planId'];power.observe(power_dir)
        # Reauthenticate after prerequisite checks and before consuming authority.
        require(b==prepare(sdk,capture,host_profile=host_profile),'SCENARIO_PREFLIGHT_DRIFT')
        if host_profile!='v2':
            from . import host_v3
            admission,supervise=host_v3.admission,host_v3.supervise
            r=dict(r,files=dict(r['files'],sensor=b['hostAdmission']['sensor']))
        grant=authority.issue(sdk.home/'scenarios/consents',b,key)
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
    b=load(out/'BINDING.json',65536);require(b['profile'] in (PROFILE,DYNAMIC_PROFILE) and b['operationCommitment']==result['operationCommitment'] and b['scenarioSha256']==sha(out/'inputs/SCENARIO.json'),'SCENARIO_RUN_BINDING')
    body=dict(b);pin=body.pop('operationCommitment')
    require(pin==digest(b'rhook/scenario-operation/0.1\n'+canonical(body)),'SCENARIO_OPERATION_DRIFT')
    if 'hostAdmission' in b:
        require(b['hostAdmission']==select_host(sdk,b['hostAdmission']['profile'])
                and b['sdkFilesCommitment']==b['hostAdmission']['sdkFilesCommitment'],'SCENARIO_HOST_BINDING_DRIFT')
        require(sha(out/'artifacts/rhook-host-sensor')==b['hostAdmission']['sensor']['sha256'],'SCENARIO_HOST_SENSOR_DRIFT')
    spec=load(out/'inputs/SCENARIO.json',8<<20);registered=runtime(sdk)
    domain=DYNAMIC_DOMAIN if b['profile']==DYNAMIC_PROFILE else 'rhook/hookr-scenario/0.1'
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
