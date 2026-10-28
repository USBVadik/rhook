"""Prepare the exact saved historical intervention. Never grants or executes."""
import argparse
import json
from pathlib import Path
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.historical import ADAPTER
from rhook_alpha.cases.historical.adapter import profile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--capsule',type=Path,required=True)
    parser.add_argument('--home',type=Path,required=True)
    args=parser.parse_args()
    sdk=CaseSDK(args.home);p=profile();case='hookr-historical-dynamic-off'
    sdk.package_case(args.package,args.capsule,case_id=case,adapter=ADAPTER,subject_index=3,
                     input_commitment=p['inputCommitment'],witness_commitment=p['witnessCommitment'])
    sdk.import_case(args.capsule)
    print(json.dumps(sdk.plan(case,{'rule':'dynamicFee','value':'OFF'})))


if __name__=='__main__':main()
