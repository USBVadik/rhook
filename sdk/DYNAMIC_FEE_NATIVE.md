# Dynamic Fee OFF — separate native profile

This derivative extends the original prepared-witness SDK. It has not yet run a
new EVM producer. The accepted LP worker and historical evidence remain intact.

For preparation before deployment approval, pass `candidate_runtime=<pinned
RUNTIME.json>` to `prepare_intervention`. This authenticates the built worker
identity read-only and creates candidate inputs only. It does not register or
copy a worker, create its consent key, observe host resources or issue authority.
Status is `EXECUTION_CANDIDATE_PREPARED`, runtime registration `PENDING`; normal
`operation/run` remains blocked until separately authorized registration. Pure
`scenario.api.operation_binding` can describe the future exact binding without
claiming a registered or admitted runtime. The execution path always recomputes
it from authenticated registrations before authority.

Use `rhook_alpha.dynamic_fee.DynamicFeeExecutionSDK` with a **new home**, reviewed
installed source and a separately registered runtime whose profile is
`nitro-hookr-dynamic-fee-off/0.1`. Its input/evidence domain is
`rhook/hookr-dynamic-fee-off/0.1`; it cannot use the LP worker. The resource policy,
RSS/CPU/wall guards, power/open-lid admission, cleanup, one-shot consent and outer
workflow limits are reused unchanged. There is no live acquisition/discovery API
for this profile; supply complete prepared original-root witness.

```python
from rhook_alpha.dynamic_fee import DynamicFeeExecutionSDK
sdk = DynamicFeeExecutionSDK('/absolute/fresh/home')
sdk.register_runtime('/absolute/derivative/RUNTIME.json')
# Register the separately pinned existing host-v3 sensor if choosing that profile.
plan = sdk.plan_intervention('/absolute/original/SCENARIO.json',
    expected_sha256='<original SHA-256>', kind='hookr.dynamic-fee-off/0.1',
    node='/absolute/pinned/node')['descriptor']
prepared = sdk.prepare_intervention(plan, '/absolute/original/SCENARIO.json',
    expected_sha256='<original SHA-256>', output='/absolute/fresh/prepared',
    node='/absolute/pinned/node')
sdk.authenticate(prepared['prepared'])  # original-state admission; no EVM
operation = sdk.operation(prepared['prepared'], host_profile='macos-host-admission-v3')
# STOP for exact founder consent on this binding and physical-host readiness.
```

A separately authorized call to inherited `run` uses the existing installed CLI
`scenario-run` and permanent attempt marker. It requires the exact operation,
`local_owner=True`, `mac_ready=True`, fresh host admission and a fresh evidence
path. No consent is created by prepare/operation/authenticate. This document is
not execution authorization. Separate `verify` and `compare` retain their original
scope: authenticated inputs and recorded-result coherence, no independent EVM
reexecution or consensus/finality proof.

The profile fixes one Hookr generation/pool and action, keeps LP100, and disables
only this pool's Dynamic Fee with **two exact ordered writes**. Config max11500
becomes3000, sensitivity2 becomes0; Root mode3 becomes2 retaining recapture. The
input binds the original root, code hashes, complete old/new words, parent
Build16 plan commitment and typed transform commitment. All other config, signed
transaction, common modeled funding and environment stay fixed. This is a
hypothetical checkpoint patch, not a setter transaction or an alteration of
recorded canonical history.

Both worlds start from independent nil-Source bridges. Both old words are checked
before any write. Each world records the transform commitment and applied words
(BASELINE unchanged, VARIANT changed). The new verifier reconstructs common setup
and initial overlay roots with StateDB/trie operations, never trusting supplied
roots alone, before checking existing header/transaction/receipt relationships.
`--authenticate-overlay` on the derivative performs only that state-relation
check, not EVM execution or transitive witness-coverage confirmation.

The original LP0.1 schema/profile/recorded verifiers remain accepted. LP inputs
cannot carry the new intervention; linked worker profiles cannot downgrade or
relabel each other's inputs. Unknown fields, extra writes, changed LP, wrong root,
wrong code identity, mixed profiles and missing state fail closed. Existing
`ExecutionSDK` remains the LP interface; use the separate Dynamic Fee facade for
the derivative. Build16 plans retain their truthful LP-backend incompatibility.

Hookr SDK1.1.1 creator checks accept zero sensitivity exactly when maxFee equals
base. That does not authorize an administrative change to an existing pool.
Dynamic Fee configured ON does not imply a positive dynamic component on this
specific buy. No new gas, receipt, token amount or economic difference is promised
before an independently initialized two-world run completes. Existing witness
coverage for this changed path remains unproven. Missing dependencies stop;
no automatic RPC hydration, provider fallback or retry exists.

No external distribution clearance is implied. HOLD.
