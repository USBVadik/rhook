# Prospective dual-producer conformance

Two heterogeneous frozen native implementations independently executed the
same six prospectively selected interventions and derived identical oriented
Branch Protocol 0.2 claims. The six cases were fixed before scientific
execution, while their outcomes were unknown. Results remained sealed until
both implementations completed all six cases. The previously frozen
comparator was then run once and passed 1410/1410 checks across 90 required
comparison group evaluations.

Result: `PROSPECTIVE_DUAL_PRODUCER_SIX_CASE_CONFORMANCE_PASS_V011`.

## Setup and procedure

| Parameter | Frozen value |
|---|---|
| Network | Robinhood Chain 4663 |
| Initial checkpoint | Block 70397226 |
| Execution domain per case | Blocks 70397227–70397276; 50 blocks, 321 arrivals |
| Initial authenticated state material | Exact v011 |
| Implementations | Native Go/Nitro/geth; Rust/arb-revm |
| Intervention | One `DERIVED_MESSAGE_DATA_ONLY` replacement with `0x` |
| Subject | First later ordinary original arrival |
| Projection | Native envelope lifecycle after the selected subject |
| Protocol | Frozen Branch Protocol 0.2 semantics |

Selection used the previously declared structural eligibility predicate:
ordinary transaction type, a recipient, nonempty original calldata and a
later ordinary subject. Previously used intervention targets were excluded.
Eligible records were sorted by numeric block number, numeric transaction
index and lowercase transaction hash; the first six remaining records were
selected. No outcome or coverage score was used.

The complete suite, profiles, canonical Queries and commitments were frozen
before admission. The retained suite was reused byte for byte, without
reselection, regeneration, reordering or replacement.

Both implementations admitted the complete suite before execution. Each
then executed CASE_01 through CASE_06 once, independently using its own
native observations and qualified ACTUAL control. Every case started from
the authenticated checkpoint and continued on branch-local successor state
through all 50 blocks, with zero canonical intermediate resets. Each case
was sealed on completion. Comparison began after both six-case producer
outputs were sealed.

The intervention replaces only derived `Message.Data`, after original sender
and message derivation, before native validation and execution. All other
message fields remain fixed. The original signed envelope is retained for
historical alignment and declared poster-cost accounting; replacement Data
drives intrinsic gas and execution. No alternative transaction was signed
or broadcast. This is an analytical input replacement, not hook or rule removal.

## Compared surfaces and result

All 15 predeclared comparison groups were required for every case. They
covered input and intervention identity; ordered lifecycle vectors and all
arrival pre/post state roots; receipts, logs, status and bloom; return/revert
bytes; gas, cumulative gas and L1 gas; effective prices and fees; block state
and receipt roots; branch continuity; L1 history and `BLOCKHASH` observations
under the frozen policy; ACTUAL and BRANCH projections; canonical Query
bytes and identity; oriented result commitments; and canonical BranchClaim
bytes and commitment.

| Measure | Producer A | Producer B |
|---|---:|---:|
| Cases admitted | 6/6 | 6/6 |
| Scientific cases completed and sealed | 6/6 | 6/6 |
| Blocks executed | 300 | 300 |
| Arrival observations | 1926 | 1926 |

All targets and subjects below are in block 70397229. Transaction indices
are zero based; full hashes and Query/claim identities are in
[prospective-result.json](prospective-result.json).

| Case | Target index | Subject index | Checks passed |
|---|---:|---:|---:|
| CASE_01 | 3 | 4 | 235/235 |
| CASE_02 | 4 | 5 | 235/235 |
| CASE_03 | 5 | 6 | 235/235 |
| CASE_04 | 6 | 7 | 235/235 |
| CASE_05 | 7 | 8 | 235/235 |
| CASE_06 | 8 | 9 | 235/235 |

The total was 1410/1410 checks and 90/90 required group evaluations.
Canonical BranchClaim bytes and commitments agreed between A and B in
every case. The selected ACTUAL and BRANCH projections were `SUCCESS` in
all six cases. Matching selected outcomes alone was insufficient for PASS:
all required execution and accounting surfaces also had to agree.

Relative to each implementation's own ACTUAL control, CASE_02 changed one
arrival lifecycle and CASE_03 changed two. The other four cases preserved
the full lifecycle vector. All six branch endpoint roots differed from
their ACTUAL endpoints. Both implementations agreed on these observations.

Retries, case replacements, binary rebuilds, post-selection apparatus
changes, post-execution repairs, witness expansions, comparator changes,
normalization changes and suite modifications/regenerations/reorders were
all zero.

## Scope

This result is limited to Robinhood Chain 4663, exact v011, the two tested
implementations, the six selected interventions, the declared 50-block /
321-arrival domain and frozen Branch Protocol 0.2 semantics. It does not
establish universal backend neutrality, arbitrary-intervention support,
equivalence across all Nitro versions, production readiness, a
consensus-valid alternative chain, cryptographic proof of execution,
economic causality or attribution, or independent third-party adoption.
Implementation diversity does not establish independent authorship.

The [earlier single-case publication](README.md) and its limits remain
separate. Evidence-format verification is not native execution proof.

## Reproducibility identifiers

| Identity | Value |
|---|---|
| Suite manifest SHA256 | `8c0cc5dc91b1a0ca364c77556b54e7dc47281595384f18ffbadca05713e9a7df` |
| Suite freeze SHA256 | `fcb833bfce972da55488c2e97e027790954f306d16508d0b9c71b0a65ff47989` |
| Suite commitment | `120ffb9914f435585f1260b40b55ebef99b490bb280d6b65175259e82f3170f4` |
| Comparator SHA256 | `a616729b8cab2c50914f19fd3bd7ec0323ae7b2f4bf95932110fedcb8b715712` |
| Normalization SHA256 | `b268c0c409dac6e7934732eea0845b2890e91e26bc5774fe408e02a27829c0f1` |

The compact JSON record includes these identifiers, the exact v011 store
and producer binary hashes, final counters, and each case's Query and claim.
Raw-file SHA256 pins are distinct from domain-separated protocol commitments.

The full suite preimages, native binaries, witnesses and execution archives
are excluded. Their hashes are provenance identifiers for retained artifacts,
not downloadable artifacts or execution proofs. The published Query/claim
objects permit commitment checks, but do not authenticate the excluded
history or repeat the native comparison. A clean checkout cannot reproduce
this full six-case experiment from the included files alone. The existing
[native demo](../../../examples/robinhood-v4/README.md) and
[single-case artifact check](README.md#published-artifacts-and-verification)
retain their original scope.
