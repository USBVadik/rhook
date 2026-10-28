"""Supported prepared Hookr scenario. Default modes never start a native producer."""
import argparse
from pathlib import Path
import sys
sys.dont_write_bytecode=True


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk-root',type=Path,default=Path(__file__).resolve().parents[1],help='Installed prefix/lib or source sdk directory')
    p.add_argument('--home',type=Path,required=True)
    p.add_argument('--prepared',type=Path)
    p.add_argument('--witness',type=Path)
    p.add_argument('--witness-sha256')
    p.add_argument('--lp-bps',type=int,default=50,help='Preparation only; execution uses the reviewed prepared input')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--operation')
    p.add_argument('--evidence',type=Path)
    p.add_argument('--local-owner',action='store_true')
    p.add_argument('--mac-ready',action='store_true')
    p.add_argument('--host-admission',choices=('v2','macos-host-admission-v3'),default='v2')
    args=p.parse_args(argv)
    sys.path.insert(0,str(args.sdk_root))
    import json
    from rhook_alpha.execution import ExecutionSDK,ExecutionError
    sdk=ExecutionSDK(args.home)
    native_result=None;stage='PREPARATION_OR_CAPABILITIES'
    try:
        if args.execute:
            # The API checks consent first; missing paths are never execution permission.
            if args.local_owner is not True or args.mac_ready is not True:
                raise ExecutionError('EXACT_LOCAL_CONSENT_REQUIRED','Review the operation and explicitly confirm owner consent and current AC/open-lid conditions.')
            if args.prepared is None or args.operation is None or args.evidence is None:
                raise ExecutionError('EXACT_OPERATION_AND_PATHS_REQUIRED','Provide the existing prepared input, exact reviewed operation and fresh evidence directory.')
            stage='NATIVE_EXECUTION'
            result=sdk.run(args.prepared,operation=args.operation,evidence=args.evidence,
                           local_owner=args.local_owner,mac_ready=args.mac_ready,host_profile=args.host_admission)
            native_result=dict(result)
            if result['status']=='EXECUTION_COMPLETED':
                # Separate read-only commands, outside the180-second replay workflow.
                stage='READ_ONLY_VERIFICATION'
                result['verified']=sdk.verify(Path(result['runDirectory']))
                stage='READ_ONLY_COMPARISON'
                result['comparison']=sdk.compare(Path(result['runDirectory']))
        elif args.witness is not None and args.prepared is not None:
            if args.witness_sha256 is None:
                raise ExecutionError('WITNESS_SHA256_REQUIRED','Supply the independently pinned prepared witness SHA-256.')
            cp=dict(chainId=4663,blockNumber=99236464,
                    blockHash='0x3d8a7eff122421e924553d9ca0949e10c919da1703b3ddd07f8433999e6d0fd9',
                    stateRoot='0x7a947171a7c1620561d1ea629e1233d078518f422ddcb9ff8dcff346ae3624be')
            config=sdk.configure(lp_bps=args.lp_bps,checkpoint=cp)
            result=sdk.prepare(config,args.witness,expected_sha256=args.witness_sha256,output=args.prepared)
        else:
            result=sdk.capabilities(witness=args.witness)
    except ExecutionError as error:result=error.as_result()
    except (OSError,ValueError,TypeError) as error:
        result=ExecutionError('EXAMPLE_INPUT_OR_RUNTIME_STOP','Inspect the exact input/runtime error; no automatic retry is performed.',{'error':str(error)[:1024]}).as_result()
    if native_result is not None and result['status']=='EXECUTION_INPUT_OR_RUNTIME_STOP':
        result.update(nativeExecution=native_result,failedStage=stage)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result['status'] in ('EXECUTION_CAPABILITIES','EXECUTION_PREPARED','EXECUTION_COMPLETED') else 1


if __name__=='__main__':raise SystemExit(main())
