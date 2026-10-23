"""Local saved-case CLI; planning never issues authority or dispatches a worker."""
import argparse
import json
from pathlib import Path
import sys
from .common import require
from .workspace import initialize, plan_request, replay_paths, verify_run
from .workflow import execute

class Parser(argparse.ArgumentParser):

    def error(self, message):
        raise ValueError('CLI_ARGUMENTS: ' + message[:160])

def main(argv: list[str] | None=None) -> int:
    try:
        require(sys.version_info >= (3, 12) and (not sys.flags.optimize), 'PYTHON_3_12_UNOPTIMIZED_REQUIRED')
        p = Parser(description=__doc__)
        sub = p.add_subparsers(dest='command', required=True)
        inspect = sub.add_parser('inspect')
        inspect.add_argument('--package', required=True, type=Path)
        inspect.add_argument('--workspace', required=True, type=Path)
        inspect.add_argument('--build-record', type=Path)
        plan = sub.add_parser('plan')
        plan.add_argument('--workspace', required=True, type=Path)
        plan.add_argument('--expected-old', required=True)
        plan.add_argument('--lp-bps', required=True)
        replay = sub.add_parser('replay')
        replay.add_argument('--workspace', required=True)
        replay.add_argument('--plan', required=True)
        replay.add_argument('--authority')
        verify = sub.add_parser('verify')
        verify.add_argument('--run', required=True, type=Path)
        args = p.parse_args(argv)
        if args.command == 'inspect':
            result = initialize(args.workspace, args.package, args.build_record)
        elif args.command == 'plan':
            result = plan_request(args.workspace, args.expected_old, args.lp_bps)
        elif args.command == 'replay':
            require(args.authority is not None, 'NOT_AUTHORIZED')
            result = execute(*replay_paths(args.workspace, args.plan, args.authority))
        else:
            result = verify_run(args.run)
    except (ValueError, OSError, KeyError, TypeError) as error:
        cause = str(error)[:240]
        if 'NOT_AUTHORIZED' in cause or 'AUTHORITY' in cause:
            status = 'NOT_AUTHORIZED'
        elif 'UNSUPPORTED_CASE' in cause:
            status = 'UNSUPPORTED_CASE'
        elif any((word in cause for word in ['PLAN_', 'LP_RANGE', 'EXPECTED_OLD'])):
            status = 'INVALID_PLAN'
        elif 'VERIFICATION' in cause or 'RECORDED_' in cause:
            status = 'VERIFICATION_FAILED'
        else:
            status = 'HOST_STOP'
        is_replay = 'args' in locals() and args.command == 'replay'
        result = {'status': status, 'causeCode': cause, 'authorityConsumed': False if status == 'NOT_AUTHORIZED' and cause == 'NOT_AUTHORIZED' or not is_replay else None}
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['status'] in ['INSPECTED', 'PLANNED', 'COMPLETED', 'RECORDED_INTEGRITY_PASS'] else 1
if __name__ == '__main__':
    raise SystemExit(main())
