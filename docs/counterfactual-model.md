# Counterfactual model

RHOOK answers a bounded question:

> Starting from a pinned checkpoint, what happens to an ordered envelope domain when one declared input changes?

## Fixed

- parent checkpoint and state commitment;
- start and terminal boundaries;
- one intervention target and replacement;
- canonical envelope identities and order;
- envelope fields not changed by the intervention;
- block-context policy;
- semantic endpoint and lookup source;
- evidence schema and verifier version.

## Regenerated

For each downstream envelope:

- pre-execution validity;
- success, revert, or invalidation;
- exception classification;
- gas and fee result;
- logs and execution-result commitments;
- successor state;
- admissibility of later envelopes;
- semantic observation at the declared endpoint.

## State propagation

Historical execution applies each transition to the state produced by the previous transition:

```text
S_(i+1) = execute(S_i, T_i)
```

After `X -> X′`, the changed branch is:

```text
S′_(i+1) = execute(S′_i, T_i)
```

RHOOK does not subtract a historical effect from the final state. It computes the replacement transition and propagates the resulting state forward.

## Analysis branch, not alternative consensus

The counterfactual branch follows an explicit historical-envelope policy. It is not asserted to be a consensus-valid Ethereum block or chain.
