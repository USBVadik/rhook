# RHOOK

[![CI](https://github.com/USBVadik/rhook/actions/workflows/ci.yml/badge.svg)](https://github.com/USBVadik/rhook/actions/workflows/ci.yml)

RHOOK is an explainable deterministic counterfactual execution substrate for onchain state machines.

```text
ACTUAL          A -> B -> X  -> C  -> D  -> E
COUNTERFACTUAL  A -> B -> X′ -> C′ -> D′ -> E′
                              ^ regenerate downstream execution
```

Change one declared historical input, then execute the remaining envelopes in order against the state produced by the changed branch. RHOOK records enough evidence to explain the first lifecycle, state, and semantic divergence without rerunning the branch.

## What stays fixed and what regenerates

| Fixed inputs | Regenerated outputs |
|---|---|
| Parent checkpoint and historical domain | Envelope validity |
| One declared intervention | `SUCCESS`, `REVERT`, or pre-execution invalidation |
| Canonical envelope identities and order | Gas, fees, logs, and execution-result commitments |
| Historical block-context policy | Successor state commitments |
| Evaluation endpoint and semantic query | State-bound semantic value |

See [`docs/counterfactual-model.md`](docs/counterfactual-model.md) for the exact boundary.

## Try it

Requires Node.js 22 or newer.

```bash
npm ci
npm test
npm run quickstart
```

`quickstart` executes both sides of the protocol-neutral branch fixture through the public host/runtime/core stack, writes a fresh transcript under the ignored `.rhook/` directory, verifies it in a separate process, then changes a nested endpoint, recomputes the public commitment, and confirms that the malformed record is rejected.

## Real-chain example

With Docker, `npm run demo:robinhood` builds a pinned native Nitro runner and
replays one Robinhood Chain v4 counterfactual over 50 continuous blocks.
The analytical intervention changes native `Message.Data` while retaining the
historical signed envelope for alignment and declared poster-cost accounting;
it is not a re-signed transaction. See [the example](examples/robinhood-v4/README.md)
for the exact fee-growth metric, fixed inputs, limits and reproduction status.

## Heterogeneous execution result

Two frozen native implementations, Go/Nitro/geth and Rust/arb-revm,
independently executed six prospectively selected historical interventions
on Robinhood Chain 4663 and derived identical oriented Branch Protocol 0.2
claims. The comparator was frozen before execution and run once after both
implementations sealed all six cases. It passed 1410/1410 checks across
90 required comparison group evaluations.

This result is limited to exact v011, the two tested implementations, the
six interventions and the 50-block / 321-arrival domain per case. It does not
establish universal backend neutrality or production readiness.

The [prospective report](docs/research/robinhood-heterogeneous/prospective-conformance.md)
records the procedure, compared surfaces and commitments. The
[earlier single-case result](docs/research/robinhood-heterogeneous/README.md)
and its offline artifact check remain available. The experimental Rust
runner and full execution archives are not distributed here.

## Clean-room verifier interoperability

A fresh-context implementer received the adopted 14-document verifier
specification and selected evidence data without access to the qualified
Reference 0.3 source, outputs, expected verdicts or prior findings. Before
writing source, it completed a separate failure-boundary audit and judged
the packet self-sufficient for the bounded task. It independently wrote a
Python standard-library verifier and sealed its final outputs before the
qualified JavaScript Reference 0.3 was invoked.

All 86 compared rows, covering 12 positive packages and 74 hostile/parser
inputs, were individually conformant and exactly equal as raw JSON values.
No diagnostic normalization or permitted diagnostic variance was required.

This completes the bounded internal clean-room verifier milestone. It does
not establish external organizational independence, production readiness,
universal verifier correctness, arbitrary-chain/intervention correctness or
cryptographic execution proof. See the
[report](docs/research/clean-room-verifier-interoperability.md),
[machine-readable result](docs/research/clean-room-verifier-interoperability-result.json)
and [research index](docs/research/README.md).

## Why replay instead of dependency analysis?

Dependency analysis can identify which transitions may depend on `X`. It cannot determine whether a downstream transaction succeeds, reverts, becomes invalid, or produces a different state. RHOOK computes those transitions.

## Evidence per envelope

- canonical envelope identity;
- predecessor and successor state commitments;
- validation and `SUCCESS / REVERT / PRE_EXECUTION_INVALIDATED` lifecycle;
- exception classification, gas, fees, logs, and execution-result commitments;
- semantic values bound to the exact successor state from which they were read.

The verifier treats the transcript producer as untrusted. Matching hashes are not enough; nested types, ordering, cross-references, presence/value rules, and divergence claims are checked independently.

## Pinned historical result

A separate frozen Alchemix study regenerated 36,847 historical transactions after replacing one declared call:

| Result | Count |
|---|---:|
| Historical-control divergences | 0 |
| Downstream `SUCCESS -> REVERT` changes | 93 |
| Pre-execution invalidations | 3 |

The Alchemix result supports sequential branch regeneration for that incident-level question. It does not establish general superiority over bespoke simulators. This repository's evidence stack is qualified separately on the protocol-neutral fixture in [`examples/minimal/transcript.json`](examples/minimal/transcript.json); it has not been scientifically rerun on Alchemix.

## Repository map

```text
core/       typed evidence and strict plain-JSON verification
runtime/    raw execution values -> typed evidence
host/       observational execution integration and transcript assembly
examples/   minimal demo, historical summary, explicit real-chain demo
docs/       model, architecture, threat boundary, limitations, provenance
scripts/    inspect, verify, and hostile-mutation commands
test/       standalone packaging and public API checks
```

Read [`QUICKSTART.md`](QUICKSTART.md), then [`docs/architecture.md`](docs/architecture.md) and [`docs/threat-model.md`](docs/threat-model.md).

## Status

Bounded prospective heterogeneous native validation is complete for the
[six-case Robinhood suite](docs/research/robinhood-heterogeneous/prospective-conformance.md).
The bounded internal specification self-sufficiency and clean-room verifier
interoperability milestone is also complete, with
[86/86 conformant, exactly matching observations](docs/research/clean-room-verifier-interoperability.md).

Engineering conformance, not production certification. The current implementation is single-target, unauthenticated at the transcript layer, and not a liability, attribution, or recovery-policy system. See [`docs/limitations.md`](docs/limitations.md).

RHOOK-authored code and documentation are licensed under [Apache-2.0](LICENSE).
[Third-party boundaries](THIRD_PARTY_NOTICES.md) remain separate, including the
LGPL-derived adapter and the native demo's Business Source License 1.1 Nitro
dependencies. Distribution is through this Git repository; `private: true`
intentionally disables npm publication.
