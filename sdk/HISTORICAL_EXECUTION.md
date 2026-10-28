# Historical Counterfactual Execution

This is the local Developer SDK historical workflow. It uses the existing
CaseSDK, one-shot issuer, native supervisor and typed profile adapters. Source
availability does not include the private worker, witness or runtime dependencies.
Nothing in this guide grants permission to run or distribute them.

The separate [typed admission candidate](INTERVENTION_ADMISSION.md) exposes a
closed catalogue and L1–L9 assurance sidecars. It does not retroactively qualify
checkpoint storage changes under the original Message.Data-only semantics.

## Supported interventions and scope

| Adapter | Developer descriptor | Scope |
| --- | --- | --- |
| `hookr-1.lp-bps/1` | `{"rule":"lpBps","value":50}` | Integer0–99; pinned Hookr pool, Rules generation and original declared word. Planning other values is not a native acceptance for each value. |
| `hookr-1.historical-dynamic-fee-off/1` | `{"rule":"dynamicFee","value":"OFF"}` | Exactly saved block93251803, parent93251802, subject ordinal3 and the pinned Root/Rules generation. No other value or block is accepted by this adapter. |

These are whole-block parent-checkpoint interventions. All original arrivals remain in order, including the selected signed transaction. ACTUAL has no initial intervention. The independent
BRANCH begins from the same original parent with its typed overlay **before the
first arrival**. It is not a patch immediately before the selected transaction
and is not a newly signed administrative transaction.

The Dynamic Fee adapter changes Rules maxFee11500→3000, sensitivity2→0 and
Root mode3→2 through two exact word writes. LP100, arb recapture, balances,
code, nonce and unrelated initial bits remain unchanged.

The separate `ExecutionSDK`/`DynamicFeeExecutionSDK` hypothetical scenario APIs
keep their own domains and modeled transactions. This historical API does not
silently substitute those scenarios for signed historical input.

## Preparation and proof authentication

Use Python3.12+ without optimization. A source-only installation is possible:

```sh
python3 -B sdk/install_cases.py --prefix /absolute/private/sdk
```

For the retained Dynamic Fee target, prepare the raw package using
[the existing example](examples/historical_dynamic_fee_off.py). Its private
BLOCK_PACKAGE bytes must match the adapter's pinned hash. This only packages,
imports and plans; it issues no consent, loads no native runtime and runs no EVM.

```sh
python3 -B sdk/examples/historical_dynamic_fee_off.py \
  --package /absolute/private/BLOCK_PACKAGE.json \
  --capsule /absolute/private/new-capsule \
  --home /absolute/private/new-case-home
```

An already prepared capsule can instead be imported with `import-case`. Use
the returned local case/plan identities, not the identities of a closed run.

```sh
RHOOK=/absolute/private/sdk/bin/rhook-cases
CASE_HOME=/absolute/private/new-case-home
"$RHOOK" --home "$CASE_HOME" import-case /absolute/private/new-capsule
"$RHOOK" --home "$CASE_HOME" inspect --case CASE_ID
"$RHOOK" --home "$CASE_HOME" plan --case CASE_ID --set dynamicFee=OFF
"$RHOOK" --home "$CASE_HOME" describe --plan PLAN_ID
```

A runtime registration must include the matching profile-specific worker,
source/policy commitments, retained v2 sensor, Node and authenticated verifier
dependencies. Supply only the approved corresponding runtime/dependencies;
the SDK does not download, rebuild or substitute them. A source-only clone
cannot complete native execution. `RUNTIME.json` missing from the selected home
means runtime registration has not been completed for that home.

```sh
"$RHOOK" --home "$CASE_HOME" register-runtime /absolute/private/RUNTIME.json
"$RHOOK" --home "$CASE_HOME" authenticate --case CASE_ID \
  --trust-checkpoint ORIGINAL_PARENT_HASH
```

Registration checks hashes and a bounded worker identity mode, then creates a
private local consent key. It grants no operation. `authenticate` verifies
present proofs/code at the declared original root in a nonproducer worker mode.
It does not establish consensus/finality, dynamic read/write closure or a new
EVM result. Declared/checksummed capsule data alone is not authenticated state.

## Review an exact operation, then obtain separate consent

```sh
"$RHOOK" --home "$CASE_HOME" operation --plan PLAN_ID \
  --trust-checkpoint ORIGINAL_PARENT_HASH
```

`operation` returns the exact existing binding and `operationCommitment`, with
worker/policy/source, input, capsule, runtime, owner/host, output path and limits.
It checks the current registered runtime, including bounded identity mode;
it issues no grant, evaluates no host admission and starts no producer.
Save this local output for review. It contains local host/path identities.

Only after a separate exact owner approval and current physical-host checks:

```sh
"$RHOOK" --home "$CASE_HOME" authorize --plan PLAN_ID \
  --trust-checkpoint ORIGINAL_PARENT_HASH --operation REVIEWED_COMMITMENT \
  --local-owner --mac-ready
```

`--operation` refuses a different current binding before reading the consent
key or issuing a grant. The legacy call without this optional argument remains
compatible; the reviewed workflow uses it. A preview is not approval, resource
admission or a reservation. If any source, runtime, input or path changes,
review a fresh operation rather than overriding the mismatch.

The corresponding Python API uses the same backend:

```python
from pathlib import Path
from rhook_alpha.cases.api import CaseSDK

sdk = CaseSDK(Path("/absolute/private/new-case-home"))
preview = sdk.operation("PLAN_ID", trusted_checkpoint="ORIGINAL_PARENT_HASH")
print(preview)  # Stop here for exact owner review; no consent or EVM.

# Only after separate approval and current prerequisites:
# grant = sdk.authorize("PLAN_ID", local_owner=True, mac_ready=True,
#     trusted_checkpoint="ORIGINAL_PARENT_HASH",
#     expected_operation=preview["operationCommitment"])
```

## One installed replay, then separate verify and compare

Use the existing bounded owner/operator execution context and the exact returned
grant. Run `replay` once, with its whole CLI bounded to180s as in the accepted
operator workflow; do not weaken or replace the retained supervisor.

```sh
"$RHOOK" --home "$CASE_HOME" replay --plan PLAN_ID --authority GRANT_PATH
```

The grant is consumed once. Fresh measured AC/open-lid, v2 resource admission
and continuous guards remain mandatory. ACTUAL must match canonical stateRoot,
receiptsRoot and blockHash before BRANCH can begin in a fresh state bridge.
Source=nil, RPC/WSS/hydration/onchain=0. RSS≤1GiB, native CPU/wall≤120s,
stage≤140s, workflow≤180s and existing cleanup/file limits are retained.
Missing dependencies, resource failure or uncertain cleanup close the attempt.
Do not retry a closed operation or silently obtain a different witness.

After `COMPLETED` and confirmed cleanup, use the newly created run directory:

```sh
"$RHOOK" --home "$CASE_HOME" verify --run NEW_RUN_DIRECTORY
"$RHOOK" --home "$CASE_HOME" compare --run NEW_RUN_DIRECTORY
```

The accepted operator runs these read-only commands separately from replay,
under a combined45s bound. The Python equivalents are `sdk.replay(plan,grant)`,
`sdk.verify(run)` and `sdk.compare(run)`; use the existing owner/operator bounds.

Verification authenticates recorded inputs, proofs, overlay, receipts/header
commitments, bindings, resources and closure. It does not independently execute
the EVM or prove the final state transition. Compare reports signed selected-
sender Transfer-event net, outer Swap fee and subject gas, rather than profit
or independently proven token-storage balances. Witness closure is scoped only
to the completed plan.

## Acceptance and remaining coupling

Build18 operation
`d5a9bcc9a7e4274e3cf67603dc24014669b0162e8efc3e677dcfb3b1633327ea`
completed one canonical ACTUAL and independent Dynamic Fee OFF BRANCH, followed
by separate recorded verify/compare. The exact implementation is preserved in
local source commit `b37e697868d08e0a01bcfadb21d49a8f372bf546`.
It remains permanently closed. Build19 adds review/consent ergonomics; it does
not silently replace the accepted installation or claim another native run.

The historical OFF profile still pins one exact block/package, contract code
hashes, storage layout, original words, subject and witness. LP support also
remains generation/pool constrained. Neither is an arbitrary-contract API.
Independent heterogeneous EVM verification and external-machine acceptance
remain unestablished; `qualifiedClaims=0`, `economicAssurance=UNRESOLVED`.
Runtime licensing, witness disclosure and recipient approval remain separate
from source correctness. No publication or executable delivery follows here.
