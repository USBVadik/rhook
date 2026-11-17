# RHOOK project status and accepted decisions

**Status date: 11 November 2026.** Start here before proposing work. This is a
public coordination index, not scientific evidence, native execution permission
or a complete copy of private project history. Check the linked commit/PR state
before acting; an accepted local milestone and a merged public release are
different facts.

RHOOK's goal is **Developer Question → Counterfactual Execution → Portable Result
→ External Consumer**. Current capabilities are bounded. Pair03 is the present
historical pilot scope, not the intended long-term boundary of the protocol.

## Public source and publication baseline

At this update's preparation, public main was
[`493dc5b7`](https://github.com/USBVadik/rhook/commit/493dc5b7a7ab101a2cfcd0be40f13eaa326405a2),
the SDK 0.6 Developer Preview merged in
[PR #19](https://github.com/USBVadik/rhook/pull/19). The existing
[PR #20](https://github.com/USBVadik/rhook/pull/20) was OPEN/DRAFT at
`7dfabe04fda71294716c8bc0ce71a706956ab868`; its
[CI run 42478097960](https://github.com/USBVadik/rhook/actions/runs/42478097960)
completed verify and sdk-offline successfully. This is a dated reference
snapshot, not a permanent assertion about current main or merge authorization.
The present status/cross-engine documentation is a separate change from PR #20.

Public entry points: [SDK](../sdk/README.md), [sessions](../sdk/SESSIONS.md),
[scenarios](../sdk/SCENARIOS.md), [descriptor specification](../sdk/PROFILE_DESCRIPTOR_SPEC.md),
[research index](research/README.md), [protocol](protocol/branch-protocol-0.2.md)
and [limitations](limitations.md). These source/docs links do not supply private
workers or state. The earlier [product-state page](PRODUCT_STATE.md) is retained
as a historical planning snapshot.

## Accepted capabilities and their verification levels

| Milestone | Established scope | What it does not establish |
| --- | --- | --- |
| Public SDK 0.6 | Source and offline descriptor catalogue/inspection/planning/validation; [G5 case study](research/sdk06-g5-descriptor-parity.md) records private native parity against prior same-engine results | A complete public native runtime, general Hookr support or independent EVM verification |
| Historical Hookr LP50 | Canonical Go/Nitro ACTUAL, separate BRANCH over the retained seven-arrival block; [original study](research/hookr-pair03-100-to-50.md) | Arbitrary pool/amount/intervention coverage |
| Historical LP37 | Privately retained Go/Nitro ACTUAL/BRANCH, selected numeric value observed before execution and after finalization; separate verification/compare passed | Rust qualification of LP37, all LP values, external self-service or a public replay kit |
| Historical LP38 through ordinary Lab | User selected 38 in Lab → shared controller/operator approval → fresh Go/Nitro ACTUAL/BRANCH → verification → automatic result in the same Lab; no per-value engine/script | Public hosted execution, a run on another developer's computer or proof of support for arbitrary questions |
| Strict Pair03 Rust/Go LP50 agreement | Two fresh Rust ACTUAL/BRANCH pairs; byte-identical repetitions and strict consensus-receipt/header/log/gas comparison with retained Go results; [case study](research/hookr-pair03-cross-engine.md) | Full JSON-RPC metadata parity, independently established L1 finality, blind external reproduction or a qualified protocol Claim |
| Historical Dynamic Fee OFF | Separate Rust BRANCH repeats agree with Go on their declared fields; a different binary and narrower direct receipt comparison, with earlier recorded ACTUAL | The LP50 four-world qualification, all Hook Blocks or arbitrary historical compositions |
| Recorder-only replay | Two retained historical cases replayed ACTUAL/BRANCH from recorded dependencies; [scope](../sdk/RECORDER_RESULTS.md) | General witness completeness, radical storage/RAM savings or a new state provider |
| Data-only causal lifecycle | Existing 321-arrival history/intervention supports downstream lifecycle queries; [application](research/real-history-counterfactual-application.md), [other intervention](research/novel-counterfactual-intervention.md) and [amount27](research/developer-amount27-native-pilot.md) retain distinct scopes | Disabling a Hook Block, a general causal-mechanism explanation or a cryptographic execution proof |

For Historical LP37/38, parent 93251802 → target 93251803, all seven original
arrivals remain in order, including the system arrival. The selected ordinary
purchase is 0.01 ETH. Only LP Rewards changes; Dynamic Fee ON and arb recapture
remain. Both worlds complete with seven SUCCESS receipts and canonical ACTUAL
control, using the saved state without chain RPC. These are private accepted
local results, not newly executed by publishing this page. Product-integrity
anchors identify them without exposing the full records:

- LP37: `41715056a77b786d6d79e443f31ccf14db7bc3206e1606e613ee18b1568cc12e`.
- LP38: `70ebd44751a4622017b063a0004f9b6ba99bbb0ae2746fe6cd8b16dd937e9af3`.

These hashes are identifiers, not independently checkable execution evidence
without their private preimages/context. LP0–99 is an admitted numeric domain;
executed LP37/38 do not establish complete coverage of that domain. `FRESH_NATIVE`
describes a result's execution origin: reading it later performs no new EVM work.
The LP50 Rust study does not silently upgrade LP37/38, LP0 or G5 verification.

## Implemented privately, not distributed here

The local historical Lab/controller/CaseSDK integration, per-operation approval,
owned execution/cleanup and prepared state support the accepted local workflow.
They are not a public execution service. A source clone, recorded result viewer
and complete private runtime installation have different capabilities.

Private workers, witness/trie/code preimages, full native world records, complete
source/build/dependency closures and operational authority/key material are not
published by this status update. The original private archive SDK Alpha03 already
supports offline `impact → compare → claim` on its fixed Data-only archive; an
external recipient's native self-service has not been demonstrated. Its recorded
checking remains DEVELOPMENT_ONLY_NOT_QUALIFIED, not fresh EVM execution.

The source license is not combined-runtime/witness distribution clearance.
Nitro/brotli BUSL questions remain unresolved here. See
[license scope](../sdk/LICENSE_SCOPE.md) and [distribution status](../sdk/DISTRIBUTION.md).
Protocol `qualifiedClaims=0`; economic assurance and broad witness completeness
remain unresolved. Cross-engine agreement and organization-independent verification
are separate claims.

## Second pool and state acquisition: what remains blocked

The RHOOK/HOOKR acquisition Build03 source route, worker/test compilation, four
native interface tests and worker startup/CaseSDK registration completed locally.
The test path included Unix Source → synthetic authenticated MPT discovery →
recorded original-state witness → fresh Source=nil replay, preserving the BRANCH
intervention. This is real Go/Nitro test execution on synthetic state, **not** a
replay of the second pool's signed historical block.

No complete authenticated second-pool capsule, canonical real-pool ACTUAL/BRANCH
pair or final Source=nil historical acceptance has been established. Historical
proof availability at a candidate parent remains a provider-specific requirement;
the prepared worker cannot supply missing state by itself. No alternative provider
was qualified by the retained documentation investigation.

The last bounded EVENT_FIRST search inspected 40 fixed heights and found no
eligible Swap event. It dispatched no proof request. **NO_ELIGIBLE_EVENT is not
PROOF_UNAVAILABLE** and proves neither availability nor unavailability of historical
state. Do not turn this bounded empty window into a universal provider conclusion
or automatically extend/repeat the search. General arbitrary-pool acquisition is
not available.

The local selected historical host profile treats free/available RAM as telemetry;
that is neither a RAM reservation nor a macOS allocation guarantee. Preserve the
exact applicable admission/resource/cleanup contract for any separately approved
operation rather than inventing a new headroom gate or weakening another guard.
This paragraph is not permission to run anything.

## Work already completed: do not reopen without a concrete reason

- LP37/LP38 and the existing Lab → controller → native → Lab route are accepted
  local milestones. Do not propose rebuilding them as a first RUN.
- Strict Pair03 LP50 Rust/Go qualification is complete for its exact scope. A
  concrete defect or new requirement is needed before another qualification.
- LP39 was cancelled. The later developer-client convenience draft was stopped,
  never accepted/activated, and is not a product dependency or an authorized task.
- The Data-only archive/portable checking path already exists. It needs a relevant
  evaluator and disclosure decision, not a sixth package or relabelling as Hookr.
- Worker readiness/interface tests do not justify rerunning metadata, builds or
  registration without evidence of relevant input drift.

Do not repeat an experiment for another PASS, publicity or to fill a status page.
Concrete defect reproduction, new admissible semantics or an external technical
requirement can justify new work under its own scope and authorization.

## Latest accepted decisions and next necessary step

**11 November 2026 — reuse accepted capabilities and obtain a real developer
requirement.** Repeated fee/qualification work was not creating a new user
capability. The near-term pilot is a way to choose the next protocol capability,
not the long-term product boundary or a dependency on one person's response.

Two audiences need different evaluations:

1. Hookr builders: ask which Hook Block behavior, transaction or downstream
   effect they actually need to investigate. Classify the question as currently
   supported, requiring new intervention semantics, or requiring new historical
   state. An unsupported question can define the next exact blocker. For a
   supported case, use the existing Lab and a separately approved operator-run
   native operation. Do not force the question into LP parameters.
2. EVM/infrastructure developers: the existing Alpha03 Data-only archive can
   support hands-on recorded impact/Query/Claim evaluation after exact disclosure
   approval. This is a separate pilot from Hookr and independent native self-service.

The next outcome is **external question → actual use → concrete usefulness**.
There is no confirmed external native acceptance or general application/contract
consumer of RHOOK results. Future engineering should deliver one specific missing
ability in **Question → Execution → Portable Result → External Consumer**, without
a parallel engine/controller or an invented universal-support claim.

**11 November 2026 — synchronize public history.** Correct the stale no-Rust-Hookr
statement, publish a reviewed scientific summary/status through an explicitly
approved workflow, and resolve PR #20 separately. A local candidate is not a GitHub
release. No push/merge/deployment follows from this document.

## Maintaining the public/private decision history

Every significant accepted milestone must end with a reviewed public record
and linked code/PR/evidence scope, **or an explicit decision explaining why it
remains private**, with a safe public status where appropriate. Record the date,
decision, reason, verification level, availability and next unresolved capability.
Track actual publication commits/PRs after publication; never infer synchronization
from a prepared patch or an unopened PR. Recheck dated claims before new work.

The detailed private history and withheld evidence remain a separate, access-
controlled source. This public repository cannot reconstruct bytes intentionally
omitted from it. Keep original scientific artifacts immutable, public summaries
separate from private runtime/evidence, and recorded integrity distinct from native
reexecution and proof verification. Documentation never creates an execution grant,
distribution right or permission to bypass an existing no-push rule.
