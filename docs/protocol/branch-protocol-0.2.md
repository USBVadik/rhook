# Branch Protocol 0.2 — wire and codec

Publication excerpt from the frozen implementation candidate. Sections 1–2
below are copied unchanged. Their normative meaning comes from
[Branch Semantics 0.1](branch-semantics-0.1.md). The original full candidate
SHA-256 is `80b1dc97a65d4a030000ed4461ee47e90705965b04b618a534a485329ede9c0b`;
the full semantics source SHA-256 is
`6908ebb6630aee0faa284742356a799be1cc5346a7ce86c5f74655813533cc55`.
These pins identify excluded full documents, not this publication excerpt.

This publishes the encoding, not the research SDK or its frozen-reference
verifier. Existing core/runtime/host exports and evidence schemas are unchanged.
The [Robinhood research result](../research/robinhood-heterogeneous/README.md)
uses the query/claim objects below. No EvidenceEnvelope execution proof or
general profile admission is added. A coherent false assertion can have valid
commitments; syntax/hash binding does not establish a lawful branch.

## 1. Core wire objects

Every object is closed: unknown/missing fields, unknown version, noncanonical digest and ambiguous JSON are rejected. Digests are SHA-256, exactly 64 lowercase hexadecimal characters without 0x.

```text
BranchQuery {
  format: "rhook/branch-query/0.2",
  HCommitment, RCommitment, CCommitment, ICommitment,
  subjectCommitment, PCommitment, thetaCommitment
}
BranchClaim {
  format: "rhook/branch-claim/0.2",
  queryCommitment,
  actualResultCommitment,
  branchResultCommitment
}
EvidenceEnvelope {
  format: "rhook/evidence-envelope/0.2",
  claimCommitment,
  verifierProfileCommitment,
  payloadCommitment
}
```

BranchQuery commits all seven conceptual components. It contains no native root-observation, witness, trace, producer, proof, recovery policy or owner field. Initial authenticated state belongs in H: removing successor-root *assertions* from the wire does not remove the initial anchor or persistent-state obligation.

BranchClaim binds an oriented result pair for that one query. Relation labels and deltas can be derived under P; neither is another stored identity field. Equal results are valid. EvidenceEnvelope permits several proofs/representations for one claim without multiplying the semantic claim.

Domain terms appear in component preimages and profile definitions, not the core schema. An asset, compensation rule or release policy is not implicitly part of every BranchClaim.

## 2. Canonical encoding and hashes

For this bounded candidate, canonical JSON is ASCII-only: ASCII keys in ascending lexicographic order, arrays in their given order, no whitespace, JSON string escaping as implemented by JSON.stringify, booleans/null and safe integral numbers (excluding -0). Large numeric quantities use profile-defined canonical decimal strings. No Unicode normalization is attempted: non-ASCII and unpaired surrogates are rejected. Extending this codec requires a versioned decision.

Duplicate transport keys, floats/exponent numeric syntax, unsafe numbers, undefined, bigint, cycles, accessors, symbol/hidden properties, sparse/extended arrays and custom prototypes are rejected. Limits: depth 64, 100,000 encoded values, 4,000,000 canonical bytes; transport bytes are bounded before parsing. This is a local resource boundary, not a claim of universal language support.

```text
commit(D, body) = lowercase_hex(SHA256(ASCII(canonical({domain:D, body}))))

componentCommitment(k,v):
  D = "rhook/query-component/" + k + "/0.2"
  body = v

queryCommitment:    D = "rhook/branch-query/0.2"; body = complete BranchQuery
claimCommitment:    D = "rhook/branch-claim/0.2"; body = complete BranchClaim
envelopeCommitment:D = "rhook/evidence-envelope/0.2"; body = complete EvidenceEnvelope

resultCommitment:
  D = "rhook/projected-result/0.2"
  body = {
    projectionCommitment: query.PCommitment,
    subjectCommitment: query.subjectCommitment,
    parametersCommitment: query.thetaCommitment,
    value: profile-canonical projected result
  }
```

Result hashing is common across both roles. BranchClaim's distinct actual/branch fields bind orientation. The claim's query commitment additionally binds H/R/C/I; those need not be duplicated in the result preimage.

Verifier profile, evidence payload and domain-profile descriptor hashing use the separate domains exported in DOMAINS. Artifact SHA-256 pins of raw files are explicitly different from protocol commitments.

Component preimages bind meaning, not packaging. For Robinhood, H contains the authenticated checkpoint, block identities, decoded header inputs and ordered original raw envelopes; witness/session/archive hashes and observations are excluded. C includes the historical context policy and canonical hash lookups. R includes normative Nitro/geth source versions and native invalidation/continuation rules. Changing those versions changes the question; changing an observational sidecar, run label or witness layout does not.

For Recovery, H contains the empty ledger checkpoint, two committed actions, original proposal and domain facts. Run IDs, trace hashes, experiment labels and truth-class annotations are not execution inputs. R names the frozen normative ledger program; its source digest is part of the reference semantics, not the producer identity. C retains every arrival. Subject and theta bind the already-frozen right and its exact allocation matcher.

## Publication notes

The candidate's `DOMAINS` symbol refers to its retained research implementation,
not a root package export. Its additional domains are:

| Purpose | Domain |
|---|---|
| Evidence payload | `rhook/evidence-payload/0.2` |
| Verifier profile | `rhook/verifier-profile/0.2` |
| Domain-profile descriptor | `rhook/domain-profile/0.2` |

These strings are copied from that implementation's domain constants. It is
identified by raw source SHA-256
`5026505f86b98441ce80092f816a4b22b711e755de3bca1ab356d0bf11c138b4`.
The domain-profile descriptor is distinct from a query component commitment.

The encoding candidate makes no implicit migration from version 0.1. Different
hash domains and semantic preimages produce new identities. Old statements and
their hashes retain their original meaning. The full candidate also contains
a separate Recovery profile; that experiment is outside this publication.
This document and its artifact check are not production certification,
generic Nitro conformance or a proof/attestation backend.
