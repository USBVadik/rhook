"""Small file primitives for trusted local installation directories."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

SOURCE_COMMITMENT = '5460f0c6fcf029ad09f3b12b711c3c9e34d438db4803d8ceb160263c72c7b9f1'
DEPENDENCY_COMMITMENT = 'b4f0794af5857e7159412bbc8ab02ed60562bc0940bb5c54f325028a3651e511'
ARTIFACT_MANIFEST_SHA256 = 'ecc21919d7e9d0aa0e6b8a1599b1c33738e3a4796727070d7b055dcdbee4982d'
MAX_FILE_BYTES = 256 << 20

def require(ok, code):
    if not ok:
        raise ValueError(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(value).hexdigest()

def no_links(value):
    path = Path(value).absolute()
    require('..' not in path.parts and all(not p.is_symlink() for p in (path, *path.parents)), 'SYMLINK_OR_TRAVERSAL')
    return path

def relative(value):
    path = PurePosixPath(value)
    require(isinstance(value, str) and str(path) == value and not path.is_absolute() and '..' not in path.parts and value not in ('', '.'), 'ARCHIVE_PATH')
    return path

def read(path, limit=2 << 20):
    path = no_links(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, 'FILE_TYPE_OR_SIZE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, 'FILE_SIZE')
        return raw
    finally:
        os.close(fd)

def sha(path, limit=MAX_FILE_BYTES):
    # Stream binaries rather than creating a second full copy in Python memory.
    path = no_links(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, 'FILE_TYPE_OR_SIZE')
        h, count = hashlib.sha256(), 0
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            while chunk := stream.read(1 << 20):
                count += len(chunk)
                require(count <= limit, 'FILE_SIZE')
                h.update(chunk)
        return h.hexdigest()
    finally:
        os.close(fd)

def strict(raw):
    text = raw.decode('utf-8', errors='strict')
    depth = 0; quoted = False; escape = False
    for char in text:
        if quoted:
            if escape: escape = False
            elif char == '\\': escape = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in '[{':
            depth += 1
            require(depth <= 64, 'JSON_DEPTH')
        elif char in ']}': depth -= 1
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'DUPLICATE_JSON_KEY')
            result[k] = v
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'JSON_CONSTANT'))

def load(path, limit=2 << 20):
    return strict(read(path, limit))

def sync(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def save(path, value):
    path = no_links(path)
    with path.open('xb') as f:
        f.write(canonical(value) + b'\n'); f.flush(); os.fsync(f.fileno())
    sync(path.parent)

def tree(root, omit=()):
    root = no_links(root)
    require(root.is_dir(), 'DIRECTORY_REQUIRED')
    files = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'TREE_SYMLINK')
        if path.is_file():
            name = str(path.relative_to(root))
            if name not in omit: files[name] = sha(path)
        else: require(path.is_dir(), 'TREE_SPECIAL_FILE')
    return files

def accepted_source(root, engine_root=None):
    engine_root = root / "engine" if engine_root is None else no_links(engine_root)
    manifest = load(root / 'developer/accepted-source.json')
    files = manifest['files']
    require(manifest['sourceCommitment'] == SOURCE_COMMITMENT == digest(canonical(files)) and len(files) == 198, 'SOURCE_MANIFEST')
    for name, pin in files.items():
        relative(name)
        require(sha(engine_root / name) == pin, 'ACCEPTED_SOURCE_DRIFT: ' + name)
    return files

def dependencies(path):
    files = tree(path, omit=('.package-lock.json',))
    require(digest(canonical(files)) == DEPENDENCY_COMMITMENT, 'DEPENDENCY_CLOSURE_MISMATCH')
    return files

def artifact_pins(root):
    raw = read(root / 'developer/artifacts.json')
    require(digest(raw) == ARTIFACT_MANIFEST_SHA256, 'ARTIFACT_MANIFEST_DRIFT')
    return strict(raw)
