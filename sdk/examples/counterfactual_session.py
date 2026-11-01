"""Counterfactual Session over one pinned SCENARIO.json: LP50 and LP0 against the LP100 baseline.

Offline only: creates or reopens the session, registers both variants, checks static coverage of the
retained witness and prepares each variant. It never starts a native worker, opens RPC or asks for consent.
"""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk-root', type=Path, default=Path(__file__).resolve().parents[1],
                   help='Installed prefix/lib or source sdk directory')
    p.add_argument('--home', type=Path, required=True)
    p.add_argument('--scenario', type=Path, required=True, help='Authenticated SCENARIO.json')
    p.add_argument('--sha256', required=True, help='Expected SHA-256 of the SCENARIO.json bytes')
    p.add_argument('--checkpoint', type=Path, required=True,
                   help='JSON with chainId, blockNumber, blockHash and stateRoot you expect the source to use')
    p.add_argument('--lp-bps', type=int, nargs='+', default=[50, 0])
    args = p.parse_args(argv)
    sys.path.insert(0, str(args.sdk_root))
    from developer.files import load
    from rhook_alpha.execution import ExecutionSDK
    from rhook_alpha.session import SessionError
    sdk = ExecutionSDK(args.home)
    try:
        session = sdk.create_session(source=args.scenario, expected_sha256=args.sha256,
                                     checkpoint=load(args.checkpoint, 65536))
        variants = [session.add_variant({'lpBps': lp}) for lp in args.lp_bps]
        coverage = session.coverage()
        prepared = [session.prepare_variant(v['variantId']) for v in variants]
        inspection = session.inspect()
    except SessionError as error:
        print(json.dumps(error.as_result(), indent=2))
        return 1
    print(json.dumps(dict(
        sessionId=session.id, checkpoint=session.header['checkpoint'],
        staticCoverage=dict(status=coverage.get('status'), code=coverage.get('code'),
                            preconditions=(coverage.get('preconditions') or {}).get('status'),
                            unresolvedDependencies=coverage.get('unresolvedDependencies'),
                            networkRequestsPerformed=coverage.get('networkRequestsPerformed')),
        variants=[{k: v[k] for k in ('variantId', 'descriptor', 'status', 'staticCoverage', 'profilePreconditions',
                                     'dynamicCoverage', 'execution', 'nextRequirement')} for v in inspection['variants']],
        preparedScenarioCommitments={str(r['selectedLpBps']): r['scenarioCommitment'] for r in prepared},
        limitations=inspection['limitations'], nativeExecutions=0, networkRequests=0), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
