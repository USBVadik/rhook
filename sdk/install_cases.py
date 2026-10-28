"""Install the portable case CLI without downloading or executing a runtime."""
import argparse
import os
from pathlib import Path
import shutil
import sys
ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from developer.files import canonical, no_links, require, save, tree

def install(prefix, dependencies=None):
    require(sys.version_info >= (3, 12) and (not sys.flags.optimize), 'PYTHON_3_12_UNOPTIMIZED_REQUIRED')
    prefix = no_links(prefix)
    require(not prefix.exists() and (not prefix.is_relative_to(ROOT)), 'FRESH_EXTERNAL_INSTALLATION_REQUIRED')
    prefix.mkdir(mode=0o700, parents=True)
    (prefix / 'lib').mkdir()
    (prefix / 'bin').mkdir()
    for name in ('rhook_alpha', 'developer', 'engine'):
        shutil.copytree(ROOT / name, prefix / 'lib' / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'node_modules', '.DS_Store'))
    if dependencies is not None:
        from developer.files import dependencies as authenticate_dependencies
        authenticate_dependencies(no_links(dependencies))
        shutil.copytree(dependencies, prefix / 'lib/engine/adapters/hookr-case/node_modules')
    command = prefix / 'bin/rhook-cases'
    command.write_text('#!' + sys.executable + ' -I\nimport sys\nfrom pathlib import Path\nsys.dont_write_bytecode=True\nsys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lib"))\nfrom rhook_alpha.cases.__main__ import main\nraise SystemExit(main())\n')
    command.chmod(0o700)
    save(prefix / 'CASE_INSTALL.json', {'schema': 'rhook/case-cli-install/0.1', 'files': tree(prefix), 'runtimeIncluded': False, 'nativeExecuted': False})
    return command
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prefix', type=Path, required=True)
    p.add_argument('--dependencies', type=Path)
    args = p.parse_args()
    try:
        command = install(args.prefix, args.dependencies)
        print(canonical({'status': 'INSTALLED', 'command': str(command), 'runtimeIncluded': False, 'nativeExecuted': False}).decode())
    except (ValueError, OSError) as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
