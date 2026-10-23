"""One local entry point; setup/build and recorded-result verification never replay history."""
import argparse
import json
from pathlib import Path
import sys

from .common import REPO, require, read_json, commitment, sources
from .build import compile_developer
from . import kit


def main(argv=None):
    require(sys.version_info >= (3, 12), 'PYTHON_3_12_OR_NEWER_REQUIRED')
    require(not sys.flags.optimize, 'PYTHON_OPTIMIZATION_FORBIDDEN')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('setup', help='Build dependencies/adapter and import one separately supplied saved package; never replay')
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--bootstrap', action='store_true', help='Explicitly allow pinned dependency downloads and Go/Rust build in a fresh root')
    p = sub.add_parser('build', help='Adapter and sensor build only, using a completed dependency root')
    p.add_argument('--build-root', type=Path, required=True)
    p = sub.add_parser('init', help='Import package and attach an existing developer build record')
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--build-record', type=Path, required=True)
    for cmd in ['doctor', 'prepare', 'replay']:
        p = sub.add_parser(cmd, help={'doctor': 'Read-only fresh resource samples; no native execution',
                                     'prepare': 'Validate and bind a fresh run without sampling or execution',
                                     'replay': 'Explicit one-use offline native pair with fresh developer admission'}[cmd])
        p.add_argument('--workspace', type=Path, required=True)
        p.add_argument('--name', required=True, help='Unique local diagnostic/run name, lowercase letters/digits/hyphens')
        if cmd == 'replay':
            p.add_argument('--confirm-native', action='store_true')
            p.add_argument('--mac-ready', action='store_true', help='Operator confirms power connected and lid open')
    p = sub.add_parser('verify', help='Verify a saved developer result and all hashes, no EVM execution')
    p.add_argument('--run', type=Path, required=True)
    p = sub.add_parser('diagnostic', help='Show a saved doctor decision and raw resource values, without taking new measurements')
    p.add_argument('--path', type=Path, required=True)
    p = sub.add_parser('policy', help='Print the developer policy; no sensors')
    a = parser.parse_args(argv)
    if a.command == 'build': result = {'status': 'BUILD_ONLY_PASS', 'buildRecord': str(compile_developer(a.build_root))}
    elif a.command == 'setup':
        # Reject bad input and used destination before expensive build/download work.
        from .common import portable, local_file, path_without_links
        package = local_file(a.package, 32<<20)
        portable.validate_package(package.read_bytes(), portable.specification(REPO))
        portable.fresh_output(a.workspace, [REPO, package, a.build_root])
        root = path_without_links(a.build_root)
        if a.bootstrap:
            import build_pair03 as build
            lock = read_json(REPO/'repro/dependencies.lock.json')
            build.bootstrap(REPO, root, lock)
            build.build_only(REPO, root, lock)
        build_record = root/'developer-alpha'/('developer-alpha-'+commitment(sources())[:16])/'BUILD.json'
        if not build_record.exists(): build_record = compile_developer(root)
        result = kit.initialize(a.workspace, a.package, build_record)
    elif a.command == 'init': result = kit.initialize(a.workspace, a.package, a.build_record)
    elif a.command == 'doctor': result = kit.doctor(a.workspace, a.name)
    elif a.command == 'prepare':
        b = kit.prepare(a.workspace, a.name)
        result = {'status': 'PREPARED_NATIVE_NOT_RUN', 'operationCommitment': b['operationCommitment'],
                  'profile': b['profile'], 'bindings': str(a.workspace/'proposals'/a.name/'BINDINGS.json')}
    elif a.command == 'replay': result = kit.replay(a.workspace, a.name, confirm_native=a.confirm_native, mac_ready=a.mac_ready)
    elif a.command == 'verify': result = kit.verify_run(a.run)
    elif a.command == 'diagnostic': result = kit.diagnostic(a.path)
    else:
        from .resources import POLICY
        result = POLICY
    print(json.dumps(result, indent=2))
    if result.get('status') == 'HOST_STOP' or a.command == 'replay' and result.get('terminal') != 'DEVELOPER_PAIR03_REPLAY_PASS': return 1
    return 0


if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({'status': 'STOP', 'cause': str(error)}), file=sys.stderr)
        sys.exit(1)
