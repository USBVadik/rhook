# Explicit checkpoint interventions (Build16)

`ExecutionSDK.plan_intervention` authenticates the original target fields from a
prepared witness and constructs a committed, explicit intervention plan. This is
an offline operation: it starts a Node proof checker, never a native worker,
network acquisition, resource admission or authority issuer. It needs Node and
the existing pinned `viem` dependency. Missing runtime/proof/code material stops
with an actionable error; no dependencies are fetched automatically.

```python
from rhook_alpha.execution import ExecutionSDK
sdk = ExecutionSDK('/absolute/new/sdk-home')
r = sdk.plan_intervention(
    '/absolute/SCENARIO.json', expected_sha256='<exact SHA-256>',
    kind='hookr.dynamic-fee-off/0.1', node='/absolute/pinned/node')
plan = r['descriptor']
```

Two explicit kinds exist:

| Kind | Exact change from the authenticated LP100 original | Native support |
| --- | --- | --- |
| `hookr.lp-rewards/0.1`, `lp_bps=0..99` | Rules config bits160..175 only | Existing LP workflow; fresh exact consent/admission still required |
| `hookr.dynamic-fee-off/0.1` | Rules maxFeePips to base3000 and sensitivity to0; clear Root dynamic mode bit248 | **Plan/projection adapter only. Accepted worker is LP-only.** |

The supported pool is `0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780`
on chain4663. This generation's original configuration is LP100, max11500,
sensitivity2; Root mode3 includes Dynamic Fee and recapture. Mode becomes2,
retaining recapture. This is no generic Hook Block enable switch: two
contract-specific fields must be changed consistently. No transaction invoking a
setter is simulated. Config/selection were frozen at binding; the intervention
is an explicitly hypothetical checkpoint state, not a valid administrative
transition or a rewrite of launch history.

The descriptor binds exact input SHA-256, original scenario commitment,
checkpoint/root, pool/profile, Root/Rules runtime code hashes, complete original
storage words, ordered allowed writes/masks, fixed signed simulation transaction,
common funding and environment, engine pins and canonical intervention
commitment. Original policy opening hashes and accrued dynamic/recapture state
are preserved. The dynamic fee calculation/simulation is bypassed for this pool;
LP Rewards remain100. No positive token-output difference is promised: the
original action may have paid zero dynamic component, and recapture/other pools
still execute under their original rules. Outputs and gas require a new run.

A saved descriptor is not a proof or an execution grant. `validate` checks byte
commitment and transform semantics only. `describe` is a low-level constructor
usable with synthetic fixtures and does **not** authenticate supplied state.
Use `plan_intervention` against the pinned input to authenticate target paths.
`prepare_intervention` repeats that authentication and compares the entire plan
before delegating LP preparation to the accepted API. For Dynamic Fee off it
raises `UNSUPPORTED_NATIVE_INTERVENTION` and creates no prepared run/output.
Existing `configure/prepare/run/verify/compare` and Build10/11 recorded verification
remain unchanged.

`fixture_worlds` returns independent Python projections, labelled
`FIXTURE_PROJECTION_ONLY_NOT_EVM`. It preserves unrelated fields and applies the
exact writes atomically to a copy. It computes neither an MPT root nor an EVM
receipt. `bind_result_hashes` creates committed **unverified result references**;
its output does not claim execution or scientific verification.

Authentication establishes the original Root/Rules account paths, their code
preimages and five storage leaves only. It does not prove canonical finality,
complete witness coverage, all transitive reads, mutation closure, independent
EVM agreement or economic results for the new intervention. Missing nodes report
subject, storage key, trie root and exact missing node hash. Missing code reports
contract and code hash. New-path coverage stays unknown until separately
admitted execution completes; never substitute recorded LP results.

Before native Dynamic Fee off, a separate versioned Go admission/spec, strict
two-write overlay, operation binding and result verifier are required. Keep the
accepted worker/policy unchanged. The first test plan must authenticate the
original root, derive the patched root itself, preserve signed input/environment,
run independent nil-Source worlds, and stop on any missing dependency. It needs a
new worker identity and founder's exact operation consent. Build16 does not
rebuild or run that worker. Distribution remains HOLD independently.
