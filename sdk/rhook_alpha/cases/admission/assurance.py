"""Bounded artifact-support report. No outcome calculation or Lawful proof."""
from pathlib import Path
from developer.files import digest, load, no_links, read, relative, require, sha, strict
from . import LP, OFF
from .catalogue import describe

# Trusted local reference pins, not an open provider/attester registry.
REFERENCES = {
    LP: dict(manifest='851bf5d878cf94225ece0ab5201169da92e5ad766dee328006dc3672d775a757',
             count=97, plan='sdk-run/inputs/RUNTIME_PLAN.json', nested='plan',
             actual='sdk-run/runtime/ACTUAL.json', branch='sdk-run/runtime/BRANCH.json',
             descriptor=dict(rule='lpBps', value=50)),
    OFF: dict(manifest='6c9ff40dfe8de1d7b739dd35bc0b4232fd4a120d5f6d9f1116ef561252e5a7f6',
              count=183, plan='sdk-run/inputs/PLAN.json', nested='runtimePlan',
              actual='sdk-run/runtime/ACTUAL.json', branch='sdk-run/runtime/BRANCH.json',
              descriptor=dict(rule='dynamicFee', value='OFF')),
}
PLAN_FIELDS = ['packageSha256', 'inputCommitment', 'witnessCommitment', 'checkpoint',
               'blockNumber', 'blockHash', 'stateRoot', 'receiptsRoot', 'transactions',
               'arrivals', 'subject', 'sender', 'router', 'observation', 'intervention']


def evidence_support(capsule, value, directory):
    from .catalogue import resolve_plan
    if directory is None:
        return dict(status='UNRESOLVED', available=False, reason='NO_ACCEPTED_EVIDENCE_SUPPLIED')
    ref = REFERENCES[capsule['adapter']['id']]
    root = no_links(directory)
    try:
        manifest_raw = read(root / 'MANIFEST.json', 2 << 20)
        require(digest(manifest_raw) == ref['manifest'], 'UNRECOGNIZED_OR_CHANGED_EVIDENCE_MANIFEST')
        files = strict(manifest_raw)['files']
        require(type(files) is dict and len(files) == ref['count'], 'EVIDENCE_INVENTORY')
        remaining = 256 << 20
        # Parse exactly the authenticated buffers. A second path lookup/load
        # would allow replacement after hashing, even in a trusted directory.
        needed = {ref['plan'], ref['actual'], ref['branch']}
        require(needed <= set(files), 'EVIDENCE_REQUIRED_RECORDS')
        records = {}
        for name, pin in files.items():
            relative(name)
            path = no_links(root / name)
            if name in needed:
                raw = read(path, min(2 << 20, remaining))
                require(digest(raw) == pin, 'EVIDENCE_FILE_HASH_MISMATCH')
                records[name] = strict(raw)
                remaining -= len(raw)
            else:
                require(remaining >= 0 and sha(path, min(128 << 20, remaining)) == pin, 'EVIDENCE_FILE_HASH_MISMATCH')
                remaining -= path.stat().st_size
        require(value == ref['descriptor'], 'ACCEPTED_EVIDENCE_IS_FOR_A_DIFFERENT_INTERVENTION')
        old = records[ref['plan']][ref['nested']]
        plan = resolve_plan(capsule, value)
        require(all(old[k] == plan[k] for k in PLAN_FIELDS), 'ACCEPTED_EVIDENCE_IS_FOR_A_DIFFERENT_QUESTION')
        actual = records[ref['actual']]['result']
        branch = records[ref['branch']]['result']
        require(actual['world'] == 'ACTUAL' and branch['world'] == 'BRANCH', 'ORDERED_RECORD_BINDING')
        require(all(actual[k] == plan[k] for k in ['stateRoot', 'receiptsRoot', 'blockHash']), 'CANONICAL_ACTUAL_RECORD_MISMATCH')
        return dict(status='ESTABLISHED', available=True, scope='PINNED_RECORDED_REFERENCE_SUPPORT_ONLY',
                    observationBasis='CAPTURED_HASHED_BYTES_NOT_FUTURE_FILESYSTEM_IMMUTABILITY',
                    manifestSha256=ref['manifest'], pinnedFiles=len(files),
                    anchorRoot=plan['checkpoint']['stateRoot'],
                    branchInitialRoot=branch.get('dynamicFeeOverlay', {}).get('initialRoot'),
                    branchInitialRootMeaning='RECORDED_AND_PREVIOUSLY_RECOMPUTED_FOR_OFF_ONLY; LP_LEGACY_RECORD_OMITS_IT',
                    independentEVM=False, completeLawfulProof=False)
    except FileNotFoundError:
        return dict(status='UNRESOLVED', available=False, reason='ACCEPTED_EVIDENCE_FILE_MISSING')
    except (ValueError, KeyError, TypeError, OSError) as error:
        return dict(status='REJECTED', available=False, reason=str(error)[:512],
                    rejectionScope='THIS_EVIDENCE_ATTEMPT_NOT_A_WORLD_OUTCOME')


def report(capsule, value, evidence=None):
    admission = describe(capsule, value)
    support = evidence_support(capsule, value, evidence)
    laws = load(Path(__file__).with_name('laws.json'))['laws']
    rows = []
    for law in laws:
        rows.append(dict(law,
            status='UNRESOLVED',
            structuralResolution=dict(status='ESTABLISHED' if law['structuralCheck'] else 'UNRESOLVED',
                                      scope=law['structuralCheck'] or 'NO_STRUCTURAL_CHECK_DISCHARGES_THIS_LAW'),
            acceptedRecordSupport=dict(status=support['status'], available=support['available']),
            fullLawfulRelationEstablished=False))
    return dict(schema='rhook/checkpoint-state-assurance/0.1',
                admissionArtifactCommitment=admission['admissionArtifactCommitment'],
                adapter=capsule['adapter']['id'], semanticClass=admission['semanticClass'],
                status='REJECTED' if support['status'] == 'REJECTED' else 'UNRESOLVED',
                statusScope='CONSUMER_KNOWLEDGE_NOT_ACTUAL_OR_BRANCH_OUTCOME',
                policy='STRUCTURAL_ADMISSION_AND_PINNED_RECORDED_REFERENCE_SUPPORT/0.1',
                evidence=support, obligations=rows,
                inheritedRouterProfileQualification=False, lawfulEstablished=False,
                qualifiedClaims=0, economicAssurance='UNRESOLVED',
                heterogeneousExecution='NOT_ESTABLISHED', worldOutcomes=None,
                limitation='Artifact hashes and prior producer records are not an independent proof of all nine laws. Canonicality, faithful R, confinement and local evolution require the stated trust or stronger evidence.')
