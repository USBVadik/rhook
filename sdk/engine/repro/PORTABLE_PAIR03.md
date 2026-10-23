# Portable Pair03: prepared, awaiting native authorization

This is a local macOS arm64 replay preparation. The new worker is compiled but has not executed block 93251803. Historical Pair03 remains a Go/Nitro observation; economic assurance is `UNRESOLVED`, heterogeneous agreement is `NOT_EVALUATED`, and B=0. Public/SDK/executable delivery remains `HOLD`.

## Build the thin adapter

Use an already completed [build-only directory](README.md). The following reuses its freshly built pinned library, toolchains and caches; it does not repeat bootstrap or rebuild Rust. Go module networking is disabled for this step. A missing dependency stops the build.

```sh
python3 -B -m unittest discover -s repro/tests -v
python3 -B repro/build_portable_pair03.py \
  --workdir /absolute/completed/build-directory --tag portable-build-01
```

The result is `portable/artifacts/rhook-saved-pair`, with hashes and dependency/source closure under `records/portable-build-01-*`. The tag must be new so the final build record is not overwritten. Only eight synthetic Go tests are staged, including the five unchanged fake-world/bitmask tests. The historical fixture test is excluded; neither a saved block nor an EVM is used by these tests.

All 65 files under `native/` stay byte-identical. The builder stages the original `pair.go` verbatim with a new `main.go`. The embedded plan removes only `packagePath` and adds the seven original arrival hashes. Scientific commitments, canonical gate and intervention are unchanged. Original module replacements are relocated only in build copies. The old worker is retained separately.

## Explicit inputs and offline preparation

The block package is a separate file, absent from Git and not downloaded by this workflow. Required SHA256: `b55ba3a6d70bd081148966f3b447135a098a26c18bae0c773f065beda807bda3` (1,417,029 bytes). It binds chain4663, parent93251802, block93251803 and all seven raw arrivals.

Use absolute, non-symlink paths with existing parents. Both proposal and output must be fresh directories. Keep them outside source directories. A Node executable is required for the unchanged host sensor and is hashed into the proposal; preparation does not start it.

```sh
python3 -B repro/portable_pair03.py prepare \
  --binary /absolute/completed/build-directory/portable/artifacts/rhook-saved-pair \
  --build-record /absolute/completed/build-directory/records/portable-build-01-RESULT.json \
  --package /absolute/input/BLOCK_PACKAGE.json \
  --output /absolute/fresh-pair03-output \
  --node /absolute/node-executable \
  --proposal /absolute/fresh-proposal
```

`prepare` verifies the portable build record against the selected executable, embedded plan and current source closure, then performs file/SHA/structural checks and creates `AUTHORIZATION_BINDINGS.json` plus an explicitly unapproved template. Build provenance is committed into the bindings and rechecked at replay. It does not create the output directory, issue an authority, measure the host, construct historical execution state, or run the worker. It checks header/checkpoint/arrival identities and Rules proof metadata. The preserved Go admission subsequently checks MPT proofs, block import, raw transaction hashes, input/witness commitments and original state before any `Run` call.

## One replay command, only after separate approval

The founder reviews the exact proposal and separately authorizes the new binary, source closure, package path, output, one host admission and one bounded ACTUAL/conditional-BRANCH attempt. A fresh authority must name that operation, confirm the Mac is powered/open, and provide a window no longer than 600 seconds with at least 140 seconds left at consumption. The template is deliberately unusable. This local latch is an auditable workflow control, not a cryptographic signature service or protection from a malicious filesystem owner.

Run from the approved `require_escalated` supervisor context:

```sh
python3 -B repro/portable_pair03.py replay \
  --bindings /absolute/fresh-proposal/AUTHORIZATION_BINDINGS.json \
  --authority /absolute/fresh-founder-authority.json \
  --package /absolute/input/BLOCK_PACKAGE.json \
  --output /absolute/fresh-pair03-output
```

The output directory is the irreversible one-use latch. Any STOP closes this authority, including host failure. Never delete it to retry or change the block/inputs to obtain a passing result. A later attempt requires separate review and a new authority/output.

The launcher captures nested sensor exit/stdout/stderr before interpreting admission, then supervises the worker with the preserved eight guard function bodies. It copies the exact new worker into `artifacts/`, retains raw authority linkage in `runtime/STARTED.json`, and writes native partials, resources, receipts, observations and a terminal `FINAL_RESULT.json`. A missing or unreliable completion is `INTERRUPTED_UNVERIFIED`; state/host failures are not invented EVM reverts.

## Preserved policy and acceptance

- Host admission is unchanged and currently accepts only Darwin with **24 GiB physical RAM**. A different RAM size fails closed. It checks normal pressure and nonincreasing swap; it does not reserve memory or promise continuous host pressure monitoring.
- One host sensor: seven-second capture, per-child CPU3s and bounded raw pipes. No sensor runs during preparation.
- Native pair wall/kernel CPU120s, sampled worker RSS4GiB, 100ms telemetry with maximum gap2s, output64MiB and sampled runtime128MiB. `GOMAXPROCS=2`, advisory `GOMEMLIMIT=1GiB`; advisory/sampled limits are not hard memory reservations or an exact peak guarantee. Own worker PID observations only, never unrelated argv/environment.
- Overall planned consumption-to-cleanup budget140s; no retry, reselection, state hydration or deadline extension. RPC=WSS=B=0.
- Each world is independently initialized from the original parent, with nil Source. No provider URL, credential or fallback is accepted by the replay interface. This is a source-enforced offline path, not an OS network sandbox claim.
- ACTUAL must match canonical stateRoot, receiptsRoot and blockHash after all seven arrivals. Only then may BRANCH apply LP100→0 at bits160–175, with the original full-word/code/witness guards intact.
- `baseline.json` pins hashes of both preserved result projections: canonical/world roots, input/witness commitments, all receipts, total gas and the full economic observation (calls, transfers, fees and states, including unchanged values). Runtime comparison reports `PAIR03_BASELINE_MISMATCH` without overwriting either baseline or new records. Exact expected selected output: ACTUAL `291469365928126821002944`, BRANCH `294409762269997223561475` RHOOK base units; selected gas delta−2210.

No successful replay of this new executable, second-machine validation, Rust agreement, general SDK compatibility or release is claimed by this preparation. Historical absolute paths remain in the preserved snapshot; the new entrypoint does not use them for package lookup or output placement.
