# Create a historical case

Witness Forge adds `capture-case`, `forge-case`, `diagnose` and `check-case` to
the existing `rhook-cases` CLI and `CaseSDK` API. The initial execution profile is
Robinhood Chain 4663, the retained Hookr-1 Root/Rules/executor bindings and the
LP Rewards field. Other contracts, generations and arbitrary forks are unsupported.

Case capsules and `BLOCK_PACKAGE.json` retain their existing formats. The worker,
native v2 policy and original engine are unchanged. New-case acquisition is an
explicit read-only operation; replay remains separately consented and offline.

## Install and register

Use the [case installer](CASE_CAPSULES.md) with Python 3.12+ without optimization,
the pinned Node dependencies and a matching private `RUNTIME.json`. These helpers
require that registration even when no EVM execution is requested. The public
source clone includes neither the historical data nor a native runtime bundle.

```sh
RHOOK=/path/to/installation/bin/rhook-cases
CASE_HOME=/path/to/private-case-home
"$RHOOK" --home "$CASE_HOME" register-runtime /path/to/RUNTIME.json
```

## Capture a selected block

Choose a block number and an ordinary transaction's ordinal after the first
Nitro system arrival. No previously saved package hash or Pair03 block number
is required. The supported Rules contract must exist at that original parent.

```sh
"$RHOOK" --home "$CASE_HOME" capture-case --chain 4663 \
  --block "$BLOCK_NUMBER" --subject-index "$SUBJECT_INDEX" --case my-hookr-case \
  --output /path/to/new-capture --allow-read-only
```

This client uses only the public Robinhood RPC, without credentials. Its fixed
ceiling is 32 requests, 30 seconds and 8 MiB including response headers; each body
is limited to 2 MiB and each header set to 8192 bytes. Requests start at least 334 ms
apart. Each request has a 3-second deadline. There are no retries, redirects,
alternative endpoints or automatic checkpoint replacement. Current capture is
limited to 2–8 arrivals and 20 million declared gas. Original headers, Rules/ArbOS context, pinned contract proofs and known transaction
accounts/code are requested; successful proofs are immediately authenticated.
Original raw transaction bytes are reconstructed and hash/root checked locally,
as described below.

`select-recent-case --output /path/to/new-selection --allow-read-only` is an
optional two-request search over the last 1024 blocks for a supported pool event.
It never starts a capture or expands the search automatically. Its event selection
is provisional, not proof of a supported execution scenario.

The raw request intents, responses, exact selected headers, timings and any partial
package survive a STOP. A missing historical root is a provider failure, not an
EVM result. Archive value reads do not establish historical proof availability.
Do not repeatedly select a newer root to hide a failed fixed-checkpoint capture.

## Import independently acquired state

Provide original headers and **all ordered raw transactions**, plus state from
an independent source. A witness input can be an existing
`rhook/remote-witness-seed/0.1` or the result object of `debug_executionWitness`
with its original-parent header chain, state nodes and code preimages.

```sh
"$RHOOK" --home "$CASE_HOME" forge-case \
  --package /path/to/developer/BLOCK_PACKAGE.json \
  --witness /path/to/developer/remote-witness.json \
  --case my-hookr-case --subject-index "$SUBJECT_INDEX" \
  --output /path/to/new-import
```

Omit `--witness` when the package already contains its state. The importer computes
the existing Go input/witness commitments instead of asking users to supply them.
It authenticates header links, transaction identities/signers/root, account/storage
paths and account/code bindings. A caller must separately trust the checkpoint's
chain identity; these checks do not prove independent consensus or finality.

Where the native importer requires explicit proof paths, Forge projects them
from authenticated original-root trie bytes. `DERIVED_PROOF_PROJECTIONS.json`
identifies their origin. These are verified local import projections, **not**
invented RPC requests/responses or claims that a provider returned those proofs.
Unresolved paths stay missing. Foreign checkpoints, bad hashes and unanchored
material in the remote-seed format are rejected.

The source package, prior registry objects and scientific evidence are never
overwritten. Each output directory must be fresh. No execution grant is created.

## Inspect readiness, then plan

```sh
"$RHOOK" --home "$CASE_HOME" import-case /path/to/new-import/capsule
"$RHOOK" --home "$CASE_HOME" inspect --case my-hookr-case
"$RHOOK" --home "$CASE_HOME" diagnose --case my-hookr-case
"$RHOOK" --home "$CASE_HOME" check-case --case my-hookr-case \
  --trust-checkpoint "$ORIGINAL_PARENT_HASH"
"$RHOOK" --home "$CASE_HOME" plan --case my-hookr-case --set lpBps=50
```

| Result | Meaning |
| --- | --- |
| `IMPORTED` / `UNAUTHENTICATED` | Local integrity only; no chain or execution claim |
| `HEADERS_ONLY_INCOMPLETE` | Header links checked; state is unavailable |
| `AUTHENTICATED_INCOMPLETE` | Original-root material authenticated; named dependencies missing |
| `UNSUPPORTED_EXECUTION_PROFILE` | Contract generation or context differs from the supported profile |
| `READY_FOR_BOUNDED_NATIVE_ATTEMPT` | Known prerequisites and native input admission passed; no EVM ran |
| `COMPLETED`, followed by successful `verify` | A fresh native pair completed and its own records passed verification |

Reports distinguish membership, proven absence and unknown paths. They identify
missing account/slot/node/code hashes. Availability at the original parent does
not establish all dynamic reads or trie-update dependencies. Write closure stays
unknown until the exact plan has actually executed. The retained native collector
and its typed missing-state evidence remain authoritative for execution demand;
capture does not run live EVM discovery or silently hydrate a failed replay.

Use the existing `authorize → replay → verify → compare` sequence for one reviewed
plan. Each replay requires a fresh local consent and host admission. A native STOP
permanently closes it. The worker has nil network Source: no replay RPC or downloads.

Python exposes `capture_case`, `forge_case`, `diagnose` and `check_case` on `CaseSDK`.
The comparison API now provides `subjectRhookTransferNet*` fields. Legacy `buyer*`
fields are compatibility aliases for the selected sender's signed Transfer-event
net, not a classification as a buyer or a profit measure. Negative baseline net
does not produce a buyer-increase percentage.

Acquisition helpers retain the frozen bounded pipe/process capture, with a separate
8 MiB per-file allowance for packages, 3 CPU seconds and a 40-second outer deadline.
Native execution limits are unchanged. Parent directories assume a trusted local
operator. This is not a multi-tenant upload service.

## Live capture

`qualify-root --output NEW_DIRECTORY --allow-read-only` makes at most four public
requests in10seconds/1MiB. It authenticates a Rules proof for a newly observed
root and records dispatch times, observation age and adjacent endpoint heights.
This is a state-access test, not a case, finality proof or retention guarantee.
The exact backend head at dispatch cannot be observed by this client.

With an installed runtime registration and its pinned local dependencies:

```sh
"$RHOOK" --home "$CASE_HOME" capture-recent-case \
  --output "$PWD/fresh-capture" --allow-read-only
```

The command observes at most three latest full blocks, with starts at least
1.5seconds apart within a4second start window. An in-flight RPC can finish
later; the entire acquisition keeps its32-request/30second/8MiB limits. A bloom
match only triggers `eth_getBlockReceipts` for that exact block hash. All ordered
receipts, their blooms, gas and transaction/block metadata are checked against
the observed header's receipts root before selecting a supported pool swap.
That header is operator-observed; independent chain finality is not established.
The observed block is reused so capture begins without another historical search.

`NO_ELIGIBLE_EVENT_IN_OBSERVATION_WINDOW` is a normal terminal result, with no
case or fallback block. A source/budget failure remains a STOP. A selected event
pins the exact target and original parent. Capture saves the local observation
age and head distance, and rechecks the target header after acquiring state.
Only `CAPTURED_AUTHENTICATED_CAPSULE` permits the import/check-case flow above;
then use the reported case ID and explicitly trusted original-parent hash.

Capture reconstructs legacy/EIP2930/EIP1559 and Nitro internal signed envelopes,
checking every hash and the ordered transactions root. Unsupported encodings
stop. Proof collection groups a20-chunk ArbOS prefix with its authenticated
length/version; longer configurations fetch only the unresolved tail. Code is
cached by the account's proven codeHash. An optional `--witness REMOTE_SEED.json`
can supply an exact-checkpoint cache; foreign roots and poisoned bytes fail.
Derived proof paths retain their labels and do not become provider statements.

## Nitro input context

ArbOS61 opens `FilteredTransactionsStorage` while admitting ChainConfig.
Its `KVStorage.SetNonce` reads account
`0xa4b0500000000000000000000000000000000001`, before EVM execution. Earlier
unseeded capture omitted that account, causing Go `PROOF_SOURCE_UNAVAILABLE`
even though JS reported its smaller prerequisite set as present. Capture now
requests that account proof and JS names any missing original-root path/node.
A proven absent account remains distinct from an unavailable path.

On the retained seven-arrival fixture, one extra proof supplies four missing
nodes (1637bytes) and makes the unchanged Go input check pass without a full
cache. The complete acquisition graph is31 RPC for seven arrivals and25 for
five, compared with the previous30/24 incomplete graphs. The authenticated
near-head route also uses31 calls for a first-observation seven-arrival fixture;
each earlier observation adds calls. Larger/later workloads can still hit32.
These are offline fixture counts, not live availability or latency guarantees.
Static Go admission does not establish all dynamic reads or trie-update closure.
A fresh execution still requires a qualified case, local consent and unchanged
v2 host admission. Closed captures and accepted native evidence remain immutable.

## Event-driven capture

`watch-case` listens for the supported PoolManager `Swap` event, filtered by
emitter, signature and PoolId. A notification only triggers discovery. The exact
block hash, original parent, entire ordered receipts root, event identity and
signed transaction root must authenticate before its state becomes a capsule.
An observed RPC header is an operator checkpoint, not independent finality.

```sh
"$RHOOK" --home "$CASE_HOME" watch-case --allow-read-only \
  --credential-file /path/to/private/token-only-file \
  --account-assertions /path/to/fresh-account-observation.json \
  --output /path/to/new-watch
```

The token file must be owned by the caller, regular, private (0600), and contain
only the existing Alchemy key. It is used only with the fixed Robinhood Mainnet
WSS endpoint; URLs and credentials are excluded from records. No new key or paid
plan is created. The local account observation has this schema:

```json
{"schema":"rhook/alchemy-free-assertions/0.1","freePlan":true,"paidUsageDisabled":true,"chainId":4663,"websocketEntitled":true,"remainingCU":2000,"observedUnixMs":0}
```

Replace quota/time with actual recent observations. An expired observation,
unknown entitlement or insufficient quota stops before network access. These
local assertions express operator-confirmed prerequisites, not provider-signed
entitlements. A confirmed unsupported entitlement allows contiguous public
`eth_getLogs` fallback without reading a credential file.

One session has a 20-second observation window, at most two WSS connections
(one reconnect), 64 incoming messages, 4 KiB per frame and 32 KiB aggregate
application payload. Local estimated usage is capped at 2000 Free CU, counting
subscription controls and payload bytes; it is not a provider billing guarantee.
HTTP discovery separately allows 16 requests / 30 seconds / 8 MiB. Startup,
disconnect and final catch-up scan contiguous ranges, each at most 64 blocks,
with at most 256 blocks per catch-up. Gaps beyond that budget stop explicitly.
No-event reports include the actual coverage horizon; they do not establish
inactivity outside that range. Unsupported subscriptions use bounded contiguous
fallback. Other transport, quota or authentication failures remain STOPs.

A selected event starts a separate acquisition budget of 32 requests / 30 seconds
/ 8 MiB. Independent same-root proofs and code reads may overlap at concurrency
two; all starts retain 334 ms pacing and byte reservations. First failure cancels
peers. No failed capture retries or changes its checkpoint. Logs/receipts discovery
and acquisition counters remain separate; `CAPTURE_LATENCY.json` and request
records show event, pin, proof start/completion times and remaining budgets.
Monotonic pin age is a client observation, not the backend retention window.

`NO_ELIGIBLE_EVENT_OBSERVED` is a normal result with no capsule or native grant.
`CAPTURED_AUTHENTICATED_CAPSULE` can proceed to the existing import/check flow;
static admission still does not establish execution or write closure. Python
provides `CaseSDK.watch_case(...)` with the same opt-in and file arguments.
The watcher child has an 80-second outer deadline covering the separate discovery,
acquisition and offline processing stages. Native v2 limits remain unchanged.
