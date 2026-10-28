# Portable historical cases

The portable API separates local case data, intervention adapters and the native
backend. Its local format is `rhook/case-capsule/0.1`. The legacy Pair03 CLI and
Python calls retain their original runtime registration.

For bounded acquisition of a developer-selected block or import of an independent
remote witness, see [Create a historical case](WITNESS_FORGE.md).

This source branch adds packaging, import, inspection, planning and a source-only
installer. On 26 October 2026, the installed CLI completed fresh ACTUAL/BRANCH
runs for two retained blocks with one data-driven Go/Nitro worker:

| Historical block | Arrivals | Intervention | Result |
| --- | --- | --- | --- |
| 93251803 (Pair03) | 7 | LP100 to 50 | Verified; both full outputs match the prior LP50 reference |
| 93251803 (Pair03) | 7 | LP100 to 0 | Verified; both full outputs match the prior LP0 reference |
| 93249252 | 5 | LP100 to 50 | Verified; canonical ACTUAL, distinct BRANCH state root |

Each operation used a fresh plan/consent, unchanged v2 resource policy, canonical
ACTUAL gate and confirmed cleanup. No RPC or state download occurred. These are
macOS arm64 results from one engine. The second case's selected transaction has
a negative RHOOK Transfer-event net; its net, fee and gas did not change. It is
not a second positive buyer-output demonstration. Coverage is established only
for these executed plans, not arbitrary historical blocks or interventions.
Earlier admission stops remain closed and preserved.

## Install without native assets

With Python 3.12+ without optimization:

```sh
python3 -B sdk/install_cases.py --prefix "$HOME/.local/opt/rhook-cases"
RHOOK="$HOME/.local/opt/rhook-cases/bin/rhook-cases"
CASE_HOME="$HOME/.local/share/rhook-cases"
"$RHOOK" --home "$CASE_HOME" cases
```

This installs source, not a witness, worker, provider or execution grant. Existing
prefixes are rejected. No dependency is downloaded and no host admission runs.
The equivalent API is `rhook_alpha.cases.api.CaseSDK`; the original `SDK` class
also exposes `import_case`, `list_cases`, `register_runtime` and `authenticate`.

## Package and import

A capsule directory contains `CAPSULE.json` and the exact `BLOCK_PACKAGE.json`.
The manifest binds chain/checkpoint, original parent root, target header, all
ordered arrivals, input/witness commitments, asset size/hash, adapter/configuration,
execution profile and provenance. It is limited to 64 KiB; this profile accepts a
block package up to 8 MiB. Paths and scripts inside capsule metadata are never
executed. Local names cannot silently replace a previously imported content ID.

An existing capture can be packaged through the built-in adapter. The two
commitments must come from the capture/import inventory; packaging does not
independently authenticate them:

```sh
"$RHOOK" --home "$CASE_HOME" package-case \
  --package /path/to/BLOCK_PACKAGE.json --output /path/to/new-capsule \
  --case my-hookr-block --adapter hookr-1.lp-bps/1 --subject-index 1 \
  --input-commitment INPUT_COMMITMENT --witness-commitment WITNESS_COMMITMENT
"$RHOOK" --home "$CASE_HOME" import-case /path/to/new-capsule
"$RHOOK" --home "$CASE_HOME" inspect --case my-hookr-block
"$RHOOK" --home "$CASE_HOME" plan --case my-hookr-block --set lpBps=50
```

Import another independently prepared capsule into the same registry:

```sh
"$RHOOK" --home "$CASE_HOME" import-case /path/to/second-capsule
"$RHOOK" --home "$CASE_HOME" cases
"$RHOOK" --home "$CASE_HOME" inspect --case second-hookr-block
"$RHOOK" --home "$CASE_HOME" plan --case second-hookr-block --set lpBps=50
```

Use the `caseId` declared by that capsule. Python callers use the same interface:

```python
from rhook_alpha.cases.api import CaseSDK

sdk = CaseSDK("/path/to/private-case-home")
sdk.import_case("/path/to/first-capsule")
sdk.import_case("/path/to/second-capsule")
first = sdk.plan("my-hookr-block", {"rule": "lpBps", "value": 50})
second = sdk.plan("second-hookr-block", {"rule": "lpBps", "value": 50})
```

`package-case` reads metadata and the declared Rules word; it does not prove
those claims. Import checks local integrity and reports `UNAUTHENTICATED` and
`NOT_EVALUATED` witness closure. Planning predicts no economics, issues no grant
and needs no native runtime or free-memory window. Save the returned plan ID.

The first adapter supports the retained `hookr-1` pool/Rules binding, with the
existing code hash and LP field layout. It takes the original packed word,
checkpoint and subject ordinal from each case. The replacement range is 0–99. The subject must follow the system arrival;
observation plans allow at most 16 accounts.
Other pools/rules need explicit adapters; another supported historical block
needs new inputs, not a worker rebuild. Unknown adapters remain inspectable but
cannot plan or execute. A second intervention on one block is not a second case.

## Register a native backend separately

There is no public runtime bundle. With approved retained toolchain/source and
matching dependencies, `tools/build_case_worker.py` builds one worker for this
profile. It never executes EVM or downloads modules:

```sh
python3 -B sdk/tools/build_case_worker.py \
  --retained /path/to/retained-build --output /path/to/fresh-build \
  --sensor /path/to/sensor --node /path/to/node
```

The retained layout contains `application/{worker,prestate}`, `go`, `go-mod`,
`go-cache-clean` and `src/nitro`. The build records its new source/binary identity,
policy and direct compiler inputs; indirect C/assembly includes are not exhaustively
inventoried. The original accepted worker is not replaced or relabelled.

For native use, install with `--dependencies /path/to/approved/node_modules`.
The exact retained dependency commitment is checked again before runtime use.
Register the generated `RUNTIME.json` in a fresh case home, then authenticate:

```sh
"$RHOOK" --home "$CASE_HOME" register-runtime /path/to/fresh-build/RUNTIME.json
"$RHOOK" --home "$CASE_HOME" authenticate --case my-hookr-block \
  --trust-checkpoint ORIGINAL_PARENT_BLOCK_HASH
```

Proofs/code/headers are checked against the declared checkpoint using the retained
prestate importer and verifier. The operator must obtain the checkpoint hash
from a source they trust. `OPERATOR_PINNED_CHECKPOINT` does not mean independent
consensus/finality verification. A self-consistent JSON/hash set is insufficient.
A canonical witness seed alone does not cover variant reads or trie updates.
The earlier Coverage Gate remains a scoped research sidecar with unknown write
closure; its report is not accepted as a blanket execution certificate.

## One fresh execution

Only on the supported macOS arm64 host, after reviewing the plan and accepting
one bounded native attempt:

```sh
"$RHOOK" --home "$CASE_HOME" authorize --plan PLAN_ID \
  --local-owner --mac-ready --trust-checkpoint ORIGINAL_PARENT_BLOCK_HASH
"$RHOOK" --home "$CASE_HOME" replay --plan PLAN_ID --authority GRANT_PATH
"$RHOOK" --home "$CASE_HOME" verify --run NEW_RUN_DIRECTORY
"$RHOOK" --home "$CASE_HOME" compare --run NEW_RUN_DIRECTORY
```

Read-only runtime/authentication/verifier helpers use bounded pipes and a
three-second CPU cap per child, with separate wall deadlines. An overflow or
helper timeout is a STOP, not proof that a provider or witness is unsupported.

The grant binds case, plan, runtime, owner/host, checkpoint and output path. It is
consumed before fresh v2 admission; every STOP closes that operation. There are
no retries or state downloads. Native execution retains independent original-parent
worlds and a canonical state/receipts/block-hash gate before BRANCH. RSS/CPU/wall,
headroom, pressure/swap and owned-process cleanup guards remain in place.

Run `verify`/`compare` only after `COMPLETED` with confirmed cleanup. They check
recorded package/proofs, headers, receipt roots, journal and operation links;
they do not independently re-execute EVM or prove final state/call observations.
Missing dependencies retain typed failure/partial records, not an invented EVM
revert or economic comparison. Completed closure is scoped to the executed plan,
not all other interventions. No Rust qualification or economic assurance follows.

Run synthetic tests with `python3 -B sdk/tools/test_offline.py`. Runtime assets,
historical witness, grants and execution records remain private. This work does
not add live acquisition, an external developer result or a hosted LaunchLab.
# Experimental macOS host admission

Scenario execution defaults to the retained v2 policy. A separately registered
`macos-host-admission-v3` sensor/profile is opt-in; it does not change the accepted
worker or historical evidence. Build its read-only sensor on macOS arm64:

```sh
clang -Wall -Wextra -Werror -O2 rhook_alpha/cases/scenario/host_v3_sensor.c -o /absolute/path/host-v3-sensor
rhook-cases --home /absolute/path/home scenario-register-host /absolute/path/host-v3-sensor
rhook-cases --home /absolute/path/home scenario-prepare /absolute/path/capture --host-admission macos-host-admission-v3
```

An authorized `scenario-run` uses the same explicit host profile and the exact
prepared `--operation` commitment, plus the existing owner/host confirmations.
V3 execution also requires the managed SDK workflow capture, which creates an
isolated CLI process group shared by SDK helpers and the worker. The outer capture
checks the whole group after CLI termination; direct unmanaged v3 runs stop before
state loading or consent. This contains the pinned SDK spawn paths, not arbitrary
programs that explicitly detach themselves.
Preparation neither issues consent nor samples admission. Runs preserve raw power
and lid observations before parsing, bind the host policy/sensor and installed
code, then use a fresh one-shot consent. A STOP permanently closes that attempt.

The experimental estimate is `free + min(inactive, fileBacked - speculative)`,
clamping the subtraction at zero and capping bytes by physical minus wired and
compressor residency. Free already includes speculative. Purgeable, anonymous and
compressed counters are telemetry, not additional credit. The estimate does not
identify clean inactive pages, reserve memory, or guarantee no impact on other
applications. Dirty pages and concurrent allocation can invalidate its forecast.

Admission retains a 1536 MiB estimated budget and a 256 MiB immediately-free
reserve. Runtime retains 512 MiB estimated and 128 MiB immediate reserves, normal
pressure, no swap-in/out or usage growth, bounded telemetry and the original
1 GiB sampled RSS/120-second native CPU/wall limits and owned-child cleanup.
Compression activity alone is recorded rather than treated as pressure. Missing
or contradictory readings fail closed. Synthetic policy tests are not host-impact
qualification. A result under v3 must be reported separately from v2 acceptances.
