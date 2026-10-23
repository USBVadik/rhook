"""Build the exact plan worker from retained dependencies. Never launch it."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from .core import HERE, ROOT, inputs, read, require, replacement, sha, source_files, source_commitment


def verify_toolchain(retained):
    lock = json.loads(read(ROOT / 'repro/dependencies.lock.json'))['go']
    archive = retained / 'downloads/go.tar.gz'
    require(sha(read(archive, 128 << 20)) == lock['sha256'], 'GO_ARCHIVE_PIN')
    tools = {}
    with tarfile.open(archive) as tar:
        for item in tar:
            if item.isfile() and item.name.startswith(('go/bin/', 'go/pkg/tool/', 'go/pkg/include/')):
                relative = item.name.removeprefix('go/')
                expected = sha(tar.extractfile(item).read())
                require(sha(read(retained / 'toolchains/go' / relative, 128 << 20)) == expected, 'GO_TOOLCHAIN_DRIFT')
                tools[relative] = expected
    require('bin/go' in tools and 'bin/gofmt' in tools, 'GO_TOOLS_INCOMPLETE')
    return tools


def build(retained, output):
    retained, output = Path(retained).resolve(), Path(output).absolute()
    require(not output.exists(), 'FRESH_BUILD_DIRECTORY_REQUIRED')
    files = source_files(); source = source_commitment(); inputs()
    tools = verify_toolchain(retained)
    prior = json.loads(read(retained / 'records/BUILD_RESULT.json'))
    require(prior['status'] == 'BUILD_ONLY_PASS', 'RETAINED_BUILD_REQUIRED')
    library = retained / 'src/nitro/target/lib/libstylus.a'
    require(sha(read(library, 512 << 20)) == prior['libstylusSha256'] ==
            'd9b05f1e0d3937fd155f194c2b0c610e8966cc1b2f2c449912b21a39d2615b55', 'LIBSTYLUS_PIN')
    deps = json.loads(read(retained / 'records/GO_DEPENDENCIES_VERIFIED.json'))['files']
    for pin in deps:
        require(sha(read(retained / pin['path'], 256 << 20)) == pin['sha256'], 'RETAINED_DEPENDENCY_DRIFT')
    output.mkdir(); module = output / 'worker'; module.mkdir()
    prestate = output / 'prestate'
    shutil.copytree(ROOT / 'native/prestate', prestate)
    original = read(prestate / 'lp_branch.go')
    (prestate / 'lp_branch.go').write_bytes(replacement(original))
    targets = {'github.com/ethereum/go-ethereum': retained / 'src/nitro/go-ethereum',
               'github.com/offchainlabs/nitro': retained / 'src/nitro',
               'local/rhook-robinhood': prestate}
    for original_dir, target_dir in [(ROOT / 'native/prestate', prestate), (ROOT / 'native/saved-pair', module)]:
        text = read(original_dir / 'go.mod').decode()
        for name, target in targets.items():
            if name == 'local/rhook-robinhood' and target_dir == prestate:
                continue
            text, n = re.subn(r'(?m)^(replace ' + re.escape(name) + r' => )[^\n]+',
                              lambda m: m[1] + os.path.relpath(target, target_dir), text)
            require(n == 1, 'MODULE_REPLACEMENT_COUNT')
        require(not re.search(r'=>\s+/', text), 'ABSOLUTE_MODULE_REPLACEMENT')
        (target_dir / 'go.mod').write_text(text)
    for name in ['pair.go', 'go.sum']:
        shutil.copyfile(ROOT / 'native/saved-pair' / name, module / name)
    for source_name, name in [('worker.go', 'main.go'), ('plan.json', 'plan.json'), ('worker_test.go', 'main_test.go')]:
        shutil.copyfile(HERE / source_name, module / name)
    tests = read(ROOT / 'native/saved-pair/pair_test.go').decode()
    synthetic, marker, _ = tests.partition('func TestPinnedSavedPackageAdmissionAndFreshNilSourceBridges')
    require(bool(marker), 'SYNTHETIC_TEST_BOUNDARY')
    (module / 'synthetic_pair_test.go').write_text(synthetic)
    for name in ['tmp', 'cache', 'home']:
        (output / name).mkdir()
    env = {'PATH': str(retained / 'toolchains/go/bin') + ':/usr/bin:/bin:/usr/sbin:/sbin',
           'HOME': str(output / 'home'), 'TMPDIR': str(output / 'tmp'), 'LANG': 'C', 'TZ': 'UTC',
           'GOENV': 'off', 'GOWORK': 'off', 'GOTOOLCHAIN': 'local', 'GOPROXY': 'off', 'GOSUMDB': 'off',
           'GOMODCACHE': str(retained / 'cache/go-mod'), 'GOCACHE': str(output / 'cache'),
           'GOPATH': str(output / 'gopath'), 'CGO_ENABLED': '1', 'CGO_LDFLAGS': '-Wl,-no_warn_duplicate_libraries',
           'GOMAXPROCS': '2', 'GOMEMLIMIT': '1073741824'}
    go = str(retained / 'toolchains/go/bin/go')
    commands = [('tests', [go, 'test', '-mod=readonly', '-p', '2', '-count=1', '-v',
                           '-ldflags=-X main.sourceCommitment=' + source, '.']),
                ('graph', [go, 'list', '-mod=readonly', '-deps', '-json', '.']),
                ('build', [go, 'build', '-mod=readonly', '-trimpath', '-p', '2',
                           '-ldflags=-X main.sourceCommitment=' + source,
                           '-o', str(output / 'rhook-saved-pair'), '.'])]
    for label, command in commands:
        print(label + ': started', flush=True)
        with (output / (label + '.log')).open('xb') as log:
            result = subprocess.run(command, cwd=module, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        require(result.returncode == 0, 'BUILD_STAGE_FAILED: ' + label)
    # Record actual compiler inputs, rejecting dependencies outside the two authenticated roots.
    decoder = json.JSONDecoder(); text = (output / 'graph.log').read_text(); closure = {}
    while text.strip():
        row, end = decoder.raw_decode(text.lstrip()); text = text.lstrip()[end:]
        require(not row.get('Error') and not row.get('DepsErrors'), 'GO_DEPENDENCY_ERROR')
        directory = Path(row['Dir']).resolve()
        require(directory.is_relative_to(retained) or directory.is_relative_to(output), 'GO_DEPENDENCY_OUTSIDE_ROOTS')
        for field in ['GoFiles', 'CgoFiles', 'CFiles', 'CXXFiles', 'MFiles', 'HFiles', 'FFiles', 'SFiles', 'SysoFiles', 'EmbedFiles']:
            for name in row.get(field, []):
                path = (directory / name).resolve()
                require(path.is_relative_to(retained) or path.is_relative_to(output), 'GO_DEPENDENCY_OUTSIDE_ROOTS')
                closure[str(path)] = sha(read(path, 256 << 20))
    require(source_files() == files, 'SOURCE_CHANGED_DURING_BUILD')
    require(verify_toolchain(retained) == tools, 'TOOLCHAIN_CHANGED_DURING_BUILD')
    for pin in deps:
        require(sha(read(retained / pin['path'], 256 << 20)) == pin['sha256'], 'RETAINED_DEPENDENCY_CHANGED_DURING_BUILD')
    require(sha(read(library, 512 << 20)) == prior['libstylusSha256'], 'LIBRARY_CHANGED_DURING_BUILD')
    require(read(module / 'pair.go') == read(ROOT / 'native/saved-pair/pair.go'), 'PAIR_CONTROLLER_DRIFT')
    result = {'status': 'BUILD_ONLY_PASS', 'sourceCommitment': source, 'sourceFiles': files,
              'binarySha256': sha(read(output / 'rhook-saved-pair', 256 << 20)),
              'binaryBytes': (output / 'rhook-saved-pair').stat().st_size,
              'runtimePlanSha256': sha(read(module / 'plan.json')), 'libstylusSha256': prior['libstylusSha256'],
              'compiledFiles': closure, 'toolchainFiles': tools, 'prestateTransform': {'beforeSha256': sha(original),
              'afterSha256': sha(read(prestate / 'lp_branch.go')), 'replacementCount': 1},
              'productionWorkerLaunched': False, 'ACTUAL': 0, 'BRANCH': 0, 'B': 0,
              'hostSensors': 0, 'RPC': 0, 'WSS': 0, 'externalDelivery': 'HOLD'}
    (output / 'BUILD.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('sourceFiles', 'compiledFiles')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--retained-build', required=True); p.add_argument('--output', required=True)
    args = p.parse_args(); build(args.retained_build, args.output)
