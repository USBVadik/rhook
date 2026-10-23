"""Reconstruct exact v0.2 plans independently of the TypeScript planner."""
import copy
from dataclasses import dataclass
import re
from .common import HERE, canonical, case_descriptor, commit, read, require, sha, strict
from plan_native.common import portable

@dataclass(frozen=True)
class ValidatedPlan:
    semantic_bytes: bytes
    runtime_bytes: bytes
    semantic_commitment: str
    runtime_sha256: str
    new_value: str

def make_plan(package: bytes, expected_old: str, new_value: str) -> ValidatedPlan:
    descriptor = case_descriptor()
    base = copy.deepcopy(descriptor['plan'])
    portable.validate_package(package, dict(base, intervention=dict(base['intervention'], newWord=base['intervention']['expectedOldWord'])))
    require(type(expected_old) is str and expected_old == '100', 'EXPECTED_OLD')
    require(type(new_value) is str and re.fullmatch('(0|[1-9][0-9]?)', new_value), 'CASE_LP_RANGE')
    old = int(base['intervention']['expectedOldWord'], 16)
    mask = 65535 << 160
    require(old >> 160 & 65535 == 100 and int(base['intervention']['mask'], 16) == mask, 'ORIGINAL_RULES_WORD')
    base['intervention']['newWord'] = f'0x{old & ~mask | int(new_value) << 160:064x}'
    descriptor_sha = sha(read(HERE / 'case.json'))
    body = {'schema': 'rhook/hookr-plan/0.2', 'caseId': descriptor['caseId'], 'caseDescriptorSha256': descriptor_sha, 'packageSha256': base['packageSha256'], 'ruleId': descriptor['ruleId'], 'expectedOld': '100', 'newValue': new_value, 'intervention': base['intervention'], 'status': 'PLANNED', 'branchResult': None, 'executionAuthorized': False, 'witnessClosure': 'NOT_EVALUATED'}
    semantic_commitment = commit('rhook/hookr-plan/0.2', body)
    semantic = dict(body, planCommitment=semantic_commitment)
    runtime = {'schema': 'rhook/hookr-runtime-plan/0.2', 'caseDescriptorSha256': descriptor_sha, 'semanticPlanCommitment': semantic_commitment, 'newValue': new_value, 'plan': base}
    runtime_bytes = canonical(runtime) + b'\n'
    return ValidatedPlan(canonical(semantic) + b'\n', runtime_bytes, semantic_commitment, sha(runtime_bytes), new_value)

def validate_semantic(package: bytes, proposed: dict) -> ValidatedPlan:
    require(type(proposed) is dict, 'PLAN_OBJECT')
    expected = make_plan(package, proposed.get('expectedOld'), proposed.get('newValue'))
    require(canonical(proposed) == expected.semantic_bytes.rstrip(b'\n'), 'PLAN_MISMATCH')
    return expected

def validate_runtime(package: bytes, raw: bytes) -> ValidatedPlan:
    require(len(raw) <= 32 << 10, 'RUNTIME_SIZE')
    proposed = strict(raw)
    require(type(proposed) is dict, 'RUNTIME_OBJECT')
    expected = make_plan(package, '100', proposed.get('newValue'))
    require(canonical(proposed) + b'\n' == expected.runtime_bytes, 'RUNTIME_MISMATCH')
    require(raw == expected.runtime_bytes, 'RUNTIME_ENCODING')
    return expected

def normalize_result(raw_terminal: str, failure: dict | None, evidence: dict) -> dict:
    status = {'CANONICAL_EXECUTION_MISMATCH': 'CANONICAL_MISMATCH', 'HOST_STOP': 'HOST_STOP', 'HOST_STOP_MISSING_STATE': 'HOST_STOP', 'BRANCH_HOST_STOP': 'HOST_STOP', 'BRANCH_STOP': 'HOST_STOP', 'RUNTIME_OR_RESOURCE_STOP': 'HOST_STOP', 'VERIFICATION_FAILED': 'VERIFICATION_FAILED'}.get(raw_terminal, 'INTERRUPTED_UNVERIFIED')
    if failure and evidence.get('typedFailureVerified') is True and (failure.get('classification') == 'HOST_STOP_MISSING_STATE'):
        status = 'MISSING_WITNESS'
    if raw_terminal == 'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED' and all((evidence.get(k) is True for k in ['verified', 'cleanupConfirmed', 'resourcesVerified'])):
        status = 'COMPLETED'
    counts = evidence.get('counts')
    if evidence.get('dispatched') is False:
        counts = {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}
    if counts is not None:
        require(type(counts) is dict and set(counts) == {'ACTUAL', 'BRANCH', 'B'} and all((type(v) is int for v in counts.values())) and (0 <= counts['BRANCH'] <= counts['ACTUAL'] <= 1) and (counts['B'] == 0), 'INVOCATION_COUNTS')
    if status == 'COMPLETED' and counts != {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}:
        status = 'INTERRUPTED_UNVERIFIED'
    return {'status': status, 'rawTerminal': raw_terminal, 'nativeInvocations': counts, 'causeCode': failure.get('code') if failure else None, 'economicAssurance': 'UNRESOLVED', 'heterogeneousAgreement': 'NOT_EVALUATED', 'qualifiedClaims': 0}

def dependencies_commitment():
    from plan_native.core import verifier_dependencies
    return sha(canonical(verifier_dependencies()))

def validate_build(build):
    from .common import sources, no_links
    files = sources()
    require(build['schema'] == 'rhook/case-sdk-build/0.1' and build['status'] == 'BUILD_ONLY_PASS' and (build['productionWorkerLaunched'] is False), 'BUILD_REQUIRED')
    require(build['sourceFiles'] == files and build['sourceCommitment'] == sha(canonical(files)), 'BUILD_SOURCE_DRIFT')
    require(build['caseDescriptorSha256'] == sha(read(HERE / 'case.json')) and build['policySha256'] == sha(read(HERE / 'policy.json')), 'BUILD_POLICY_OR_CASE')
    require(build['verifierDependenciesCommitment'] == dependencies_commitment(), 'VERIFIER_DEPENDENCY_DRIFT')
    for path, pin in [('workerPath', 'binarySha256'), ('sensorPath', 'sensorSha256'), ('nodePath', 'nodeSha256')]:
        require(sha(read(no_links(build[path]), 256 << 20)) == build[pin], 'BUILD_ARTIFACT_DRIFT')
    return build

def prepare_request(build: dict, plan: ValidatedPlan, paths: dict) -> dict:
    from pathlib import Path
    from .common import DOMAIN, PROFILE, no_links, portable
    validate_build(build)
    require(set(paths) == {'workspace', 'planId', 'outputPath', 'packagePath', 'semanticPlanPath', 'runtimePlanPath'}, 'REQUEST_PATH_FIELDS')
    workspace = no_links(paths['workspace'])
    ref = paths['planId']
    require(re.fullmatch('[0-9a-f]{32}', ref), 'PLAN_ID')
    expected = {'workspace': str(workspace), 'planId': ref, 'outputPath': str(workspace / 'runs' / ref), 'packagePath': str(workspace / 'BLOCK_PACKAGE.json'), 'semanticPlanPath': str(workspace / 'plans' / ref / 'semantic.json'), 'runtimePlanPath': str(workspace / 'plans' / ref / 'runtime.json')}
    require(paths == expected, 'WORKSPACE_PATH_LINK')
    package = read(paths['packagePath'], 2 << 20)
    require(validate_runtime(package, read(paths['runtimePlanPath'], 32768)) == plan, 'RUNTIME_PATH_PIN')
    require(read(paths['semanticPlanPath'], 16384) == plan.semantic_bytes, 'SEMANTIC_PATH_PIN')
    descriptor = case_descriptor()['plan']
    body = {'schema': 'rhook/native-plan-request/0.2', 'domain': DOMAIN, 'profile': PROFILE, **paths, **{k: build[k] for k in ['sourceCommitment', 'binarySha256', 'caseDescriptorSha256', 'policySha256', 'sensorPath', 'sensorSha256', 'nodePath', 'nodeSha256', 'verifierDependenciesCommitment']}, 'semanticPlanCommitment': plan.semantic_commitment, 'runtimePlanSha256': plan.runtime_sha256, **{k: descriptor[k] for k in ['packageSha256', 'inputCommitment', 'witnessCommitment']}, 'limits': portable.LIMITS, 'workflowSeconds': 180, 'nativeStageSeconds': 140, 'maximumInvocations': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, 'RPC': 0, 'WSS': 0, 'executionContext': 'require_escalated', 'externalDelivery': 'HOLD'}
    body['requestCommitment'] = commit('rhook/native-plan-request/0.2', body)
    return dict(body, operationCommitment=commit('rhook/hookr-operation/0.2', body))

def validate_approval(binding: dict, raw: bytes, now: int) -> dict:
    require(len(raw) < 16384, 'AUTHORITY_SIZE')
    a = strict(raw)
    require(type(a) is dict, 'AUTHORITY_OBJECT')
    expected = dict(binding, founderApproved=True, macOnPowerOpenLid=True, noRetry=True, notBeforeUnix=a.get('notBeforeUnix'), expiresUnix=a.get('expiresUnix'))
    require(canonical(a) == canonical(expected), 'EXACT_FRESH_FOUNDER_AUTHORITY_REQUIRED')
    begin, end = (a['notBeforeUnix'], a['expiresUnix'])
    require(type(begin) is int and type(end) is int and (begin <= now < end) and (0 < end - begin <= 600) and (end - now >= 180), 'AUTHORITY_WINDOW')
    return a
