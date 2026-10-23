"""Bounded immutable-input rehearsal, without consent, sensors or execution."""
from pathlib import Path
import hashlib
import json
import os
import stat
import sys

CLI_STAGING_FILE_BYTES = 256 << 20


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def no_links(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('INPUT_OR_DESTINATION_SYMLINK')
    return path


def identity(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def stage(spec_path, destination):
    """Keep partials on failure; READY exists only after every hash passes."""
    spec = json.loads(no_links(spec_path).read_text())
    target = no_links(destination)
    target.mkdir(mode=0o700)  # Exclusive: neither retry nor overwrite.
    rows = []
    names = set()
    for row in spec['inputs']:
        name = row['name']
        if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..', 'READY.json') or name in names:
            raise ValueError('UNSAFE_OR_DUPLICATE_INPUT_NAME')
        names.add(name)
        source = no_links(row['source'])
        expected_size = row['bytes']
        if type(expected_size) is not int or not 0 < expected_size <= CLI_STAGING_FILE_BYTES:
            raise ValueError('STAGING_INPUT_SIZE_LIMIT')
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as src:
            before = os.fstat(src.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
                raise ValueError('STAGING_INPUT_NOT_EXACT_REGULAR_FILE')
            h = hashlib.sha256()
            total = 0
            with (target/name).open('xb') as out:
                while block := src.read(1 << 20):
                    total += len(block)
                    if total > expected_size:
                        raise ValueError('STAGING_INPUT_GREW')
                    h.update(block)
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
            after = os.fstat(src.fileno())
            if identity(before) != identity(after) or identity(after) != identity(os.stat(source, follow_symlinks=False)):
                raise ValueError('STAGING_SOURCE_CHANGED')
            if total != expected_size or h.hexdigest() != row['sha256'] or digest(target/name) != row['sha256']:
                raise ValueError('STAGING_HASH_MISMATCH')
        (target/name).chmod(0o400)  # Snapshot is data, never executed.
        rows.append(dict(row, stagedSha256=row['sha256']))
    ready = {'status': 'INPUTS_STAGED_NOT_AUTHORIZED_NOT_EXECUTED', 'inputs': rows,
             'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}, 'RPC': 0, 'WSS': 0,
             'freshAdmissionStillRequired': True, 'sdkCopiesAndVerifiesAgainAtUse': True,
             'externalDelivery': 'HOLD'}
    with (target/'READY.json').open('x') as out:
        json.dump(ready, out, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    (target/'READY.json').chmod(0o400)
    fd = os.open(target, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return ready


if __name__ == '__main__':
    try:
        result = stage(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({'status': 'STAGING_STOP', 'cause': type(error).__name__+': '+str(error),
                          'workerDispatchAttempted': False, 'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}}))
        sys.exit(1)
    print(json.dumps(result))
