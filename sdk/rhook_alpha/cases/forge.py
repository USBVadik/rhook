"""Bounded read-only acquisition and offline import using the case backend."""
import json
from pathlib import Path
import tempfile
import sys
import types
import re
from developer.files import load, no_links, require, save, sha, sync
from . import native


def capture_helper(command, directory, timeout, stdout_limit=65536, stderr_limit=65536):
    """Capture-only file allowance; original v2/native guards stay unchanged."""
    native.python_required()
    engine = str(native.SDK_ROOT / 'engine')
    if engine not in sys.path:
        sys.path.insert(0, engine)
    from .workflow import active_group, guard_module
    group = active_group()
    if group is not None:
        return guard_module(group=group, helper_file=True).capture(command, directory, timeout, stdout_limit, stderr_limit)
    from sdk_alpha_v2._frozen import bind
    module = types.ModuleType('sdk_alpha_v2._forge_capture')
    module.__package__ = 'sdk_alpha_v2'
    bind(vars(module), 'repro/portable/legacy_guards.py', [
        ('4<<30', '1<<30', 2),
        ("'GOMEMLIMIT':'1073741824'", "'GOMEMLIMIT':'536870912'", 1),
        ('resource.setrlimit(resource.RLIMIT_FSIZE,(1<<20,1<<20))',
         'resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20))', 1),
    ])
    return module.capture(command, directory, timeout, stdout_limit, stderr_limit)


def run(sdk, output, *, action, package=None, witness=None, block=None, chain=4663, read_only=False, credential_file=None, account_assertions=None):
    require(action in ('capture', 'capture-recent', 'qualify-root', 'forge', 'diagnose', 'select', 'watch'), 'FORGE_ACTION')
    require(chain == 4663 and type(chain) is int, 'SUPPORTED_CHAIN_4663_REQUIRED')
    if action in ('capture', 'capture-recent', 'qualify-root', 'select', 'watch'):
        require(read_only is True, 'EXPLICIT_READ_ONLY_ACQUISITION_APPROVAL_REQUIRED')
    if action == 'capture':
        require(type(block) is int and 0 < block < 2 ** 53, 'EXPLICIT_BLOCK_NUMBER_REQUIRED')
    r = native.runtime(sdk)
    output = no_links(output)
    output.mkdir(mode=0o700)
    sync(output.parent)
    config = {'action': action, 'output': str(output), 'block': block, 'chain': chain, 'readOnlyApproved': read_only}
    for name, value in (('package', package), ('witness', witness), ('credentialFile', credential_file), ('accountAssertions', account_assertions)):
        if value is not None:
            config[name] = str(no_links(value))
    save(output / 'STARTED.json', config)
    with tempfile.TemporaryDirectory(prefix='.forge-config-', dir=sdk.home) as temp:
        path = Path(temp) / 'CONFIG.json'
        save(path, config)
        result, stdout, stderr = capture_helper([r['files']['node']['path'], str(Path(__file__).with_name('witness') / 'main.mjs'), str(path)], output / 'CHILD', 80 if action == 'watch' else 40, 65536, 65536)
    require(result['ownedChildReaped'], 'FORGE_CHILD_CLEANUP_UNCONFIRMED')
    if result['stop'] or result['exitCode'] not in (0, 1):
        return {'status': 'FORGE_HELPER_STOP', 'causeCode': result['stop'] or 'CHILD_EXIT_' + str(result['exitCode']), 'output': str(output), 'nativeExecutions': 0}
    value = load(output / 'ACQUISITION_RESULT.json', 65536)
    require(value == json.loads(stdout), 'FORGE_HELPER_RESULT_LINK')
    return dict(value, output=str(output), cleanupConfirmed=True)


def create(sdk, output, *, case_id, subject_index):
    output = no_links(output)
    report = load(output / 'DEPENDENCIES.json')
    require(report['packageSha256'] == sha(output / 'BLOCK_PACKAGE.json'), 'DIAGNOSTIC_PACKAGE_DRIFT')
    require(report['authentication'] == 'PROOFS_VERIFIED_AT_DECLARED_ROOT', 'AUTHENTICATED_STATE_REQUIRED')
    require(report['status'] != 'UNSUPPORTED_EXECUTION_PROFILE', 'UNSUPPORTED_EXECUTION_PROFILE')
    require(report['inputCommitment'] is not None and report['rulesWord'] is not None, 'CAPSULE_INPUT_OR_CONFIG_INCOMPLETE_SEE_DEPENDENCIES')
    return sdk.package_case(output / 'BLOCK_PACKAGE.json', output / 'capsule', case_id=case_id,
        adapter='hookr-1.lp-bps/1', subject_index=subject_index,
        input_commitment=report['inputCommitment'], witness_commitment=report['witnessCommitment'], original_word=report['rulesWord'])


def capture_case(sdk, output, *, block, case_id, subject_index, chain=4663, read_only=False, witness=None):
    require(type(case_id) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', case_id), 'CASE_ID')
    require(type(subject_index) is int and 1 <= subject_index < 8, 'CAPTURE_SUBJECT_ORDINAL_1_TO_7_REQUIRED')
    value = run(sdk, output, action='capture', block=block, chain=chain, read_only=read_only, witness=witness)
    # A transport STOP stays a STOP. Its authenticated partial material is kept
    # for diagnosis/import, without issuing consent or silently resuming it.
    if value['status'] == 'CAPTURED_SEED':
        try:
            capsule = create(sdk, output, case_id=case_id, subject_index=subject_index)
            value.update(status='CAPTURED_AUTHENTICATED_CAPSULE', capsule=capsule, capsuleDirectory=str(no_links(output) / 'capsule'), executionCoverage='UNKNOWN')
        except (ValueError, KeyError, TypeError) as error:
            value.update(status='AUTHENTICATED_PARTIAL_CAPTURE', capsuleBlocker=str(error))
    save(no_links(output) / 'CAPTURE_RESULT.json', value)
    return value


def capture_recent_case(sdk, output, *, case_prefix='hookr', read_only=False, witness=None):
    require(type(case_prefix) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,44}', case_prefix), 'CASE_PREFIX')
    value = run(sdk, output, action='capture-recent', read_only=read_only, witness=witness)
    if value['status'] == 'CAPTURED_SEED':
        selection = value['selection']
        case_id = case_prefix + '-' + str(selection['blockNumber'])
        try:
            capsule = create(sdk, output, case_id=case_id, subject_index=selection['subjectIndex'])
            value.update(status='CAPTURED_AUTHENTICATED_CAPSULE', caseId=case_id, capsule=capsule,
                         capsuleDirectory=str(no_links(output) / 'capsule'), executionCoverage='UNKNOWN')
        except (ValueError, KeyError, TypeError) as error:
            value.update(status='AUTHENTICATED_PARTIAL_CAPTURE', capsuleBlocker=str(error))
    save(no_links(output) / 'CAPTURE_RESULT.json', value)
    return value


def forge_case(sdk, package, output, *, case_id, subject_index, witness=None):
    value = run(sdk, output, action='forge', package=package, witness=witness)
    if value['status'] == 'MATERIAL_IMPORTED':
        try:
            value.update(capsule=create(sdk, output, case_id=case_id, subject_index=subject_index),
                         status='AUTHENTICATED_CAPSULE_CREATED', capsuleDirectory=str(no_links(output) / 'capsule'), executionCoverage='UNKNOWN')
        except (ValueError, KeyError, TypeError) as error:
            value.update(status='AUTHENTICATED_PARTIAL_IMPORT', capsuleBlocker=str(error))
    save(no_links(output) / 'IMPORT_RESULT.json', value)
    return value


def diagnose(sdk, case, *, trusted_checkpoint=None):
    path, capsule = sdk.registry.resolve(case)
    if trusted_checkpoint is not None:
        require(trusted_checkpoint == capsule['checkpoint']['blockHash'], 'TRUSTED_CHECKPOINT_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='.diagnose-', dir=sdk.home) as temp:
        output = Path(temp) / 'output'
        value = run(sdk, output, action='diagnose', package=path / 'BLOCK_PACKAGE.json')
        require(value['status'] == 'MATERIAL_IMPORTED', 'CASE_DIAGNOSTIC_STOP: ' + str(value))
        report = load(output / 'DEPENDENCIES.json')
    require(report['inputCommitment'] == capsule['execution']['inputCommitment'] and report['witnessCommitment'] == capsule['execution']['witnessCommitment'], 'DIAGNOSTIC_COMMITMENT_DRIFT')
    return dict(report, caseId=case, capsuleId=capsule['capsuleId'], executionAuthorized=False,
                chainTrust='OPERATOR_PINNED_CHECKPOINT' if trusted_checkpoint else 'NOT_INDEPENDENTLY_ESTABLISHED')


def watch_case(sdk, output, *, credential_file=None, account_assertions, case_prefix='hookr', read_only=False):
    require(type(case_prefix) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,44}', case_prefix), 'CASE_PREFIX')
    value = run(sdk, output, action='watch', read_only=read_only, credential_file=credential_file, account_assertions=account_assertions)
    if value['status'] == 'CAPTURED_SEED':
        selection = value['selection']
        case_id = case_prefix + '-' + str(selection['blockNumber'])
        try:
            capsule = create(sdk, output, case_id=case_id, subject_index=selection['subjectIndex'])
            value.update(status='CAPTURED_AUTHENTICATED_CAPSULE', caseId=case_id, capsule=capsule,
                         capsuleDirectory=str(no_links(output) / 'capsule'), executionCoverage='UNKNOWN')
        except (ValueError, KeyError, TypeError) as error:
            value.update(status='AUTHENTICATED_PARTIAL_CAPTURE', capsuleBlocker=str(error))
    save(no_links(output) / 'WATCH_RESULT.json', value)
    return value
