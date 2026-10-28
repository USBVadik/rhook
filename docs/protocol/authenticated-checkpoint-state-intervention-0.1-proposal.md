# AuthenticatedCheckpointStateIntervention/0.1

**Versioned local extension candidate. NOT a frozen-spec amendment, published
release, qualified InterventionProfile or complete Lawful proof.**

Branch Semantics0.1 section6.1 expressly excludes generic storage/code overrides.
Its admitted Robinhood boundary changes derived Message.Data after sender
derivation. Build18 uses checkpoint state, not Message.Data. It must not be
relabeled as qualified by the unchanged router profile. The original semantics
and Branch Protocol0.2 files remain immutable.

This candidate proposes an additional initialization boundary, with explicit
refinements of L1/L2/L5/L6 and section7 provenance. It retains their purposes but
does **not** assert literal conformance to the old same-execution-initial-root
wording. Acceptance of this extension and its reference binding is a separate
consumer/domain decision; the catalogue cannot make it on the consumer's behalf.

## 1. Anchor, transform and execution starts

Let H identify accepted original parent a, authenticated root r0, all ordered
original signed arrivals E, historical environment U and canonical comparison
references. MPT proofs/code establish values relative to r0; they do not prove
that a/r0 belongs to the canonical chain. Operator/trusted-capture or consensus
authentication basis must be stated separately.

Both worlds first resolve the **same pre-intervention anchor** (s0,z0). Define
one bounded initialization transform T_I and its exact identity/preconditions:

```text
Commit(s0) = r0
T_Id(s0) = s0
sA_init = s0;       rA_init = r0
sB_init = T_I(s0);  rB_init = Commit(T_I(s0))
zA_init = zB_init = z0, apart from required fresh state-cache initialization

A = Run_R(E,U,C; sA_init,z0)
B = Run_R(E,U,C; sB_init,z0)
```

The original anchor r0 and branch execution-initial rB_init are different
objects. rB_init must be derived from r0 and T_I, never selected independently.
It is a hypothetical root, not a new canonical parent or an administrative
transaction. A no-effect transform may have rB_init=r0; inequality is not a law.
The admitted boundary is after original-state authentication and before block
start/first historical arrival, including the system arrival. Its application
count is one, with a separately bounded storage-write count.

The equal prefix is the shared anchor/context before this initialization
boundary; this profile does not imply an equal prefix through the selected
purchase. The transform therefore has whole-block causal scope.

## 2. Closed target resolution and admissible changes

Only two trusted built-in classes are covered:

| Class | Permitted initial difference | Existing executor |
| --- | --- | --- |
| `hookr-1.lp-bps/1` | One full-word precondition, bits160–175 only, integer0–99 replacement | `nitro-hookr-lp/0.1` |
| `hookr-1.historical-dynamic-fee-off/1` | Exact saved Rules max11500→3000/sensitivity2→0 and Root mode3→2; two full-word preconditions | `nitro-hookr-historical-dynamic-fee-off/0.1` |

The exact existing pool, account/slot, runtime code hashes, masks, checkpoint,
target identity, subject and profile pins remain mandatory. Dynamic OFF remains
fixed to block93251803/original parent93251802 and its retained package. A
descriptor is not an arbitrary write list, executable script or plugin import.
Unknown profiles, unsupported values, code/layout mismatch, zero/multiple target
resolution or extra writes leave the question unadmitted.

Every old word and account/code binding must authenticate at r0. Resolve all
preconditions before any mutation; failure leaves no partial semantic transform.
No balance, nonce, code, account existence, unrelated storage bit or other
application state may change at initialization. All state outside the exact
allowlist must be preserved, including unobserved state. Checking a short list
of accounts alone is not proof of that global preservation.

The state adapter must initialize both current and committed/original-slot
semantics coherently (including EIP-2200 behavior), without altering the r0
witness or carrying transaction-local warm/refund/context effects into block
execution. Its implementation equivalence and confinement require their own
evidence/trust basis; a matching program hash alone does not provide it.

## 3. Common transition semantics and conserved history

After initialization, both worlds use the same accepted R, configuration,
validation/accounting, native system transitions and finalization. Ordinary
transitions must not select different rules by ACTUAL/BRANCH label. Only the
admitted initial state differs. No later corrective patch, nonce repair, rescue
funding, code replacement or canonical reset is allowed.

All signed historical bytes, order, block number, timestamp, declared header
context and environment-origin policy remain fixed. Internal calls, fees,
validation results, logs, gas and state are regenerated from each world's own
predecessor. A header-context lookup may be frozen under C; mutable system
storage must still evolve locally. This is conditional replay, not a
consensus-valid alternative chain. Unknown engine/state failures are STOP;
qualified invalid-arrival handling is only that already accepted in R, never an
invented branch-only success/revert path.

ACTUAL must discharge the declared canonical-control contract before BRANCH
results are interpreted. Here it must reproduce stateRoot, receiptsRoot and
blockHash of the complete saved block; matching a selected metric is insufficient.

## 4. Provenance and witness closure

Before the transform, reads originate in state authenticated at r0. The new
allowed origin is **the result of the admitted initialization transition T_I**,
with preconditions, confined writes and derived rB_init established to the
consumer's assurance standard. It is not an unauthenticated arbitrary third
source. Later reads originate in that world's own preceding R transitions.

Original-root proofs may close unknown initial dependencies only while local
state still denotes the original value. The admitted initial writes and all
later local writes/deletions/code/tombstones must take precedence. No original
proof may overwrite them, and no later canonical proof may supply predecessor
state. Code must match authenticated codeHash. Missing nodes/code are unknown,
not authenticated absence or zero.

Completeness must cover both fresh worlds, system/finalization operations and
all trie updates needed to compute final roots, not merely observed reads. The
existing offline runtime uses Source=nil and stops on missing dependencies.
One completed plan establishes operational witness coverage only for that
plan; it does not establish a universal witness for other descriptors or blocks.

## 5. Subject, projection and evidence

Subject resolution binds original transaction hash and ordinal, sender/router
and the full fixed arrival domain. P/theta use the same world-local facts,
evaluation boundaries, exact integer arithmetic, units, codec and absence policy
in both roles. A subject receipt is observed after that subject; block-final
state observations are explicitly after finalization/before commit. These are
different boundaries. Transfer-event net is not automatically token-storage
balance or profit. Projection cannot mutate execution or select convenient
different subjects/boundaries after seeing the results.

Required evidence covers the obligations in the L1–L9 matrix and original
section9: anchor/inputs, accepted R/C, actual control, exact transform, prefix/
continuation, provenance, outcome handling, symmetric P and oriented results.
Terminal roots cannot be asserted as independently proven merely because their
recorded headers and receipt roots recompute. Recorded commitment checks,
trusted producer execution, heterogeneous comparison and cryptographic execution
proof are distinct assurance bases.

Build18 supplies one accepted same-engine historical ON/OFF record, not
retroactive admission under this future class or the router profile. Some
artifact/receipt/transform checks are established; faithful full R, global
confinement/local evolution and canonicality rely on stated trust or remain
unresolved. No new qualified claim follows. qualifiedClaims remains0.

## 6. Identity and migration boundary

The new `rhook/checkpoint-state-admission/0.1` sidecar is a catalogue **artifact**,
not BranchQuery0.2, BranchClaim or EvidenceEnvelope. It separates descriptive
meaning from artifact bindings (capsule/package/witness/native-plan hashes).
Its hash must not be advertised as a backend-independent semantic query identity.
H/R/C/I/subject/P/theta still need fully resolved accepted definitions for a
future Protocol0.2 integration. No new cryptographic proof backend is defined.

Legacy runtime-plan, input/witness, overlay and operation serialization is
retained. Catalogue resolution returns the original typed adapter plan exactly;
its sidecars are not inserted into accepted plans or receipts. Any future
semantic or serialization change needs a named version boundary and separate
comparison/qualification; old claims and frozen artifacts retain their meaning.

## 7. Consumer knowledge model

`rhook/checkpoint-state-assurance/0.1` reports required evidence, structural
checks, available pinned records, enforcement, producer/anchor trust and open
obligations. ESTABLISHED means only the explicitly named subcheck. REJECTED means
the particular evidence/admission attempt failed, not that a world reverted or
the semantic proposition was disproven. UNRESOLVED means insufficient accepted
knowledge. These are not ACTUAL/BRANCH outcomes.

The initial consumer model never promotes complete Lawful or qualifiedClaims.
Even an exact accepted archive leaves overall assurance UNRESOLVED. A different
consumer policy would require explicit acceptance of the extension/R/trust or
stronger evidence. A producer cannot enable that policy by passing a JSON flag.
The full L1–L9 obligation matrix is shipped in the SDK's admission/laws.json and
rendered in the local Build20 report. Public specs are not retroactively edited.
