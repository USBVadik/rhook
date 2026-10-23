"""Reuse authenticated v1 code in isolated v2 module namespaces.

Only these checked-in source files are executable inputs. No runtime record,
external path or caller-supplied code is loaded. Exact edit counts reject drift.
The original modules/files and their globals remain unchanged.
"""
import hashlib
from pathlib import Path
import types

REPO = Path(__file__).resolve().parents[1]
BASE_COMMIT = 'e9af4dfd999846d8ace36fce4068de054362aa19'
PINS = {
    'sdk_alpha/resources.py': '6d2711eccbb5b8993d2398637de3d7b499f6790aad4719f8c75df0be3993ef49',
    'sdk_alpha/kit.py': '63bd05fa235cfc5632fbcdc9fc2bcd59164794dd427ac37ac41864d58623a667',
    'sdk_alpha/build.py': '1ed965ac8e0ac1ed6baa061538f0d6f53669abb7fc66142f1f7131c3fc18da3c',
    'sdk_alpha/__main__.py': '830ae72e1f0db493febdc95b9a632365f0c15523d4f309b416a425612ca86882',
    'repro/portable/legacy_guards.py': '073bd72dea8cbdef31b6d6af61e1b9c71959c8e840fa4fbc29e276a50a14f36f',
}


def source(relative, edits=()):
    if relative not in PINS: raise ValueError('UNREVIEWED_V1_SOURCE')
    path = REPO/relative
    if any(p.is_symlink() for p in [path, *path.parents]): raise ValueError('V1_SOURCE_SYMLINK')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PINS[relative]: raise ValueError('FROZEN_V1_SOURCE_DRIFT: '+relative)
    text = raw.decode()
    for old, new, count in edits:
        if text.count(old) != count: raise ValueError('V2_ADAPTER_BOUNDARY_DRIFT: '+old)
        text = text.replace(old, new)
    return text


def bind(namespace, relative, edits=()):
    # Relative imports in frozen source resolve only to the v2 package.
    text = source(relative, edits)
    exec(compile(text, 'authenticated-v1/'+relative, 'exec'), namespace)


def isolated_guards():
    module = types.ModuleType('sdk_alpha_v2._worker_guards')
    module.__package__ = 'sdk_alpha_v2'
    bind(vars(module), 'repro/portable/legacy_guards.py', [
        ('4<<30', '1<<30', 2),
        ("'GOMEMLIMIT':'1073741824'", "'GOMEMLIMIT':'536870912'", 1),
    ])
    return module
