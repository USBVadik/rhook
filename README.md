# RHOOK

RHOOK is an explainable deterministic counterfactual execution substrate for onchain state machines.

```text
ACTUAL          A -> B -> X  -> C  -> D  -> E
COUNTERFACTUAL  A -> B -> X′ -> C′ -> D′ -> E′
                              ^ regenerate downstream execution
```

Change one declared historical input, then execute the remaining envelopes in order against the state produced by the changed branch. RHOOK records enough evidence to explain the first lifecycle, state, and semantic divergence without rerunning the branch.

## Try it

Requires Node.js 22 or newer.

```bash
npm install
npm test
npm run quickstart
```

`quickstart` inspects the included transcript, verifies it offline, then changes a nested endpoint, recomputes the public commitment, and confirms that the malformed record is rejected.

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

Claim R is the incident-level claim that the exact answer requires sequential branch regeneration. Claim P is the broader claim that a reusable general-purpose system adds material value over the strongest bespoke substitute.

The Alchemix study supports Claim R for that specific question. It does not establish general superiority or Claim P. This repository's evidence stack is qualified separately on the protocol-neutral fixture in [`examples/minimal/transcript.json`](examples/minimal/transcript.json); it has not been scientifically rerun on Alchemix.

## Repository map

```text
core/       typed evidence and strict plain-JSON verification
runtime/    raw execution values -> typed evidence
host/       observational execution integration and transcript assembly
examples/   one minimal transcript and one historical case summary
docs/       model, architecture, threat boundary, limitations, provenance
scripts/    inspect, verify, and hostile-mutation commands
test/       standalone packaging and public API checks
```

Read [`QUICKSTART.md`](QUICKSTART.md), then [`docs/architecture.md`](docs/architecture.md) and [`docs/threat-model.md`](docs/threat-model.md).

## Status

Engineering conformance, not production certification. The current implementation is single-target, unauthenticated at the transcript layer, and not a liability, attribution, or recovery-policy system. See [`docs/limitations.md`](docs/limitations.md).

No software license has been granted yet. Distribution is through this Git repository; `private: true` intentionally disables npm publication.
