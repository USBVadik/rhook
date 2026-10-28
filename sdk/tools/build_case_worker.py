"""Build one data-driven worker from an explicitly supplied retained toolchain.

Requires the existing source-companion build layout; never downloads dependencies
or executes a blockchain case. Outputs stay outside the public source checkout.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
SDK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SDK))
from developer.files import canonical, digest, no_links, require, save, sha
POLICY = '1b081fd77d61a4037ec0055a1a129d3fdcc4f9a075f9b56b3c7d66be318e4688'

def build(retained, output, sensor, node):
    retained = no_links(retained)
    output = no_links(output)
    require(not output.exists() and (not output.is_relative_to(SDK)), 'FRESH_EXTERNAL_BUILD_REQUIRED')
    output.mkdir(mode=448)
    shutil.copytree(retained / 'application/prestate', output / 'prestate')
    (output / 'worker').mkdir()
    source = SDK / 'rhook_alpha/cases/native'
    for p in source.glob('*.go'):
        shutil.copyfile(p, output / ('prestate' if p.name == 'overlay.go' else 'worker') / p.name)
    for module in ('prestate', 'worker'):
        original = retained / 'application' / module
        text = (original / 'go.mod').read_text()
        targets = {'github.com/ethereum/go-ethereum': retained / 'src/nitro/go-ethereum', 'github.com/offchainlabs/nitro': retained / 'src/nitro', 'local/rhook-robinhood': output / 'prestate'}
        for name, target in targets.items():
            text = re.sub('(?m)^(replace ' + re.escape(name) + ' => )[^\\n]+', lambda m: m[1] + os.path.relpath(target, output / module), text)
        (output / module / 'go.mod').write_text(text)
        shutil.copyfile(original / 'go.sum', output / module / 'go.sum')
    files = {str(p.relative_to(output)): sha(p) for folder in ('prestate', 'worker') for p in sorted((output / folder).rglob('*')) if p.is_file()}
    identity = digest(canonical(files))
    go = retained / 'go/bin/go'
    env = {'PATH': str(go.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(output), 'GOENV': 'off', 'GOWORK': 'off', 'GOTOOLCHAIN': 'local', 'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOMODCACHE': str(retained / 'go-mod'), 'GOCACHE': str(retained / 'go-cache-clean'), 'GOMAXPROCS': '2', 'GOMEMLIMIT': '536870912', 'CGO_ENABLED': '1', 'CGO_LDFLAGS': '-Wl,-no_warn_duplicate_libraries', 'LANG': 'C', 'TZ': 'UTC'}

    def caps():
        resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
        resource.setrlimit(resource.RLIMIT_FSIZE, (128 << 20, 128 << 20))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    ld = '-s -w -X main.sourceCommitment=' + identity + ' -X main.policyCommitment=' + POLICY

    def run(label, args):
        with (output / (label + '.log')).open('xb') as log:
            process = subprocess.Popen([str(go), *args], cwd=output / 'worker', env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=caps)
            try:
                code = process.wait(timeout=600)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        require(code == 0, 'BUILD_STAGE_FAILED: ' + label)
    run('tests', ['test', '-mod=readonly', '-p', '2', '-count=1', '-v', '-ldflags=' + ld, '.'])
    run('graph', ['list', '-mod=readonly', '-deps', '-json', '.'])
    run('build', ['build', '-mod=readonly', '-trimpath', '-p', '2', '-ldflags=' + ld, '-o', str(output / 'worker.bin'), '.'])
    compiled = {}
    text = (output / 'graph.log').read_text()
    decoder = json.JSONDecoder()
    while text.strip():
        row, end = decoder.raw_decode(text.lstrip())
        text = text.lstrip()[end:]
        require(not row.get('Error') and (not row.get('DepsErrors')), 'COMPILER_DEPENDENCY_ERROR')
        for field in ('GoFiles', 'CgoFiles', 'CFiles', 'CXXFiles', 'MFiles', 'HFiles', 'FFiles', 'SFiles', 'SysoFiles', 'EmbedFiles'):
            for name in row.get(field, []):
                path = Path(row['Dir']) / name
                compiled[str(path)] = sha(path)
    require(files == {str(p.relative_to(output)): sha(p) for folder in ('prestate', 'worker') for p in sorted((output / folder).rglob('*')) if p.is_file()}, 'BUILD_SOURCE_CHANGED')
    save(output / 'BUILD.json', {'schema': 'rhook/case-worker-build/0.1', 'sourceCommitment': identity, 'sourceFiles': files, 'compiledFiles': compiled, 'binarySha256': sha(output / 'worker.bin'), 'toolchainSha256': sha(go), 'policySha256': POLICY, 'nativeExecutions': 0, 'retainedDependencies': 'OPERATOR_SUPPLIED_RETAINED_SOURCE_COMPANION', 'inventoryLimit': 'Direct compiler sources/embeds; not an exhaustive indirect C/assembly include list'})
    runtime = {'schema': 'rhook/case-runtime/0.1', 'profile': 'nitro-hookr-lp/0.1', 'sourceCommitment': identity, 'policySha256': POLICY, 'files': {k: {'path': str(no_links(v)), 'sha256': sha(v)} for k, v in [('worker', output / 'worker.bin'), ('sensor', sensor), ('node', node)]}}
    save(output / 'RUNTIME.json', runtime)
    return {'status': 'BUILD_ONLY_PASS', 'sourceCommitment': identity, 'binarySha256': sha(output / 'worker.bin'), 'runtime': str(output / 'RUNTIME.json'), 'nativeExecutions': 0}
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('retained', 'output', 'sensor', 'node'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.retained, a.output, a.sensor, a.node)))
