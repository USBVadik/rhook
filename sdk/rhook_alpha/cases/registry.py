"""Immutable capsule objects, separate local names, no extraction or imports of code."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import tempfile
from developer.files import canonical, load, no_links, read, require, save, sync
from .capsule import MAX_PACKAGE, validate

class Registry:

    def __init__(self, home):
        self.home = no_links(home)

    def _prepare(self):
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(self.home.stat().st_uid == os.getuid() and self.home.stat().st_mode & 0o077 == 0, 'PRIVATE_CASE_HOME_REQUIRED')
        for name in ('objects', 'names', 'plans', 'runs', 'consents'):
            p = no_links(self.home / name)
            p.mkdir(mode=0o700, exist_ok=True)
        sync(self.home)

    def import_case(self, directory):
        src = no_links(directory)
        raw = read(src / 'BLOCK_PACKAGE.json', MAX_PACKAGE)
        d = validate(load(src / 'CAPSULE.json', 65536), raw)
        self._prepare()
        fd = os.open(self.home / '.registry.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            import stat
            require(stat.S_ISREG(os.fstat(fd).st_mode), 'REGISTRY_LOCK_TYPE')
            fcntl.flock(fd, fcntl.LOCK_EX)
            alias = no_links(self.home / 'names' / d['caseId'])
            target = no_links(self.home / 'objects' / d['capsuleId'])
            if alias.exists():
                require(load(alias) == {'capsuleId': d['capsuleId']}, 'CASE_ID_ALREADY_REGISTERED')
                self.resolve(d['caseId'])
                return self.inspect(d['caseId'])
            if target.exists():
                require(load(target / 'CAPSULE.json') == d and read(target / 'BLOCK_PACKAGE.json', MAX_PACKAGE) == raw, 'EXISTING_CAPSULE_DRIFT')
            else:
                temp = Path(tempfile.mkdtemp(prefix='.import-', dir=self.home / 'objects'))
                try:
                    save(temp / 'CAPSULE.json', d)
                    with (temp / 'BLOCK_PACKAGE.json').open('xb') as f:
                        f.write(raw)
                        f.flush()
                        os.fsync(f.fileno())
                    sync(temp)
                    os.rename(temp, target)
                    sync(target.parent)
                finally:
                    if temp.exists():
                        shutil.rmtree(temp)
            save(alias, {'capsuleId': d['capsuleId']})
        finally:
            os.close(fd)
        return self.inspect(d['caseId'])

    def resolve(self, case):
        require(type(case) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', case), 'CASE_ID')
        ref = load(self.home / 'names' / case, 4096)
        require(type(ref) is dict and set(ref) == {'capsuleId'} and re.fullmatch('[0-9a-f]{64}', ref['capsuleId']), 'REGISTRY_REFERENCE')
        path = no_links(self.home / 'objects' / ref['capsuleId'])
        d = validate(load(path / 'CAPSULE.json', 65536), read(path / 'BLOCK_PACKAGE.json', MAX_PACKAGE))
        require(d['capsuleId'] == ref['capsuleId'] and d['caseId'] == case, 'REGISTRY_CASE_LINK')
        return (path, d)

    def inspect(self, case):
        _, d = self.resolve(case)
        return {'status': 'IMPORTED', 'caseId': case, 'capsuleId': d['capsuleId'], 'checkpoint': d['checkpoint'], 'target': d['target'], 'arrivals': len(d['arrivals']), 'adapter': d['adapter']['id'], 'profile': d['execution']['profile'], 'authentication': 'UNAUTHENTICATED', 'nativeSupported': False, 'witnessClosure': 'NOT_EVALUATED', 'chainTrust': 'NOT_ESTABLISHED_BY_LOCAL_HASHES', 'executionAuthorized': False}

    def list_cases(self):
        if not (self.home / 'names').exists():
            return []
        return [self.inspect(p.name) for p in sorted((self.home / 'names').iterdir())]
