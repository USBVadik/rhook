"""Developer-facing prepared-witness execution, separate from recorded playback.

Configuration/import checks are not Merkle authentication. Actual execution is
always delegated to the pinned native scenario backend with nil Source.
"""
import copy
import os
from pathlib import Path
import platform
import re
import sys
from developer.files import canonical, digest, load, no_links, read, save, sha, sync

SDK_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = SDK_ROOT / 'rhook_alpha/cases/scenario'
PROFILE = 'hookr-buy/0.1'
DOMAIN = 'rhook/hookr-scenario/0.1'
CONFIG = 'rhook/developer-execution-config/0.1'
TX = dict(amountInWei='1000000000000000', gas=10000000, fundingWei='1000000000000000000')
LIMITS = dict(nativeWallSeconds=120, nativeCPUSeconds=120, workerRSSBytes=1 << 30,
              stageWallSeconds=140, workflowWallSeconds=180, outputBytes=64 << 20, rpc=0, worlds=2)


class ExecutionError(ValueError):
    """Stable code plus actionable diagnostics; no fabricated successful outcome."""
    def __init__(self, code, next_step, details=None):
        self.code, self.next_step, self.details = code, next_step, details or {}
        super().__init__(code)

    def as_result(self):
        return dict(status='EXECUTION_INPUT_OR_RUNTIME_STOP', causeCode=self.code,
                    nextStep=self.next_step, details=self.details, automaticRetry=False)


def check(ok, code, next_step, details=None):
    if not ok:
        raise ExecutionError(code, next_step, details)


def commit(domain, value):
    return digest(domain.encode() + b'\n' + canonical(value))


def _checkpoint(value):
    check(type(value) is dict and set(value) == {'chainId', 'blockNumber', 'blockHash', 'stateRoot'},
          'CHECKPOINT_FIELDS', 'Provide chainId, blockNumber, blockHash and stateRoot.')
    check(type(value['chainId']) is int and value['chainId'] == 4663,
          'UNSUPPORTED_CHAIN', 'This profile supports Robinhood Chain4663 only.')
    check(type(value['blockNumber']) is int and 0 <= value['blockNumber'] < (1 << 53) - 1,
          'CHECKPOINT_NUMBER', 'Use a safe non-negative integer checkpoint number.')
    for key in ('blockHash', 'stateRoot'):
        check(type(value[key]) is str and re.fullmatch('0x[0-9a-f]{64}', value[key]) and int(value[key], 16) != 0,
              'CHECKPOINT_HASH', 'Provide the exact lowercase32-byte checkpoint hashes.', {'field': key})
    return copy.deepcopy(value)


def _profile():
    try:
        value = load(SCENARIO / 'native/profile.json', 65536)
    except (OSError, ValueError, AttributeError) as error:
        raise ExecutionError('CHAIN_PROFILE_MISSING_OR_INVALID', 'Install the complete SDK source/profile.', {'error': str(error)[:400]}) from error
    valid=(type(value) is dict and value.get('schema') == 'rhook/hookr-scenario-profile/0.1'
           and type(value.get('manifest')) is dict and value['manifest'].get('chainId') == '4663'
           and type(value.get('poolId')) is str and re.fullmatch('0x[0-9a-f]{64}',value['poolId'])
           and type(value.get('baselineConfigWords')) is list and len(value['baselineConfigWords'])==4
           and all(type(w) is str and re.fullmatch('0x[0-9a-f]{64}',w) for w in value['baselineConfigWords']))
    check(valid, 'CHAIN_PROFILE_MISSING_OR_INVALID', 'Restore the complete reviewed Hookr scenario profile.')
    return value


def _input(path, expected_sha256=None):
    try:
        raw = read(path, 8 << 20)
    except FileNotFoundError as error:
        raise ExecutionError('PREPARED_WITNESS_MISSING', 'Supply a local complete SCENARIO.json witness.', {'path': str(path)}) from error
    except (OSError, ValueError) as error:
        raise ExecutionError('PREPARED_WITNESS_FILE_INVALID', 'Use a bounded regular file without symlinks.', {'error': str(error)[:400]}) from error
    if expected_sha256 is not None:
        check(type(expected_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_sha256),
              'WITNESS_SHA256_REQUIRED', 'Pin the prepared input SHA-256 explicitly.')
        check(digest(raw) == expected_sha256, 'PREPARED_WITNESS_HASH_MISMATCH', 'Use the exact reviewed input; do not replace its expected hash to hide drift.')
    from developer.files import strict
    try:
        spec = strict(raw)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ExecutionError('PREPARED_WITNESS_JSON_INVALID', 'Supply strict bounded JSON.', {'error': str(error)[:400]}) from error
    pending = [spec]
    while pending:
        value = pending.pop()
        check(type(value) is not float and not (type(value) is int and abs(value) > (1 << 53) - 1),
              'SCENARIO_INTEGER_ENCODING', 'Use safe integer JSON numbers and decimal strings for uint256 values.')
        if type(value) is dict: pending.extend(value.values())
        elif type(value) is list: pending.extend(value)
    check(type(spec) is dict and 'scenarioCommitment' in spec, 'SCENARIO_COMMITMENT', 'Supply a committed scenario input, not FINAL evidence.')
    body = dict(spec); pin = body.pop('scenarioCommitment')
    check(spec.get('schema') == DOMAIN and pin == commit(DOMAIN, body), 'SCENARIO_COMMITMENT', 'Restore the complete original committed scenario input.')
    return raw, spec


def _shape(spec, profile):
    fields = {'schema','origin','checkpoint','parent','chainConfig','inventory','releaseManifestSha256',
              'poolId','configurations','commonSetup','actions','environment','engine','limits','scenarioCommitment'}
    check(set(spec) == fields and spec['poolId'] == profile['poolId']
          and spec['releaseManifestSha256'] == commit(DOMAIN + '/release', profile['manifest']),
          'UNSUPPORTED_SCENARIO_SHAPE', 'Use the supported Hookr profile and its exact release manifest.')
    cp = _checkpoint(spec['checkpoint']); parent = spec['parent']; env = spec['environment']
    check(type(parent) is dict and type(env) is dict, 'CHECKPOINT_HEADER_FIELDS', 'Supply the complete selected parent header and scenario environment.')
    try:
        linked = (parent['hash'] == cp['blockHash'] and parent['stateRoot'] == cp['stateRoot']
                  and int(parent['number'],16) == cp['blockNumber'] and env['l2BlockNumber'] == cp['blockNumber'] + 1
                  and env['l2Timestamp'] == int(parent['timestamp'],16) + 1
                  and env['poster'] == parent['miner'] and env['syntheticL1BaseFeeWei'] == '1000000000')
    except (KeyError, ValueError, TypeError): linked = False
    check(linked, 'CHECKPOINT_ENVIRONMENT_MISMATCH', 'Keep checkpoint/header/common synthetic environment consistent; native authentication will recompute header identity.')
    check(type(spec['chainConfig']) is str and re.fullmatch('0x(?:[0-9a-f]{2})+',spec['chainConfig']),
          'MISSING_CHAIN_CONFIG', 'Include the authenticated ArbOS61 chain configuration.')
    inventory = spec['inventory']
    check(type(inventory) is dict and set(inventory) == {'nodes','codes'}, 'WITNESS_INVENTORY_FIELDS', 'Supply trie nodes and code preimages.')
    missing = [k for k in ('nodes','codes') if type(inventory[k]) is not list or not inventory[k]]
    check(not missing, 'MISSING_WITNESS_MATERIAL', 'Obtain a complete prepared witness separately; offline execution cannot hydrate missing state.',
          {'missingInventory':missing,'checkpointRoot':cp['stateRoot']})
    for key in ('nodes','codes'):
        check(all(type(v) is str and len(v) <= 2 * 98304 + 2 and re.fullmatch('0x(?:[0-9a-f]{2})+',v) for v in inventory[key]),
              'WITNESS_PREIMAGE_ENCODING', 'Supply bounded hex preimages; native admission checks their Keccak hashes/order/proofs.', {'inventory':key})
    configs = spec['configurations']; mask = 65535 << 160
    try:
        base = configs['baseline']; variant = configs['variant']; lp = (int(variant[0],16) >> 160) & 65535
        valid = (base == profile['baselineConfigWords'] and len(variant) == 4 and base[1:] == variant[1:]
                 and 0 <= lp <= 99 and int(variant[0],16) == ((int(base[0],16) & ~mask) | lp << 160))
    except (KeyError, ValueError, TypeError, IndexError): valid = False
    check(valid, 'LP_ONLY_INTERVENTION', 'Only the supported LP field may differ; baseline must be the pinned LP100 configuration.')
    intent = dict(schema='rhook/on-demand-hookr-intent/0.1',poolId=profile['poolId'],lpBps=lp)
    check(spec['origin'] == dict(kind='AUTHENTICATED_CHECKPOINT_SCENARIO',capsuleId=commit('rhook/scenario-checkpoint/0.1',dict(checkpoint=cp,intent=intent))),
          'SCENARIO_ORIGIN_LINK', 'Restore the checkpoint/intent commitment.')
    setup = spec['commonSetup']; actions = spec['actions']
    actor = '0xd2480fd61af9bc73b8c73e8fdcabceb6f21ea8ff'
    check(setup == dict(actor=actor,fundingWei=TX['fundingWei'],nonce=0,requireOriginalAbsence=True),
          'UNSUPPORTED_TRANSACTION', 'Use the declared public simulation actor, nonce0 and common1ETH funding.')
    check(type(actions) is list and len(actions) == 1, 'UNSUPPORTED_TRANSACTION', 'This profile supports exactly one bounded buy.')
    a = actions[0]
    check(type(a) is dict and set(a) == {'id','nonce','gas','gasPriceWei','amountInWei','minimumOutputBaseUnits','sqrtPriceLimitX96','deadline','signedTransaction'}
          and a['nonce'] == 0 and type(a['gas']) is int and a['gas'] == TX['gas'] and a['amountInWei'] == TX['amountInWei']
          and a['minimumOutputBaseUnits'] == '1' and a['sqrtPriceLimitX96'] == '4295128740' and a['deadline'] == env['l2Timestamp'] + 300,
          'UNSUPPORTED_TRANSACTION', 'Use the fixed0.001ETH action,10m gas and declared bounds; arbitrary transactions are unsupported.')
    check(type(a['gasPriceWei']) is str and re.fullmatch('[1-9][0-9]{0,77}',a['gasPriceWei'])
          and int(a['gasPriceWei']) * a['gas'] + int(a['amountInWei']) <= int(setup['fundingWei']),
          'UNSUPPORTED_TRANSACTION', 'The declared gas cost and value must fit common modeled funding.')
    body = dict(a); pin = body.pop('id')
    check(pin == commit(DOMAIN + '/action',body) and type(a['signedTransaction']) is str
          and re.fullmatch('0x(?:[0-9a-f]{2}){1,98304}',a['signedTransaction']),
          'ACTION_COMMITMENT', 'Restore the committed signed simulation action; native admission checks its signature/calldata.')
    check(spec['limits'] == LIMITS, 'SCENARIO_LIMITS', 'Use the unchanged native scenario resource/isolation limits.')
    check(type(spec['engine']) is dict and set(spec['engine']) == {'sourceSha256','binarySha256','policySha256'}
          and all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for v in spec['engine'].values()),
          'SCENARIO_ENGINE_PINS', 'Include source, binary and policy pins matching the explicitly registered runtime.')
    return lp


def _validate_spec(spec, profile):
    try:
        return _shape(spec, profile)
    except ExecutionError:
        raise
    except (KeyError, TypeError, IndexError, ValueError) as error:
        raise ExecutionError('UNSUPPORTED_SCENARIO_SHAPE', 'Supply the complete supported prepared input.', {'error': str(error)[:400]}) from error


class ExecutionSDK:
    """Supported prepared-state workflows; no automatic acquisition or authority."""
    def __init__(self, home):
        self.home = no_links(home)

    def plan_intervention(self, witness, *, expected_sha256, kind, lp_bps=None, node=None):
        """Offline target-state authentication and explicit plan; never authority."""
        from .interventions import plan
        return plan(witness,expected_sha256=expected_sha256,kind=kind,lp_bps=lp_bps,node=node)

    def prepare_intervention(self, descriptor, witness, *, expected_sha256, output, node=None):
        """Reauthenticate saved plans before existing LP preparation; reject new native kinds."""
        from .interventions import validate, execution_configuration
        d=validate(descriptor)
        check(d['sourceInputSha256']==expected_sha256,'INTERVENTION_SOURCE_PIN',
              'Use the original pinned witness that produced this descriptor.')
        fresh=self.plan_intervention(witness,expected_sha256=expected_sha256,kind=d['kind'],lp_bps=d['lpBps'],node=node)
        check(fresh['descriptor']==d,'INTERVENTION_PLAN_MISMATCH',
              'Restore the exact descriptor derived from this witness; saved authentication is never trusted.')
        configuration=execution_configuration(d,self)
        return self.prepare(configuration,witness,expected_sha256=expected_sha256,output=output)

    def _sdk(self):
        check(os.name == 'posix', 'UNSUPPORTED_NATIVE_HOST', 'Use a supported POSIX installation; native execution currently requires macOS arm64.')
        from .cases.api import CaseSDK
        return CaseSDK(self.home)

    def profiles(self):
        p = _profile()
        return [dict(id=PROFILE,backend='nitro-hookr-scenario/0.1',chainId=4663,poolId=p['poolId'],
                     transaction=dict(TX),baselineLpBps=100,configurableLpBps=dict(minimum=0,maximum=99),
                     referenceCheckpoint=99236464,acceptedIntervention=50,
                     witnessCoverage='ONLY_ESTABLISHED_BY_COMPLETED_NATIVE_RUN_FOR_EXACT_INPUT',
                     nativeHost='darwin-arm64',livePreparation='SEPARATE_EXPLICIT_EXISTING_WORKFLOW')]

    def configure(self, *, profile=PROFILE, lp_bps=50, checkpoint=None, transaction=None):
        check(profile == PROFILE, 'UNSUPPORTED_PROFILE', 'Select hookr-buy/0.1; arbitrary pools/profiles are not supported.')
        self.profiles()
        check(type(lp_bps) is int and 0 <= lp_bps <= 99, 'LP_BPS_0_TO_99_REQUIRED', 'Choose an integer replacement0–99; baseline is100.')
        cp = _checkpoint(checkpoint) if checkpoint is not None else None
        check(transaction is None or transaction == TX and all(type(transaction[k]) is type(TX[k]) for k in TX),
              'UNSUPPORTED_TRANSACTION', 'Use the supported fixed amount, gas and common funding.', {'supported':dict(TX)})
        value = dict(schema=CONFIG,status='EXECUTION_CONFIGURED',profile=profile,lpBps=lp_bps,checkpoint=cp,
                     transaction=dict(TX),executionAuthorized=False)
        return dict(value,configCommitment=commit(CONFIG,value))

    def _configuration(self, configuration):
        check(type(configuration) is dict, 'CONFIGURATION_DRIFT', 'Use ExecutionSDK.configure output unchanged.')
        try:
            expected=self.configure(profile=configuration['profile'],lp_bps=configuration['lpBps'],checkpoint=configuration['checkpoint'],transaction=configuration['transaction'])
        except KeyError as error:
            raise ExecutionError('CONFIGURATION_DRIFT','Use the complete configure output.') from error
        check(configuration == expected, 'CONFIGURATION_DRIFT', 'Regenerate an explicit configuration rather than editing committed fields.')
        return expected

    def capabilities(self, *, witness=None):
        missing=[]
        def absent(code, step, details=None):missing.append(dict(code=code,nextStep=step,details=details or {}))
        host=dict(platform=sys.platform,machine=platform.machine(),supported=sys.platform=='darwin' and platform.machine()=='arm64',resourceAdmission='NOT_RUN',powerAndLid='NOT_OBSERVED')
        if not host['supported']:absent('UNSUPPORTED_NATIVE_HOST','Native execution of this profile currently requires macOS arm64.')
        try:profiles=self.profiles()
        except ExecutionError as error:profiles=[];absent(error.code,error.next_step,error.details)
        runtime_path=self.home/'scenarios/RUNTIME.json';components={n:dict(available=False,validation='NO_REGISTRATION') for n in ('worker','node','sensor')};runtime=dict(configured=False,identityChecked=False)
        if not runtime_path.exists():absent('NATIVE_RUNTIME_MISSING','Explicitly register a compatible scenario runtime; no worker is downloaded.')
        else:
            try:
                r=load(runtime_path,2<<20)['runtime'];runtime.update(configured=True,profile=r['profile'])
                for name in ('worker','node','sensor'):
                    row=r['files'][name]
                    try:available=sha(no_links(row['path']))==row['sha256']
                    except (ValueError,OSError):available=False
                    components[name]=dict(available=available,validation='STATIC_SHA256_ONLY' if available else 'MISSING_OR_DRIFTED')
                    if not available:absent('NATIVE_'+name.upper()+'_MISSING_OR_DRIFTED','Restore the explicitly registered artifact.',{'component':name})
            except (ValueError,OSError,KeyError,TypeError) as error:absent('NATIVE_RUNTIME_INVALID','Re-register the runtime from a reviewed manifest.',{'error':str(error)[:400]})
        host['admissionProfiles']={
            'v2':dict(default=True,registered=runtime['configured'] and components['sensor']['available'],validation='REGISTERED_RUNTIME_FILES_ONLY'),
            'macos-host-admission-v3':dict(default=False,optIn=True,registered=False,validation='NOT_REGISTERED')}
        if (self.home/'scenarios/HOST_V3.json').exists():
            try:
                from .cases.scenario import api
                api.select_host(self._sdk(),'macos-host-admission-v3')
                host['admissionProfiles']['macos-host-admission-v3'].update(registered=True,validation='STATIC_SOURCE_AND_SENSOR_PINS_ONLY')
            except (ExecutionError,OSError,ValueError,KeyError,TypeError) as error:
                host['admissionProfiles']['macos-host-admission-v3'].update(validation='INVALID_OR_DRIFTED',causeCode=str(error)[:400],nextStep='Register the matching v3 sensor against this SDK version; no resource observation was made.')
        deps=SDK_ROOT/'engine/adapters/hookr-case/node_modules';dependencies=all((deps/n/'package.json').is_file() for n in ('viem','hookr-sdk'))
        if not dependencies:absent('RUNTIME_DEPENDENCIES_MISSING','Install the existing pinned Node dependencies locally; no automatic download is performed.')
        prepared=dict(available=False,authentication='NOT_EVALUATED',closure='NOT_EVALUATED')
        if witness is None:absent('PREPARED_WITNESS_MISSING','Supply a complete local prepared SCENARIO.json; recorded FINAL files are not execution inputs.')
        else:
            try:
                _,v=_input(witness);_validate_spec(v,_profile());prepared.update(available=True,checkpoint=v['checkpoint'],nodes=len(v['inventory']['nodes']),codes=len(v['inventory']['codes']),authentication='PENDING_NATIVE_ADMISSION')
            except ExecutionError as error:absent(error.code,error.next_step,error.details)
        return dict(status='EXECUTION_CAPABILITIES',profiles=profiles,host=host,runtime=runtime,components=components,
                    dependencies=dict(available=dependencies,validation='PRESENCE_ONLY'),preparedWitness=prepared,
                    recordedEvidenceVerifier=dict(available=(SCENARIO/'recorded.py').is_file(),EVMReexecution=False),
                    livePreparation=dict(automatic=False,providerConfigured=False,credentialInspected=False,interface='Use separately authorized existing CaseSDK live preparation; this facade is offline.'),
                    nativeExecutionReady=False,executionAuthorized=False,staticDependenciesPresent=not missing,
                    requiresExactConsentAndFreshAdmission=True,missing=missing)

    def prepare(self, configuration, witness, *, expected_sha256, output):
        config=self._configuration(configuration);out=no_links(output)
        check(not out.exists(),'FRESH_PREPARED_OUTPUT_REQUIRED','Choose a new directory; existing inputs are never overwritten.')
        raw,spec=_input(witness,expected_sha256);profile=_profile();old_lp=_validate_spec(spec,profile)
        if config['checkpoint'] is not None:
            check(spec['checkpoint']==config['checkpoint'],'CHECKPOINT_MISMATCH','Use a witness for the explicitly selected checkpoint; no checkpoint replacement is performed.')
        value=copy.deepcopy(spec);lp=config['lpBps'];intent=dict(schema='rhook/on-demand-hookr-intent/0.1',poolId=profile['poolId'],lpBps=lp)
        value['configurations']['variant'][0]='0x'+((int(value['configurations']['baseline'][0],16)&~(65535<<160))|(lp<<160)).to_bytes(32,'big').hex()
        value['origin']['capsuleId']=commit('rhook/scenario-checkpoint/0.1',dict(checkpoint=value['checkpoint'],intent=intent))
        value.pop('scenarioCommitment');value['scenarioCommitment']=commit(DOMAIN,value)
        sdk=self._sdk();plan=sdk.configure_scenario(pool_id=profile['poolId'],lp_bps=lp)
        out.mkdir(mode=0o700,parents=True);sync(out.parent);save(out/'SCENARIO.json',value)
        save(out/'SDK_RESULT.json',dict(status='PREPARED_SCENARIO_INPUT',authentication='PENDING_NATIVE_ADMISSION',nativeExecutions=0,
             cleanupConfirmed=True,planId=plan['planId'],planCommitment=plan['planCommitment'],scenarioSha256=sha(out/'SCENARIO.json'),scenarioCommitment=value['scenarioCommitment']))
        result=dict(status='EXECUTION_PREPARED',schema='rhook/developer-prepared-execution/0.1',profile=PROFILE,
                    prepared=str(out),planId=plan['planId'],configuration=config,checkpoint=value['checkpoint'],
                    scenarioSha256=sha(out/'SCENARIO.json'),scenarioCommitment=value['scenarioCommitment'],sourceWitnessSha256=digest(raw),
                    originalLpBps=old_lp,selectedLpBps=lp,authentication='PENDING_NATIVE_ADMISSION',witnessClosure='NOT_EVALUATED',
                    nativeRunDirectory=str(sdk.home/'scenarios/runs'/plan['planId']),nativeExecutions=0,executionAuthorized=False)
        save(out/'PREPARATION.json',result);return result

    def _prepared(self, prepared):
        from .cases.scenario import api
        path=no_links(prepared)
        try:
            meta=load(path/'PREPARATION.json',65536)
            self._configuration(meta['configuration'])
            _,capture,plan,spec=api._input(self._sdk(),path)
            _validate_spec(spec,_profile())
            check(meta['schema']=='rhook/developer-prepared-execution/0.1' and meta['profile']==PROFILE
                  and meta['planId']==plan['planId'] and meta['scenarioSha256']==capture['scenarioSha256']
                  and meta['scenarioCommitment']==spec['scenarioCommitment']
                  and meta['selectedLpBps']==meta['configuration']['lpBps']==plan['intent']['lpBps'],
                  'PREPARATION_DRIFT','Use the unchanged prepared directory and its matching SDK home.')
            cp=meta['configuration']['checkpoint']
            check(cp is None or cp==spec['checkpoint'],'CHECKPOINT_MISMATCH','Use the explicitly selected checkpoint.')
        except ExecutionError:raise
        except (OSError,ValueError,KeyError,TypeError) as error:
            raise ExecutionError('PREPARATION_MISSING_OR_DRIFTED','Prepare a fresh input through this SDK; do not reuse old home/grants.',{'error':str(error)[:400]}) from error
        return path,meta

    @staticmethod
    def _host():
        check(sys.platform=='darwin' and platform.machine()=='arm64', 'UNSUPPORTED_NATIVE_HOST',
              'Native execution of this profile requires macOS arm64 and its registered runtime. Offline preparation/recorded inspection remain separate.')

    def _backend(self, call):
        try:return call()
        except ExecutionError:raise
        except (OSError,ValueError,KeyError,TypeError) as error:
            report=getattr(error,'report',None)
            if report is not None:
                raise ExecutionError('NATIVE_INPUT_AUTHENTICATION_STOP',
                    'Inspect the exact retained helper stderr/evidence. Missing state must be prepared separately; no hydration or retry is performed.',report) from error
            filename=str(getattr(error,'filename',''))
            code='NATIVE_RUNTIME_MISSING' if isinstance(error,FileNotFoundError) and filename.endswith('RUNTIME.json') else 'NATIVE_BACKEND_REJECTED'
            raise ExecutionError(code,'Register the compatible pinned runtime/host and matching SDK installation; preserve existing evidence and do not weaken guards.',{'error':str(error)[:1024]}) from error

    def register_runtime(self, path):
        self._host()
        return self._backend(lambda:self._sdk().register_scenario_runtime(path))

    def register_host(self, sensor):
        self._host()
        return self._backend(lambda:self._sdk().register_scenario_host(sensor))

    def authenticate(self, prepared):
        self._host();path,_=self._prepared(prepared)
        return self._backend(lambda:self._sdk().check_scenario(path))

    def operation(self, prepared, *, host_profile='v2'):
        check(host_profile in ('v2','macos-host-admission-v3'),'UNSUPPORTED_HOST_PROFILE','Choose v2 or the separately registered opt-in macos-host-admission-v3.')
        path,_=self._prepared(prepared)
        result=self._backend(lambda:self._sdk().prepare_scenario(path,host_profile=host_profile))
        return dict(status='EXECUTION_OPERATION_PREPARED',binding=result,
                    operationCommitment=result['operationCommitment'],outputPath=result['outputPath'],
                    executionAuthorized=False,nativeExecutions=0,nativeAuthentication='REQUIRED_AGAIN_BEFORE_AUTHORITY')

    def run(self, prepared, *, operation, evidence, local_owner=False, mac_ready=False, host_profile='v2'):
        # No input, process, resource probe or authority access before direct consent.
        check(local_owner is True and mac_ready is True,'EXACT_LOCAL_CONSENT_REQUIRED',
              'Review the exact operation, confirm AC/open lid and pass explicit local_owner/mac_ready consent.')
        self._host()
        check(type(operation) is str and re.fullmatch('[0-9a-f]{64}',operation),
              'OPERATION_COMMITMENT_REQUIRED','Provide the exact reviewed operation commitment.')
        path,_=self._prepared(prepared);binding=self.operation(path,host_profile=host_profile)
        check(binding['operationCommitment']==operation,'OPERATION_MISMATCH','Stop: use only the exact reviewed binding; do not substitute another operation.')
        sdk=self._sdk();out=no_links(binding['outputPath']);evidence=no_links(evidence)
        attempts=no_links(self.home/'scenarios/execution-attempts');marker=attempts/(operation+'.json')
        check(not marker.exists(),'OPERATION_ALREADY_ATTEMPTED','This attempt is permanently closed. Any successor needs a fresh plan and separate exact consent.')
        check(not out.exists(),'OPERATION_ALREADY_CLOSED_OR_STARTED','Do not retry an existing native operation.')
        check(not evidence.exists(),'FRESH_EVIDENCE_DIRECTORY_REQUIRED','Choose a fresh workflow evidence directory.')
        check(not any(evidence==p or evidence.is_relative_to(p) or p.is_relative_to(evidence) for p in (path,self.home,out)),
              'EVIDENCE_PATH_OVERLAP','Keep workflow evidence separate from prepared input and SDK home.')
        sdk.registry._prepare();attempts.mkdir(mode=0o700,parents=True,exist_ok=True)
        try:save(marker,dict(operationCommitment=operation,automaticRetry=False,prepared=str(path),evidence=str(evidence),status='ATTEMPT_STARTED'))
        except FileExistsError as error:
            raise ExecutionError('OPERATION_ALREADY_ATTEMPTED','Do not retry a concurrent or previous attempt.') from error
        evidence.mkdir(mode=0o700,parents=True);sync(evidence.parent)
        from .cases import native
        bootstrap='import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);from rhook_alpha.cases.__main__ import main;raise SystemExit(main(sys.argv[2:]))'
        command=[sys.executable,'-I','-c',bootstrap,str(SDK_ROOT),'--home',str(self.home),'scenario-run',str(path),
                 '--local-owner','--mac-ready','--host-admission',host_profile,'--operation',operation]
        result=dict(status='EXECUTION_STOP',operationCommitment=operation,runDirectory=str(out),
                    evidenceDirectory=str(evidence),automaticRetry=False,operationPermanentlyClosed=True,
                    cleanupConfirmed=False,nativeResult=None,externalDelivery='HOLD')
        try:
            process,stdout,stderr=native.capture_workflow(command,evidence/'workflow',180,1<<20,1<<20)
            result['workflow']=process
            from developer.files import strict
            try:child=strict(stdout)
            except (ValueError,UnicodeError,RecursionError):child=None
            linked=False
            if type(child) is dict and (out/'RESULT.json').is_file() and (out/'BINDING.json').is_file():
                linked=(load(out/'RESULT.json',65536)==child and child.get('operationCommitment')==operation
                        and load(out/'BINDING.json',65536).get('operationCommitment')==operation)
            diagnostic=child if type(child) is dict else {}
            if diagnostic and not linked:
                result['childDiagnostics']=diagnostic
                result['childDiagnosticsScope']='UNLINKED_STDOUT_NOT_NATIVE_EXECUTION_EVIDENCE'
            if linked:
                result['nativeResult']=child
                if child.get('primaryStop'):result['primaryStop']=child['primaryStop']
            workflow_clean=(process.get('ownedChildReaped') is True and process.get('workflowGroupGone') is True
                            and process.get('cleanupError') is None)
            result['cleanupConfirmed']=workflow_clean and linked and child.get('cleanupConfirmed') is True
            completed=(linked and child.get('status')=='SCENARIO_COMPLETED'
                       and type(child.get('producerInvocations')) is int and child['producerInvocations']==2
                       and child.get('RPC')==0 and child.get('WSS')==0
                       and process.get('exitCode')==0 and not process.get('stop') and result['cleanupConfirmed'])
            if completed:result['status']='EXECUTION_COMPLETED'
            else:
                child_cause=diagnostic.get('causeCode') if diagnostic.get('status')!='SCENARIO_COMPLETED' else None
                result['causeCode']=child_cause or process.get('stop') or ('NATIVE_STOP' if linked else 'UNLINKED_NATIVE_RESULT')
                result['nextStep']=diagnostic.get('nextStep') or 'Preserve raw workflow/native diagnostics. Do not retry this operation or fabricate missing observations.'
        except BaseException as error:
            result.update(causeCode=type(error).__name__+': '+str(error)[:1024],
                          nextStep='Inspect retained workflow evidence; cleanup is unconfirmed and this attempt is closed.')
        save(evidence/'EXECUTION_RESULT.json',result)
        return result

    def verify(self, run):
        self._host()
        return self._backend(lambda:self._sdk().verify_scenario(run))

    def compare(self, run):
        self._host()
        value=self._backend(lambda:self._sdk().compare_scenario(run))
        # Preserve legacy keys, adding accurate target-token names for the facade.
        result=copy.deepcopy(value)
        for world in result.get('worlds',[]):
            world['actorTargetTokenTransferNetBaseUnits']=world['actorRhookTransferNetBaseUnits']
        result['targetTokenTransferNetDeltaBaseUnits']=result['rhookTransferNetDeltaBaseUnits']
        return result
