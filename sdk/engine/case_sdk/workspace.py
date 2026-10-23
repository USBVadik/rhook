"""Immutable external case workspaces and opaque plan references."""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from . import common as c
from .contract import validate_build, validate_semantic, prepare_request, make_plan

def sync(directory):
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def write(path, raw):
    path = c.no_links(path)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 384), 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)

def planner(node, action, package, value=None):
    command = [str(node), '--import', str(c.ROOT / 'adapters/hookr-case/test/no-network.mjs'), str(c.ROOT / 'adapters/hookr-case/runtime.ts'), action, str(package)]
    if value is not None:
        command.append(value)
    result = subprocess.run(command, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'TZ': 'UTC'}, capture_output=True, timeout=30)
    c.require(result.returncode == 0 and len(result.stdout) <= 16384 and (not result.stderr), 'OFFLINE_PLANNER_REJECTED')
    return c.strict(result.stdout)

def initialize(workspace: Path, package: Path, build_record: Path | None) -> dict:
    workspace = c.no_links(workspace)
    package = c.no_links(package)
    c.require(not workspace.exists() and (not workspace.is_relative_to(c.ROOT)), 'FRESH_EXTERNAL_WORKSPACE_REQUIRED')
    raw = c.read(package, 2 << 20)
    descriptor = c.case_descriptor()
    c.require(c.sha(raw) == descriptor['plan']['packageSha256'], 'UNSUPPORTED_CASE')
    build = None
    if build_record is not None:
        build = validate_build(c.strict(c.read(build_record)))
    node = build['nodePath'] if build else os.environ.get('RHOOK_NODE') or shutil.which('node')
    c.require(node is not None, 'NODE_24_REQUIRED')
    node = c.no_links(node)
    version = subprocess.run([str(node), '--version'], capture_output=True, timeout=5, env={'PATH': '/usr/bin:/bin'})
    c.require(version.returncode == 0 and re.fullmatch(b'v(2[4-9]|[3-9][0-9])\\.[0-9]+\\.[0-9]+\\s*', version.stdout), 'NODE_24_REQUIRED')
    result = planner(node, 'inspect', package)
    workspace.mkdir(mode=448)
    sync(workspace.parent)
    (workspace / 'plans').mkdir(mode=448)
    (workspace / 'runs').mkdir(mode=448)
    write(workspace / 'BLOCK_PACKAGE.json', raw)
    kit = {'schema': 'rhook/case-workspace/0.1', 'packageSha256': c.sha(raw), 'nodePath': str(node), 'nodeSha256': c.sha(c.read(node, 256 << 20)), 'buildRecordSha256': None}
    if build is not None:
        build_bytes = c.canonical(build) + b'\n'
        write(workspace / 'BUILD.json', build_bytes)
        kit['buildRecordSha256'] = c.sha(build_bytes)
    write(workspace / 'KIT.json', c.canonical(kit) + b'\n')
    sync(workspace)
    return dict(result, workspace=str(workspace), buildRegistered=build is not None)

def kit(workspace):
    workspace = c.no_links(workspace)
    k = c.strict(c.read(workspace / 'KIT.json', 16384))
    c.require(k['schema'] == 'rhook/case-workspace/0.1' and c.sha(c.read(workspace / 'BLOCK_PACKAGE.json', 2 << 20)) == k['packageSha256'], 'WORKSPACE_PACKAGE_PIN')
    c.require(c.sha(c.read(k['nodePath'], 256 << 20)) == k['nodeSha256'], 'WORKSPACE_NODE_PIN')
    return (workspace, k)

def plan_request(workspace: Path, expected_old: str, new_value: str) -> dict:
    workspace, k = kit(workspace)
    c.require(k['buildRecordSha256'] is not None, 'BUILD_NOT_REGISTERED')
    build_raw = c.read(workspace / 'BUILD.json')
    c.require(c.sha(build_raw) == k['buildRecordSha256'], 'REGISTERED_BUILD_DRIFT')
    build = validate_build(c.strict(build_raw))
    c.require(expected_old == '100', 'EXPECTED_OLD')
    make_plan(c.read(workspace / 'BLOCK_PACKAGE.json', 2 << 20), expected_old, new_value)
    proposed = planner(k['nodePath'], 'plan', workspace / 'BLOCK_PACKAGE.json', new_value)
    plan = validate_semantic(c.read(workspace / 'BLOCK_PACKAGE.json', 2 << 20), proposed)
    ref = secrets.token_hex(16)
    directory = workspace / 'plans' / ref
    c.require(not directory.exists() and (not directory.is_symlink()), 'PLAN_REF_COLLISION')
    directory.mkdir()
    sync(directory.parent)
    write(directory / 'semantic.json', plan.semantic_bytes)
    write(directory / 'runtime.json', plan.runtime_bytes)
    paths = {'workspace': str(workspace), 'planId': ref, 'outputPath': str(workspace / 'runs' / ref), 'packagePath': str(workspace / 'BLOCK_PACKAGE.json'), 'semanticPlanPath': str(directory / 'semantic.json'), 'runtimePlanPath': str(directory / 'runtime.json')}
    binding = prepare_request(build, plan, paths)
    write(directory / 'BINDINGS.json', c.canonical(binding) + b'\n')
    return {'status': 'PLANNED', 'execution': 'NOT_RUN', 'branchResult': None, 'planId': ref, 'semanticPlanCommitment': plan.semantic_commitment, 'runtimePlanSha256': plan.runtime_sha256, 'bindingsPath': str(directory / 'BINDINGS.json'), 'runOutput': binding['outputPath'], 'executionAuthorized': False}

def resolve_plan(workspace: Path, plan_ref: str) -> dict:
    c.require(type(plan_ref) is str and re.fullmatch('[0-9a-f]{32}', plan_ref), 'INVALID_PLAN_ID')
    workspace, k = kit(workspace)
    c.require(k['buildRecordSha256'] is not None, 'BUILD_NOT_REGISTERED')
    build_raw = c.read(workspace / 'BUILD.json')
    c.require(c.sha(build_raw) == k['buildRecordSha256'], 'REGISTERED_BUILD_DRIFT')
    path = workspace / 'plans' / plan_ref / 'BINDINGS.json'
    binding = c.strict(c.read(path, 65536))
    c.require(binding['workspace'] == str(workspace) and binding['planId'] == plan_ref, 'PLAN_WORKSPACE_LINK')
    return {'bindingsPath': path, 'buildPath': workspace / 'BUILD.json', 'binding': binding}

def replay_paths(workspace, plan_ref, authority):
    resolved = resolve_plan(Path(workspace), plan_ref)
    return (resolved['bindingsPath'], Path(authority), resolved['buildPath'])

def verify_run(run: Path) -> dict:
    run = c.no_links(run)
    manifest = c.strict(c.read(run / 'MANIFEST.json'))
    actual = {str(p.relative_to(run)): c.sha(c.read(p, 256 << 20)) for p in sorted(run.rglob('*')) if p.is_file() and p != run / 'MANIFEST.json'}
    c.require(actual == manifest['files'], 'RECORDED_MANIFEST_DRIFT')
    b = c.strict(c.read(run / 'proposal/AUTHORIZATION_BINDINGS.json', 65536))
    workspace, k = kit(run.parent.parent)
    c.require(b['outputPath'] == str(run) and b['workspace'] == str(workspace), 'RECORDED_WORKSPACE_LINK')
    build_raw = c.read(workspace / 'BUILD.json')
    c.require(c.sha(build_raw) == k['buildRecordSha256'], 'REGISTERED_BUILD_DRIFT')
    build = validate_build(c.strict(build_raw))
    for staged, pin in [('artifacts/rhook-saved-pair', 'binarySha256'), ('artifacts/rhook-host-sensor', 'sensorSha256'), ('inputs/BLOCK_PACKAGE.json', 'packageSha256'), ('inputs/RUNTIME_PLAN.json', 'runtimePlanSha256')]:
        c.require(c.sha(c.read(run / staged, 256 << 20)) == b[pin], 'RECORDED_ARTIFACT_PIN')
    c.require(build['nodePath'] == b['nodePath'] and build['nodeSha256'] == b['nodeSha256'], 'VERIFIER_NODE_PIN')
    result = subprocess.run([b['nodePath'], '--import', str(c.ROOT / 'adapters/hookr-case/test/no-network.mjs'), str(c.HERE / 'verify.mjs'), str(run / 'inputs/BLOCK_PACKAGE.json'), str(run / 'inputs/RUNTIME_PLAN.json'), str(run)], capture_output=True, timeout=40, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'TZ': 'UTC'})
    c.require(result.returncode == 0 and len(result.stdout) <= 32 << 20, 'VERIFICATION_FAILED')
    verified = c.strict(result.stdout, allow_fractions=True)
    c.require(verified['status'] == 'RECORDED_INTEGRITY_PASS', 'VERIFICATION_FAILED')
    return verified
