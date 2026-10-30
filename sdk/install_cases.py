"""Install the portable case CLI without downloading or executing a runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import types
ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

INVENTORY_SHA256 = 'ff3514ab35e5a344d5b1f91436972361f745e76ea556ba7574f63cb987cb9d0e'
SOURCE_ROOTS = ('rhook_alpha', 'developer', 'engine')

def bootstrap_read(path, limit):
    """Only stdlib may inspect source before its validation helper is trusted."""
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('INSTALL_BOOTSTRAP_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('INSTALL_BOOTSTRAP_FILE_TYPE_OR_SIZE')
        raw = stream.read(limit + 1)
    if len(raw) > limit: raise ValueError('INSTALL_BOOTSTRAP_FILE_SIZE')
    return raw

def admitted_source():
    """Authenticate all copied bytes before creating an installation."""
    raw = bootstrap_read(ROOT / 'case-install-inventory.json', 128 << 10)
    if hashlib.sha256(raw).hexdigest() != INVENTORY_SHA256:
        raise ValueError('INSTALL_INVENTORY_PIN_MISMATCH')
    inventory = json.loads(raw)
    helper = bootstrap_read(ROOT / 'developer/files.py', 2 << 20)
    if hashlib.sha256(helper).hexdigest() != inventory['files']['developer/files.py']:
        raise ValueError('INSTALL_SOURCE_DRIFT: developer/files.py')
    # Execute the authenticated bytes, not a later import from the mutable tree.
    # This helper imports only stdlib and requires no developer package init.
    tools = types.ModuleType('_rhook_install_files')
    exec(compile(helper, str(ROOT / 'developer/files.py'), 'exec'), vars(tools))
    require = tools.require
    require(inventory['schema'] == 'rhook/case-install-source/0.1'
            and inventory['roots'] == list(SOURCE_ROOTS), 'INSTALL_INVENTORY_PROFILE')
    files = {}
    for name in SOURCE_ROOTS:
        folder = tools.no_links(ROOT / name)
        require(folder.is_dir(), 'INSTALL_SOURCE_DIRECTORY')
        for path in sorted(folder.rglob('*')):
            parts = path.relative_to(ROOT).parts
            if any(p in ('__pycache__', 'node_modules', '.DS_Store') for p in parts) or path.name.endswith('.pyc'):
                continue
            require(not path.is_symlink(), 'INSTALL_SOURCE_SYMLINK')
            if path.is_file(): files[str(path.relative_to(ROOT))] = tools.read(path)
            else: require(path.is_dir(), 'INSTALL_SOURCE_TYPE')
    require(set(files) == set(inventory['files']), 'INSTALL_SOURCE_INVENTORY')
    for name, content in files.items():
        require(tools.digest(content) == inventory['files'][name], 'INSTALL_SOURCE_DRIFT: ' + name)
    executables = set(inventory['executableFiles'])
    require(executables <= set(files), 'INSTALL_INVENTORY_EXECUTABLES')
    return raw, files, executables, tools

def install(prefix, dependencies=None):
    if sys.version_info < (3, 12) or sys.flags.optimize:
        raise ValueError('PYTHON_3_12_UNOPTIMIZED_REQUIRED')
    inventory, sources, executables, tools = admitted_source()
    require = tools.require
    prefix = tools.no_links(prefix)
    require(not prefix.exists() and (not prefix.is_relative_to(ROOT)), 'FRESH_EXTERNAL_INSTALLATION_REQUIRED')
    if dependencies is not None:
        dependencies = tools.no_links(dependencies)
        dependency_files = tools.dependencies(dependencies)
    prefix.mkdir(mode=0o700, parents=True)
    (prefix / 'lib').mkdir()
    (prefix / 'bin').mkdir()
    for name, content in sources.items():
        target = prefix / 'lib' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o755 if name in executables else 0o644)
    (prefix / 'SOURCE_INSTALL_INVENTORY.json').write_bytes(inventory)
    if dependencies is not None:
        shutil.copytree(dependencies, prefix / 'lib/engine/adapters/hookr-case/node_modules')
        require(tools.tree(prefix / 'lib/engine/adapters/hookr-case/node_modules', omit=('.package-lock.json',)) == dependency_files,
                'INSTALLED_DEPENDENCY_DRIFT')
    command = prefix / 'bin/rhook-cases'
    command.write_text('#!' + sys.executable + ' -I\nimport sys\nfrom pathlib import Path\nsys.dont_write_bytecode=True\nsys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lib"))\nfrom rhook_alpha.cases.__main__ import main\nraise SystemExit(main())\n')
    command.chmod(0o700)
    tools.save(prefix / 'CASE_INSTALL.json', {'schema': 'rhook/case-cli-install/0.1', 'files': tools.tree(prefix),
         'sourceInventorySha256': INVENTORY_SHA256, 'runtimeIncluded': False, 'nativeExecuted': False})
    return command
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prefix', type=Path, required=True)
    p.add_argument('--dependencies', type=Path)
    args = p.parse_args()
    try:
        command = install(args.prefix, args.dependencies)
        print(json.dumps({'status': 'INSTALLED', 'command': str(command), 'runtimeIncluded': False, 'nativeExecuted': False}, sort_keys=True, separators=(',', ':'), ensure_ascii=False))
    except (ValueError, OSError) as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
