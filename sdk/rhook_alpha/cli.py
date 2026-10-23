"""Local Hookr Pair03: inspect, plan, authorize, replay, verify and compare."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from .api import CASE, LpBps, SDK


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, help='Private local case workspace; defaults to ~/.local/share/rhook-alpha')
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('inspect'); a.add_argument('--case', default=CASE)
    a = sub.add_parser('plan'); a.add_argument('--case', default=CASE); a.add_argument('--set', required=True, dest='intervention')
    a = sub.add_parser('describe'); a.add_argument('--plan', required=True)
    a = sub.add_parser('authorize', help='One local-owner grant; does not start admission or native execution')
    a.add_argument('--plan', required=True)
    a.add_argument('--local-owner', required=True, action='store_true', help='I own and control this local execution environment')
    a.add_argument('--mac-ready', required=True, action='store_true', help='Mac is on power, lid open; I consent to one bounded execution')
    a = sub.add_parser('replay'); a.add_argument('--plan', required=True); a.add_argument('--authority', required=True, type=Path)
    for command in ('verify', 'compare'):
        a = sub.add_parser(command); a.add_argument('--run', required=True, type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        intervention = None
        if args.command == 'plan':
            match = re.fullmatch(r'lpBps=(0|[1-9][0-9]?)', args.intervention)
            if match is None: raise ValueError('SUPPORTED_RULE_IS_lpBps_INTEGER_0_TO_99')
            intervention = LpBps(int(match[1]))
        sdk = SDK(args.home)
        if args.command == 'inspect': value = sdk.inspect(args.case)
        elif args.command == 'plan': value = sdk.plan(args.case, intervention)
        elif args.command == 'describe': value = sdk.describe(args.plan)
        elif args.command == 'authorize':
            grant = sdk.authorize(args.plan, local_owner=args.local_owner, mac_ready=args.mac_ready)
            value = {'status': 'LOCAL_CONSENT_ISSUED', 'authority': str(grant), 'nativeExecuted': False,
                     'scope': 'LOCAL_OWNER_MAC_ONLY_NOT_REMOTE', 'expiresAfterSeconds': 600}
        elif args.command == 'replay': value = sdk.replay(args.plan, args.authority)
        elif args.command == 'verify': value = sdk.verify(args.run)
        else: value = sdk.compare(args.run)
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        value = {'status': 'INPUT_OR_RUNTIME_STOP', 'causeCode': str(error)[:240], 'automaticRetry': False}
    print(json.dumps(value, ensure_ascii=True))
    return 0 if value.get('status') in {'INSPECTED', 'PLANNED', 'PLAN_AUTHENTICATED', 'LOCAL_CONSENT_ISSUED',
                                      'COMPLETED', 'RECORDED_INTEGRITY_PASS', 'VERIFIED_COMPARISON'} else 1


if __name__ == '__main__': raise SystemExit(main())
