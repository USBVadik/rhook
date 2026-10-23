"""Run with the installed Alpha Python. Native execution requires explicit flags."""
import argparse
import json
from pathlib import Path

from rhook_alpha import LpBps, SDK


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', required=True, type=Path)
    parser.add_argument('--lp-bps', type=int, default=50)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--local-owner', action='store_true')
    parser.add_argument('--mac-ready', action='store_true')
    args = parser.parse_args()
    sdk = SDK(args.home)
    inspected = sdk.inspect('hookr-pair03')
    if inspected['status'] != 'INSPECTED': raise ValueError(inspected)
    plan = sdk.plan('hookr-pair03', LpBps(args.lp_bps))
    print(json.dumps(plan))
    if plan['status'] != 'PLANNED': return 1
    if not args.execute: return 0
    grant = sdk.authorize(plan['planId'], local_owner=args.local_owner, mac_ready=args.mac_ready)
    result = sdk.replay(plan['planId'], grant)
    print(json.dumps(result))
    if result['status'] != 'COMPLETED': return 1
    print(json.dumps(sdk.compare(result['runDirectory']), indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
