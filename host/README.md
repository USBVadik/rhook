# Host

Host connects a compatible execution engine to runtime evidence collection and branch transcript assembly.

Public entry point: [`src/index.mjs`](src/index.mjs)

`executeInstrumentedBlock()` requires an explicit `runBlock` function. The public package does not vendor the private historical runner. With evidence enabled, host observes `beforeTx` and `afterTx`; with evidence disabled, it attaches no listeners.

A thrown runner error is not automatically a pre-execution invalidation. An adapter may provide `classifyPreExecutionFailure`, which must return either `null` or exactly `{ kind: 'PRE_EXECUTION_VALIDATION', classification }`. Host attaches `PRE_EXECUTION_INVALIDATED` evidence only when one `beforeTx` has no matching `afterTx` and the current state root equals that envelope's predecessor root both before and after classification. Unknown failures, classifier failures, partial state mutation, and non-extensible errors are rethrown without an evidence sidecar.

Host does not implement transaction semantics or duplicate core verification rules.

`verifyIntegrationEvidenceBundle()` requires exact actual/counterfactual projection shapes and one ordered native state-root binding per covered envelope. It cross-binds projection identities and execution commitments to the strict core transcript, checks changed-envelope lifecycle/accounting correspondence, verifies native boundary commitments and branch continuity, and only then recomputes execution and integration commitments.

The projection's `finalStateRoot` and `receiptsRoot` are canonical post-block values covered by the execution commitment. They are not independently derived from the compact transcript, and `finalStateRoot` is not equated to the last `afterTx` successor because block finalization may occur after that event boundary.

The frozen qualification's execution and hostile-producer checks are summarized in [`../docs/reproducibility/provenance.md`](../docs/reproducibility/provenance.md).
