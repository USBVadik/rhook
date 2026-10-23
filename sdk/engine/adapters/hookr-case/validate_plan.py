"""Offline Python boundary: revalidate a semantic plan without executing it."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import stat

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location('hookr_saved_package', REPO / 'repro/portable_pair03.py')
saved_package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(saved_package)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def commitment(domain, value):
    return hashlib.sha256((domain + '\n' + canonical(value)).encode()).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('JSON_CONSTANT')))


def read_input(path, limit):
    checked = saved_package.local_file(path, limit)
    fd = os.open(checked, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('INPUT_FILE_TYPE_OR_SIZE')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            data = source.read(limit + 1)
        if len(data) > limit:
            raise ValueError('INPUT_SIZE_LIMIT')
        return data
    finally:
        os.close(fd)


def validate_plan(package_bytes, proposed):
    """Reuse the SDK's exact package pin; independently rebuild slot/mask/word."""
    saved = saved_package.specification(REPO)
    saved_package.validate_package(package_bytes, saved)
    pins = strict_json((HERE / 'pins.json').read_bytes())
    if not isinstance(proposed, dict):
        raise ValueError('PLAN_OBJECT')
    values = [proposed.get('expectedOld'), proposed.get('newValue')]
    if any(not isinstance(v, str) or not v.isascii() or not v.isdecimal()
           or str(int(v)) != v or len(v) > 4 for v in values):
        raise ValueError('DECIMAL_BPS_REQUIRED')
    old, new = map(int, values)
    source = saved['intervention']
    original = int(source['expectedOldWord'], 16)
    if old != (original >> 160) & 65535:
        raise ValueError('EXPECTED_OLD')
    if not int(pins['minimumNewValue']) <= new <= int(pins['maximumNewValue']) or old == new:
        raise ValueError('CASE_LP_RANGE_OR_NO_CHANGE')
    identity = {'schema': 'rhook/hookr-case/0.1', 'packageSha256': saved['packageSha256'],
                'checkpoint': saved['checkpoint'], 'blockNumber': str(saved['blockNumber']),
                'blockHash': saved['blockHash'], 'arrivals': saved['arrivals'],
                'poolId': source['pool'], 'generation': 'hookr-1', 'rulesModule': 'standard'}
    mask = 65535 << 160
    if source['mask'] != f'0x{mask:064x}':
        raise ValueError('PINNED_MASK')
    intervention = dict(source, newWord=f'0x{((original & ~mask) | (new << 160)):064x}')
    body = {'schema': 'rhook/hookr-plan/0.1',
            'caseId': commitment('rhook/hookr-case/0.1', identity),
            'packageSha256': saved['packageSha256'], 'ruleId': pins['caseRule'],
            'expectedOld': values[0], 'newValue': values[1], 'intervention': intervention,
            'status': 'PLANNED_NOT_EXECUTED', 'branchResult': None,
            'savedInterventionMatch': intervention == source,
            'executionSupport': 'MATCHES_SAVED_INTERVENTION' if new == 0 else 'NEW_NATIVE_PLAN_REQUIRED',
            'witnessClosure': 'NOT_EVALUATED', 'executionAuthorized': False}
    expected = dict(body, planCommitment=commitment('rhook/hookr-plan/0.1', body))
    # Compare canonical JSON bytes, including exact types and unknown fields.
    if canonical(proposed) != canonical(expected):
        raise ValueError('PLAN_MISMATCH')
    return {'status': 'INTERVENTION_VALIDATED_NOT_AUTHORIZED',
            'planCommitment': expected['planCommitment'], 'intervention': intervention,
            'nativeInvocations': 0, 'executionAuthorized': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--plan', required=True)
    args = parser.parse_args()
    try:
        # Existing no-symlink, regular-file and size guards; no sensor/native entry.
        package = read_input(args.package, 2 << 20)
        raw = read_input(args.plan, 16384)
        print(json.dumps(validate_plan(package, strict_json(raw)), indent=2))
    except Exception:
        raise SystemExit('PLAN_REJECTED')
