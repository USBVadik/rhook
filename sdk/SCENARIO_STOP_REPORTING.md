# Supervised scenario STOP reporting

Scenario discovery, final nil-Source execution and one-world diagnostics share
`rhook_alpha.cases.scenario.outcome`. It interprets bounded saved records; it
does not change admission, execution limits, authority, cleanup actions or EVM.

A previously sticky supervisor limit remains primary. If the supervisor records
only a generic `SUPERVISION_FAILURE_*`, the original `HOST_RUNTIME/STOP.json`
cause (or worker-observer STOP) supplies the more precise primary reason. A
missing, invalid or wrong-operation native completion cannot replace that STOP.
Records from one fresh stage are used; there is no fabricated temporal ordering
between unrelated stages. Missing or unreadable evidence always fails closed.

For the retained Page05 resource interruption, the result reports:

- `causeCode: HOST_STOP: IMMEDIATE_FREE_RESERVE`
- `nativeCompletion: MISSING`
- `workerExit: {code: -9, signal: SIGKILL}`
- `processTermination: CONFIRMED`
- `engineBridgeClosure: UNKNOWN`
- `cleanupConfirmed: false`

Evidence paths and, for readable records, SHA-256 hashes point to original
records. Existing native completion stays on disk; it is not embedded wholesale
in an error result. A linked completion is required before bridge closure can
be confirmed. Reaping a process establishes termination, not normal engine
cleanup, completed worlds or successful transactions. ProduceBlock counts are
unknown without authenticated native accounting. Cleanup errors are separate
from the first execution failure and cannot turn a STOP into success.

The installed `scenario-close` command returns exit code1 for a STOP. Existing
success checks, one-shot operation closure and all resource policies remain in
force. This change requires fresh SDK code bindings for any future operation;
old closed proposals cannot authorize the changed code. No replay is implied
by installation, diagnosis or offline tests.

The page-on-miss tests authenticate a synthetic eight-key page, reject missing,
malformed and wrong-root proofs, exercise cancellation, and preserve independent
collector state. The separate Go Bridge fixture checks LP overlays and fresh
nil-Source reads without ProduceBlock. These tests are not a live page capture,
a complete swap, proof of the64RPC budget, or independent EVM agreement.
