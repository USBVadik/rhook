"""Authenticate the installed wrapper and the unchanged execution runtime."""
import os
from pathlib import Path
import platform
import sys

from developer import cli as engine
from developer.files import digest, load, no_links, read, require, sha, tree

PREFIX = Path(__file__).resolve().parents[2]


def context():
    manifest = load(PREFIX / 'ALPHA_INSTALL.json')
    require(manifest['schema'] == 'rhook/executable-alpha-install/0.1' and
            manifest['prefix'] == str(PREFIX), 'ALPHA_INSTALL_PREFIX')
    require(tree(PREFIX / 'lib/rhook_alpha') == manifest['alphaFiles'], 'ALPHA_CODE_DRIFT')
    for name, pin in manifest['runtimeFiles'].items():
        require(sha(PREFIX / name) == pin, 'ALPHA_PYTHON_RUNTIME_DRIFT')
    actual = {'installationId': manifest['installationId'], 'ownerUid': os.getuid(),
              'host': os.uname().nodename, 'platform': sys.platform, 'machine': platform.machine(),
              'prefix': str(PREFIX)}
    require(actual == manifest['environment'] and actual['platform'] == 'darwin' and
            actual['machine'] == 'arm64', 'ALPHA_LOCAL_ENVIRONMENT_CHANGED')
    require(PREFIX.stat().st_uid == os.getuid() and PREFIX.stat().st_mode & 0o077 == 0, 'PRIVATE_INSTALLATION_REQUIRED')
    key_path = no_links(PREFIX / '.local-consent.key')
    require(key_path.stat().st_uid == os.getuid() and key_path.stat().st_mode & 0o077 == 0, 'PRIVATE_INSTALLATION_KEY_REQUIRED')
    key = read(key_path, 32)
    require(len(key) == 32 and digest(key) == manifest['keySha256'], 'INSTALLATION_KEY_DRIFT')
    pins = engine.installation()
    sys.path.insert(0, str(PREFIX / 'lib/engine'))
    return pins, actual, key
