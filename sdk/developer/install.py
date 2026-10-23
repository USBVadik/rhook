"""Install the preserved case engine with one explicit private input bundle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from developer.files import artifact_pins, accepted_source, dependencies, digest, load, no_links, relative, require, save, sha, strict, sync, tree

class RegularTarInfo(tarfile.TarInfo):
    def _proc_member(self, archive):
        require(self.type in (tarfile.REGTYPE, tarfile.AREGTYPE), 'REGULAR_USTAR_FILES_ONLY')
        return super()._proc_member(archive)

def extract(bundle, target, pins):
    require(sha(bundle, 1 << 30), 'BUNDLE_REQUIRED')
    with tarfile.open(bundle, 'r|gz', tarinfo=RegularTarInfo) as archive:
        members = iter(archive)
        first = next(members, None)
        require(first is not None and first.name == 'ASSETS.json' and first.isfile() and first.size <= 4 << 20, 'ASSET_MANIFEST_REQUIRED')
        manifest = strict(archive.extractfile(first).read((4 << 20) + 1))
        require(manifest['schema'] == 'rhook/private-alpha-inputs/0.1', 'ASSET_SCHEMA')
        files = manifest['files']
        require(isinstance(files, dict) and len(files) <= 16000, 'ASSET_COUNT')
        require(all(name in files and files[name] == pin for name, pin in pins['files'].items()), 'REQUIRED_ASSET_PIN')
        total = 0
        for name, row in files.items():
            relative(name)
            require(type(row) is dict and set(row) == {'bytes', 'sha256'} and isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'ASSET_ROW_SHAPE')
            require(name in pins['files'] or name.startswith('node_modules/'), 'UNEXPECTED_ASSET')
            require(type(row['bytes']) is int and 0 <= row['bytes'] <= 256 << 20, 'ASSET_SIZE')
            total += row['bytes']
        require(total <= 768 << 20, 'BUNDLE_TOTAL_LIMIT')
        seen = set()
        for member in members:
            name = member.name
            relative(name)
            require(member.isfile() and name in files and name not in seen and not member.issparse(), 'UNEXPECTED_ARCHIVE_MEMBER')
            require(member.size == files[name]['bytes'], 'ARCHIVE_MEMBER_SIZE')
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            h, count = hashlib.sha256(), 0
            with archive.extractfile(member) as source, destination.open('xb') as output:
                while chunk := source.read(1 << 20):
                    count += len(chunk); require(count <= member.size, 'ARCHIVE_STREAM_SIZE')
                    h.update(chunk); output.write(chunk)
                output.flush(); os.fsync(output.fileno())
            require(count == member.size and h.hexdigest() == files[name]['sha256'], 'ARCHIVE_STREAM_HASH')
            destination.chmod(0o500 if name in ('node', 'worker', 'sensor') else 0o400)
            seen.add(name)
        require(seen == set(files), 'INCOMPLETE_BUNDLE')
    dependencies(target / 'node_modules')
    return files

def install(prefix, bundle, runtime_source=None):
    require(sys.version_info >= (3, 12) and not sys.flags.optimize, 'PYTHON_3_12_UNOPTIMIZED_REQUIRED')
    require(sys.platform == 'darwin' and platform.machine() == 'arm64', 'MACOS_ARM64_ONLY')
    files = accepted_source(ROOT) if runtime_source is None else accepted_source(ROOT, runtime_source)
    engine_source = ROOT / "engine" if runtime_source is None else no_links(runtime_source)
    pins = artifact_pins(ROOT)
    prefix, bundle = no_links(prefix), no_links(bundle)
    require(prefix.parent.is_dir() and not prefix.exists(), 'FRESH_INSTALL_PREFIX_REQUIRED')
    require(not prefix.is_relative_to(engine_source), 'INSTALL_SOURCE_OVERLAP')
    temporary = Path(tempfile.mkdtemp(prefix='.rhook-install-', dir=prefix.parent))
    reserved = False
    try:
        assets = temporary / 'assets'; assets.mkdir()
        extract(bundle, assets, pins)
        lib = temporary / 'lib'; lib.mkdir()
        engine = lib / 'engine'; engine.mkdir()
        for name, pin in files.items():
            target = engine / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(engine_source / name, target)
            require(sha(target) == pin, 'COPIED_SOURCE_DRIFT')
        shutil.move(str(assets / 'node_modules'), engine / 'adapters/hookr-case/node_modules')
        (lib / 'developer').mkdir()
        for name in ['__init__.py', 'files.py', 'cli.py', 'artifacts.json', 'accepted-source.json']:
            shutil.copyfile(ROOT / 'developer' / name, lib / 'developer' / name)
        runtime = prefix / 'assets'
        registration = {'schema': 'rhook/case-sdk-build/0.1', 'status': 'BUILD_ONLY_PASS', 'productionWorkerLaunched': False,
                        'sourceCommitment': pins['sourceCommitment'], 'sourceFiles': files,
                        'caseDescriptorSha256': pins['caseDescriptorSha256'], 'policySha256': pins['policySha256'],
                        'verifierDependenciesCommitment': pins['verifierDependenciesCommitment'],
                        'registrationKind': 'DERIVED_INSTALL_REGISTRATION_NOT_NEW_COMPILATION',
                        'originalBuildRecordSha256': pins['originalBuildRecordSha256']}
        for name, path_key, pin_key in [('worker', 'workerPath', 'binarySha256'), ('sensor', 'sensorPath', 'sensorSha256'), ('node', 'nodePath', 'nodeSha256')]:
            registration[path_key] = str(runtime / name)
            registration[pin_key] = pins['files'][name]['sha256']
        save(temporary / 'BUILD.json', registration)
        (temporary / 'bin').mkdir()
        command = '#!/bin/sh\nexec ' + shlex.quote(str(Path(sys.executable).resolve())) + ' -I -B ' + shlex.quote(str(prefix / 'lib/developer/cli.py')) + ' "$@"\n'
        (temporary / 'bin/rhook').write_text(command)
        (temporary / 'bin/rhook').chmod(0o500)
        save(temporary / 'INSTALL.json', {'schema': 'rhook/controlled-alpha-install/0.1', 'prefix': str(prefix), 'bundleSha256': sha(bundle, 1 << 30), 'sourceCommitment': pins['sourceCommitment'], 'buildRecordSha256': sha(temporary / 'BUILD.json'), 'developerFiles': tree(temporary / 'lib/developer'), 'launcherSha256': sha(temporary / 'bin/rhook'), 'externalDelivery': 'HOLD'})
        # Publish only a fully verified installation. No existing prefix is replaced.
        prefix.mkdir(mode=0o700)  # Exclusive publication reservation.
        reserved = True
        temporary.rename(prefix); reserved = False; sync(prefix.parent)
    except BaseException:
        if reserved: prefix.rmdir()
        if temporary.exists(): shutil.rmtree(temporary)
        raise
    return {'status': 'INSTALLED', 'command': str(prefix / 'bin/rhook'), 'sourceCommitment': pins['sourceCommitment'], 'workerSha256': pins['files']['worker']['sha256'], 'nativeExecuted': False, 'externalDelivery': 'HOLD'}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prefix', required=True, type=Path)
    p.add_argument('--assets', required=True, type=Path)
    p.add_argument('--runtime-source', type=Path, help='Authenticated original 198-file engine tree; public snapshot is sanitized')
    a = p.parse_args()
    try:
        print(json.dumps(install(a.prefix, a.assets, a.runtime_source)))
    except (ValueError, OSError, KeyError, TypeError, EOFError, tarfile.TarError) as error:
        print(json.dumps({'status': 'INSTALL_FAILED', 'causeCode': str(error)[:240], 'nativeExecuted': False})); return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
