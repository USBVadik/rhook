"""Offline synthetic tests and compilation using authenticated retained inputs."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from .common import HERE, ROOT, canonical, read, require, sha, sources
from plan_native.build import verify_toolchain

def verify_retained(retained):
    tools = verify_toolchain(retained)
    prior = json.loads(read(retained / 'records/BUILD_RESULT.json'))
    require(prior['status'] == 'BUILD_ONLY_PASS', 'RETAINED_BUILD_REQUIRED')
    library = retained / 'src/nitro/target/lib/libstylus.a'
    require(sha(read(library, 512 << 20)) == prior['libstylusSha256'] == 'd9b05f1e0d3937fd155f194c2b0c610e8966cc1b2f2c449912b21a39d2615b55', 'LIBRARY_PIN')
    dependencies = json.loads(read(retained / 'records/GO_DEPENDENCIES_VERIFIED.json'))['files']
    for item in dependencies:
        require(sha(read(retained / item['path'], 256 << 20)) == item['sha256'], 'DEPENDENCY_DRIFT')
    return {'toolchainFiles': tools, 'libstylusSha256': prior['libstylusSha256'], 'retainedDependencies': dependencies}

def stage(retained: Path, output: Path, suite: str) -> dict:
    retained, output = (Path(retained).resolve(), Path(output).absolute())
    require(suite in ['prestate', 'worker'] and (not output.exists()), 'FRESH_BUILD_DIRECTORY_REQUIRED')
    metadata = verify_retained(retained)
    output.mkdir()
    prestate = output / 'prestate'
    prestate.mkdir()
    module = output / 'worker'
    module.mkdir()
    for p in (ROOT / 'native/prestate').iterdir():
        if p.is_file() and (not p.name.endswith('_test.go')):
            shutil.copyfile(p, prestate / p.name)
    for p in (HERE / 'native/prestate').glob('*.go'):
        if suite == 'prestate' or not p.name.endswith('_test.go'):
            shutil.copyfile(p, prestate / p.name)
    targets = {'github.com/ethereum/go-ethereum': retained / 'src/nitro/go-ethereum', 'github.com/offchainlabs/nitro': retained / 'src/nitro', 'local/rhook-robinhood': prestate}
    for original, target in [(ROOT / 'native/prestate', prestate), (ROOT / 'native/saved-pair', module)]:
        text = read(original / 'go.mod').decode()
        for name, directory in targets.items():
            if name == 'local/rhook-robinhood' and target == prestate:
                continue
            text, count = re.subn('(?m)^(replace ' + re.escape(name) + ' => )[^\\n]+', lambda m: m[1] + os.path.relpath(directory, target), text)
            require(count == 1, 'MODULE_REPLACEMENT_COUNT')
        require(not re.search('=>\\s+/', text), 'ABSOLUTE_MODULE_REPLACEMENT')
        (target / 'go.mod').write_text(text)
    for n in ['pair.go', 'go.sum']:
        shutil.copyfile(ROOT / 'native/saved-pair' / n, module / n)
    shutil.copyfile(ROOT / 'repro/portable/plan.json', module / 'plan.json')
    shutil.copyfile(HERE / 'case.json', module / 'case.json')
    for p in (HERE / 'native/worker').glob('*.go'):
        shutil.copyfile(p, module / p.name)
    synthetic, marker, _ = read(ROOT / 'native/saved-pair/pair_test.go').decode().partition('func TestPinnedSavedPackageAdmissionAndFreshNilSourceBridges')
    require(marker, 'SYNTHETIC_TEST_BOUNDARY')
    (module / 'synthetic_pair_test.go').write_text(synthetic)
    for name in ['tmp', 'cache', 'home']:
        (output / name).mkdir()
    metadata.update(productionWorkerLaunched=False)
    return metadata

def environment(retained, output):
    return {'PATH': str(retained / 'toolchains/go/bin') + ':/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(output / 'home'), 'TMPDIR': str(output / 'tmp'), 'LANG': 'C', 'TZ': 'UTC', 'GOENV': 'off', 'GOWORK': 'off', 'GOTOOLCHAIN': 'local', 'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOMODCACHE': str(retained / 'cache/go-mod'), 'GOCACHE': str(retained / 'cache/go-build'), 'GOPATH': str(output / 'gopath'), 'CGO_ENABLED': '1', 'CGO_LDFLAGS': '-Wl,-no_warn_duplicate_libraries', 'GOMAXPROCS': '2', 'GOMEMLIMIT': '1073741824'}

def run(retained, output, suite, label, args):
    go = str(retained / 'toolchains/go/bin/go')
    with (output / (label + '.log')).open('xb') as log:
        result = subprocess.run([go, *args], cwd=output / suite, env=environment(retained, output), stdout=log, stderr=subprocess.STDOUT, timeout=900)
    require(result.returncode == 0, 'BUILD_STAGE_FAILED: ' + label)
    return read(output / (label + '.log'), 64 << 20).decode()

def test_count(text):
    count = len(re.findall('^--- PASS: ', text, re.M))
    require(count > 0 and 'no tests to run' not in text, 'EMPTY_TEST_SELECTION')
    return count

def test_go(retained: Path, output: Path, suite: str) -> dict:
    retained = Path(retained).resolve()
    output = Path(output).absolute()
    meta = stage(retained, output, suite)
    text = run(retained, output, suite, 'tests', ['test', '-mod=readonly', '-p', '2', '-count=1', '-v', '.'])
    return dict(meta, testsPassed=test_count(text))

def compiler_input(path, retained, output, expected):
    require(path.is_relative_to(retained) or path.is_relative_to(output), 'UNAUTHENTICATED_BUILD_ROOT')
    digest = sha(read(path, 256 << 20))
    if path.is_relative_to(retained):
        require(expected.get(str(path.relative_to(retained))) == digest, 'UNPINNED_COMPILER_INPUT')
    return digest

def compile_worker(retained: Path, output: Path, sensor: Path, node: Path) -> dict:
    retained = Path(retained).resolve()
    output = Path(output).absolute()
    files = sources()
    source = sha(canonical(files))
    meta = stage(retained, output, 'worker')
    require((output / 'worker/main.go').exists(), 'WORKER_SOURCE_REQUIRED')
    policy = sha(read(HERE / 'policy.json'))
    ld = '-X main.sourceCommitment=' + source + ' -X main.policyCommitment=' + policy
    text = run(retained, output, 'worker', 'tests', ['test', '-mod=readonly', '-p', '2', '-count=1', '-v', '-ldflags=' + ld, '.'])
    meta['testsPassed'] = test_count(text)
    graph = run(retained, output, 'worker', 'graph', ['list', '-mod=readonly', '-deps', '-json', '.'])
    run(retained, output, 'worker', 'build', ['build', '-mod=readonly', '-trimpath', '-p', '2', '-ldflags=' + ld, '-o', str(output / 'rhook-case-worker'), '.'])
    decoder = json.JSONDecoder()
    closure = {}
    expected = {p['path']: p['sha256'] for p in meta['retainedDependencies']}
    while graph.strip():
        row, end = decoder.raw_decode(graph.lstrip())
        graph = graph.lstrip()[end:]
        require(not row.get('Error') and (not row.get('DepsErrors')), 'DEPENDENCY_ERROR')
        directory = Path(row['Dir']).resolve()
        for field in ['GoFiles', 'CgoFiles', 'CFiles', 'CXXFiles', 'MFiles', 'HFiles', 'FFiles', 'SFiles', 'SysoFiles', 'EmbedFiles']:
            for n in row.get(field, []):
                p = (directory / n).resolve()
                closure[str(p)] = compiler_input(p, retained, output, expected)
    require(files == sources() and verify_retained(retained) == {k: v for k, v in meta.items() if k not in ['productionWorkerLaunched', 'testsPassed']}, 'BUILD_INPUT_CHANGED')
    from plan_native.core import verifier_dependencies
    record = dict(meta, schema='rhook/case-sdk-build/0.1', status='BUILD_ONLY_PASS', sourceCommitment=source, sourceFiles=files, caseDescriptorSha256=sha(read(HERE / 'case.json')), policySha256=policy, workerPath=str(output / 'rhook-case-worker'), binarySha256=sha(read(output / 'rhook-case-worker', 256 << 20)), sensorPath=str(Path(sensor).absolute()), sensorSha256=sha(read(sensor)), nodePath=str(Path(node).absolute()), nodeSha256=sha(read(node, 256 << 20)), verifierDependenciesCommitment=sha(canonical(verifier_dependencies())), compiledFiles=closure)
    (output / 'BUILD.json').write_bytes(canonical(record) + b'\n')
    return record
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--retained-build', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--tests-only', action='store_true')
    p.add_argument('--suite', choices=['prestate', 'worker'], default='worker')
    p.add_argument('--sensor', type=Path)
    p.add_argument('--node', type=Path)
    a = p.parse_args()
    result = test_go(a.retained_build, a.output, a.suite) if a.tests_only else compile_worker(a.retained_build, a.output, a.sensor, a.node)
    print(json.dumps({k: v for k, v in result.items() if k not in ['sourceFiles', 'compiledFiles', 'retainedDependencies', 'toolchainFiles']}))
