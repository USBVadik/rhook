#!/usr/bin/env python3
"""Profile Descriptor 0.1: run gofmt, go vet and the descriptor/overlay Go unit tests in a scratch module.

Development check only, not a worker build: it stages the scenario sources as tools/build_scenario_worker.py
does, but never runs `go build` and produces no worker binary. Tests use synthetic fixtures and, when given,
read-only accepted inputs; none enters Nitro's producer. Needs the retained offline closure (no network).

Usage: run_descriptor_go_tests.py --retained DIR --scratch NEW_DIR [--fixtures DIR] [--accepted-records DIR]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SDK = Path(__file__).resolve().parents[1]
MAIN = ('package main\nimport("fmt";"os";scenario "local/rhook-scenario")\nvar sourceCommitment,policyCommitment string\n'
        'func main(){if e:=scenario.WorkerEntry(sourceCommitment,policyCommitment,os.Args[1:]);e!=nil{fmt.Fprintln(os.Stderr,e);os.Exit(1)}}\n')
TESTS = 'Descriptor|Overlay|Legacy|Profile'


def stage(retained, out):
    shutil.copytree(retained / 'application/prestate', out / 'prestate')
    module = out / 'scenario'
    module.mkdir()
    native = SDK / 'rhook_alpha/cases/scenario/native'
    for p in native.iterdir():
        if p.suffix == '.go' or p.name == 'profile.json':
            shutil.copyfile(p, (out / 'prestate' if p.name == 'scenario_setup.go' else module) / p.name)
    shutil.copytree(native / 'descriptors', module / 'descriptors')
    (module / 'cmd').mkdir()
    (module / 'cmd/main.go').write_text(MAIN)
    for folder, original, name in [(out / 'prestate', retained / 'application/prestate', 'local/rhook-robinhood'),
                                   (module, retained / 'application/worker', 'local/rhook-scenario')]:
        text = (original / 'go.mod').read_text()
        text = re.sub(r'(?m)^module .*$', 'module ' + name, text, count=1)
        for dependency, target in {'github.com/ethereum/go-ethereum': retained / 'src/nitro/go-ethereum',
                                   'github.com/offchainlabs/nitro': retained / 'src/nitro', 'local/rhook-robinhood': out / 'prestate'}.items():
            text = re.sub(r'(?m)^(replace ' + re.escape(dependency) + r' => )[^\n]+', lambda m: m[1] + os.path.relpath(target, folder), text)
        (folder / 'go.mod').write_text(text)
        shutil.copyfile(original / 'go.sum', folder / 'go.sum')
    return module


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--retained', type=Path, required=True)
    a.add_argument('--scratch', type=Path, required=True)
    a.add_argument('--fixtures', type=Path)
    a.add_argument('--accepted-records', type=Path)
    a.add_argument('--run', default=TESTS)
    a.add_argument('--gocache', type=Path, help='scratch build cache to reuse (default: new, inside --scratch)')
    args = a.parse_args()
    if args.scratch.exists():
        raise SystemExit('SCRATCH_MUST_BE_NEW')
    args.scratch.mkdir(mode=0o700)
    module = stage(args.retained, args.scratch)
    go = args.retained / 'go/bin/go'
    env = {'PATH': str(go.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(args.scratch), 'GOENV': 'off', 'GOWORK': 'off',
           'GOTOOLCHAIN': 'local', 'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOFLAGS': '-mod=readonly', 'GOMODCACHE': str(args.retained / 'go-mod'),
           'GOCACHE': str(args.gocache or args.scratch / 'gocache'), 'GOMAXPROCS': '2', 'GOMEMLIMIT': '1073741824', 'CGO_ENABLED': '1',
           'CGO_LDFLAGS': '-Wl,-no_warn_duplicate_libraries', 'LANG': 'C', 'TZ': 'UTC', 'TMPDIR': str(args.scratch) + '/'}
    if args.fixtures:
        env['RHOOK_PROFILE_FIXTURES'] = str(args.fixtures)
    if args.accepted_records:
        env['RHOOK_ACCEPTED_RECORDS'] = str(args.accepted_records)
    env.update({k: v for k, v in os.environ.items() if k in ('RHOOK_OVERLAY_SOURCE', 'RHOOK_LEGACY_SPECS', 'RHOOK_LEGACY_RUNS', 'RHOOK_PARITY_OUT', 'RHOOK_LEGACY_INPUT', 'RHOOK_LEGACY_FINAL')})
    fmt = subprocess.run([str(args.retained / 'go/bin/gofmt'), '-l', *sorted(p.name for p in module.glob('*.go'))], cwd=module, env=env, capture_output=True, text=True)
    vet = subprocess.run([str(go), 'vet', '.'], cwd=module, env=env, capture_output=True, text=True, timeout=1500)
    test = subprocess.run([str(go), 'test', '-count=1', '-p', '2', '-timeout', '25m', '-v', '-run', args.run, '.'], cwd=module, env=env,
                          capture_output=True, text=True, timeout=1800)
    (args.scratch / 'go-test.log').write_text(test.stdout + '\n--- stderr ---\n' + test.stderr)
    (args.scratch / 'go-vet.log').write_text(vet.stdout + vet.stderr)
    lines = test.stdout.splitlines()
    summary = dict(gofmtUnformatted=fmt.stdout.split(), vetExit=vet.returncode, testExit=test.returncode,
                   passed=[l.split()[2] for l in lines if l.startswith('--- PASS')],
                   failed=[l.split()[2] for l in lines if l.startswith('--- FAIL')],
                   skipped=[l.split()[2] for l in lines if l.startswith('--- SKIP')],
                   logs=[l.strip() for l in lines if any(k in l for k in ('G1_TABLE', 'G1_INTEGRATED', 'SHARED_FIXTURES', 'G3_', 'ADMISSION_PARITY', 'TUNING_GRID'))],
                   goBuildInvoked=False, workerBinaryProduced=False)
    print(json.dumps(summary, indent=1))
    if test.returncode or vet.returncode or fmt.stdout.strip():
        print('\n'.join(l for l in lines if 'FAIL' in l or 'want' in l or '.go:' in l)[-6000:], file=sys.stderr)
        print(test.stderr[-4000:], vet.stderr[-3000:], file=sys.stderr)
    return 0 if not (test.returncode or vet.returncode or fmt.stdout.strip()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
