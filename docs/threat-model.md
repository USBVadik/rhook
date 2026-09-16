# Threat model

## Untrusted transcript producer

Assume the producer controls every JSON field and can recompute every public commitment after changing the record.

The verifier independently checks:

1. duplicate-key-safe JSON parsing;
2. exact object shapes and nested types;
3. canonical ordering and uniqueness;
4. envelope ranges and cross-references;
5. nested and transcript commitments;
6. lifecycle and presence/value consistency;
7. semantic-to-state bindings;
8. reported divergence locations.

A matching hash is necessary, not sufficient.

The included tamper test changes an endpoint to `not-an-address` and recomputes the transcript commitment. The verifier rejects it as malformed rather than reporting a hash mismatch.

## Execution instrumentation

Evidence collection must be observational. Enabling it must not change validation, transaction order, lifecycle, gas, logs, state, or semantic output.

The canonical qualification compared the predecessor execution projection with evidence disabled and enabled. All three were equal on the bounded fixture. That does not prove equivalence for every EVM program.

## Integrity is not authenticity

Offline verification establishes transcript internal validity and state-binding consistency; it does not independently prove that the claimed execution was produced by a trusted EVM run. The verifier also does not identify the producer. Signatures, attestations, and trust-root distribution are outside this repository.

## Out of scope

RHOOK does not currently provide:

- production certification;
- multi-target interventions;
- consensus-valid alternative-chain construction;
- legal or human attribution;
- recovery or allocation policy;
- a multi-agent contribution mechanism;
- proof that general-purpose replay is always better than specialized analysis.

See [`limitations.md`](limitations.md) for the full qualification boundary.
