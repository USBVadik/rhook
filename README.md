# RHOOK

[![CI](https://github.com/USBVadik/rhook/actions/workflows/ci.yml/badge.svg)](https://github.com/USBVadik/rhook/actions/workflows/ci.yml)

RHOOK is an explainable deterministic counterfactual execution substrate for onchain state machines.

**[Hookr Pair03: a real pool replay](docs/research/hookr-pair03.md).** Seven arrivals,
canonical ACTUAL, `RulesConfig.lpBps: 100 → 0`, and **1.0088% more RHOOK** for the
selected buyer. One Go/Nitro case; independent Rust replay is pending.

```text
ACTUAL          A -> B -> X  -> C  -> D  -> E
COUNTERFACTUAL  A -> B -> X′ -> C′ -> D′ -> E′
                              ^ regenerate downstream execution
```

Change one declared historical input and execute the remaining envelopes in
order against the changed state. Inspect the resulting lifecycle, state and
semantic differences.

| Fixed inputs | Regenerated outputs |
|---|---|
| Parent checkpoint, history and arrival order | Successor state, validity and execution results |
| Declared intervention and block-context policy | Gas, fees, logs and state-bound semantic values |

## Try it

Requires Node.js 22 or newer.

```bash
npm ci
npm test
npm run quickstart
```

The quickstart runs the [protocol-neutral fixture](examples/minimal/transcript.json)
through host, runtime and core,
writes a transcript under ignored `.rhook/`, verifies it in a separate process,
and checks that a malformed semantic endpoint is rejected.
See [QUICKSTART.md](QUICKSTART.md) for the commands and expected output.

## Hookr Pair03

The [case study](docs/research/hookr-pair03.md) and
[static visual](docs/research/hookr-pair03/index.html) describe saved block
93251803. ACTUAL matched its canonical state root, receipts root and block hash.
The alternative changed the LP Rewards parameter, preserving base/dynamic fees
and recapture. The visual displays recorded results; opening it does not replay
the block. Its files can be opened locally after downloading the repository.

[SDK Alpha v2's local workflow](docs/research/sdk-alpha-v2-status.md) passed for
this saved case on one Mac. Alpha sources and binaries remain private. Official
Hookr SDK integration is the next development milestone; ABI compatibility is
confirmed, but the TypeScript adapter is not implemented.

## Native example and research

With Docker, `npm run demo:robinhood` builds a pinned Nitro runner and replays a
50-block Robinhood Chain v4 example. Its analytical intervention replaces native
`Message.Data` while retaining the historical signed envelope. See the
[example](examples/robinhood-v4/README.md) for inputs, accounting and limits.
This command does not run the private Hookr Alpha case.

Earlier public demo: [recorded Robinhood counterfactual](https://robinhook.tech/counterfactual).
It displays a separate case; viewing it performs no replay.

Separate Go/Nitro/geth and Rust/arb-revm experiments agreed on six prospectively
selected cases, with 1410/1410 checks. Those cases have their own frozen profiles;
they do not supply Rust qualification for Hookr Pair03. The
[research index](docs/research/README.md) links those results, the clean-room
verifier comparison and the later developer-workflow pilots.

The [Alchemix study](examples/alchemix/README.md) is a separate historical result.
The protocol-neutral evidence stack has not been scientifically rerun on Alchemix.

## Verification boundary

The verifier checks nested types, ordering, cross-references and divergence claims
rather than accepting matching hashes alone. The current public implementation
is single-target and unauthenticated at the transcript layer. Engineering
conformance does not establish production certification, universal backend
neutrality, canonical finality or cryptographic execution proof.

Read the [counterfactual model](docs/counterfactual-model.md),
[architecture](docs/architecture.md), [threat model](docs/threat-model.md) and
[limitations](docs/limitations.md) for the full boundary.

## Repository map

```text
core/       typed evidence and strict plain-JSON verification
runtime/    raw execution values -> typed evidence
host/       observational execution integration and transcript assembly
examples/   fixtures and the explicit real-chain demo
docs/       protocol, architecture, limitations and research records
scripts/    inspect, verify and tamper-check commands
```

RHOOK-authored code and documentation are licensed under [Apache-2.0](LICENSE).
[Third-party boundaries](THIRD_PARTY_NOTICES.md) remain separate, including the
LGPL-derived adapter and the native demo's Business Source License 1.1 Nitro
dependencies. Distribution is through this Git repository; `private: true`
intentionally disables npm publication.
