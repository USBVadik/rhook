# Developer SDK Alpha

Local CLI and Python API for the saved Hookr Pair03 example, on macOS arm64.
This developer profile has a new admission adapter and resource policy. The
scientific runner, prestate, Pair03 commitments and old admission remain unchanged.
The existing Archive SDK is a separate product and is not replaced by this kit.

## Start here

Prerequisites: macOS arm64, Xcode Command Line Tools, Python 3.12+, Node 20+,
npm, internet for the initial pinned dependency build, and disk space for the
Go/Rust toolchains, Nitro sources and caches. Other operating systems, CI/cloud
runners and other physical machines have not been validated. CPU/RAM results
from the old replay do not validate the new developer admission profile.

Obtain `BLOCK_PACKAGE.json` separately from the founder. It is never downloaded
from a provider by this kit. The exact accepted SHA-256 is
`b55ba3a6d70bd081148966f3b447135a098a26c18bae0c773f065beda807bda3`.
It contains original-parent state, witness, original inputs and all seven arrivals
for chain 4663, block 93251803. No other block, intervention or network source
can be selected in this Alpha.

From the repository root, with a fresh build root and workspace:

```sh
./rhook setup \
  --workspace "$HOME/rhook-local" \
  --build-root "$HOME/rhook-build" \
  --package "/absolute/path/BLOCK_PACKAGE.json" \
  --bootstrap
```

This performs the pinned dependency bootstrap/build, builds the developer
adapter and host sensor, validates and copies the package into the workspace.
It does not execute the historical block or take host resource measurements.
The dependency builder compiles Rust Stylus support; that is **not** an independent
Rust EVM replay or heterogeneous qualification.

To reuse a completed dependency build root, omit `--bootstrap`. `setup` finds or
builds the matching developer adapter automatically. A partial build failure
requires inspection; no automatic retry, fallback or cleanup of evidence occurs.
For an existing matching developer build, `init --build-record /absolute/BUILD.json`
imports a package into another fresh workspace without building.

Read-only resource diagnostics, with a unique diagnostic name:

```sh
./rhook doctor --workspace "$HOME/rhook-local" --name host-check-01
./rhook prepare --workspace "$HOME/rhook-local" --name pair03-01
```

`doctor` samples this host only. Its PASS is a momentary observation, cannot be
reused as execution admission, and is not a scientific grant. `prepare` checks
input/build/source hashes and creates a fresh run binding without sampling or
starting the engine. There is no manual authority JSON to construct.
The CLI shows observed free memory, pressure and swap even for a rejected first
sample. To inspect that saved diagnostic again without new measurements:

```sh
./rhook diagnostic --path "$HOME/rhook-local/diagnostics/host-check-01"
```

Only an operator explicitly allowed to run the native example should use:

```sh
./rhook replay --workspace "$HOME/rhook-local" --name pair03-01 \
  --confirm-native --mac-ready
./rhook verify --run "$HOME/rhook-local/runs/pair03-01"
```

`--mac-ready` confirms power connected and lid open. `replay` creates a local
operator consent record, consumes the output directory before fresh admission,
then dispatches at most one ACTUAL and one conditional BRANCH. BRANCH requires
canonical ACTUAL stateRoot, receiptsRoot and blockHash match. Each world gets
independent original-parent state, nil Source and LP100→0 in bits 160–175 only.
There is no network hydration. A used run name cannot be replayed; any STOP closes
that local run. A different name is a new manual run requiring fresh explicit
operator consent, never an automatic retry.

`verify` checks saved files/hashes, both complete result projections against
the preserved Pair03 baseline, canonical comparisons, counts and resource records.
It does not rerun EVM. A manifest establishes local integrity, not authenticity
against a malicious local operator and not a protocol Claim.

## Resources and stops

Policy: [`policy.json`](policy.json), profile `developer-darwin-arm64/1`.
Total physical RAM is recorded for sanity, with **no exact-size equality**.
Admission requires two normal-pressure samples about one second apart, no swap
output/usage growth and at least **5.25 GiB free**: a 4 GiB worker ceiling,
1 GiB OS reserve and 256 MiB supervisor allowance. These are conservative policy
choices, not measured minimum requirements of the engine.

The sensor reads Darwin `HOST_VM_INFO64`, page size and pressure/swap sysctls.
The sensor process has a 1 s launch/capture deadline; its internal measurement
must finish within 250 ms. Slow startup is not counted as a measured VM interval.
`free_count` already includes speculative pages. It does not add them again, or
count inactive/cache pages as guaranteed free. Thus a cache-heavy host may STOP
even when macOS could reclaim memory. This Alpha favors a conservative decision
over assuming such reclamation. No allocated reservation is established.

During execution: sampled worker RSS ≤4 GiB every ~100 ms, host checks about
every 250 ms, telemetry gap ≤2 s, normal pressure/no swap output or usage growth,
and free headroom ≥1.25 GiB. Sensor error, stale/invalid data, regression or host
change stops the owned worker. The 120 s wall/CPU limits, 64 MiB combined output,
128 MiB sampled runtime storage, no-core and file/descriptor limits are preserved.
CPU accounting conservatively includes owned observers. GOMAXPROCS=2 and the
1 GiB Go memory limit remain advisory settings. RSS/headroom sampling is not a
hard memory cap, hard reservation, exact peak or guarantee of launcher RSS.
The original overall plan is 140 s including admission/cleanup; the worker has
its own kernel CPU limit and bounded owned-process cleanup.

`HOST_STOP` means no native invocation was dispatched after rejected admission.
`INTERRUPTED_UNVERIFIED` preserves partial evidence and unknown counts where
completion/cleanup cannot be established. Before dispatch, zero native invocations
are known; after a dispatch attempt they remain unknown without verified native
completion. `workerDispatchAttempted` records this distinction. SIGINT/SIGTERM
unwind pre-admission capture to clean up the owned sensor; the worker supervisor
handles signals during execution and reaps its owned worker. Missing state is a host failure, never
an invented EVM REVERT. A developer PASS remains an unqualified Go observation:
economic assurance UNRESOLVED, heterogeneous agreement NOT_EVALUATED, B=0,
qualified Claims=0. Even a baseline mismatch retains original records.

## Workspace and API

```text
rhook-local/
  KIT.json                      # build/package binding
  inputs/BLOCK_PACKAGE.json     # exact separately supplied local input
  diagnostics/<name>/           # raw bounded sensor records and decision
  proposals/<name>/BINDINGS.json
  runs/<name>/                  # operator consent, raw results/resources, manifest
```

All local paths must be absolute, with no symlinks. Workspaces must be outside
the source checkout, so saved inputs and runtime cannot accidentally become source
files. Build records refer to their
local build root. Moving a checkout/build/workspace requires rebuilding/rebinding;
editing paths in a completed run does not make it portable.

```python
from pathlib import Path
from sdk_alpha import kit

workspace = Path.home() / 'rhook-local'
binding = kit.prepare(workspace, 'api-example-01')  # no sensors, no native run
print(binding['operationCommitment'])
# Explicit native call for an authorized operator only:
# result = kit.replay(workspace, 'api-example-01', confirm_native=True, mac_ready=True)
# checked = kit.verify_run(workspace / 'runs/api-example-01')
```

The CLI and Python API are single-operator local workflows, not a service or
multitenant SDK. A workspace file lock rejects overlapping doctor/replay actions;
an in-process lock also protects the preserved supervisor's mutable context.
Run operator actions on Python's main thread (the supervisor handles SIGINT/SIGTERM).
No automatic monitoring, new experiment selection,
provider credentials, push, publication or SDK distribution follows from use.
`externalDelivery=HOLD` remains in force. Build/runtime/input payloads stay out
of Git. To run synthetic tests without host measurements or historical EVM:

```sh
python3 -m unittest discover -s sdk_alpha -p 'test_*.py'
python3 -m unittest discover -s repro/tests -p 'test_*.py'
```

The supervision tests compile and execute a small owned C fixture to exercise
pipe overflow and termination/reaping. They do not load Nitro, open the package,
execute historical EVM or measure real host memory pressure. Tests require clang
and permission to inspect only their newly spawned fixture PID with `ps`.
