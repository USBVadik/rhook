# Saved Pair03 developer memory profile v2

Proposed profile `developer-darwin-arm64/2`, only for chain 4663, saved block
93251803, all seven original arrivals and LP100→0. This is preparation for a
future acceptance, not native validation, another scientific grant or a release.
macOS arm64 only; no other machine/OS/cloud support is claimed.

## Exact policy

[`policy.json`](policy.json) is the authoritative proposed policy input.

| Setting | Developer v1 | Proposed developer v2 |
| --- | --- | --- |
| Sampled worker RSS ceiling | 4 GiB | 1 GiB |
| Admission free headroom | 5.25 GiB | 1.5 GiB |
| Runtime free-headroom floor | 1.25 GiB | 0.5 GiB |
| OS stop-margin allowance | 1 GiB | 256 MiB |
| Launcher/observer allowance | 256 MiB | 256 MiB |
| Go memory soft limit | 1 GiB | 512 MiB |
| Worker CPU / pair wall | 120 s / 120 s | unchanged |
| Worker RSS cadence / max telemetry gap | nominal 100 ms / 2 s | unchanged |
| Host snapshot cadence | nominal 250 ms | unchanged |
| Pressure and swap | normal=1, no swap-out/usage growth | unchanged |
| Combined output / sampled runtime storage | 64 MiB / 128 MiB | unchanged |
| Native scope | ACTUAL≤1, conditional BRANCH≤1, B0 | unchanged |
| Provider RPC/WSS and hydration | 0, nil Source | unchanged |

All native acceptance still requires canonical ACTUAL stateRoot, receiptsRoot and
blockHash equality, independent original-parent BRANCH and exact full Pair03
baseline comparison. Missing state remains a host error, not an invented REVERT.
Interrupts, unknown completion and unconfirmed cleanup remain fail-closed.

## Why these numbers

The authenticated previous portable replay observed worker RSS 406110208 bytes
(~387 MiB), over 14 samples, and pair wall 1.416712125 s. A 1 GiB monitored class
is about 2.64 times that sampled peak. That is sizing evidence for this one saved
workload, not a proof of a maximum or of successful execution under v2.

The fixed admission budget is **1 GiB class + 512 MiB margin = 1.5 GiB**.
The margin is half the class, split into two explicit 256 MiB allowances:

- The launcher/observer allowance accounts for Python, metadata, bounded pipes
  and its existing whole-worker-file copy. The pinned worker is approximately
  124 MiB; 256 MiB is roughly twice that copy-buffer size. It is not a measured
  launcher RSS ceiling. Copying occurs before admission; the snapshot already
  reflects any pages still resident then.
- The OS allowance is a 256 MiB *stop margin* for this short bounded workload,
  accompanied by continuous pressure/swap/headroom checks. It does not reserve
  memory or certify that macOS needs only 256 MiB. It is an explicit developer
  policy tradeoff to be reviewed and tested, not a derived safety guarantee.

The runtime floor retains both allowances (512 MiB) while the worker grows toward
its class ceiling. No cache/inactive pages are counted as guaranteed available.
The policy does not read or tune itself to saved/current host readings. Headroom
immediately below/at/above each boundary is covered with synthetic page counts.

512 MiB GOMEMLIMIT is advisory and applies to Go-managed memory, not all native
allocations or total RSS. The supervisor enforces the separate 1 GiB *sampled*
RSS decision, terminating/reaping its own worker on violation. Both RSS and host
headroom can change between samples; nominal 100 ms/250 ms cadences can stretch
within the existing 2 s telemetry-gap bound. No hard RSS cap, hard reservation,
precise peak or guarantee against transient pressure is asserted.

## Preserving v1

The original 113-file checkpoint `e9af4dfd999846d8ace36fce4068de054362aa19` is left
byte-for-byte intact, including v1 SDK, scientific profile, engine and baseline.
`./rhook` remains v1. The new entry point is `./rhook-v2`.

The v2 wrappers reuse five hash-authenticated v1 source modules in separate Python
namespaces. They load only fixed checked-in source paths; raw runtime data is
never executable input. Exact source hashes and edit counts reject drift.
Reviewed changes are the policy path, consent domain/profile commitment, two
RSS-bound expressions (4→1 GiB) and Go advisory limit. CPU/wall, pipe/storage,
signal and owned-child cleanup logic is otherwise preserved. The five original
files and their globals are not patched. This avoids a second copy of the engine
or a fork of the full CLI/workflow. V1 builds keep their original source closure.

Build records bind all v1+v2 source files and the v2 policy. A v1 KIT/build or
consent cannot authorize v2. The v2 Go adapter has its own domain/profile/hash;
`pair.go`, admission of original inputs/state and nil Source remain unchanged.

## Local commands

These are safe preparation commands and do not measure the host or execute EVM:

```sh
./rhook-v2 policy
./rhook-v2 --help
./rhook-v2 build --build-root /absolute/completed/pinned-build-root
```

`setup` can attach the resulting build and import the exact separately supplied
block package into a fresh workspace. `--bootstrap` would download/build pinned
dependencies; it is not needed for this prepared local checkpoint.

Future execution requires separate founder approval. The reviewed plan will use
one `doctor → prepare → replay → verify` sequence: doctor failure stops before
prepare; replay performs its own fresh admission before any EVM; no repeat,
threshold change, fallback, other block or process restart. A second admission
may fail even if the initial doctor passed. `externalDelivery=HOLD`.

## Tests and limitations

```sh
python3 -m unittest discover -s sdk_alpha_v2 -p 'test_*.py'
```

Tests use pure host packets and a small owned C fixture with synthetic RSS rows.
They test pressure/swap/data boundaries, 1 GiB RSS violation, signals before/after
dispatch, forced termination/reaping, v1 isolation and canonical/no-repeat scope.
No real host sensor, memory stress, historical package execution, provider RPC or
Rust replay is involved. Fixture process CPU/exit metadata is used only for owned
cleanup tests. A synthetic PASS or reassessment of saved doctor data is not a
fresh admission PASS. Until future approved native acceptance, v2 remains untested
on the real saved Pair03 execution path.
