# Evidence model

## Envelope evidence

Each envelope record contains:

| Field | Purpose |
|---|---|
| identity | block number, transaction index, transaction hash |
| predecessor commitment | state consumed by execution |
| validation | valid or explicitly classified invalid |
| lifecycle | `SUCCESS`, `REVERT`, or `PRE_EXECUTION_INVALIDATED` |
| exception | none, revert, or validation classification |
| gas and fee | gas limit, gas used, fee paid |
| logs commitment | ordered execution logs |
| result commitment | normalized execution result |
| successor commitment | state produced by execution |
| semantic references | ordered commitments when present |

Impossible combinations fail. An invalidated envelope cannot consume gas or change state. A revert must carry a revert classification.

## Semantic evidence

A semantic value carries its endpoint, source descriptor, record identity, presence state, canonical value, and exact successor-state commitment.

`PRESENT`, `VALID_ABSENT`, and `NOT_COMPUTED` are separate states. Present zero, empty code, missing storage, and absence are not interchangeable.

## Compact transcript

Changed envelopes retain full evidence for both branches. Unchanged envelopes may retain compact receipt and post-state commitments. Full EVM state is intentionally excluded.

The verifier derives the first lifecycle, state, and semantic divergence independently. See [`examples/minimal/README.md`](../examples/minimal/README.md) for the included fixture.

## Integration bundle

The optional host integration bundle retains the two exact replay projections and native predecessor/successor roots that produced the core transcript. Its verifier requires complete actual/counterfactual projection schemas, contiguous per-envelope root bindings, canonical identities, branch commitments, changed-envelope lifecycle/accounting correspondence, and native-root commitments bound to the matching core evidence before accepting self-commitments.

Post-block `receiptsRoot` and `finalStateRoot` remain execution-committed projection values, not independently reconstructed claims. The compact transcript binds `afterTx` successor states; it does not claim that the last one equals a post-finalization block root.

## Internal validity

The producer is untrusted and may recompute every public commitment. Verification therefore checks nested structure and semantics before accepting a record. [`scripts/tamper-transcript.mjs`](../scripts/tamper-transcript.mjs) demonstrates the difference between internal validity and a simple hash check.
