"""Historical replay and separately profiled hypothetical Hookr scenarios."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from .api import CaseSDK
from ..execution import ExecutionSDK, ExecutionError

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home() / '.local/share/rhook-cases')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('execution-profiles')
    p=sub.add_parser('execution-capabilities');p.add_argument('--witness',type=Path)
    p=sub.add_parser('execution-configure');p.add_argument('--profile',default='hookr-buy/0.1');p.add_argument('--lp-bps',type=int,default=50);p.add_argument('--checkpoint',type=Path);p.add_argument('--transaction',type=Path)
    p=sub.add_parser('execution-prepare');p.add_argument('--configuration',type=Path,required=True);p.add_argument('--witness',type=Path,required=True);p.add_argument('--witness-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('execution-authenticate');p.add_argument('--prepared',type=Path,required=True)
    p=sub.add_parser('execution-operation');p.add_argument('--prepared',type=Path,required=True);p.add_argument('--host-admission',choices=['v2','macos-host-admission-v3'],default='v2')
    p=sub.add_parser('execution-run');p.add_argument('--prepared',type=Path,required=True);p.add_argument('--operation',required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--host-admission',choices=['v2','macos-host-admission-v3'],default='v2');p.add_argument('--local-owner',action='store_true',required=True);p.add_argument('--mac-ready',action='store_true',required=True)
    for command in ('execution-verify','execution-compare'):
        p=sub.add_parser(command);p.add_argument('--run',type=Path,required=True)
    for command in ('scenario-evidence-inspect', 'scenario-evidence-verify', 'scenario-evidence-compare'):
        p = sub.add_parser(command, help='Worker-free pinned recorded-evidence inspection')
        p.add_argument('--bundle', type=Path, required=True)
    for command in ['scenario-diagnostic-prepare', 'scenario-diagnose']:
        p = sub.add_parser(command)
        p.add_argument('--plan', required=True)
        p.add_argument('--scenario', type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
        if command == 'scenario-diagnose':
            p.add_argument('--operation', required=True)
            p.add_argument('--local-owner', action='store_true', required=True)
            p.add_argument('--mac-ready', action='store_true', required=True)
    p = sub.add_parser('scenario-closure-prepare')
    p.add_argument('--plan', required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('scenario-close')
    p.add_argument('--plan', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--credential-file', type=Path, required=True)
    p.add_argument('--account-assertions', type=Path, required=True)
    p.add_argument('--operation', required=True)
    p.add_argument('--local-owner', action='store_true', required=True)
    p.add_argument('--mac-ready', action='store_true', required=True)
    p = sub.add_parser('scenario-pool')
    p.add_argument('--pool')
    p = sub.add_parser('scenario-configure')
    p.add_argument('--pool')
    p.add_argument('--lp-bps', type=int, default=50)
    p = sub.add_parser('scenario-register-runtime')
    p.add_argument('path', type=Path)
    p = sub.add_parser('scenario-register-host')
    p.add_argument('sensor', type=Path)
    p = sub.add_parser('scenario-acquire')
    p.add_argument('--plan', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--credential-file', type=Path, required=True)
    p.add_argument('--account-assertions', type=Path, required=True)
    p.add_argument('--allow-read-only', action='store_true', required=True)
    p = sub.add_parser('scenario-check')
    p.add_argument('capture', type=Path)
    p = sub.add_parser('scenario-run')
    p.add_argument('capture', type=Path)
    p.add_argument('--local-owner', action='store_true', required=True)
    p.add_argument('--mac-ready', action='store_true', required=True)
    p.add_argument('--host-admission', choices=['v2', 'macos-host-admission-v3'], default='v2')
    p.add_argument('--operation')
    p = sub.add_parser('scenario-prepare')
    p.add_argument('capture', type=Path)
    p.add_argument('--host-admission', choices=['v2', 'macos-host-admission-v3'], default='v2')
    for command in ['scenario-verify', 'scenario-compare']:
        p = sub.add_parser(command)
        p.add_argument('--run', type=Path, required=True)
    p = sub.add_parser('package-case')
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--adapter', required=True)
    p.add_argument('--subject-index', type=int, required=True)
    p.add_argument('--input-commitment', required=True)
    p.add_argument('--witness-commitment', required=True)
    p = sub.add_parser('import-case')
    p.add_argument('directory', type=Path)
    p = sub.add_parser('capture-case')
    p.add_argument('--chain', type=int, required=True)
    p.add_argument('--block', type=int, required=True)
    p.add_argument('--subject-index', type=int, required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-read-only', action='store_true', required=True)
    p.add_argument('--witness', type=Path)
    p = sub.add_parser('capture-recent-case')
    p.add_argument('--case-prefix', default='hookr')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-read-only', action='store_true', required=True)
    p.add_argument('--witness', type=Path)
    p = sub.add_parser('watch-case')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--credential-file', type=Path)
    p.add_argument('--account-assertions', type=Path, required=True)
    p.add_argument('--case-prefix', default='hookr')
    p.add_argument('--allow-read-only', action='store_true')
    p = sub.add_parser('qualify-root')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-read-only', action='store_true', required=True)
    p = sub.add_parser('select-recent-case')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-read-only', action='store_true', required=True)
    p = sub.add_parser('forge-case')
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--witness', type=Path)
    p.add_argument('--subject-index', type=int, required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--output', type=Path, required=True)
    for name in ('diagnose', 'check-case'):
        p = sub.add_parser(name)
        p.add_argument('--case', required=True)
        p.add_argument('--trust-checkpoint')
    sub.add_parser('cases')
    sub.add_parser('interventions', help='List only trusted historical descriptor classes; no execution')
    p = sub.add_parser('admission', help='Resolve a proposed checkpoint-state descriptor; not proof or consent')
    p.add_argument('--plan', required=True)
    p = sub.add_parser('assurance', help='Report knowledge obligations separately from world outcomes')
    p.add_argument('--plan', required=True)
    p.add_argument('--evidence', type=Path)
    p = sub.add_parser('inspect')
    p.add_argument('--case', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--case', required=True)
    p.add_argument('--set', required=True)
    p = sub.add_parser('describe')
    p.add_argument('--plan', required=True)
    p = sub.add_parser('register-runtime')
    p.add_argument('runtime', type=Path)
    p = sub.add_parser('authenticate')
    p.add_argument('--case', required=True)
    p.add_argument('--trust-checkpoint')
    p = sub.add_parser('operation', help='Review an exact local binding; no consent or EVM execution')
    p.add_argument('--plan', required=True)
    p.add_argument('--trust-checkpoint', required=True)
    p = sub.add_parser('authorize')
    p.add_argument('--plan', required=True)
    p.add_argument('--local-owner', action='store_true', required=True)
    p.add_argument('--mac-ready', action='store_true', required=True)
    p.add_argument('--trust-checkpoint', required=True)
    p.add_argument('--operation', help='Require the exact previously reviewed operation commitment')
    p = sub.add_parser('replay')
    p.add_argument('--plan', required=True)
    p.add_argument('--authority', required=True, type=Path)
    for name in ('verify', 'compare'):
        p = sub.add_parser(name)
        p.add_argument('--run', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        sdk = CaseSDK(args.home)
        if args.command.startswith('execution-'):
            executor=ExecutionSDK(args.home)
            from developer.files import load
            if args.command=='execution-profiles':value=dict(status='EXECUTION_PROFILES',profiles=executor.profiles())
            elif args.command=='execution-capabilities':value=executor.capabilities(witness=args.witness)
            elif args.command=='execution-configure':value=executor.configure(profile=args.profile,lp_bps=args.lp_bps,checkpoint=load(args.checkpoint,65536) if args.checkpoint else None,transaction=load(args.transaction,65536) if args.transaction else None)
            elif args.command=='execution-prepare':value=executor.prepare(load(args.configuration,65536),args.witness,expected_sha256=args.witness_sha256,output=args.output)
            elif args.command=='execution-authenticate':value=executor.authenticate(args.prepared)
            elif args.command=='execution-operation':value=executor.operation(args.prepared,host_profile=args.host_admission)
            elif args.command=='execution-run':value=executor.run(args.prepared,operation=args.operation,evidence=args.evidence,local_owner=args.local_owner,mac_ready=args.mac_ready,host_profile=args.host_admission)
            elif args.command=='execution-verify':value=executor.verify(args.run)
            else:value=executor.compare(args.run)
        elif args.command == 'scenario-evidence-inspect':
            value = sdk.inspect_recorded_scenario(args.bundle)
        elif args.command == 'scenario-evidence-verify':
            value = sdk.verify_recorded_scenario(args.bundle)
        elif args.command == 'scenario-evidence-compare':
            value = sdk.compare_recorded_scenario(args.bundle)
        elif args.command == 'scenario-diagnostic-prepare':
            from .scenario.diagnostic import prepare
            value = prepare(sdk, args.plan, args.scenario, args.output)
        elif args.command == 'scenario-diagnose':
            from .scenario.diagnostic import run
            value = run(sdk, args.plan, args.scenario, args.output, expected_operation=args.operation,
                        local_owner=args.local_owner, mac_ready=args.mac_ready)
        elif args.command == 'scenario-closure-prepare':
            from .scenario.closure import prepare
            value = prepare(sdk, args.plan, args.output)
        elif args.command == 'scenario-close':
            from .scenario.closure import run_owned
            value = run_owned(sdk, args.plan, args.output, credential_file=args.credential_file,
                        account_assertions=args.account_assertions, expected_operation=args.operation,
                        local_owner=args.local_owner, mac_ready=args.mac_ready)
        elif args.command == 'scenario-pool':
            value = sdk.scenario_pool(args.pool)
        elif args.command == 'scenario-configure':
            value = sdk.configure_scenario(pool_id=args.pool, lp_bps=args.lp_bps)
        elif args.command == 'scenario-register-runtime':
            value = sdk.register_scenario_runtime(args.path)
        elif args.command == 'scenario-register-host':
            value = sdk.register_scenario_host(args.sensor)
        elif args.command == 'scenario-acquire':
            value = sdk.acquire_scenario(args.plan, args.output, credential_file=args.credential_file,
                                         account_assertions=args.account_assertions, read_only=args.allow_read_only)
        elif args.command == 'scenario-check':
            value = sdk.check_scenario(args.capture)
        elif args.command == 'scenario-run':
            value = sdk.run_scenario(args.capture, local_owner=args.local_owner, mac_ready=args.mac_ready, host_profile=args.host_admission, expected_operation=args.operation)
        elif args.command == 'scenario-prepare':
            value = sdk.prepare_scenario(args.capture, host_profile=args.host_admission)
        elif args.command == 'scenario-verify':
            value = sdk.verify_scenario(args.run)
        elif args.command == 'scenario-compare':
            value = sdk.compare_scenario(args.run)
        elif args.command == 'package-case':
            value = sdk.package_case(args.package, args.output, case_id=args.case, adapter=args.adapter, subject_index=args.subject_index, input_commitment=args.input_commitment, witness_commitment=args.witness_commitment)
        elif args.command == 'import-case':
            value = sdk.import_case(args.directory)
        elif args.command == 'capture-case':
            value = sdk.capture_case(args.output, block=args.block, chain=args.chain, subject_index=args.subject_index,
                                     case_id=args.case, read_only=args.allow_read_only, witness=args.witness)
        elif args.command == 'capture-recent-case':
            value = sdk.capture_recent_case(args.output, case_prefix=args.case_prefix, read_only=args.allow_read_only, witness=args.witness)
        elif args.command == 'watch-case':
            value = sdk.watch_case(args.output, credential_file=args.credential_file, account_assertions=args.account_assertions,
                                   case_prefix=args.case_prefix, read_only=args.allow_read_only)
        elif args.command == 'qualify-root':
            value = sdk.qualify_root(args.output, read_only=args.allow_read_only)
        elif args.command == 'select-recent-case':
            value = sdk.select_recent_case(args.output, read_only=args.allow_read_only)
        elif args.command == 'forge-case':
            value = sdk.forge_case(args.package, args.output, case_id=args.case, subject_index=args.subject_index, witness=args.witness)
        elif args.command in ('diagnose', 'check-case'):
            value = getattr(sdk, 'check_case' if args.command == 'check-case' else 'diagnose')(args.case, trusted_checkpoint=args.trust_checkpoint)
        elif args.command == 'cases':
            value = {'status': 'CASES_LISTED', 'cases': sdk.list_cases()}
        elif args.command == 'inspect':
            value = sdk.inspect(args.case)
        elif args.command == 'describe':
            value = dict(sdk.describe(args.plan), status='PLAN_AUTHENTICATED', executionAuthorized=False)
        elif args.command == 'register-runtime':
            value = sdk.register_runtime(args.runtime)
        elif args.command == 'plan':
            match = re.fullmatch('([A-Za-z][A-Za-z0-9]*)=(0|[1-9][0-9]{0,9}|OFF)', args.set)
            if match is None:
                raise ValueError('EXPECTED_RULE_INTEGER_ASSIGNMENT')
            value = sdk.plan(args.case, {'rule': match[1], 'value': 'OFF' if match[2]=='OFF' else int(match[2])})
        elif args.command == 'interventions':
            value = sdk.interventions()
        elif args.command == 'admission':
            value = sdk.admission(args.plan)
        elif args.command == 'assurance':
            value = sdk.assurance(args.plan, evidence=args.evidence)
        elif args.command == 'authenticate':
            value = sdk.authenticate(args.case, trusted_checkpoint=args.trust_checkpoint)
        elif args.command == 'operation':
            value = sdk.operation(args.plan, trusted_checkpoint=args.trust_checkpoint)
        elif args.command == 'authorize':
            options = dict(local_owner=args.local_owner, mac_ready=args.mac_ready, trusted_checkpoint=args.trust_checkpoint)
            if args.operation is not None:
                options['expected_operation'] = args.operation
            grant = sdk.authorize(args.plan, **options)
            value = {'status': 'LOCAL_CONSENT_ISSUED', 'authority': str(grant), 'nativeExecuted': False}
        elif args.command == 'replay':
            value = sdk.replay(args.plan, args.authority)
        elif args.command == 'verify':
            value = sdk.verify(args.run)
        else:
            value = sdk.compare(args.run)
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        if isinstance(error,ExecutionError):value=error.as_result()
        elif type(getattr(error,'report',None)) is dict:
            value={'status':'INPUT_OR_RUNTIME_STOP','causeCode':str(error)[:1024],'automaticRetry':False,
                   'details':error.report,'nextStep':'Inspect retained native helper diagnostics; do not retry a closed operation or invent missing state.'}
        elif args.command.startswith('execution-'):
            value=ExecutionError('EXECUTION_INPUT_OR_RUNTIME_ERROR','Check the selected paths/configuration and complete local installation; no execution was inferred from this error.',{'error':str(error)[:1024]}).as_result()
        else:value={'status': 'INPUT_OR_RUNTIME_STOP', 'causeCode': str(error)[:1024], 'automaticRetry': False}
    print(json.dumps(value, ensure_ascii=True))
    if args.command == 'scenario-diagnostic-prepare' and value.get('schema') == 'rhook/scenario-result-diagnostic/0.1':
        return 0
    if args.command == 'scenario-diagnose' and value.get('status') == 'DIAGNOSTIC_COMPLETED' and value.get('cleanupConfirmed') is True:
        return 0
    if args.command == 'scenario-closure-prepare' and value.get('schema') == 'rhook/scenario-witness-discovery/0.1':
        return 0
    if args.command == 'scenario-close' and value.get('status') == 'SCENARIO_WITNESS_CLOSURE_COMPLETED':
        return 0
    if args.command == 'scenario-prepare' and value.get('schema') == 'rhook/scenario-operation/0.1':
        return 0
    if args.command == 'operation' and value.get('schema') == 'rhook/case-native-request/0.1':
        return 0
    if args.command in {'interventions', 'admission'} and value.get('schema') in {
            'rhook/historical-intervention-catalogue/0.1', 'rhook/checkpoint-state-admission/0.1'}:
        return 0
    if args.command == 'assurance' and value.get('schema') == 'rhook/checkpoint-state-assurance/0.1':
        return 2 if value['status'] == 'UNRESOLVED' else 1
    return 0 if value.get('status') in {'CAPSULE_PACKAGED', 'IMPORTED', 'CASES_LISTED', 'PLANNED', 'PLAN_AUTHENTICATED', 'RUNTIME_REGISTERED', 'PROOFS_VERIFIED_AT_DECLARED_ROOT', 'LOCAL_CONSENT_ISSUED', 'COMPLETED', 'RECORDED_PAIR_INTEGRITY_PASS', 'VERIFIED_COMPARISON',
        'CAPTURED_AUTHENTICATED_CAPSULE', 'AUTHENTICATED_CAPSULE_CREATED', 'AUTHENTICATED_KNOWN_DEPENDENCIES_PRESENT', 'READY_FOR_BOUNDED_NATIVE_ATTEMPT', 'UNAUTHENTICATED_EVENT_SELECTED','FRESH_ROOT_PROOF_AUTHENTICATED','NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW','NO_ELIGIBLE_EVENT_OBSERVED',
        'SUPPORTED_SCENARIO_POOL','SCENARIO_PLANNED','SCENARIO_RUNTIME_REGISTERED','HOST_PROFILE_REGISTERED','AUTHENTICATED_SCENARIO_CAPTURED','AUTHENTICATED_SCENARIO_INPUT','SCENARIO_COMPLETED','SCENARIO_RECORDED_INTEGRITY_PASS','VERIFIED_SCENARIO_COMPARISON',
        'SCENARIO_EVIDENCE_INSPECTED','SCENARIO_EVIDENCE_INTEGRITY_PASS','SCENARIO_EVIDENCE_COMPARISON_PASS',
        'EXECUTION_PROFILES','EXECUTION_CAPABILITIES','EXECUTION_CONFIGURED','EXECUTION_PREPARED','EXECUTION_OPERATION_PREPARED','EXECUTION_COMPLETED'} else 1
if __name__ == '__main__':
    raise SystemExit(main())
