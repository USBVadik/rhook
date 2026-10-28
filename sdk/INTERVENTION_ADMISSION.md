# Typed historical intervention admission candidate

`AuthenticatedCheckpointStateIntervention/0.1` is a proposed extension, not
qualification under unchanged Branch Semantics0.1. The original router profile
changes Message.Data; these historical adapters change checkpoint storage.
Read the [versioned proposal](../docs/protocol/authenticated-checkpoint-state-intervention-0.1-proposal.md)
and the existing [execution guide](HISTORICAL_EXECUTION.md).

The common pre-intervention anchor is r0. ACTUAL begins execution at r0;
BRANCH begins at Commit(T_I(s0)), derived from the authenticated original state
by one admitted initialization transform. Both then evolve independently under
the common reference semantics. The transform precedes arrival0 of the full
historical block, not only the selected purchase. Code, balances, nonces and all
non-authorized initial bits/state must be preserved.

## Read-only catalogue and sidecars

```sh
rhook-cases --home /absolute/private/home interventions
rhook-cases --home /absolute/private/home admission --plan PLAN_ID
rhook-cases --home /absolute/private/home assurance --plan PLAN_ID
```

The catalogue contains exactly `hookr-1.lp-bps/1` (integer0–99) and
`hookr-1.historical-dynamic-fee-off/1` (only OFF). Existing generation, pool,
layout, old-word, target and executor restrictions remain. Unknown profiles,
extra writes, invalid values or ambiguous identities fail closed. No module,
write script or provider is loaded from case data.

These commands need no runtime, consent, host admission, helper or EVM.
`admission` resolves declared metadata and validates the typed relation, but
does not authenticate MPT/code or prove actual application to a native world.
Its output explicitly remains authentication-pending. Use the separate
`authenticate`/operation/consent/replay workflow for those stages.

```python
catalogue = sdk.interventions()
descriptor = sdk.admission(plan_id)
knowledge = sdk.assurance(plan_id)  # UNRESOLVED without accepted evidence
```

The sidecar schemas are `rhook/checkpoint-state-admission/0.1` and
`rhook/checkpoint-state-assurance/0.1`. They are **not** BranchQuery0.2 or
BranchClaim, and do not rewrite existing plan/input/witness/overlay identities.
The descriptor separates meaning from capsule/package/witness/runtime artifact
bindings. Its artifact commitment is not a backend-independent semantic query.

## Evidence support is not a world outcome

Optionally supply one of the two exact retained private acceptance archives:

```sh
rhook-cases --home /absolute/private/home assurance --plan PLAN_ID \
  --evidence /absolute/private/accepted-archive
```

The source-pinned archive manifest and complete inventory must match, and the
accepted plan must match this exact question. Supplying a valid LP50 archive
for LP49 does not establish support for LP49. A complete wrong/tampered archive
is rejected as evidence; missing files remain unresolved. Neither becomes
REVERT, absence or zero. This is a closed two-reference consumer model, not an
attester registry or generic proof backend. It streams bounded files (at most
128MiB each/256MiB total) for artifact checks; these limits do not change the
native execution policies.

Each L1–L9 row names required evidence, existing enforcement, recorded support,
trust assumptions and remaining obligations. A subcheck may be ESTABLISHED at
its named scope; full Lawful remains UNRESOLVED, even when all pinned files
match. canonicality still needs an accepted anchor policy; faithful reference
execution, global initial confinement and local evolution still require stated
producer trust or stronger evidence. Recorded receipts/projections are not an
independent EVM or final-state transition proof. qualifiedClaims remains0 and
worldOutcomes is null in the knowledge report.

CLI exit0 for `admission` means only descriptor resolution. `assurance` exits2
for UNRESOLVED and1 for REJECTED. There is no exit0 complete-Lawful path in this
initial assurance model, and no JSON flag can enable one.

Historical OFF stays pinned to block93251803 and its exact witness/package.
The legacy LP record does not emit its branch execution-initial root; the model
does not manufacture that evidence. A completed witness applies only to its
executed plan, including trie updates. No generic contracts, code replacement,
new native execution, publication or external delivery follows from this API.
