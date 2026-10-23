"""Prepare an immutable native-request descriptor. No execution entry exists."""
import argparse
import copy
import hashlib
import json

from validate_plan import (REPO, commitment, read_input,
                           saved_package, strict_json, validate_plan)


def _retained_material(package_bytes, available):
    """Check supplied cache bytes against all original package entries, not branch closure."""
    packet = strict_json(package_bytes)
    required = {kind: sorted(packet[kind]) for kind in ['state', 'codes']}
    if available is None:
        available = required
    if not isinstance(available, dict) or set(available) != {'state', 'codes'}:
        raise ValueError('MATERIAL_FIELDS')
    for kind in required:
        values = available[kind]
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError('MATERIAL_ENTRIES')
        # No extra/synthesized preimages or canonical intermediate state are admitted.
        if sorted(values) != required[kind]:
            raise ValueError('RETAINED_WITNESS_MATERIAL_MISSING_OR_CHANGED')
    return {kind: len(required[kind]) for kind in required}


def prepare_native_plan(package_bytes, proposed, *, available_material=None):
    validated = validate_plan(package_bytes, proposed)
    if proposed['newValue'] not in ['0', '50']:
        raise ValueError('NATIVE_REVIEW_SCOPE_ONLY_0_OR_50')
    material = _retained_material(package_bytes, available_material)
    saved = saved_package.specification(REPO)
    runtime_plan = copy.deepcopy(saved)
    runtime_plan['intervention'] = validated['intervention']
    raw = (json.dumps(runtime_plan, indent=2) + '\n').encode()
    is_saved = proposed['newValue'] == '0'
    source_pins = {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in [
        'native/prestate/lp_branch.go', 'native/saved-pair/pair.go',
        'repro/portable/main.go', 'repro/portable_pair03.py', 'sdk_alpha_v2/policy.json']}
    body = {
        'schema': 'rhook/native-plan-request/0.1',
        'status': 'ADMITTED_FOR_REVIEW_NOT_EXECUTABLE',
        'caseId': proposed['caseId'], 'planCommitment': validated['planCommitment'],
        'packageSha256': saved['packageSha256'], 'checkpoint': saved['checkpoint'],
        'originalInputCommitment': saved['inputCommitment'],
        'originalWitnessCommitment': saved['witnessCommitment'],
        'runtimePlan': runtime_plan, 'runtimePlanSha256': hashlib.sha256(raw).hexdigest(),
        'runtimePlanEncoding': 'UTF8_PYTHON_JSON_INDENT2_TRAILING_LF',
        'legacySourcePins': source_pins,
        'retainedMaterial': material, 'additionalBranchStateCoverage': 'NOT_EVALUATED',
        'canonicalActualGate': ['stateRoot', 'receiptsRoot', 'blockHash'],
        'worldConstruction': 'INDEPENDENT_ORIGINAL_PARENT_NIL_SOURCE',
        'missingStatePolicy': 'HOST_STOP_NO_HYDRATION_NO_RETRY',
        'legacyInterventionCompatible': is_saved,
        'executionPrerequisites': ['FRESH_SEPARATE_AUTHORIZATION', 'FRESH_RESOURCE_ADMISSION'] +
            ([] if is_saved else ['NEW_SCOPED_WORKER_AND_PROFILE', 'PLAN_AWARE_COMPLETION_VERIFIER']),
        'executionAuthorized': False, 'canExecuteNow': False,
        'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0},
        'externalDelivery': 'HOLD',
    }
    return dict(body, requestCommitment=commitment('rhook/native-plan-request/0.1', body))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--plan', required=True)
    args = parser.parse_args()
    try:
        request = prepare_native_plan(read_input(args.package, 2 << 20),
                                      strict_json(read_input(args.plan, 16384)))
        print(json.dumps(request, indent=2))
    except Exception:
        raise SystemExit('NATIVE_PLAN_REJECTED')
