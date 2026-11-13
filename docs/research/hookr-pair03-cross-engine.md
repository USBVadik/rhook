# Hookr Pair03: bounded Rust/Go execution agreement

Report prepared 11 November 2026. This report summarizes retained
local execution evidence. The public deliverable is this report and a
[selected-commitment summary](hookr-pair03-cross-engine-result.json), **not a
publicly reproducible native execution kit**. Protocol `qualifiedClaims=0`.

## Question and fixed history

Do Go/Nitro and a separate Rust/arb-revm implementation compute the same result
for two specific changes to the same historical Hookr pool?

- Chain 4663, parent 93251802, target block 93251803.
- Seven original ordered arrivals, including the system arrival.
  Subject ordinal 3 is the historical 0.01 ETH purchase. Ordinary signed
  transaction envelopes are retained; the system arrival is not called signed.
- One fixed prepared package, SHA-256
  `b55ba3a6d70bd081148966f3b447135a098a26c18bae0c773f065beda807bda3`.
- LP50 changes only LP Rewards 100→50, retaining Dynamic Fee and arb recapture.
- Dynamic Fee OFF changes Rules maxFeePips 11500→3000, dynamicFeeSens 2→0 and
  Root mode 3→2 across two storage words/contracts; LP100 and recapture remain.

These are initial-state interventions before the first arrival. They do not
rewrite the original signed transactions or inject a synthetic buy/funding.
The [original LP50 study](hookr-pair03-100-to-50.md) and
[historical Dynamic Fee source summary](../../sdk/SOURCE_SYNC.md) describe the
Go/Nitro milestones. G5 checkpoint scenarios are separate experiments.

## Canonical ACTUAL is a control

The Rust ACTUAL computes its header and matches stateRoot, receiptsRoot and
blockHash, along with the declared header fields, against the canonical header
retained in the package. Each world starts from the original parent state.
BRANCH is compared with the corresponding previously completed Go/Nitro record.
Go was not reexecuted during these Rust experiments.

This checks the computed ACTUAL against the supplied historical control. It
does not independently establish that header's L1 canonicality/finality or
provide a cryptographic proof of the state transition. Public readers do not
receive the package/proofs needed to repeat its input authentication.

## Two experiments with different coverage

| Property | Strict LP50 qualification | Separate Dynamic Fee OFF record |
| --- | --- | --- |
| Rust execution | Fresh ACTUAL/BRANCH twice: 4 complete worlds | BRANCH twice; prior recorded ACTUAL reused |
| Binary SHA-256 | `90c94d60cb99a93b4ed3ec4552f24c175799f602d7bea03e025a0db566f91012` | Reported `43e03704a4474c419f3f9b39ed3b836d5a29a20c9b86679842faed6f53155de4` |
| Repetition | WORLD, arrivals and completion records byte-identical per world | WORLD and arrivals byte-identical between BRANCH repeats |
| Direct comparison | Full typed consensus receipts: type/status/cumulativeGasUsed/logsBloom/ordered log payloads; full admitted header, roots/hash, transaction hash and gas fields | State/receipt/transaction roots, blockHash, block gas/header bloom; each transaction's hash/status/gas/cumulative gas/L1 gas and ordered log payloads |
| Result | PAIR03_PARITY_PASS; 0 mismatches | Recorded RUST_GO_PARITY_PASS; 0 mismatches in declared checks |

The strict LP50 outputs were completed and sealed before a separate comparator
opened the Go reference documents. Its native argv did not supply Go outputs;
the local sandbox also denied the known Go-reference directory and network.
This is useful execution/input separation, not organizationally blind testing
or a malicious-producer security proof. The operators had prior knowledge of
Go results and the implementations were developed within the project.

DF OFF did **not** run through that same four-world qualification. Its comparator
label `everyReceiptField` covers only the fields listed above; this report does
not expand that label into a direct comparison of every JSON/receipt field.
The DF binary did not rerun ACTUAL or LP50. Its ACTUAL reference came from an
earlier Rust binary, reported SHA-256
`52fed73717dc601a0d110e81535d92228b3976db977fe6f87b21f244810eab2f`.
The DF binary identity is retained report provenance, not a new per-world
completion binding or a binary recovered/reexecuted for this publication.

`fullJsonRpcObjectParity=false`. In LP50, 602 coverage entries are unavailable
metadata, including repeated log-location fields and Go effectiveGasPrice=null;
they are not 602 EVM disagreements. The declared consensus comparison passed.
Neither experiment establishes full JSON-RPC object parity.

## Results and commitments

All seven arrivals are SUCCESS in ACTUAL and both intervention outcomes.

| Selected purchase observation | ACTUAL | LP50 | Dynamic Fee OFF |
| --- | ---: | ---: | ---: |
| Gas used |1,483,206 |1,483,206 |1,409,955 |
| Outer Swap fee, pips |11,048 |7,048 |11,000 |
| Buyer RHOOK Transfer-event net, base units |291469365928126821002944 |292938400920971228766928 |291486689098951541822309 |

LP50's Transfer-event net increases by approximately 0.5040100829%. DF OFF's
increases by approximately 0.005943393320%, while purchase/block gas decreases
by 73,251. These are event-derived observations, not profit, authenticated token
storage balances or values converted using authenticated token decimals.

| Commitment | ACTUAL | LP50 BRANCH | DF OFF BRANCH |
| --- | --- | --- | --- |
| stateRoot | `0xd4ea0fe6f558cbc4a6b4161e3afc41ee4b7709001c170e32bc2144e64bdeb10b` | `0xa6bf412783c620248df6746dfb2c637a87e828481abff901797463c73b777ad2` | `0x50580e7affb2053fc12348bbf64071898a08fdb3409eeece8aaedef3a4fe1914` |
| receiptsRoot | `0x920c08cb6953014f0800587bbe2c0f8db5a7855ddb9f6263d5b4e230edeba98f` | `0xc55c829dd13052c41831de4ff6518a8c62c57bdcf798e14193ca5f225ac92b1c` | `0xa7d56998ae3adcf7ebf064ac8782fbfc3319acf65964cc503f4280a3dd889980` |
| blockHash | `0xc73ef372869ad5bf2a664bc1bc4cbe411c3adeb1938f349dd7686d82425398cd` | `0xb8bc78a61d8394f24a6a3c5bdeb79be801ec63eaa52764e814ef2a1f2a88a542` | `0x4db925e1d21a04617cc8be59d68ac3a36eae7437011b24c2e12fdf19099cc527` |

The [JSON summary](hookr-pair03-cross-engine-result.json) supplies exact roots,
package/intervention/output hashes, binary identities and comparison scope.
LP50's local source/contract manifest is
`ed1f6cd60927bcb1ef20eb30d99919f69d88e89dd7436e236a07213a2bf927a6`;
its output seal is
`aa6a8fc5051687598e5e0ef47b7445f3556a209d287b7fd451d1c1da6bcca005`.
DF OFF's runner-file hash is
`4788f666b5fa1b211fe610253d78dc64671290c105bb7808501a1dfce87368a2`.
A runner-file digest is not a complete source/dependency/build closure.

## What the public files do and do not establish

These selected hashes identify private inputs/results and support comparison
with a later separately authorized disclosure. A digest without its preimage
does not let a reader recompute the recorded comparison or authenticate the
producer. Reading/parsing the summary is not native reproduction or proof
verification. No new SDK/API/release or protocol EvidenceEnvelope is introduced.

The worker, prepared witness, full source/dependency closure, raw world records,
run/authority records and audit logs are not included. A public native kit and
independent external reexecution remain pending. No new EVM/RPC execution was
performed to prepare this publication candidate.

The retained arb-revm NOTICE identifies a linked Nitro `brotli` crate under
BUSL-1.1, distinct from the Brotli C library's MIT license. Rust here does not
mean a BUSL-free binary. This report does not settle distribution/production-use
rights for either combined runtime or witness; see the existing
[license scope](../../sdk/LICENSE_SCOPE.md) and
[third-party notices](../../THIRD_PARTY_NOTICES.md).

Agreement is bounded to one history, one pool/generation, these exact transforms
and their recorded software identities. It does not qualify LP0, LP37/38, G5,
arbitrary pools or all ArbOS/EVM behavior. General witness completeness,
economic assurance and full Lawful qualification remain unresolved;
`qualifiedClaims=0`.
