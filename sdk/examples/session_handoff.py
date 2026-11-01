"""Session Handoff 0.1 end to end, offline: developer A exports a session, developer B imports and prepares it.

Two independent SDK homes under --work. A creates the session from one pinned SCENARIO.json, registers the
LP variants, prepares them and exports a complete package (source material included by explicit opt-in).
B authenticates the package with its manifest SHA-256, rebuilds the session, prepares every variant with
ExecutionSDK.prepare and compares identities and prepared commitments with A's. Nothing is executed natively,
no RPC is opened and no consent is requested. --synthetic uses the public test fixture; it is not chain data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk-root', type=Path, default=HERE, help='Installed prefix/lib or source sdk directory')
    p.add_argument('--work', type=Path, required=True, help='New directory for both homes and the package')
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--synthetic', action='store_true', help='Use the synthetic fixture from sdk/tests_cases')
    source.add_argument('--scenario', type=Path, help='Authenticated SCENARIO.json (needs --sha256 and --checkpoint)')
    p.add_argument('--sha256', help='Expected SHA-256 of the SCENARIO.json bytes')
    p.add_argument('--checkpoint', type=Path, help='JSON with chainId, blockNumber, blockHash and stateRoot')
    p.add_argument('--lp-bps', type=int, nargs='+', default=[50, 0])
    args = p.parse_args(argv)
    sys.path.insert(0, str(args.sdk_root))
    from developer.files import canonical, load
    from rhook_alpha.execution import ExecutionSDK
    from rhook_alpha.session import SessionError
    work = args.work.absolute()
    if work.exists():
        p.error('--work must not exist yet')
    work.mkdir(mode=0o700, parents=True)
    synthetic = None
    if args.synthetic:
        sys.path.insert(0, str(HERE / 'tests_cases'))
        import test_session
        if test_session.NODE and test_session.DEPS:
            # Made-up tries whose parent header hashes to the checkpoint, so static coverage can be evaluated.
            value, _ = test_session.hash_linked_fixture('complete')
            synthetic = 'HASH_LINKED_SYNTHETIC_STATE'
        else:
            value = test_session.execution_fixture()
            synthetic = 'SYNTHETIC_PARENT_NOT_HASH_LINKED_COVERAGE_STOPS'
        scenario = work / 'SYNTHETIC-SCENARIO.json'
        scenario.write_bytes(canonical(value) + b'\n')
        pin, checkpoint = hashlib.sha256(scenario.read_bytes()).hexdigest(), value['checkpoint']
    else:
        if not (args.sha256 and args.checkpoint):
            p.error('--scenario needs --sha256 and --checkpoint')
        scenario, pin, checkpoint = args.scenario, args.sha256, load(args.checkpoint, 65536)
    try:
        # Developer A.
        a = ExecutionSDK(work / 'developer-a-home')
        session = a.create_session(source=scenario, expected_sha256=pin, checkpoint=checkpoint)
        variants = [session.add_variant({'lpBps': lp})['variantId'] for lp in args.lp_bps]
        exported_prepared = {v: session.prepare_variant(v)['scenarioCommitment'] for v in variants}
        export = session.export_handoff(work / 'handoff', include_source=True)
        # Developer B: only the package directory and the separately shared pin.
        b = ExecutionSDK(work / 'developer-b-home')
        inspection = b.inspect_session_handoff(work / 'handoff', expected_manifest_sha256=export['manifestSha256'])
        imported = b.import_session_handoff(work / 'handoff', expected_manifest_sha256=export['manifestSha256'])
        reconstructed = {v['variantId']: imported.prepare_variant(v['variantId'])['scenarioCommitment'] for v in imported.variants()}
        coverage = imported.coverage()
        view = imported.inspect()
    except SessionError as error:
        print(json.dumps(error.as_result(), indent=2))
        return 1
    same = imported.id == session.id and reconstructed == exported_prepared
    print(json.dumps(dict(
        status='HANDOFF_RECONSTRUCTED' if same else 'HANDOFF_RECONSTRUCTION_DIFFERS',
        syntheticFixture=synthetic, manifestSha256=export['manifestSha256'],
        packageIntegrity=inspection['packageIntegrity'], mode=export['mode'], sourceMaterial=export['sourceMaterial'],
        sessionId=dict(exporter=session.id, importer=imported.id),
        checkpoint=view['checkpoint'], canonicality=view['checkpointTrust']['canonicality'],
        variants=[dict(variantId=v['variantId'], lpBps=v['descriptor']['replacement'], status=v['status'],
                       exporterScenarioCommitment=exported_prepared.get(v['variantId']),
                       importerScenarioCommitment=reconstructed.get(v['variantId']),
                       staticCoverage=v['staticCoverage'], profilePreconditions=v['profilePreconditions'],
                       dynamicCoverage=v['dynamicCoverage'], execution=v['execution'], nextRequirement=v['nextRequirement'])
                  for v in view['variants']],
        staticCoverage=dict(status=coverage.get('status'), code=coverage.get('code'),
                            preconditions=(coverage.get('preconditions') or {}).get('status'),
                            networkRequestsPerformed=coverage.get('networkRequestsPerformed')),
        assurance=inspection['assurance'], nativeExecutions=0, networkRequests=0), indent=2))
    return 0 if same else 1


if __name__ == '__main__':
    raise SystemExit(main())
