# Source synchronization: historical execution and typed admission

This update publishes SDK source, tests and documentation. It does not publish
a native executable, runtime bundle, private witness, execution archive or grant.
An installed source-only CLI must report missing native components explicitly;
it must not substitute recorded results for execution.

## Three different milestones

| Milestone | What exists | What it does not establish |
| --- | --- | --- |
| Build18 | One accepted historical Go/Nitro Dynamic Fee ON/OFF pair: block 93251803, original parent 93251802, seven original arrivals and a signed 0.01 ETH subject at ordinal 3. ACTUAL matched canonical stateRoot/receiptsRoot/blockHash before independent BRANCH. | Independent Rust execution, full state-transition proof, finality, arbitrary-pool support or public access to the retained witness. |
| Build19 | Maintained historical `CaseSDK` API/CLI, operation review before separate exact owner consent, and separate recorded verify/compare. | Another native replay or permission to execute. |
| Build20 | Closed LP / historical Dynamic Fee OFF catalogue, typed admission descriptors and L1–L9 assurance sidecars. | Qualification under the unchanged Message.Data-only profile, a BranchClaim 0.2, or a complete Lawful proof. |

The historical Dynamic Fee intervention changes two initial storage words before
arrival 0: Rules maxFeePips 11500→3000 and sensitivity 2→0, Root mode 3→2.
LP100 and arb recapture remain enabled. Original signed inputs and arrival order
are retained. This is a whole-block checkpoint intervention, not an edit of the
selected transaction or an onchain administrative call.

In the accepted pair both subjects succeeded. Token Transfer-event net increased
by 0.0059433933201%; outer Swap fee changed 11048→11000 pips; subject gas changed
1483206→1409955. These are retained observations, not a new run by this source
export, a profit forecast or independent proof of final token-storage balance.
The complete private evidence is not distributed here.

Separate earlier Robinhood experiments have heterogeneous Go/Nitro and
Rust/arb-revm research results; see the [research index](../docs/research/README.md).
Those results do not transfer to Hookr LP or Dynamic Fee OFF. For these Hookr
profiles economic assurance remains unresolved and qualified Claims remain 0.
The [admission candidate](INTERVENTION_ADMISSION.md) keeps full Lawful unresolved,
even when matching retained records support a named subcheck.

## Public entry points

- [Case capsules and planning](CASE_CAPSULES.md): import a local capsule and select
  a supported adapter; declarations/checksums alone are not MPT authentication.
- [Historical execution](HISTORICAL_EXECUTION.md): ACTUAL gate, independent
  BRANCH, exact operation review, separate consent and existing resource guards.
- [Prepared hypothetical scenarios](DEVELOPER_EXECUTION.md): a distinct domain
  with explicitly modeled funding and action; not a canonical historical buy.
- [Typed intervention admission](INTERVENTION_ADMISSION.md): read-only catalogue,
  admission and assurance; no arbitrary storage-write API or automatic execution.

The legacy fixed Alpha installer and `rhook_alpha.API` retain their older
source/runtime binding. New `install_cases.py` and `CaseSDK` do not silently
register that old worker as a current derivative. A later local installed
[on-demand scenario acceptance](SCENARIOS.md#installed-on-demand-acceptance)
completed discovery and fresh offline pairs at one new checkpoint. That result
uses the supported scenario path and retained private runtime; it does not
qualify every exported profile or supply an externally reproducible runtime.

## Run source-only checks

Python 3.12+ without optimization:

```sh
python3 -B sdk/tools/test_offline.py
```

The full SDK JavaScript checks use Node 24+ and the existing adapter lockfile:

```sh
npm ci --ignore-scripts --no-audit --no-fund --prefix sdk/engine/adapters/hookr-case
npm run test:sdk-cases
```

These checks use synthetic data, local mock transports and bounded benign
process fixtures. They do not start Go/Nitro, query a live provider or establish
new scientific results. Root protocol checks continue to support Node 22+.

Private-fixture tests are explicitly optional: `RHOOK_RECORDED_TEST_BUNDLE`
selects separately approved Build10/11 records, and
`RHOOK_HISTORICAL_TEST_PACKAGE` selects the exact retained historical input.
Without these assets their named tests skip; public CI must not acquire or
embed them to turn a skip into a pass. Unconditional boundary/configuration
tests run without either asset. Synthetic witness bytes are never represented
as authenticated state or completed native execution.

The worker-free Build10/11 recorded consumer retains its production descriptor
pin and API. Its evidence bundle and packaging example are not part of this
source synchronization. Supplying a missing or altered bundle fails explicitly.
Opening or checking recorded data grants no execution authority.

## Provenance and distribution

The original private milestone identities remain:

- Build18: `b37e697868d08e0a01bcfadb21d49a8f372bf546`.
- Build19: `baa2ef4cc1bf1c0eb9aff49c9c7910ffdbb7d2f2`.
- Build20: `9c4e880d4d141e73a2749382344df15ef0cd5afd`.

They are provenance references, not parents imported into public Git history.
The integration starts from public `ff7c881c89fe5c92fb77341fdccc0e80c000c616`
and gets its own commit identity. Accepted scientific archives, workers, plans
and original protocol documents are not rewritten. `case-source.json` inventories
the additional public files; `source-provenance.json` retains the original
218-file Alpha import and its publication adaptations.

The selective export excludes internal plans, private recorded JSON and preview
packaging. It includes source profiles and hashes needed to identify supported
cases; those metadata do not include witness preimages, private runtime files,
authority, telemetry or provider credentials. Legacy public research fixtures
remain unchanged and retain their existing notices and scope.

Original RHOOK code uses Apache-2.0 within [LICENSE_SCOPE](LICENSE_SCOPE.md).
Upstream Nitro/geth, Hookr SDK, viem and other dependencies retain their own terms;
see [third-party notices](../THIRD_PARTY_NOTICES.md). Source availability does not
clear a combined executable or private historical data for redistribution.
