# On-demand Hookr scenarios

This profile evaluates a hypothetical transaction at an authenticated checkpoint.
It is separate from historical `ACTUAL/BRANCH` replay. Its outputs are
`SCENARIO_BASELINE` and `SCENARIO_VARIANT`; canonical historical root matching is
not applicable to the simulated block.

The first adapter supports the retained Hookr-1 pool on Robinhood Chain 4663,
using its pinned Root, Rules, PoolManager and current HookrRouter. It models one
0.001 ETH exact-input buy, a public simulation-only caller, a common 1 ETH mint,
nonce 0, a 10,000,000 gas limit and an explicit synthetic Nitro environment.
Both worlds start independently from the same checkpoint. Only the LP Rewards
field changes in VARIANT (original 100, replacement 0–99). These assumptions are
recorded in the plan and input. Never fund or broadcast from the public signer.
The historical adapter and its external router are unchanged.

Install the [case CLI](CASE_CAPSULES.md) with its pinned dependencies. Register a
separately built scenario runtime; this does not replace the historical runtime:

```sh
RHOOK=/path/to/install/bin/rhook-cases
CASE_HOME=/path/to/private-home
"$RHOOK" --home "$CASE_HOME" scenario-register-runtime /path/to/scenario/RUNTIME.json
"$RHOOK" --home "$CASE_HOME" scenario-pool
"$RHOOK" --home "$CASE_HOME" scenario-configure --lp-bps 50
```

Use the returned plan ID. Configuration is offline and requires no memory
admission or execution grant. Acquisition is a separate read-only operation:

```sh
"$RHOOK" --home "$CASE_HOME" scenario-acquire --plan PLAN_ID \
  --output /path/to/fresh-capture --allow-read-only \
  --credential-file /path/to/private/alchemy-token \
  --account-assertions /path/to/recent-account-observation.json
"$RHOOK" --home "$CASE_HOME" scenario-check /path/to/fresh-capture
```

The credential file has the same private ownership/file constraints as
[the watcher](WITNESS_FORGE.md). Only the fixed Alchemy Robinhood HTTPS endpoint
receives its Bearer token. No URL key is recorded, redirects are not followed,
and echoed credentials are rejected before response persistence. The local
account assertion uses schema `rhook/scenario-account-assertions/0.1`, with
`freePlan: true`, `paidUsageDisabled: true`, `chainId: 4663`, actual `remainingCU`
(at least 2000), `throughputCUPerSecond` (at least 200), and `observedUnixMs` from
an observation no more than ten minutes old. Local assertions are operator
statements, not signed provider entitlements.

One checkpoint-only acquisition allows at most 64 RPC, 30 seconds and 8 MiB
response/header bytes. Starts are at least 125 ms apart, with at most two
in flight and a 3-second per-request deadline. With the published 20 CU costs
for these state reads, the worst-case local estimate is 1280 Free CU; provider
billing and other account workloads remain external observations. Historical
capture retains its existing 32-request budget and pacing.

The prefetch catalogue carries only address/slot hints from prior scenarios.
Every proof/code read authenticates against the newly pinned root. The ArbOS61
HistoryStorage slot is derived from the checkpoint L2 number modulo 393168;
its original path and pinned Arbitrum runtime must pass Go admission before
producer entry. Missing paths remain unknown, including slots about to be overwritten. Old trie
nodes are never transplanted. Receipts or a live Swap event are not required.
A missing root/proof/code stops and retains partial material. The collector does
not certify dynamic reads or trie-update coverage before execution.

After reviewing a successful capture, on the supported macOS arm64 host:

```sh
"$RHOOK" --home "$CASE_HOME" scenario-run /path/to/fresh-capture \
  --local-owner --mac-ready
"$RHOOK" --home "$CASE_HOME" scenario-verify --run NEW_RUN_DIRECTORY
"$RHOOK" --home "$CASE_HOME" scenario-compare --run NEW_RUN_DIRECTORY
```

One operation-bound consent is consumed before fresh host admission. Execution
uses the unchanged v2 numerical memory/CPU/wall/cleanup guards under its own
scenario policy commitment. Each world has a fresh nil-Source bridge; there is
no replay RPC, hydration, historical canonical gate, automatic retry or checkpoint
replacement. Missing state closes the operation with the failed world and lookup
identity. An EVM revert remains a receipt outcome; it is distinct from missing
state or a resource stop. The first world must complete before VARIANT starts.

Recorded verification reauthenticates original inputs and checks synthetic
headers, transaction/receipt roots, mappings, common setup and output integrity.
It does not independently rerun EVM, certify consensus/finality, prove all future
interventions, or establish economic assurance. Comparison derives token
Transfer net, selected-pool Swap fees and gas from the verified receipts.
Qualified Claims remain zero; no Rust qualification follows.

Python exposes the same workflow through `CaseSDK.scenario_pool`,
`configure_scenario`, `register_scenario_runtime`, `acquire_scenario`,
`check_scenario`, `run_scenario`, `verify_scenario` and `compare_scenario`.
No public runtime, private witness or remote service is included in the source
clone. Building a derivative runtime requires the retained Nitro toolchain and
`tools/build_scenario_worker.py`; it never downloads dependencies or executes EVM.
# Execution-guided witness closure

`scenario-close` is a separate opt-in operation. It acquires one fresh root,
prefetches the signed action's Nitro filter slot, then permits at most one
discovery BASELINE and VARIANT. A private Unix socket connects the native worker
to a broker using the same 64-request, 30-second, 8 MiB acquisition budget.
Proofs remain bound to the original root; code must match its proven codeHash.
The broker retains credentials; the worker receives only authenticated data.

Discovery records backing-reader misses and successes, code accesses and any
observable trie-update gap. StateDB cache hits are not an exhaustive access log.
An unknown trie sibling or original state stops the operation; it is never zero.
Discovery output has `discoveryOnly=true` and cannot pass the offline verifier.

After acquisition closes, the installed SDK starts two new independent worlds
from the sealed inventory with `nil Source`. It verifies their recorded evidence
and compares their deterministic outputs with discovery. This covers only the
declared pool, caller, action, environment and LP intervention. It establishes
neither historical canonical execution nor an independent Rust/EVM verification.

Prepare without execution:

```sh
rhook-cases --home "$SDK_HOME" scenario-closure-prepare --plan "$PLAN" --output "$OUTPUT"
```

Execute once, through the managed workflow capture, after exact owner approval:

```sh
rhook-cases --home "$SDK_HOME" scenario-close --plan "$PLAN" --output "$OUTPUT" \
  --credential-file "$CREDENTIAL_FILE" --account-assertions "$ACCOUNT_ASSERTIONS" \
  --operation "$OPERATION" --local-owner --mac-ready
```

The existing v2 policy and accepted workers are unchanged. This initial closure
launcher explicitly uses the separately registered experimental macOS v3 host
profile, with fresh power/lid checks, runtime observation and owned-process cleanup.
Its resource estimate is not a reservation or a guarantee of no effect on other
applications. Any STOP consumes this operation; there is no automatic recapture.

The [Developer Execution SDK](DEVELOPER_EXECUTION.md) imports a prepared witness
into a new home and wraps the owned native workflow. It keeps exact consent,
separate recorded verification and native authentication scope explicit.
