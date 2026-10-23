"""Fixed plan and reviewed source closure; importing this module performs no I/O."""
import hashlib
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'plan_native'
DOMAIN = 'HOOKR_PLAN_NATIVE_0_1'
PLAN_SHA = '61a37caca6dad2282d2488fe8e64cf3e1d5157697592362464d00b34a0d5078e'
SEMANTIC = 'e8a0e1d0a8158ec073ea076507864bb9b828a96fd81cdd22732ab902345b6cd7'
REQUEST = '8488d6926409f6612c48d51744cb3044329c2830831fff85d150782a6f40dcdc'
POLICY_SHA = '9461c7fcd288292aea4a34a6278deb699f522ccf1cf566d285f1d6c97460d01b'


def require(ok, cause):
    if not ok:
        raise ValueError(cause)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def read(path, maximum=32 << 20):
    path = Path(path).absolute()
    require(all(not p.is_symlink() for p in (path, *path.parents)), 'SOURCE_OR_INPUT_SYMLINK')
    require(hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_NONBLOCK'), 'DESCRIPTOR_ADMISSION_UNSUPPORTED')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise ValueError('INPUT_OPEN_REJECTED') from error
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum, 'INPUT_TYPE_OR_SIZE')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            raw = source.read(maximum + 1)
        require(len(raw) <= maximum, 'INPUT_SIZE')
        return raw
    finally:
        os.close(fd)


def strict(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'DUPLICATE_JSON_KEY')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'JSON_CONSTANT'))


def inputs():
    raw = read(HERE / 'plan.json')
    require(sha(raw) == PLAN_SHA, 'RUNTIME_PLAN_PIN')
    plan = strict(raw)
    policy_raw = read(HERE / 'policy.json')
    require(sha(policy_raw) == POLICY_SHA, 'POLICY_PIN')
    policy = strict(policy_raw)
    request = strict(read(HERE / 'request.json'))
    body = dict(request); body.pop('requestCommitment')
    require(request['requestCommitment'] == REQUEST == sha(b'rhook/native-plan-request/0.1\n' + canonical(body)),
            'REQUEST_COMMITMENT')
    require(request['runtimePlan'] == plan and request['runtimePlanSha256'] == PLAN_SHA
            and request['planCommitment'] == SEMANTIC, 'PLAN_REQUEST_LINK')
    return plan, policy


def source_files():
    pins = strict(read(HERE / 'legacy-pins.json'))
    for name, pin in pins.items():
        require(sha(read(ROOT / name)) == pin, 'PRESERVED_SOURCE_DRIFT: ' + name)
    files = dict(pins)
    for path in sorted(HERE.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        require(not path.is_symlink(), 'SOURCE_SYMLINK')
        if path.is_file():
            files[str(path.relative_to(ROOT))] = sha(read(path))
    return files


def source_commitment():
    return sha(canonical(source_files()))


def verifier_dependencies():
    directory = ROOT / 'adapters/hookr-case/node_modules'
    require(directory.is_dir() and not directory.is_symlink(), 'RETAINED_VERIFIER_DEPENDENCIES_REQUIRED')
    files = {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'VERIFIER_DEPENDENCY_SYMLINK')
        if path.is_file():
            files[str(path.relative_to(directory))] = sha(read(path))
    require('viem/package.json' in files and 'hookr-sdk/package.json' in files, 'VERIFIER_DEPENDENCIES_INCOMPLETE')
    return files


def replacement(raw):
    require(sha(raw) == '341f27d85edf31aa4193ec2aca4ce01c1b57378934d8e5548573eb730d229bb9',
            'ORIGINAL_LP_VALIDATOR_PIN')
    old = b'result[10], result[11] = 0, 0'
    require(raw.count(old) == 1, 'EXACT_LP_TRANSFORM')
    return raw.replace(old, b'result[10], result[11] = 0, 50')
