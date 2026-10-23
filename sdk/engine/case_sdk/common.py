"""Bounded local data admission and source identities; no execution on import."""
import hashlib
import json
import os
from pathlib import Path
import stat
ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'case_sdk'
DOMAIN = 'HOOKR_UNIFIED_PLAN_NATIVE_0_1'
PROFILE = 'hookr-case-darwin-arm64/0.1'

def require(ok, code):
    if not ok:
        raise ValueError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

def commit(domain, value):
    return sha(domain.encode('ascii') + b'\n' + canonical(value))

def no_links(path):
    path = Path(path).absolute()
    require(all((not p.is_symlink() for p in (path, *path.parents))), 'INPUT_SYMLINK')
    return path

def read(path, maximum=32 << 20):
    path = no_links(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise ValueError('INPUT_OPEN_REJECTED') from error
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum, 'INPUT_TYPE_OR_SIZE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(maximum + 1)
        require(len(raw) <= maximum, 'INPUT_SIZE')
        return raw
    finally:
        os.close(fd)

def strict(raw, *, allow_fractions=False):
    try:
        text = raw.decode('utf-8', errors='strict') if isinstance(raw, bytes) else raw
        depth = 0
        quoted = False
        escape = False
        for char in text:
            if quoted:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in '[{':
                depth += 1
                require(depth <= 64, 'JSON_DEPTH')
            elif char in ']}':
                depth -= 1

        def pairs(items):
            out = {}
            for key, value in items:
                require(key not in out, 'DUPLICATE_JSON_KEY')
                out[key] = value
            return out

        def integer(token):
            require(token != '-0' and len(token) <= 16, 'JSON_INTEGER')
            n = int(token)
            require(abs(n) <= 9007199254740991, 'JSON_INTEGER')
            return n

        def reject(_):
            raise ValueError('JSON_INTEGER_REQUIRED')

        def fraction(token):
            import re, math
            require(allow_fractions and re.fullmatch('-?(0|[1-9][0-9]*)\\.[0-9]+', token), 'JSON_INTEGER_REQUIRED')
            value = float(token)
            require(math.isfinite(value) and abs(value) <= 9007199254740991, 'JSON_NUMBER_RANGE')
            return value
        return json.loads(text, object_pairs_hook=pairs, parse_int=integer, parse_float=fraction, parse_constant=reject)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('INVALID_JSON') from error

def case_descriptor():
    return strict(read(HERE / 'case.json', 32 << 10))

def sources():
    pins = strict(read(HERE / 'accepted-source.json'))
    require(sha(canonical(pins)) == '361e59224a54e4f449c8886fb1fe3cf757e468b4bc6ccf57031a2d1afb809a5f', 'ACCEPTED_SOURCE_PIN')
    for name, pin in pins.items():
        require(sha(read(ROOT / name)) == pin, 'BASELINE_SOURCE_DRIFT')
    files = dict(pins)
    for path in sorted(HERE.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        require(not path.is_symlink(), 'SOURCE_SYMLINK')
        if path.is_file():
            files[str(path.relative_to(ROOT))] = sha(read(path))
    for name in ['rhook-case', 'adapters/hookr-case/runtime.ts', 'adapters/hookr-case/test/runtime.test.ts']:
        if (ROOT / name).exists():
            files[name] = sha(read(ROOT / name))
    return files
import types
from sdk_alpha_v2 import common as _v2
from sdk_alpha_v2._frozen import isolated_guards
REPO = ROOT
portable = types.SimpleNamespace(**vars(_v2.portable))
portable.guards = isolated_guards()
store = portable.guards.store
local_file = _v2.local_file
