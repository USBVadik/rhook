# Architecture

```text
checkpoint + ordered envelopes + one intervention
                     |
                     v
               host execution
                     |
           beforeTx / afterTx events
                     |
                     v
              typed runtime ingress
                     |
       envelope evidence + state bindings
                     |
                     v
             branch transcript
                     |
                     v
           strict offline verifier
```

## Core

[`core/`](../core/) contains the typed boundary values, per-envelope evidence builder, semantic extraction model, compact branch transcript, duplicate-key-safe JSON parser, and strict verifier.

Core does not execute transactions. It has no filesystem, network, protocol adapter, recovery policy, or historical case.

## Runtime

[`runtime/`](../runtime/) is the conversion boundary between an execution engine and core. It normalizes native state roots, envelope identities, receipt status, exceptions, gas, fees, logs, return data, and semantic observations exactly once.

A native EVM state root is retained as a Keccak-256 value and bound to the SHA-256 commitment used by the evidence schema. It is not relabeled as a SHA-256 digest.

## Host

[`host/`](../host/) attaches evidence collection to a compatible `runBlock` function supplied by the caller. Evidence-enabled execution observes `beforeTx` and `afterTx`; evidence-disabled execution attaches no listeners. The host does not implement transaction semantics or duplicate verifier rules.

The canonical qualification used a frozen EthereumJS runner derivative. The public package keeps that execution port explicit instead of vendoring the private research apparatus.

## Verifier order

```text
strict JSON parse
-> exact top-level and nested schemas
-> lexical types and domains
-> canonical ordering and uniqueness
-> ranges and cross-references
-> commitment recomputation
-> lifecycle and semantic consistency
-> divergence derivation
```

Malformed data never reaches divergence derivation as trusted evidence.

## Two qualification tracks

The historical Alchemix result and the protocol-neutral engineering fixture answer different questions. Alchemix demonstrates real branch regeneration. The minimal fixture qualifies typed evidence, observational instrumentation, and offline verification. Neither result substitutes for the other.
