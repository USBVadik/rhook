# Branch Semantics 0.1 — core requirements

Publication excerpt from the frozen design draft prepared on 1 October 2026.
Sections 2–9 below are copied unchanged. This excerpt omits the research
comparisons, case appendix, workspace links and task-preservation logs.
It does not amend the draft or upgrade the assurance of an execution artifact.

MUST and MUST NOT express requirements for conformance to the draft. MAY
permits a choice only within those constraints. Laws L1–L9 are cumulative;
a profile cannot waive one. The admitted continuation is frozen historical
arrival: external envelopes/environment stay fixed while execution regenerates.

The original full-document SHA-256 is
`6908ebb6630aee0faa284742356a799be1cc5346a7ce86c5f74655813533cc55`.
That is a provenance pin for the excluded full source, not this excerpt's hash.
The [published result](../research/robinhood-heterogeneous/README.md) records
the later bounded heterogeneous comparison. Requirements below are a semantic
contract; publishing them does not cryptographically enforce them.

## 2 Terms and trust boundaries

### 2.1 History and anchor

`H` is the semantic history input. It comprises an anchor `a`, a commitment to initial application state `r0`, an ordered finite external event stream `E`, and the declared historical environment `U` needed to interpret those events. It also binds the canonical comparison references needed to establish actual control.

The anchor identifies the application or network, checkpoint, its place in the canonical history, and the authority or consensus evidence under which that history is accepted. A chain ID alone is insufficient to distinguish competing histories. A state proof proves a value relative to a root; it does not by itself prove that the root belongs to the accepted canonical chain.

Canonical references are observations or commitments against which the actual execution is checked. They MUST NOT become replacement predecessor state for either replay. An initial-state witness is material establishing reads from `r0`; its packaging is not the history itself.

### 2.2 State and execution events

`s` is application state. `z` is execution context maintained by the reference semantics, including such things as block gas accounting and system context. Their separation is explanatory: all stateful data that affects execution MUST be accounted for, whether stored in a trie, memory, an auxiliary database, or a proof relation.

An event is an arrival or a structural execution boundary. For the Robinhood case, `E` orders block start, every historical envelope, and native block finalization. The envelope stream includes Nitro system transactions. Internal calls are consequences of execution; they are not additional historical arrivals to freeze.

An event has a stable historical identity and position. In the Robinhood profile, an envelope identity aligns the original transaction hash, block number, and transaction index. This identity does not assert that an altered execution message has a valid signature under that hash.

### 2.3 Reference semantics and implementation

`R` is the accepted deterministic reference semantics. It specifies decoding and message derivation, validation, execution, accounting, system transitions, finalization, environmental lookup, and handling of qualified invalid arrivals. It also specifies the admissible intervention boundaries.

An executable runner, zkVM guest, incremental evaluator, or proof circuit is an **implementation of R**, not R merely because it has a code hash. Its accepted binding to R requires review, qualification, an equivalence argument, or another explicitly named trust basis. The identity of an arbitrary producer-selected program is not sufficient.

R MUST be world independent. Its ordinary transitions MUST NOT inspect an ACTUAL/BRANCH label to select different rules, special balances, expected outputs, or exception handling. The sole declared intervention supplies a changed operand at its admitted boundary. The transition semantics applied to that operand are otherwise the same.

### 2.4 Observation and knowledge

`P` is a ProjectionProfile: a deterministic read of semantic facts from an execution, followed by a defined result mapping and codec. `subject` identifies what is observed. `theta` fixes projection parameters and evaluation boundaries.

A semantic result describes the execution. A verification outcome describes what a verifier knows about that result. These are different objects. Runner failure, unavailable state, or missing evidence MUST NOT be encoded as a world outcome such as REVERT or INELIGIBLE.

Evidence may establish internal consistency, a match to frozen reference artifacts, trusted producer execution, or a cryptographic execution proposition. Acceptance MUST name which assurance is being used. This draft does not make those forms equivalent.

## 3 BranchQuery

### 3.1 Mathematical definition

Define the semantic question as:

```text
BQ = (H, R, C, I, subject, P, theta)
```

`C` is the continuation policy. Here it is the admitted frozen historical arrival policy, including the exact partition of fixed environment inputs and locally evolving state. `I` is an instance of an admitted InterventionProfile, fixing its target, replacement, preconditions, preservation rules, and application count. `Id` means no intervention.

The two executions and projected results are:

```text
A  = Run_R(H, C; Id)
B  = Run_R(H, C; I)
yA = Observe_P(A, subject, theta)
yB = Observe_P(B, subject, theta)
```

The lawful branch relation is:

```text
Lawful(BQ, A, B) =
  Admitted(BQ)
  AND ActualControl(H, R, C, A)
  AND L1 AND L2 AND L3 AND L4 AND L5
  AND L6 AND L7 AND L8 AND L9
```

A semantic claim asserts the **ordered** result `(BQ, yA, yB)` of that relation. A pair of values obtained by unrelated programs is not such a claim. The relation can hold when `yA = yB`, when the states reconverge, or when the intervention has no effect. Inequality is not a conformance requirement.

Writing `B = F(I(H))` is acceptable shorthand only when `I(H)` means the declared boundary transformation under R. It MUST NOT silently mean rewriting raw signed history. In the frozen Robinhood case, H and the signed transaction remain unchanged; a derived `Message.Data` operand changes after sender derivation.

### 3.2 Admission before evaluation

An admitted question MUST determine the following before the claimed comparison is evaluated:

1. Anchor identity, authentication policy, initial root, complete arrival order, and environmental inputs.
2. Reference semantics, its configuration and accepted implementation binding, and actual-control requirements.
3. Continuation partition and rules for all environmental reads.
4. Intervention boundary, target identity, committed replacement, application count, and preserved fields.
5. Subject, common projection, common boundaries, units, result mapping, and equality convention.

This prevents an underdetermined question, rather than proving honest experimental pre-registration. A claim intended to show that a metric or window was chosen before anyone saw the result needs separate evidence of that timing. A digest produced after an experiment does not prove it.

Target resolution MUST be deterministic and unambiguous. If an intervention expects one occurrence, zero or multiple occurrences leave that question unresolved. An implementation MUST NOT silently select a different target or shorten the interval.

The subject resolver MUST define what absence means. A missing contract, nonexistent position, or absent callback can be a typed semantic outcome if P expressly defines it and its absence is established. Failure to obtain the data needed to determine absence is not the same result.

### 3.3 Semantic identity and artifact identity

Query identity MUST bind all execution-relevant contents of BQ, including C, R, and both profiles with parameters. Labels, version strings, and URLs are not substitutes for resolved definitions. The ordered result binding MUST distinguish the actual and branch roles even when their values are equal.

Producer identity, witness packing, trace compression, proof bytes, local paths, and instrumentation configuration MUST NOT alter the semantic question when they implement the same H, R, C, I, subject, P, and theta. If a source-code choice changes behavior, its semantic difference does belong in R; it is not merely a backend detail.

No wire encoding, queryHash, claimHash, EvidenceEnvelope, or migration is specified here. Branch Statement 0.1 retains its existing definitions, even where its identity binds more apparatus detail than this future requirement permits. Cross-backend identity remains an implementation test to be performed later.

## 4 Operational branch construction

### 4.1 State fold

Conceptually, both executions start at `(s0, z0)` authenticated or determined by the same H and R. For each ordered event `e[k]`, the reference operation is:

```text
(s[k+1], z[k+1], o[k]) =
  Advance_R(s[k], z[k], e[k], U, C; admittedBoundaryTransform)
```

`Advance_R` derives operands from the original event and the execution's own predecessor, reaches any admitted boundary, applies Id or I there, and performs the same reference transition. For a top-level message boundary, the replacement occurs after canonical envelope decoding and native sender derivation, before validation and execution of the resulting message.

For an operand m at a matched boundary with declared field allowlist W, the transformation MUST satisfy `m'[f] = m[f]` for every field f outside W. At unmatched boundaries it is Id. The allowlist authorizes an operand change, not arbitrary successor-state differences; those differences must follow from Advance_R. For the current profile, W contains only Data.

Operationally, a conforming evaluation resolves BQ and its admission policy, authenticates initial and historical inputs, establishes or accepts the required actual control, resolves I, evaluates the ordered branch continuation, and applies the common P to each world's defined observation boundary. Joint proofs may establish these obligations together. Branch outputs MUST NOT be interpreted as established before actual control is discharged. An incomplete or failed attempt produces a knowledge decision, not fabricated endpoint values.

This notation also covers block-start and finalization operations. Final state after finalization is not automatically the same root as a per-envelope post-execution observation. Evaluation boundaries MUST distinguish them.

The implementation need not materialize every state or trace. It MUST nevertheless establish the same conceptual relation for the claimed observations. Selective or incremental execution is permissible only with a sound justification that omitted work cannot change them. A declared shortcut is not a license to replace required consequences.

### 4.2 Arrival continuation and invalidation

For an envelope, R distinguishes execution from a qualified failure before execution:

```text
valid arrival -> execute native transition -> execution outcome
qualified pre-execution invalid arrival -> unchanged state/accounting -> next arrival
unknown engine/apparatus failure -> STOP this evaluation attempt
```

SUCCESS and REVERT are execution outcomes. REVERT does not generally mean that all transaction-level state and fees remain unchanged; R supplies its native accounting and rollback rules.

A pre-execution invalidation is admitted only when R identifies an allowed validation failure, proves that execution has not begun, and establishes the prescribed absence of state and accounting effects. The same rule applies in actual and branch. The actual history usually contains no such invalid arrivals because its transactions were canonically included.

This arrival wrapper is part of R. It is not a claim that the unmodified consensus block processor accepts a block containing an invalid transaction. For the frozen Nitro case, canonical signed arrivals remain in the historical domain even when the branch rejects them before execution. No nonce repair, gas top-up, transaction deletion, or re-signing is implied.

### 4.3 Actual control

Actual control MUST establish that A is the accepted history under R, rather than a convenient baseline invented by the producer. The required comparison surfaces belong to the anchor/reference contract and cannot be reduced to whichever metric happens to match.

For the qualified Robinhood path, the preserved standard is continuous replay from one checkpoint with per-block canonical comparisons, including state root, receipts root, and reconstructed block hash, plus qualified envelope and accounting comparisons. State is not reloaded between blocks.

A different backend MAY use accepted authenticated reference evidence or prove an equivalent actual execution rather than repeat the same native run. Its assurance and coverage MUST be explicit. Checking only `P(A)` against a cached value does not establish full canonical execution or qualify a different R.

## 5 The nine branch laws

### L1 Canonical Anchor

Both executions MUST start from the same initial state commitment and the same authenticated history inputs. Actual control MUST bind A to the accepted anchor and canonical history. Proofs of account/storage values MUST verify against the declared root; code MUST match its authenticated code binding.

Canonicality and state authentication are separate obligations. If the anchor is accepted through a trusted capture or authority, the claim MUST disclose that basis. Hash agreement with a captured transaction list is not independent consensus authentication.

**Reject:** a guest authenticates one real checkpoint but begins B from another root, or accepts an invented history merely because its JSON is content-addressed.

### L2 Declared Difference

Every intentional execution-input difference MUST be authorized by the one declared I. I MUST fix a bounded boundary, exact target resolution, replacement rule or bytes, preconditions, and permitted fields. For a single-target profile the expected application count is one.

The two prefixes MUST be equal before the admitted boundary, including state, context, and derived operands. At the boundary, non-authorized operands MUST be preserved. After it, differing state, validation, gas, internal calls, outputs, and locally derived operands are permitted **only as consequences of the shared transition semantics**, not additional interventions.

An intervention MUST NOT force an execution result, patch a downstream value, or disguise state mutation as message replacement. A signature-breaking analytical operand change MUST be disclosed as such. Retaining the historical alignment identity does not validate a replacement signature.

**Reject:** the declared change is router Data, but the producer also credits the sender, changes a later nonce, or overwrites a callback result.

### L3 Exogenous Conservation

Under C, the same ordered external arrivals and declared historical environment MUST be supplied to both executions. Preservation concerns submitted inputs, not their successful realization. An invalidated arrival remains an identified member of the historical domain.

For this continuation, downstream signed bytes, ordering, block number, timestamps, and declared header context are fixed. No reordering, adaptation, fee substitution, wallet re-signing, or behavioral response model may be introduced silently.

Every environment-dependent read MUST have an explicit origin: frozen historical input, initial authenticated state, or state generated locally under R. Inputs normally endogenous to consensus, such as later base fees or header hashes, MAY be explicitly held fixed for this conditional question. That externalization and its limitations MUST be bound into C; it is not a consensus-fork claim.

Internal call topology, validation results, receipts, and execution fees are not historical arrivals to preserve. Neither profile may redefine the partition to import arbitrary canonical state. C is an admitted input policy, not a producer-supplied continuation script.

**Reject:** a later transaction is dropped because it becomes invalid, or the runner substitutes a synthetic block hash without the declared environmental policy.

### L4 Endogenous Regeneration

Both executions MUST regenerate state-dependent validation, execution outcomes, return/revert data, logs, gas/accounting, system effects, finalization, and successor state under R against their own predecessors.

An implementation MUST NOT replay canonical outcomes or traces as executable consequences. Such data may be a comparison oracle for actual control or a hint for discovery, but it cannot replace native branch computation. Branch-internal calls are generated by branch execution, including calls that disappear or first occur after divergence.

Within the admitted continuation, preservation of a historical fee **input** does not imply preservation of the fee **charged**. That accounting is regenerated according to R and the declared intervention policy.

**Reject:** the branch changes balances but reuses canonical SUCCESS receipts, charged gas, hook outputs, or finalization state.

### L5 No Canonical State Injection

After initialization, successor state MUST derive solely from the execution's own predecessor under R and I. The prohibition applies before and after the first observed divergence; a reset is not justified by temporary equality or by crossing a block boundary.

Additional authenticated initial-state material MAY close a partial witness. It MUST authenticate to the same r0 and MUST NOT overwrite any locally created, modified, or deleted value. A trace may discover keys; it may not supply unauthenticated values. Later canonical proofs authenticate a different state and are not branch predecessor material.

Block-context inputs explicitly conserved under C are not state injection. Their use MUST remain distinguishable from importing account/storage/code values or mutable native system state.

**Reject:** B's state is replaced with canonical state at the next block, even if the guest subsequently executes every remaining transaction correctly.

### L6 Shared Reference Semantics

The same R, configuration, validation policy, accounting rules, system handling, environmental policy, and finalization MUST govern A and B. Only the admitted boundary operand differs.

Implementations MAY differ while conforming to the same R. They MUST justify the same semantics for the claimed question; a separate code hash or proof does not make a changed invalidation policy equivalent. Instrumentation MUST be observational and MUST NOT become an additional input to execution.

Unknown errors MUST remain STOP in both roles. A profile cannot turn a native engine failure into a new semantic lifecycle or introduce branch-only rescue behavior.

**Reject:** actual uses native validation while branch bypasses insufficient funds, changes poster-cost rules, or patches the engine to continue after unclassified errors.

### L7 Projection Symmetry

The same P, subject resolver, parameters, result mapping, arithmetic, and symbolic evaluation boundaries MUST be applied to A and B. Each observation MUST read its own world's facts. A common endpoint block number does not permit reading actual storage for B.

P MUST be a pure observation. It MUST NOT modify state, trigger another simulation, choose a boundary after seeing differences, inspect a producer/branch-role label, or use evidence availability as a semantic input. Typed absence may be observed; missing knowledge cannot be converted into absence.

P may classify different native facts into different domain results. The classification rule MUST be identical. Equality is defined by the admitted canonical result codec, not presentation text or floating-point rounding.

**Reject:** actual reports accrued pool fee growth while branch reports collected tokens, or the two projections select different endpoints to obtain a larger difference.

### L8 Actual to Branch Directionality

The roles MUST be ordered and bound throughout query evaluation, result publication, and evidence verification. A is the unmodified canonical control; B is the execution with I. Swapping them changes the assertion even when a symmetric comparison yields DIFFERENT in both orders.

An inverse intervention does not automatically give the reverse query: B is not the original canonical history. Signed differences such as `yA - yB` MUST preserve orientation, units, and the specified arithmetic convention.

**Reject:** a consumer receives two roots with no role binding or accepts a proof for B's result in the actual field.

### L9 Fail Closed Knowledge

No claim may be accepted as established under a stated assurance unless every obligation required by that assurance is discharged. Missing initial state, ambiguous target, incomplete continuation, unknown reference/profile, unbound projection read, failed proof, and runner failure MUST leave the affected proposition unaccepted.

An evaluation attempt may be accepted under a named policy, rejected for an established violation, or unresolved for insufficient knowledge. These are verification decisions, not prescribed wire enums or branch result values.

An early completed observation MAY support its own separately specified prefix question; it MUST NOT be presented as a completed endpoint question. A partial full-window run cannot claim final Y. A proof of envelope lifecycle does not also prove a pool metric unless the relevant read and extraction are covered.

**Reject:** missing branch storage becomes zero, an apparatus crash becomes REVERT, or strict artifact verification is promoted to a proof of native execution.

## 6 Semantic ownership and profile limits

The following ownership is normative. It prevents a profile from making a forbidden branch lawful by redefining the law it violates.

| Item | Semantic owner | Permitted customization |
|---|---|---|
| Network, checkpoint, canonical arrival order | H and anchor policy | Exact historical case and accepted authentication basis |
| Native validation, execution, system handling, accounting, finalization | R | Explicit accepted domain semantics and configuration |
| External continuation and environment partition | Admitted C | Fixed historical arrivals and explicitly identified historical environment |
| Target and authorized boundary operand change | InterventionProfile instance | Bounded transformation satisfying L2 |
| Subject, observation, result mapping, codec and units | ProjectionProfile instance | Pure symmetric extraction satisfying L7 |
| Lawful relationship between executions | This contract | Cannot be waived by a profile |
| Evidence acceptance and required assurance | Consumer verification policy | Named assurance sufficient for the consumer's decision |

Consumers MUST resolve and accept R and both profile definitions rather than trust arbitrary self-describing names. A content hash makes a definition identifiable; it does not certify conformance. Unknown or incompatible definitions are unresolved. No global registry is required by this draft.

### 6.1 InterventionProfile

An InterventionProfile MUST define its native boundary, input and output types, deterministic target resolver, admissible target class, preconditions, exact change allowlist, and preservation obligations. An instance MUST bind the replacement and expected number of applications.

Where relevant, it MUST define how historical identity, sender derivation, signature interpretation, original envelope bytes, and accounting operands relate to the changed operand. A native system transaction requires its own admitted treatment; an ordinary user-message profile does not qualify it automatically.

| MAY customize | MUST NOT customize |
|---|---|
| A precise replacement at an admitted input boundary | Reference execution or validation rules |
| Target selector and deterministic resolution preconditions | Downstream arrivals, ordering or continuation policy |
| Replacement bytes or a bounded deterministic operand transformation | Arbitrary mutation of balances, storage, code or successor state |
| Expected application count and preserved operand fields | Unknown-error handling, canonicality or witness authentication |
| Explicit analytical signature and accounting disclosure | Projection, desired outcomes, acceptance policy or proof meaning |

An intervention handler MUST return only the admitted boundary operands. It MUST NOT write application state, perform environmental lookups outside the declared model, install branch-only engine rules, or act as a second simulator. Any permitted deterministic replacement computation must have fully specified inputs and the same confinement; a general mutation script is not an admitted profile.

A future internal-rule boundary would require a precise occurrence identity under regenerated execution, a bounded replacement, preservation of the caller/callee and native transition context as specified, and evidence of its faithful implementation. If the intended occurrence disappears, its profile must define admissibility rather than invent a callback. None of this is qualified by the current router case. Router replacement MUST NOT be called hook removal.

This draft does not admit generic storage or code overrides as substitutes for message replacement. Extending to another intervention class requires a separately reviewed boundary contract that preserves L1–L9 and actual control. Assigning the name “profile” to arbitrary state mutation does not achieve that extension.

### 6.2 ProjectionProfile

A ProjectionProfile MUST identify observable semantic facts, a subject resolver, a symbolic evaluation boundary, a pure extraction and mapping, a result type, exact arithmetic, units, canonical codec, equality, and treatment of established absence. These definitions MUST be deterministic.

| MAY customize | MUST NOT customize |
|---|---|
| Subject type such as envelope, pool or claim | Construction of the branch or its continuation |
| A fixed observation boundary such as after finalization | Boundary or subject chosen separately after seeing each result |
| Lifecycle, fee-growth, eligibility or another defined observable | Engine rules, intervention scope or validation behavior |
| Domain classifications, units and deterministic arithmetic | State injection, witness acquisition or proof acceptance |
| Canonical result codec and equality | Producer identity, evidence availability or ACTUAL/BRANCH labels as semantic facts |

Pure extraction can involve computation. “Pure” does not mean a simple storage read, nor does it provide a general ban on arbitrary mathematical functions. The restriction is that P observes the same defined facts in each lawful world and cannot redefine or manufacture those worlds. A constant projection can be conforming but tells the consumer nothing about impact.

A projection parameter may fix an account or claim owner as a subject. It MUST NOT resolve the actual subject from one world's convenient event and a different branch subject from another, unless the same declared resolver specifies those semantics and reports the resolved identities. A shared policy may intentionally select, for example, the highest-fee position in each world; that answers a different question from following one fixed position and must be named accordingly.

Economic predicates such as “profitable” require explicit units, valuation inputs and arithmetic. An undeclared external price feed cannot be added during extraction. Hypothetical eligibility or lending profiles are permitted design examples here, not qualified second applications.

### 6.3 Continuation and reference limits

C MUST NOT be executable arbitrary behavior capable of fabricating later arrivals. This draft admits only the fixed historical stream and an explicit environment-origin table. Adaptive participant behavior, nonce repair, re-signing, alternate consensus header derivation, or regenerated submission decisions require a different declared query and additional semantics; they cannot be hidden inside I or P.

R MUST identify its transition rules and distinguish native application effects from the analytical arrival wrapper. A producer MUST NOT choose “execute whatever this guest does” as R while claiming native historical branch semantics. Accepting a new R requires an explicit consumer/domain decision and actual-control basis; it does not change the nine common laws.

The frozen v0.1 profile places some continuation, accounting, and error-policy descriptions together. Those artifacts remain unchanged. This section assigns semantic responsibility for future design; it neither migrates that placement nor asserts that v0.1 already implements general profile admission.

## 7 State provenance and witness closure

Every execution-affecting state read MUST be justified by one of two origins:

1. The initial state authenticated to r0, including authenticated absence and code-hash binding.
2. A value created or carried forward by that execution's own preceding transitions under R.

Conceptually, each execution consists of S0 and its own evolving overlay. Initial proofs may fill an unknown initial value only when the local predecessor still refers to that initial value. Locally written values, deleted accounts, cleared slots, tombstones, new code, and code changes take precedence over any original-state material. Hydrating an initial account MUST NOT overwrite its already modified storage or balance.

The witness MAY grow when a branch first accesses a new key. Each addition MUST retain the same root and authentication rules and record its origin. Replay MAY restart a new attempt from S0 with the authenticated extension, or continue through a sound root-preserving witness mechanism. Neither route permits a canonical intermediate reset.

A missing trie node, absent RPC response, unverified code blob, or partial proof is not authenticated nonexistence. Defaulting any of these to zero violates L9. If required material cannot be authenticated or produced locally, the evaluation remains unresolved.

Canonical traces MAY discover potential addresses, slots, or code identities. Trace-provided values MUST NOT be used as branch values. Fetching code by address from a later canonical block likewise does not establish its initial code-hash binding.

It is unnecessary to commit witness layout into semantic query identity. Different producers can establish the same initial reads using different authenticated packaging. Their evidence still MUST bind the same r0 and the correct locally evolved predecessor. This is a requirement for future interoperability, not proof that two existing backends satisfy it.

## 8 Environment and block context

A question MUST make every environmental read deterministic. The environment-origin table identifies whether a value comes from frozen H/U, native evolving state, or deterministic R. Undeclared wall-clock time, live RPC responses, randomness, host filesystem state, and moving dependency branches cannot supply semantic operands.

For conditional blockchain replay, canonical header context can remain external after branch divergence. It follows that historical `parentHash` may identify a canonical block while the branch predecessor state has a different root. This is legitimate only under the explicit conditional policy; it is not a valid alternative header chain.

BLOCKHASH needs its actual native meaning, not a blanket “use historical hashes” instruction. A lookup supplied by canonical header context can be frozen under C. A lookup implemented through mutable native system storage MUST read that world's locally evolving system state. It cannot be forced to canonical storage by calling the result an environment input.

System envelope inputs may be frozen, but their state effects and finalization MUST run on each world's predecessor. Freezing a canonical expected system result violates L4. Apparatus observations of a system-state table do not authorize transplanting that table.

For a new case, an unavailable or ambiguous environmental policy leaves the question unresolved. A producer MUST NOT substitute convenient values to achieve a PASS.

## 9 Evidence obligations and consumer acceptance

### 9.1 Required bindings

An acceptance policy for an established branch result MUST cover the following obligations to its stated trust standard. They may be discharged by a proof, authenticated references, qualified replay plus explicit producer trust, or a combination. Merely asserting that an obligation exists does not discharge it.

| Obligation | What must be established |
|---|---|
| Anchor and inputs | Accepted canonical basis, initial root, complete ordered arrivals and environment |
| Reference binding | Implementation computes the accepted R with the declared C |
| Actual control | The unmodified world agrees with the required canonical surfaces |
| Declared transformation | Exact boundary, target, replacement, preservation and application count |
| Prefix and continuation | Shared prefix and each world's own predecessor through the observation boundary |
| State provenance | Initial authentication, local evolution, no forbidden canonical injection |
| Outcome handling | Regenerated validation/execution; strict invalidation; unknown errors do not become outcomes |
| Projection | Same P, subject, theta and codec; reads belong to the corresponding worlds |
| Role and output binding | Exact question and ordered actual/branch results are what the evidence establishes |

If terminal roots are claimed, evidence MUST establish those roots. A proof of only a projected predicate need not expose a full terminal state root, but it MUST establish the lawful reference execution relation sufficient for that predicate. It cannot assert an unproved root as an incidental decoration.

Backend optimization is allowed. The producer must establish semantic equivalence for the claimed observations even if it does not generate a complete native trace. Full replay is one way of discharging obligations, not a mandatory evidence representation for all implementations.

### 9.2 Consumer policy

The consumer MUST own its accepted query, reference/profile definitions, anchor policy, and assurance requirements. A producer cannot supply an unknown verifier that always returns true and thereby establish the claim. A guest ImageID, attester address, or registry UID is useful only with that prior interpretation.

The consumer MUST bind accepted evidence to the exact ordered semantic result and reject an unrelated proof. Different evidence artifacts can support the same result; verification or caching MUST NOT confuse one valid artifact, one missing artifact, and conflicting claims. An invalid attached artifact does not by itself disprove the world proposition; it fails that verification attempt.

Acceptance under a trusted producer policy MUST remain labeled as such. It MUST NOT be described as trustless execution verification. Cryptographic execution verification additionally depends on proof soundness, the accepted program's implementation of R and the laws, and correct public-input binding. It does not remove the need to accept an anchor's canonicality basis.

### 9.3 Existing verifier boundary

The existing strict RHOOK verifier checks serialized evidence structure and consistency under its existing contract. Matching all 642 frozen records establishes that the presented records match those artifacts. Neither operation alone proves native Nitro execution, consensus canonicality, or endpoint storage extraction.

This draft adds semantic obligations; it does not retrofit their proof into the old verifier. The frozen endpoint reads remain apparatus inputs bound to declared roots in the existing presentation/statement layer. An established metric under a stronger policy would require evidence of the reads and extraction, not only the root label.
