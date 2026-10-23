"""Shared file checks; imports do not measure the host or start a worker."""
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'repro'))
import portable_pair03 as portable

require = portable.require
sha = portable.sha
commitment = portable.commitment
local_file = portable.local_file
path_without_links = portable.path_without_links
store = portable.guards.store


def sources():
    files = portable.source_closure(REPO)
    for p in sorted((REPO/'sdk_alpha').rglob('*')):
        if '__pycache__' in p.parts: continue
        require(not p.is_symlink(), 'SOURCE_SYMLINK')
        if p.is_file(): files[str(p.relative_to(REPO))] = sha(p)
    files['rhook'] = sha(REPO/'rhook')
    return files


def read_json(path, maximum=2<<20):
    return json.loads(local_file(path, maximum).read_text())


def exact_copy(source, target, maximum=None):
    raw = local_file(source, maximum).read_bytes()
    with Path(target).open('xb') as out:
        out.write(raw); out.flush()
        import os
        os.fsync(out.fileno())
    require(sha(source) == sha(target), 'COPIED_FILE_CHANGED')
