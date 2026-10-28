#!/usr/bin/env python3
"""Plan Dynamic Fee off from local witness. No acquisition, grant or EVM run."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhook_alpha.execution import ExecutionSDK, ExecutionError


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('witness',type=Path)
    p.add_argument('--sha256',required=True)
    p.add_argument('--node',required=True,type=Path,help='Existing pinned Node runtime')
    args=p.parse_args()
    try:
        sdk=ExecutionSDK(Path.cwd()/'unused-planner-home')
        value=sdk.plan_intervention(args.witness,expected_sha256=args.sha256,
                                   kind='hookr.dynamic-fee-off/0.1',node=args.node)
    except ExecutionError as error:
        print(json.dumps(error.as_result(),indent=2));return 1
    print(json.dumps(value,indent=2));return 0


if __name__=='__main__':
    raise SystemExit(main())
