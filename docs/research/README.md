# Research results

These records describe bounded experiments and preserve their respective
scope. They trace native execution agreement through independently
implemented consumer verification and a bounded real-history application.

| Result | What was established |
|---|---|
| [Initial heterogeneous execution](robinhood-heterogeneous/README.md) | Go/Nitro/geth and Rust/arb-revm agreed on one frozen Robinhood case and its oriented Branch Protocol 0.2 claim. Selected public artifacts have an offline check. |
| [Prospective six-case conformance](robinhood-heterogeneous/prospective-conformance.md) | Two frozen native implementations agreed on six prospectively selected interventions: 1410/1410 checks and 90/90 required group evaluations. |
| [Clean-room verifier interoperability](clean-room-verifier-interoperability.md) | A fresh-context Python implementation written from the adopted specification matched qualified JavaScript Reference 0.3: 86/86 individually conformant observations, all exactly equal as raw JSON values. |
| [Real-history counterfactual application](real-history-counterfactual-application.md) | A verified portable Claim establishes `SUCCESS` → `REVERT` for subject `70397229:10` under one exact calldata intervention on Chain 4663, yielding `DOES_NOT_SURVIVE`. ACTUAL uses retained authenticated controls; fresh, previously authorized A/B BRANCH executions agree. |

The clean-room milestone reuses sealed native evidence from the execution
lineage. Its verifier comparison is a separate experiment. The public
summaries identify internal sealed records through hashes; they do not
distribute the complete research apparatus. See [limitations](../limitations.md).
