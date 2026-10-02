# Heterogeneous historical counterfactual — claim agreement

For one frozen real 50-block historical counterfactual on Robinhood Chain,
two heterogeneous execution pipelines produced the same oriented
ACTUAL/BRANCH lifecycle result and identical Branch Protocol 0.2 claim.

The later [six-case prospective comparison](prospective-conformance.md)
passed 1410/1410 checks with a comparator frozen before execution. The
single-case result and its comparison limits below retain their original scope.

This publishes a completed research result. Producer A is the previously
qualified native Go/Nitro/geth execution. Producer B is a separately qualified
Rust/arb-revm execution. The comparison reused A's frozen observations; it
did not rerun native execution.

## Question and intervention

| Input | Frozen value |
|---|---|
| Chain | Robinhood Chain, 4663 |
| Initial checkpoint | 70397226 |
| Complete interval | 70397227–70397276; 50 blocks, 321 original arrivals |
| Pool | `0xb4619c2502932d4c10623f1862982b477536c2788648b2fda718aaf05c748523` |
| Intervention | 70397227:index3, `DERIVED_MESSAGE_DATA_ONLY`, applied once |
| Observed subject | 70397227:index4, `0x14ce0aadfca7435e2735ea5eeb5533766059079a72a700edb0221559e066bf4e` |
| Projection | Native envelope lifecycle, immediately after the selected envelope |
| Reference domain | All 50 blocks; observation does not shorten the execution domain |
| Parameters | Empty object |

The intervention replaces only native `Message.Data`, after deriving the
sender/message from the original signed envelope. The replacement is the
router call with empty commands and inputs, retaining the original deadline.
All other Message fields remain unchanged. `Message.Tx` retains the original
signed envelope for the declared Nitro poster-cost policy. Replacement Data
drives intrinsic gas and execution.

The altered calldata was not signed or broadcast by the historical sender.
The original transaction hash is retained for historical alignment; it is
not the hash of an alternative signed transaction. This is a **changed router
action**, not hook removal.

## Execution and comparison

The qualified native A control replayed the interval continuously from one
authenticated checkpoint, matching canonical per-block state roots, receipts
roots and reconstructed block hashes. Its changed branch continued on its own
state through the same historical arrival domain. The existing
[public native demo](../../../examples/robinhood-v4/README.md) reproduces that
experiment; its earlier [clean-checkout qualification](../../../examples/robinhood-v4/REPRODUCIBILITY.md)
is a separate retained result.

B's exact branch-capable source/binary first completed its own 50-block ACTUAL
qualification, then executed BRANCH over the same complete interval. B
reported 49/49 block-boundary and 271/271 within-block continuity checks,
one intervention, no canonical state resets and no witness additions.

B's results and claim were sealed before the comparison revealed the
pre-pinned A observations. A's same-profile claim was then constructed from
its own retained records without using B's values or claim hash as a target,
checked by existing Python and JavaScript encoders, and sealed before
comparison. B used its own Rust codec. No native run, rebuild or witness
acquisition occurred during this reveal/comparison step.

The coordinator had historical exposure. This is implementation diversity
with the stated reveal order, not a claim of fresh-blind authorship or
malicious-agent-proof isolation. The pipelines share the frozen history,
reference/query specification and sequential replay strategy.

| Selected result | Producer A | Producer B |
|---|---|---|
| ACTUAL | `SUCCESS` | `SUCCESS` |
| BRANCH | `REVERT` | `REVERT` |

All **34/34 exact comparison checks** passed: seven semantic bodies and their
component preimages, intervention/subject/projection/parameters, oriented
values, commitments, query/claim objects and canonical bytes. There was no
first divergence between the compared claim surfaces.

Shared domain-separated BranchClaim commitment:

```text
1cb8488e019b5550d32ea1169b6a7fac72af8f840314709672973661156c33f0
```

Canonical claim: **304 bytes**; raw-file SHA-256:

```text
ee8331c7e4116fd6fce0335519aae5a31b5a9c15f6dc3ab61458bab19c0bec51
```

These are different hashes: the protocol commitment hashes the domain/body
preimage; the raw-file digest hashes the canonical claim bytes alone.

## Descriptive downstream agreement

This comparison is additional descriptive evidence, outside the selected
claim's identity. Original envelope identities match 321/321; lifecycles
match 321/321 in each role.

| Lifecycle | ACTUAL, both pipelines | BRANCH, both pipelines |
|---|---:|---:|
| SUCCESS | 303 | 287 |
| REVERT | 18 | 21 |
| PRE_EXECUTION_INVALIDATED | 0 | 13 |

Both pipelines retain the same **16 downstream lifecycle changes**:
3 `SUCCESS -> REVERT` and 13 `SUCCESS -> PRE_EXECUTION_INVALIDATED`.
All 13 observed invalidations were classified by the native engine as core.ErrInsufficientFunds. They retain the
historical arrival, have no state/gas transition, and permit continuation.
Unknown failures are STOP conditions, not invalidations.

Both ACTUAL endpoint roots:

```text
0xd5b84a377ee7ed7b7bf04f88c98988ed0cb5fd0a4679670515a9bac2f0a90193
```

Both BRANCH endpoint roots:

```text
0x47601a8a2f7fb0e68778fab892470e7577169c1c2f041df95261f60abe5a5792
```

All 642 retained historical A evidence records passed the existing strict
verifier. This does not assert that B generated those same evidence records
or that evidence-format verification proves native execution.

## Fixed inputs and regenerated consequences

| Fixed | Regenerated against each role's own predecessor |
|---|---|
| Initial checkpoint; original signed arrivals and order | Validation and lifecycle |
| One committed Data replacement | Native execution, gas/accounting, results and logs |
| Declared historical header environment | Successor state and block finalization |
| Same subject, projection, parameters and codec | Selected lifecycle observation |

Later canonical state is never imported into the changed branch. Additional
state material must authenticate to the initial checkpoint or arise locally.
The frozen header parent context is external to the branch state; no synthetic
fork-header feedback is supplied. Nitro EVM `BLOCKHASH` uses each branch's
native ArbOS L1-history state, rather than a storage overwrite. The original
case observed no `BLOCKHASH` opcode query. This is conditional historical
execution, not a new consensus-valid Robinhood chain or a trader-response model.

## Published artifacts and verification

- [result.json](result.json): compact query definition, reported comparisons,
  output identities and provenance pins.
- [query.json](query.json) and [claim.json](claim.json): byte-exact canonical
  query and claim retained from the sealed A output and equal to B's bytes.
- [Branch Protocol 0.2](../../protocol/branch-protocol-0.2.md): unchanged wire
  and codec sections from the frozen candidate, with publication context.
- [Branch Semantics 0.1](../../protocol/branch-semantics-0.1.md): unchanged core
  requirements from the frozen design draft, with publication context.

From the repository root, using Node.js 22 or newer:

```bash
node docs/research/robinhood-heterogeneous/verify.mjs
```

This checks included raw-file pins, canonical wire bytes, six disclosed
component bodies, query/result/claim commitments and role orientation. The
large H component preimage is excluded: its commitment is retained in the
query. This command does not execute either pipeline, independently authenticate
H, recheck all 34 retained A/B comparisons, or validate excluded seals.

The existing `npm run demo:robinhood` remains the independently runnable native
A experiment. The experimental Rust runner, full witnesses, access logs and
raw A/B research archives are not distributed by this update. Consequently,
a clean checkout can check this compact publication and rerun A, but cannot
reproduce the full heterogeneous experiment from these files alone.

Pins for excluded artifacts are provenance attestations, not downloadable
artifacts, execution proofs or evidence of independent producer authorship.
The result manifest is case-local research metadata, not a new core schema.
The protocol documents are publication excerpts; original full-document hashes
are recorded separately from the public excerpt hashes. No package export,
existing evidence API, historical claim or earlier provenance file changes.

## Claim boundary

The supported result is agreement on this frozen lifecycle question under
the respective retained execution qualifications. It does not establish:

- generic Nitro conformance or arbitrary-intervention equivalence;
- full intermediate native accounting, state, trace, header or finalization
  conformance (the complete G3–G5 comparison was not performed here);
- universal causal correctness, economic attribution or LP payout;
- production safety or a consensus-valid alternative chain;
- cryptographic execution proof, product usefulness or general superiority.

The candidate commitment format can encode a false assertion. Hash consistency
is not proof of the lawful branch relationship. Native assurance comes from
the retained qualifications and their disclosed apparatus trust basis.
