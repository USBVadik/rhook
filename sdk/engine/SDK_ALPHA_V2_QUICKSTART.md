# Developer SDK Alpha v2: saved Hookr Pair03

The fixed-case `doctor → prepare → replay → verify` workflow passed locally on
macOS arm64. It replays the seven arrivals of block 93251803 on chain 4663 and
changes only checkpoint `lpBps: 100 → 0`. It cannot select another block,
intervention, contract or provider. The historical package is supplied separately;
this private source checkpoint contains no package, witness or executable.

This is the current entry document. Earlier root/v1 READMEs and the v2
preparation README are retained unchanged for source/build commitments.
See [confirmed scope and resources](docs/SDK_ALPHA_V2_STATUS.md) and
[hash provenance](docs/SDK_ALPHA_V2_PROVENANCE.json).

## Inspect without execution

Use Python 3.12+ from the repository root:

```sh
./rhook-v2 --help
./rhook-v2 policy
```

`./rhook` remains the separate developer v1 profile. The v2 entry is `./rhook-v2`.
Neither command above measures host readiness, builds dependencies or runs EVM.

## Prepare a local workspace

Prerequisites for building: macOS arm64, Xcode Command Line Tools, Python 3.12+,
Node 20+/npm and space for pinned upstream sources, Go/Rust toolchains and caches.
The complete dependency list and hashes are in `repro/dependencies.lock.json`.
Fresh installation on a second computer has not been validated. Building Rust
Stylus support is not an independent Rust EVM replay.

Obtain the saved `BLOCK_PACKAGE.json` separately through an approved channel.
Its SHA-256 must be
`b55ba3a6d70bd081148966f3b447135a098a26c18bae0c773f065beda807bda3`.
Use fresh absolute paths without symlinks, outside this source checkout:

```sh
./rhook-v2 setup \
  --workspace "$HOME/rhook-v2-local" \
  --build-root "$HOME/rhook-v2-build" \
  --package "/absolute/path/BLOCK_PACKAGE.json" \
  --bootstrap
```

This explicitly downloads/builds pinned dependencies and imports the saved
package; it does not run historical EVM or host sensors. To reuse a completed
dependency build root, omit `--bootstrap`. To attach an existing matching v2
`BUILD.json` without building:

```sh
./rhook-v2 init --workspace "$HOME/rhook-v2-local" \
  --package "/absolute/path/BLOCK_PACKAGE.json" \
  --build-record "/absolute/path/BUILD.json"
```

These are alternative setup paths. A used workspace/build failure requires
inspection; do not silently retry, rewrite completed records or reuse old consent.
Build records bind the source closure, policy and worker: changing any file in
that closure requires a new build, not editing its recorded hashes.

## Run only with fresh explicit operator permission

The commands below describe the accepted workflow. This checkpoint task and
`externalDelivery=HOLD` do not authorize another native run. Under a separately
approved one-run plan, with power connected, lid open and a fresh run name:

```sh
./rhook-v2 doctor --workspace "$HOME/rhook-v2-local" --name host-01 &&
./rhook-v2 prepare --workspace "$HOME/rhook-v2-local" --name pair03-01 &&
./rhook-v2 replay --workspace "$HOME/rhook-v2-local" --name pair03-01 \
  --confirm-native --mac-ready &&
./rhook-v2 verify --run "$HOME/rhook-v2-local/runs/pair03-01"
```

The chain stops on any failed command. Doctor PASS is a momentary observation;
replay performs its own fresh admission. A used run or any operation-ending STOP
cannot be retried under that permission. Missing state/host failure is not an EVM
REVERT. Inspect a saved diagnostic without new measurements with
`./rhook-v2 diagnostic --path /absolute/workspace/diagnostics/host-01`.

Acceptance03 ran these commands through an external dispatcher with an inclusive
180 s workflow bound and 140 s replay bound. The shell chain above alone does
not provide those outer bounds. The exact tested dispatcher is retained as a
[local-layout reference](tools/sdk-alpha-v2-acceptance-reference/README.md),
not a turnkey launcher for a new installation. Preserve reviewed outer deadlines
for any future controlled acceptance; do not treat a historical reference plan
as permission to execute.

`verify` authenticates saved hashes, receipts, roots, observations, counts and
resource records without rerunning EVM. A Go result matching the Go baseline is
reproducibility, not independent Rust verification or a qualified protocol Claim.

## Synthetic checks

These use mocked packets and small owned C/Python fixtures, without a historical
block, real host-readiness sensors, provider requests or Go/Nitro execution:

```sh
python3 -m unittest discover -s sdk_alpha_v2 -p 'test_*.py'
python3 tools/sdk-alpha-v2-acceptance-reference/run_regression_tests.py
```

Keep packages, workspaces, raw diagnostics/evidence, grants, executables, caches
and credentials outside Git. This commit is a private checkpoint; public release,
SDK delivery, further native execution and GitHub push remain separately gated.
