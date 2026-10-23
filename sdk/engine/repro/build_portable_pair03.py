#!/usr/bin/env python3
"""Build only the portable adapter in an already completed Pair03 build root.

No bootstrap, Rust rebuild, network, host admission or historical execution.
Go tests staged here contain only synthetic fake-world and rejection tests.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil

import build_pair03 as build
import portable_pair03 as portable

REPO = Path(__file__).resolve().parents[1]


def stage(repo, work):
    module = work/'portable/pair'
    module.mkdir(parents=True, exist_ok=True)
    expected = {'pair.go', 'go.mod', 'go.sum', 'main.go', 'main_test.go', 'plan.json', 'synthetic_pair_test.go'}
    if any(p.is_symlink() or p.name not in expected for p in module.iterdir()):
        raise ValueError('UNEXPECTED_PORTABLE_STAGE_CONTENT')
    for name in ['pair.go', 'go.sum']:
        shutil.copyfile(repo/'native/saved-pair'/name, module/name)
    for name in ['main.go', 'main_test.go', 'plan.json']:
        shutil.copyfile(repo/'repro/portable'/name, module/name)
    # Preserve the five existing fake-world/bitmask tests verbatim. Exclude the
    # historical package admission test so even `go test .` cannot open it.
    tests = (repo/'native/saved-pair/pair_test.go').read_text()
    synthetic, marker, _ = tests.partition('func TestPinnedSavedPackageAdmissionAndFreshNilSourceBridges')
    portable.require(bool(marker), 'SYNTHETIC_TEST_BOUNDARY')
    (module/'synthetic_pair_test.go').write_text(synthetic)
    text = (repo/'native/saved-pair/go.mod').read_text()
    replacements = [('github.com/ethereum/go-ethereum', work/'src/nitro/go-ethereum'),
                    ('github.com/offchainlabs/nitro', work/'src/nitro'),
                    ('local/rhook-robinhood', work/'src/checkpoint/native/prestate')]
    for name, target in replacements:
        text, count = re.subn(r'(replace '+re.escape(name)+r' => )[^\n]+',
                            lambda m: m[1]+os.path.relpath(target, module), text)
        portable.require(count == 1, 'EXACT_MODULE_REPLACEMENT')
    portable.require(not re.search(r'=>\s+/', text), 'ABSOLUTE_MODULE_REPLACEMENT')
    (module/'go.mod').write_text(text)
    return module


def compile_adapter(repo, work, tag):
    work = portable.path_without_links(work)
    portable.require(re.fullmatch(r'[a-z0-9-]+', tag) is not None, 'SAFE_BUILD_TAG')
    portable.require(not (work/'records'/(tag+'-RESULT.json')).exists(), 'BUILD_RECORD_ALREADY_EXISTS')
    portable.verify_preserved(repo)
    source_before = portable.source_closure(repo)
    lock = json.loads((repo/'repro/dependencies.lock.json').read_text())
    build.verify_staged_rhook(repo, work, lock)
    build.reject_ambient_configuration(work)
    prior = json.loads((work/'records/BUILD_RESULT.json').read_text())
    portable.require(prior['status'] == 'BUILD_ONLY_PASS', 'COMPLETED_BUILD_ROOT_REQUIRED')
    library = work/'src/nitro/target/lib/libstylus.a'
    portable.require(build.sha256(library) == prior['libstylusSha256'], 'NATIVE_LIBRARY_DRIFT')
    # Recheck the complete compiled dependency closure from the successful build.
    for pin in json.loads((work/'records/GO_DEPENDENCIES_VERIFIED.json').read_text())['files']:
        portable.require(build.sha256(portable.local_file(work/pin['path'])) == pin['sha256'],
                         'PRIOR_COMPILED_DEPENDENCY_DRIFT: '+pin['path'])
    module = stage(repo, work)
    bootstrap = json.loads((work/'records/BOOTSTRAP_COMPLETE.json').read_text())
    node = portable.local_file(bootstrap['node'])
    portable.require(build.sha256(node) == bootstrap['nodeSha256'], 'BUILD_NODE_DRIFT')
    env = build.build_environment(work, node.parent)
    env.update({'GOPROXY': 'off', 'GOSUMDB': 'off'})
    go = str(work/'toolchains/go/bin/go')
    build.step(work, tag+'-synthetic-tests', [go, 'test', '-mod=readonly', '-p', '2', '-count=1', '-v', '.'], module, env, 180)
    graph = build.step(work, tag+'-dependencies', [go, 'list', '-mod=readonly', '-deps', '-json', '.'], module, env, 180)
    files = build.validate_dependency_paths(list(build.json_stream(graph.read_text())), work)
    closure = [{'path': str(p.relative_to(work)), 'sha256': build.sha256(p)} for p in files]
    build.record(work, tag+'-DEPENDENCIES.json', {'allWithinBuildRoot': True, 'files': closure})
    artifacts = work/'portable/artifacts'; artifacts.mkdir(exist_ok=True)
    binary = artifacts/'rhook-saved-pair'
    build.step(work, tag+'-build', [go, 'build', '-mod=readonly', '-trimpath', '-p', '2', '-o', str(binary), '.'], module, env, 180)
    portable.require((module/'pair.go').read_bytes() == (repo/'native/saved-pair/pair.go').read_bytes(), 'PAIR_ENGINE_DRIFT')
    portable.verify_preserved(repo)
    build.verify_staged_rhook(repo, work, lock)
    portable.require(portable.source_closure(repo) == source_before, 'SOURCE_CHANGED_DURING_BUILD')
    for name in ['main.go', 'plan.json']:
        portable.require((module/name).read_bytes() == (repo/'repro/portable'/name).read_bytes(), 'PORTABLE_STAGE_DRIFT')
    portable.require(build.sha256(library) == prior['libstylusSha256'], 'NATIVE_LIBRARY_DRIFT')
    result = {'status': 'PORTABLE_ADAPTER_BUILD_ONLY_PASS', 'binaryPath': str(binary),
              'binarySha256': build.sha256(binary), 'binaryBytes': binary.stat().st_size,
              'planSha256': build.sha256(module/'plan.json'),
              'pairGoSha256': build.sha256(module/'pair.go'), 'sourceFiles': source_before,
              'libstylusSha256': build.sha256(library), 'goDependencyFiles': len(files),
              'GOPROXY': 'off', 'GOSUMDB': 'off', 'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0},
              'hostSensors': 0, 'providerRPC': 0, 'WSS': 0, 'externalDelivery': 'HOLD'}
    build.record(work, tag+'-RESULT.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'sourceFiles'}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workdir', type=Path, required=True)
    p.add_argument('--tag', required=True)
    a = p.parse_args()
    compile_adapter(REPO, a.workdir, a.tag)
