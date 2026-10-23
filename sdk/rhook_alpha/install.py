"""Install the private Alpha using accepted, prebuilt native assets."""
import argparse
import json
import os
from pathlib import Path
import platform
import secrets
import shlex
import shutil
import subprocess
import sys
import venv

from developer import install as baseline
from developer.files import canonical, digest, load, no_links, require, save, sha, sync, tree

SOURCE_COMMIT = '3a4e8e326ce8d61a0160dc21ca94e3ab4355c3b6'
BUNDLE_SHA256 = 'fcc13ab3013054cb4df646b82bbc054b9eba71666a50912925824c0e75d84b20'
PACKAGE = Path(__file__).resolve().parent


def launcher(prefix):
    return '#!/bin/sh\nexec ' + shlex.quote(str(prefix / 'python/bin/python')) + ' -I -B -m rhook_alpha.cli "$@"\n'


def install(prefix, bundle, runtime_source=None):
    prefix, bundle = no_links(prefix), no_links(bundle)
    require(sha(bundle, 1 << 30) == BUNDLE_SHA256, 'EXACT_PRIVATE_INPUT_BUNDLE_REQUIRED')
    require(runtime_source is not None, "ACCEPTED_RUNTIME_SOURCE_REQUIRED")
    result = baseline.install(prefix, bundle, runtime_source)
    # ALPHA_INSTALL.json is published last. A partial install cannot authenticate
    # or issue grants, and is never silently repaired by a subsequent install.
    package = prefix / 'lib/rhook_alpha'; package.mkdir()
    for source in sorted(PACKAGE.glob('*.py')):
        require(not source.is_symlink(), 'ALPHA_SOURCE_SYMLINK')
        shutil.copyfile(source, package / source.name)
    venv.EnvBuilder(with_pip=False, symlinks=False).create(prefix / 'python')
    python = prefix / 'python/bin/python'
    probe = subprocess.run([str(python), '-I', '-B', '-c', 'import sysconfig;print(sysconfig.get_path("purelib"))'],
                           check=True, capture_output=True, timeout=10, env={'PATH': '/usr/bin:/bin'})
    site = no_links(probe.stdout.decode().strip())
    require(site.is_relative_to(prefix / 'python'), 'VENV_SITE_PATH')
    pth = site / 'rhook_alpha.pth'
    pth.write_text('import sys; sys.dont_write_bytecode = True\n' + str(prefix / 'lib') + '\n')
    command = prefix / 'bin/rhook'; command.chmod(0o700); command.write_text(launcher(prefix)); command.chmod(0o500)
    record = load(prefix / 'INSTALL.json'); record['launcherSha256'] = sha(command)
    # This is a derived installation record, not an accepted source or engine seal.
    with (prefix / 'INSTALL.json').open('wb') as stream:
        stream.write(canonical(record) + b'\n'); stream.flush(); os.fsync(stream.fileno())
    key = secrets.token_bytes(32)
    fd = os.open(prefix / '.local-consent.key', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(key); stream.flush(); os.fsync(stream.fileno())
    installation_id = secrets.token_hex(16)
    environment = {'installationId': installation_id, 'ownerUid': os.getuid(), 'host': os.uname().nodename,
                   'platform': sys.platform, 'machine': platform.machine(), 'prefix': str(prefix)}
    runtime_files = {str(path.relative_to(prefix)): sha(path) for path in (python, pth, prefix / 'python/pyvenv.cfg')}
    save(prefix / 'ALPHA_INSTALL.json', {'schema': 'rhook/executable-alpha-install/0.1',
         'prefix': str(prefix), 'installationId': installation_id, 'environment': environment,
         'baselineCommit': SOURCE_COMMIT, 'alphaFiles': tree(package), 'runtimeFiles': runtime_files,
         'keySha256': digest(key), 'localConsentOnly': True, 'externalDelivery': 'HOLD'})
    result.update(status='EXECUTABLE_ALPHA_INSTALLED', python=str(python),
                  localConsentOnly=True, nativeValues=[0, 50], planningValues='0..99')
    sync(prefix)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prefix', required=True, type=Path)
    p.add_argument('--assets', required=True, type=Path)
    p.add_argument('--runtime-source', required=True, type=Path, help='Exact original engine tree, distributed separately')
    args = p.parse_args(argv)
    try: value = install(args.prefix, args.assets, args.runtime_source)
    except (ValueError, OSError, KeyError, TypeError, EOFError, subprocess.SubprocessError) as error:
        value = {'status': 'INSTALL_FAILED', 'causeCode': str(error)[:240], 'nativeExecuted': False}
    print(json.dumps(value, ensure_ascii=True))
    return 0 if value['status'] == 'EXECUTABLE_ALPHA_INSTALLED' else 1
