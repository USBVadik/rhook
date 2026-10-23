"""Thin developer admission overlay; the saved pair and prestate stay unchanged."""
import json
import os
from pathlib import Path
import platform
import re
import shutil

from .common import REPO, require, sha, sources, commitment, local_file, portable, read_json, store
from .resources import POLICY
import build_pair03 as upstream

DOMAIN = 'DEVELOPER_SAVED_PAIR03'
CONTEXT = 'local-terminal'
POLICY_HASH = commitment(POLICY)


def replace_once(text, old, new):
    require(text.count(old) == 1, 'DEVELOPER_OVERLAY_BOUNDARY_DRIFT: '+old[:60])
    return text.replace(old, new, 1)


def overlay(text, tests=False):
    # Admission-only edits; no change to checkedFresh or pair.go.
    text = replace_once(text, '"PORTABLE_SAVED_PAIR03"', '"'+DOMAIN+'"')
    text = replace_once(text, '"require_escalated"', '"'+CONTEXT+'"')
    if tests:
        text = replace_once(text, 'portableBinding{Operation:',
                            'portableBinding{Profile: developerProfile, Policy: developerPolicyHash, Operation:')
        text = replace_once(text, 'portableAuthority{Approved:',
                            'portableAuthority{Profile: developerProfile, Policy: developerPolicyHash, Approved:')
    else:
        for struct in ['portableBinding', 'portableAuthority']:
            text = replace_once(text, 'type '+struct+' struct {', 'type '+struct+' struct {\n'
                                '\tProfile string `json:"profile"`\n\tPolicy string `json:"policySha256"`')
        text = replace_once(text, 'json:"founderApproved"', 'json:"operatorApproved"')
        text = replace_once(text, 'if !a.Approved ||',
                            'if a.Profile != developerProfile || b.Profile != developerProfile || '
                            'a.Policy != developerPolicyHash || b.Policy != developerPolicyHash || !a.Approved ||')
        text = replace_once(text, 'Accepted bool `json:"accepted"`',
                            'Accepted bool `json:"accepted"`\n\t\tProfile string `json:"profile"`\n'
                            '\t\tPolicy string `json:"policySha256"`')
        text = replace_once(text, 'e != nil || !gate.Accepted {',
                            'e != nil || !gate.Accepted || gate.Profile != developerProfile || '
                            'gate.Policy != developerPolicyHash {')
    return text


def stage(work, directory):
    directory.mkdir(parents=True)
    native = REPO/'native/saved-pair'
    for name in ['pair.go', 'go.sum']: shutil.copyfile(native/name, directory/name)
    shutil.copyfile(REPO/'repro/portable/plan.json', directory/'plan.json')
    for name in ['main.go', 'main_test.go']:
        (directory/name).write_text(overlay((REPO/'repro/portable'/name).read_text(), name.endswith('_test.go')))
    (directory/'developer_profile.go').write_text(
        'package main\nconst developerProfile = '+json.dumps(POLICY['profile'])+'\n'
        'const developerPolicyHash = '+json.dumps(POLICY_HASH)+'\n')
    (directory/'developer_profile_test.go').write_text('''package main
import ("testing"; "time")
func TestDeveloperProfileCannotUseScientificConsentOrChangedPolicy(t *testing.T) {
 b:=portableBinding{Profile:developerProfile,Policy:developerPolicyHash,Operation:"op",Binary:"bin",Plan:digest(planBytes),Package:"/input",Output:"/out"}
 a:=portableAuthority{Profile:developerProfile,Policy:developerPolicyHash,Approved:true,Domain:"DEVELOPER_SAVED_PAIR03",Operation:"op",Binary:"bin",Package:"/input",Output:"/out",NotBefore:990,Expires:1200,NoRetry:true,MacReady:true,Context:"local-terminal"}
 a.Maximum.ACTUAL=1; a.Maximum.BRANCH=1
 if checkAuthority(a,b,"/out","bin",time.Unix(1000,0))!=nil {t.Fatal("valid developer consent rejected")}
 for _,mutate:=range []func(*portableAuthority){func(x *portableAuthority){x.Domain="PORTABLE_SAVED_PAIR03"},func(x *portableAuthority){x.Context="require_escalated"},func(x *portableAuthority){x.Profile="scientific"},func(x *portableAuthority){x.Policy="changed"}} {
  bad:=a; mutate(&bad); if checkAuthority(bad,b,"/out","bin",time.Unix(1000,0))==nil {t.Fatal("cross-profile consent accepted")}
 }
}
''')
    fake, marker, _ = (native/'pair_test.go').read_text().partition(
        'func TestPinnedSavedPackageAdmissionAndFreshNilSourceBridges')
    require(bool(marker), 'SYNTHETIC_BOUNDARY_DRIFT')
    (directory/'synthetic_pair_test.go').write_text(fake)
    text = (native/'go.mod').read_text()
    for name, target in [('github.com/ethereum/go-ethereum', work/'src/nitro/go-ethereum'),
                         ('github.com/offchainlabs/nitro', work/'src/nitro'),
                         ('local/rhook-robinhood', work/'src/checkpoint/native/prestate')]:
        text, count = re.subn(r'(replace '+re.escape(name)+r' => )[^\n]+',
                             lambda m: m[1]+os.path.relpath(target, directory), text)
        require(count == 1, 'EXACT_MODULE_REPLACEMENT')
    require(not re.search(r'=>\s+/', text), 'ABSOLUTE_MODULE_REPLACEMENT')
    (directory/'go.mod').write_text(text)


def compile_developer(work):
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'ONLY_MACOS_ARM64_BUILD_VALIDATED')
    work = portable.path_without_links(work)
    portable.verify_preserved(REPO)
    pins = sources(); tag = 'developer-alpha-'+commitment(pins)[:16]
    directory = work/'developer-alpha'/tag
    require(not directory.exists(), 'BUILD_ALREADY_ATTEMPTED_USE_RECORDED_RESULT_OR_REVIEW_FAILURE')
    lock = read_json(REPO/'repro/dependencies.lock.json')
    upstream.verify_staged_rhook(REPO, work, lock)
    upstream.reject_ambient_configuration(work)
    prior = read_json(work/'records/BUILD_RESULT.json')
    require(prior['status'] == 'BUILD_ONLY_PASS', 'COMPLETED_DEPENDENCY_BUILD_REQUIRED')
    library = work/'src/nitro/target/lib/libstylus.a'
    require(sha(library) == prior['libstylusSha256'], 'NATIVE_LIBRARY_DRIFT')
    for p in read_json(work/'records/GO_DEPENDENCIES_VERIFIED.json')['files']:
        require(sha(local_file(work/p['path'])) == p['sha256'], 'COMPILED_DEPENDENCY_DRIFT: '+p['path'])
    module = directory/'pair'; stage(work, module)
    node = local_file(read_json(work/'records/BOOTSTRAP_COMPLETE.json')['node'])
    require(sha(node) == read_json(work/'records/BOOTSTRAP_COMPLETE.json')['nodeSha256'], 'BUILD_NODE_DRIFT')
    env = upstream.build_environment(work, node.parent)
    env.update({'GOPROXY': 'off', 'GOSUMDB': 'off'})
    go = str(work/'toolchains/go/bin/go')
    upstream.step(work, tag+'-tests', [go, 'test', '-mod=readonly', '-p', '2', '-count=1', '-v', '.'], module, env, 180)
    graph = upstream.step(work, tag+'-deps', [go, 'list', '-mod=readonly', '-deps', '-json', '.'], module, env, 180)
    files = upstream.validate_dependency_paths(list(upstream.json_stream(graph.read_text())), work)
    (directory/'artifacts').mkdir()
    worker = directory/'artifacts/rhook-saved-pair'; sensor = directory/'artifacts/rhook-host-sensor'
    upstream.step(work, tag+'-go', [go, 'build', '-mod=readonly', '-trimpath', '-p', '2', '-o', str(worker), '.'], module, env, 180)
    upstream.step(work, tag+'-sensor', ['/usr/bin/clang', '-Wall', '-Wextra', '-Werror', '-O2',
                  str(REPO/'sdk_alpha/host_sensor.c'), '-o', str(sensor)], REPO, env, 60)
    require(sha(module/'pair.go') == sha(REPO/'native/saved-pair/pair.go'), 'PAIR_ENGINE_DRIFT')
    require(sha(library) == prior['libstylusSha256'] and pins == sources(), 'BUILD_SOURCE_DRIFT')
    portable.verify_preserved(REPO)
    record = {'status': 'DEVELOPER_BUILD_ONLY_PASS', 'profile': POLICY['profile'], 'policySha256': POLICY_HASH,
              'sourceFiles': pins, 'worker': str(worker), 'workerSha256': sha(worker),
              'sensor': str(sensor), 'sensorSha256': sha(sensor), 'pairGoSha256': sha(module/'pair.go'),
              'planSha256': sha(module/'plan.json'), 'libstylusSha256': sha(library),
              'goDependencyFiles': [{'path': str(p.relative_to(work)), 'sha256': sha(p)} for p in files],
              'nativeInvocations': {'ACTUAL': 0, 'BRANCH': 0, 'B': 0}, 'hostSensors': 0,
              'RPC': 0, 'WSS': 0, 'externalDelivery': 'HOLD'}
    store(directory/'BUILD.json', record)
    return directory/'BUILD.json'


def verify_build(record_path):
    record = read_json(record_path)
    require(record['status'] == 'DEVELOPER_BUILD_ONLY_PASS' and record['profile'] == POLICY['profile']
            and record['policySha256'] == POLICY_HASH and record['sourceFiles'] == sources(), 'BUILD_PROFILE_OR_SOURCE_DRIFT')
    portable.verify_preserved(REPO)
    for name in ['worker', 'sensor']:
        path = local_file(record[name], 256<<20)
        require(os.access(path, os.X_OK) and sha(path) == record[name+'Sha256'], 'BUILD_ARTIFACT_DRIFT_'+name)
    return record
