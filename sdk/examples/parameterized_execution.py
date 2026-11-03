"""Developer workflow for one chosen lpBps: plan -> doctor -> ready -> (one owner-consented run) -> result.

    python3 -B examples/parameterized_execution.py --home HOME --lp-bps 37 \
        --scenario SCENARIO.json --sha256 HEX --checkpoint CHECKPOINT.json      # first time: pin the session
    python3 -B examples/parameterized_execution.py --home HOME --lp-bps 37 --session SESSION_ID \
        --runtime RUNTIME.json --sensor rhook-host-sensor                         # Stage B inputs, once per home

Without --operation it stops after printing the exact operationCommitment. The native run happens only when
--operation, --local-owner and --mac-ready are all given, and only once: the operation is closed afterwards,
whatever the result. A verified variant is never run again; its result is printed instead. Run it from a
regular macOS Terminal: app and agent sandboxes that forbid /bin/ps stop at the doctor, before any consent.
"""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True


def say(text):
    print(text, file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--sdk-root', type=Path, default=Path(__file__).resolve().parents[1], help='Installed prefix/lib or source sdk directory')
    p.add_argument('--home', type=Path, required=True)
    p.add_argument('--lp-bps', type=int, required=True, help='Replacement LP Rewards bps, 0-99 (the baseline is 100)')
    p.add_argument('--session', help='Existing session id; otherwise pin one with --scenario, --sha256 and --checkpoint')
    p.add_argument('--scenario', type=Path); p.add_argument('--sha256'); p.add_argument('--checkpoint', type=Path)
    p.add_argument('--runtime', type=Path, help='Reviewed runtime manifest, if this home has none registered')
    p.add_argument('--sensor', type=Path, help='Reviewed macos-host-admission-v4 sensor, if this home has none registered')
    p.add_argument('--operation', help='The exact operationCommitment printed by the ready step')
    p.add_argument('--local-owner', action='store_true'); p.add_argument('--mac-ready', action='store_true')
    args = p.parse_args(argv)
    if (args.operation is not None) != (args.local_owner and args.mac_ready):
        p.error('a run needs --operation together with --local-owner and --mac-ready; without them nothing is run')
    sys.path.insert(0, str(args.sdk_root))
    from developer.files import load
    from rhook_alpha.execution import ExecutionSDK, ExecutionError
    from rhook_alpha.session import SessionError
    from rhook_alpha.session.workflow import render
    sdk = ExecutionSDK(args.home)
    try:
        if args.session is not None:
            verified = [v for v in sdk.open_session(args.session).variants()
                        if v['descriptor']['replacement'] == args.lp_bps and v['status'] == 'RECORDED_RUN_VERIFIED']
            if verified:
                card = sdk.lp_variant_result(args.session, lp_bps=args.lp_bps)
                say('Already verified; a variant keeps its first run.\n' + render(card))
                print(json.dumps(dict(step='result', result=card)))
                return 0
        say(f'1. plan lpBps {args.lp_bps} (offline: session, variant, static coverage, preparation)')
        plan = sdk.plan_lp_variant(args.lp_bps, session_id=args.session, source=args.scenario, expected_sha256=args.sha256,
                                   checkpoint=None if args.checkpoint is None else load(args.checkpoint, 65536))
        say(f"   {plan['status']}; static coverage {(plan['staticCoverage'] or {}).get('status')}; session {plan['sessionId']}")
        if plan['readiness']['status'] != 'READY_FOR_STAGE_B':
            print(json.dumps(dict(step='plan', plan=plan)))
            return 1
        say('2. doctor (read-only: platform, /bin/ps telemetry, power and lid)')
        doctor = sdk.doctor()
        for c in doctor['checks']:
            say(f"   {'OK ' if c['ok'] else 'BAD'} {c['check']}" + ('' if c['ok'] else f"  {c['nextStep']}"))
        say('3. ready (Stage B: registration, input authentication, exact operation; no consent)')
        ready = sdk.ready_lp_variant(plan['sessionId'], lp_bps=args.lp_bps, runtime=args.runtime, sensor=args.sensor)
        say(f"   {ready['status']}; operationCommitment {ready['operationCommitment']}")
        if args.operation is None or ready['status'] != 'RUN_READY':
            say('   Stopping here. Review the operation; ' + ready['next']['step'])
            print(json.dumps(dict(step='ready', ready=ready)))
            return 0 if ready['status'] == 'RUN_READY' else 1
        say('4. run (one native execution of exactly this operation, then verification; never retried)')
        run = sdk.run_lp_variant(plan['sessionId'], lp_bps=args.lp_bps, operation=args.operation,
                                 local_owner=args.local_owner, mac_ready=args.mac_ready)
        say(f"   {run['status']}")
        if run['status'] == 'RUN_VERIFIED':
            say(render(run['result']))
        print(json.dumps(dict(step='run', run=run)))
        return 0 if run['status'] == 'RUN_VERIFIED' else 1
    except (SessionError, ExecutionError) as error:
        print(json.dumps(error.as_result()))
        return 1


if __name__ == '__main__':
    sys.exit(main())
