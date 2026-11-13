# RHOOK Hookr Studio — Public Developer Preview 01

RHOOK is Counterfactual Execution infrastructure. Hookr Studio is its first
developer-facing application: ask how a configuration changes execution,
compare two worlds and inspect the limits of the evidence.

This package reuses the existing Studio catalogue renderer, revision model and
result rendering contract with a static read-only provider. It does not install
or connect to the private CaseSDK, controller, HostLedger or a chain endpoint.

## Start from a clean checkout

Requires Node.js 22 or later. No installation, account, wallet or secret is needed.
Run from the repository root:

```sh
node --test examples/studio-preview/tests/*.test.mjs
node examples/studio-preview/serve.mjs
```

Open [the local preview](http://127.0.0.1:4173). Stop the server with Ctrl-C.
`PORT=4174` selects another port. Opening `index.html` as a `file:` URL is not
supported: the static datasets need an HTTP origin. Production uses HTTPS.

## What you can do

- Select A, B or Auto Burn and inspect exact saved BASELINE/VARIANT results.
- Expand transaction receipts, gas, worker-reported state words and provenance.
- Inspect Auto Burn balance snapshots and exact per-buy token/quote accounting.
- Explore 21 blocks / 131 fields from retained Hookr SDK 1.6.1 metadata.
- Change block settings and buy amounts, reset, search and export a local draft.

The result panel always names its selected **recorded** configuration. An edited
draft has no execution result. Downloaded drafts are explicitly unexecuted and
unvalidated; the public editor does not replace the private scenario compiler.
Returning the draft to the selected saved values restores its reference match,
not a new execution. Run remains disabled for every configuration.

## Feature and evidence matrix

| Capability | Preview status |
| --- | --- |
| Catalogue discovery / draft editing | 21 blocks / 131 retained metadata fields |
| A / B native configurations | Recorded Nitro execution; same 0.2 worker |
| A / B controller workflow | Verify → Compare → Read Final PASS |
| Auto Burn 0.3 native / recorded Verify | Completed / PASS |
| Auto Burn original controller | Compare STOP; original Lab result not installed |
| Corrected Compare + saved-result sidecar | Separate acceptance PASS; original STOP/quarantine unchanged |
| Other blocks or arbitrary edited settings | No demonstrated execution coverage |
| Public live Run / RPC / wallet / dispatch | Unavailable |
| Independent EVM verification of these cases | Not performed; Qualified Claims = 0 |
| Historical chain authentication | Not established; hypothetical Playground |

Changing AS and DF together does not isolate the causal contribution of each
mechanism. Additional matched controls would be needed for that question.

A/B BASELINE disables AS/DF. Auto Burn BASELINE enables the same AS/DF settings
as its VARIANT, with burn OFF; VARIANT sets burn to 100 bps. These controls must
not be conflated. Each record has APPROVE → LAUNCH_POOL → BUY → BUY; both buys
use 0.001 ETH input and one actor in the declared local environment.

Auto Burn transfers subject tokens to DEAD. It does **not** reduce totalSupply.
Protocol observations are accrued quote claims, not withdrawals. Subject-token
base units and quote wei are separate units. Output reduction differs from DEAD
transfer because the protocol quote slice changes too. All comparisons use
integer strings / BigInt, with no floating-point token arithmetic.

## Data, schemas and integrity

[Data schemas](schema.json) describe the versioned publication contracts.
[Integrity metadata](data/integrity.json) pins the four dataset files;
`data-pins.mjs` pins that manifest. Browser reads fail closed on changed bytes.
The retained result validator checks transaction/world binding and Auto Burn
snapshot deltas. Tests reproduce exact economic differences from the public
records without running EVM or a native verifier.

`projection.resultIdentity` belongs to the **original full projection**. Logs
and environment details have been removed here, so this ID is not a digest of
the public sanitized object. `originalRecordSha256` references the original
private record bytes (the acceptance sidecar for Auto Burn). Dataset SHA-256
checks byte consistency only. Neither hash consistency nor saved verification
proves independent EVM correctness. Private artifacts are not downloadable.

Auto Burn's nested producer flags describe its original native execution.
The separate sidecar has `nativeExecutionPerformedNow=false`, recording a later
verification-only acceptance. Opening the preview performs neither operation.

## Deploy to HTTPS

Create one small static folder, from the repository root:

```sh
node examples/studio-preview/package.mjs /tmp/rhook-studio-preview-dist
```

The destination must not already exist. The command copies only the explicit
public file list and prints SHA-256 values. It does not upload or deploy anything.
No private files, build cache, archives, runtime binaries or dependency tree are
copied. This is a buildless site; there is no npm install or server-side runtime.

After owner approval, publish that folder as a static HTTPS site using the
existing RHOOK website hosting process. A separate preview hostname or `/studio/`
path works: asset and dataset URLs are relative. Preserve the supplied `_headers`
(or translate them into the host's header configuration). Serve `.mjs` as
JavaScript and JSON as JSON. Do not add an SPA fallback for missing data files.
Keep one version of assets and data together; do not cache a changed manifest
under old assets. HTTPS is required for browser Web Crypto outside loopback.

Before announcing a live URL, verify on its actual HTTPS origin:

1. A, B and Auto Burn load without private endpoints or console errors.
2. Auto Burn shows the original Compare STOP and the separate acceptance.
3. Editing any setting produces an unexecuted draft, with Run disabled.
4. Rapid switching cannot display an old response under another record's label.
5. Desktop and narrow mobile layouts, keyboard navigation and table scrolling work.
6. Network requests are same-origin static reads only.

This preparation does not claim a live public deployment. Publication and
hosting actions follow the owner's separate deployment decision.

See [attribution and source lineage](THIRD_PARTY_NOTICES.md).
