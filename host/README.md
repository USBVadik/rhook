# Host

Host connects a compatible execution engine to runtime evidence collection and branch transcript assembly.

Public entry point: [`src/index.mjs`](src/index.mjs)

`executeInstrumentedBlock()` requires an explicit `runBlock` function. The public package does not vendor the private historical runner. With evidence enabled, host observes `beforeTx` and `afterTx`; with evidence disabled, it attaches no listeners.

Host does not implement transaction semantics or duplicate core verification rules.

The frozen qualification's execution and hostile-producer checks are summarized in [`../docs/reproducibility/provenance.md`](../docs/reproducibility/provenance.md).
