# One real Robinhood v4 counterfactual

What changes if one historical router action is replaced, while later signed
inputs and the historical block environment stay fixed?

This example replays **Robinhood Chain 4663, blocks 70397227–70397276**, from
parent 70397226: one ETH/SHIB v4 pool, 50 continuous blocks, 321 envelopes and
one declared intervention. The window spans approximately five seconds.

## Run

Requires Node.js 22+ and Docker with Buildx and a Linux arm64 execution environment. The
container builds the pinned native Nitro runner from public source; it does not
use a prebuilt research binary. Network is needed for the first build. Replay
runs with Docker `--network none` and needs no RPC, credentials or downloaded
intermediate state.

From the repository root:

```bash
npm ci
npm run demo:robinhood
```

The first run compiles Go and Rust dependencies. Later builds can reuse Docker
layers. Results and all generated-file SHA-256 hashes are written beneath the
printed `.rhook/robinhood-<timestamp>/` path. The existing `npm run quickstart`
remains the small synthetic example and requires no Docker.

Only Linux arm64 is the qualification target. Native Linux amd64 and native
macOS/Windows builds are not claimed supported. Resource measurements and the
clean-environment result are recorded in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## What exactly changes

X is block **70397227, transaction index 3**:
`0x5f82e30b8ad8ae0bd4e5b60cbde55a47702d2d4b90234ad0db58bd9b89a458db`.
Its `UniversalRouter.execute(commands, inputs, deadline)` execution message is
replaced with `execute(empty commands, empty inputs, same deadline)`.

**The historical transaction is not re-signed.** This is an analytical
intervention at the native execution-message boundary. The historical envelope
identity is retained for alignment; replacement calldata is separately committed
and is not claimed to have been signed or broadcast by the historical sender
under the same transaction hash.

Only native `Message.Data` changes after native sender derivation.
`Message.Tx` remains the original signed envelope for Nitro poster-cost
accounting. Native intrinsic/floor calldata gas and EVM execution use the
replacement Data. Sender, nonce, destination, zero value, gas limit, fee inputs,
access lists, authorizations and other Message fields are preserved. This is
not described as simply removing a transaction.

The terminal prints both calldata digests and the preserved-field list.
`work/results/intervention-commitment.json` contains all before/after fields and
the original qualified commitment:
`52d56c3538dd4b1f959359bc63f8c0de4635d1b574336193fc846a2d35601bba`.

## Fixed versus regenerated

| Fixed | Regenerated against each branch's own predecessor |
|---|---|
| Authenticated initial checkpoint | Native transaction validation |
| Historical envelope identities and order | SUCCESS / REVERT / PRE_EXECUTION_INVALIDATED |
| Downstream signed transaction inputs | Gas and native fee/accounting results |
| Declared Message.Data intervention | Return/revert data and logs |
| Historical block-context policy | Successor state and subsequent block state |
| Endpoint and semantic query | Endpoint pool fee-growth values |

Each session loads initial state once, then propagates locally computed state
across 49 block boundaries. No canonical intermediate state is imported.

The L2 number, timestamp, coinbase, base fee, gas limit, parent hash and native
randomness inputs stay historical. Native L2 GetHash uses canonical headers;
Nitro's BLOCKHASH opcode uses its unchanged ArbOS L1 history. All 50 internal
0x6a envelopes and native finalization run on branch state. The full L1 history
is checked equal to control; no BLOCKHASH opcode query occurs in this case.
Counterfactual header/hash outputs are deliberately null. This is **conditional
historical execution**, not a new consensus-valid Robinhood fork.

## Frozen result to reproduce

PoolManager: `0x8366a39cc670b4001a1121b8f6a443a643e40951`.
Pool ID: `0xb4619c2502932d4c10623f1862982b477536c2788648b2fda718aaf05c748523`.
Currency0 is native ETH. Currency1 is
`0xd136b862ebbb1bd362a637ed67b7b0efe1052e7f` (SHIB display symbol).

| Lifecycle | ACTUAL | COUNTERFACTUAL |
|---|---:|---:|
| SUCCESS | 303 | 287 |
| REVERT | 18 | 21 |
| PRE_EXECUTION_INVALIDATED | 0 | 13 |

State diverges at 70397227:3; the first lifecycle change is SUCCESS → REVERT
at 70397227:4. Divergence crosses 70397227 → 70397228 and reaches the endpoint.
All 13 invalidations are native insufficient-gas-funds failures before EVM
execution, with unchanged state and gas accounting. Replay continues after each;
unknown native errors stop the run. All actual/counterfactual records must pass
the existing strict verifier: **321 + 321**.

| Exact raw X128 fee growth | ACTUAL | COUNTERFACTUAL |
|---|---:|---:|
| Currency0 | 117405592307991752542647857526 | 345006148638713097624462876 |
| Currency1 | 32700633101007239109545731257336627650 | 20880764066545906648862117208042138011 |

Y is **pool-level accrued fee growth per active liquidity unit**:
`(feeGrowthGlobaliX128(endpoint) - feeGrowthGlobaliX128(initial)) mod 2^256`.
The terminal prints exact signed `Y_actual - Y_counterfactual` separately for
each currency. Semantic reads are bound to their respective local endpoint roots.
No canonical RPC proof is claimed for the counterfactual endpoint.

## Evidence and limits

The published [native sources](native/) provide bounded block orchestration over
unmodified pinned Nitro/geth execution. [run-host.mjs](scripts/run-host.mjs)
supplies a public `runBlock` adapter to unchanged `executeInstrumentedBlock` for
ACTUAL. The continuing counterfactual uses existing runtime builders for executed
and invalidated envelopes: the current host block bundle cannot express a
missing receipt while continuing. Session/intervention commitments are case-local
sidecars, not a new generic RHOOK schema.

The checker compares every full native block output with frozen digests and all
642 serialized envelope records byte-for-byte. Native control, evidence OFF and
ON must agree. Canonical roots, receipts roots and reconstructed ACTUAL block
hashes are also compared with the pinned historical references.

The engine, adapter and input acquisition remain trusted apparatus. Evidence
verification establishes internal consistency, not an independent proof of EVM
execution or producer identity. The checkpoint is authenticated state relative
to a pinned root; that root's canonicality/L1 finality is not independently proven.
Witness reads verify native trie/code hashes and fail closed on missing material.

This single short window does not establish adaptive trader behavior, general
Nitro compatibility, position-level collected fees, LP payout/profit/PnL, Hookr
value, or causal attribution. No Hookr-specific association is established for
this pool. The historical Alchemix claims and their provenance are unchanged.

## Contents and fast checks

- `case-data.json.gz`: one initial witness, sanitized execution inputs,
  historical context headers and the original case/intervention manifests.
- `reference.json.gz`: frozen block-output digests, exact outcomes, all 642
  strict records and the 13 invalidation records. Never used as native state.
- `case-integrity.json`: archive and expanded-file SHA-256 pins.
- `dependencies.json`, native Go locks and tooling npm lock: build source pins.
- `Dockerfile`: source bootstrap, build and separate offline execution image.

`npm run test:robinhood` verifies frozen artifacts, evidence and rejection of
changed inputs/results quickly; it does **not** replay Nitro. Full replay stays
an explicit command, outside default CI.

RHOOK-authored code is licensed under [Apache-2.0](../../LICENSE), with explicit
[third-party boundaries](../../THIRD_PARTY_NOTICES.md). The derived geth block
orchestration remains LGPL-3.0-or-later. Pinned Nitro and precompile dependencies
retain **Business Source License 1.1**, not the root Apache-2.0 license. This is
an offline analysis demo, not a general production-use grant for the native
stack. Source URLs and locked versions are in [dependencies.json](dependencies.json);
upstream license texts are retained in [notices](notices).
