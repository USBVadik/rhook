# Integrated developer workflow — amount27 native pilot

The frozen Build06 Developer SDK workflow, using the exact Build07 input,
completed one new bounded native acquisition. Two heterogeneous native
implementations agreed on the same BRANCH. One ordinary lifecycle Claim
for the preselected subject verified retained ACTUAL `SUCCESS` → fresh
BRANCH `REVERT` under the admitted profile.

Sealed source terminal: `DIRECT_AMOUNT27_NATIVE_RESULT_ESTABLISHED`.
This is a result record, not a public Developer SDK release. See the
[machine-readable summary](developer-amount27-native-pilot-result.json).

## Exact question and result

| Item | Value |
|---|---|
| Chain / history | 4663 / `robinhood-4663-window-01` |
| Replay domain | 50 blocks / 321 total arrivals |
| Domain split | 41 before the target + 1 target + 279 downstream |
| Intervention target | `70397233:4` |
| Replacement | Exact 68-byte derived `Message.Data` encoding raw amount `27` |
| Selected subject | `70397233:5` |
| Retained ACTUAL | `SUCCESS` |
| Fresh A BRANCH / B BRANCH | `REVERT` / `REVERT` |
| Heterogeneous agreement | PASS |
| Ordinary verified lifecycle Claims | 1 |
| Recorded assurance | `ESTABLISHED_UNDER_PROFILE` |
| Bindings / obligations | 4/4 true / 9/9 `DISCHARGED_UNDER_PROFILE` |

Replacement Data:

```text
0x095ea7b300000000000000000000000065050a9b7e5075a2ba5ced7b1b64ee66262c40dc000000000000000000000000000000000000000000000000000000000000001b
```

The original transaction and all other declared message/context fields were
retained. Only derived `Message.Data` was replaced, from 68 bytes to 68 bytes;
the replacement encodes amount27. No transaction was removed or re-signed.
This does not change canonical chain history or establish a consensus-valid
alternative chain. No token decimals or economic threshold are asserted.

## What executed

The exact request was authorized before one sequential A/B acquisition:
A=1, B=1, ACTUAL=0. Both BRANCH producers completed the declared domain;
their 50-entry continuity vectors and all 321 lifecycle/state-root
observations agreed. ACTUAL uses retained authenticated controls.

The frozen SDK verified the selected Claim against the newly acquired world
and issued its comparison receipt. Recorded verification was `accepted=true`
with the bindings, obligations and assurance above. Reading this public
summary does not perform another verification or issue a live receipt.

Downstream lifecycle inspection contains **1 CHANGED / 278 UNCHANGED /
0 UNRESOLVED**, among **279 arrivals**. The changed row is `70397233:5`.
The map has `SDK_LOCAL_INSPECTION_ONLY` authority; it is not 279 independently
verified Claims. UNCHANGED concerns lifecycle, not gas, fees, logs, balances
or all state. The total of 321 includes arrivals before the intervention.

No retry, rebuild, witness expansion, intervention/subject substitution,
source repair or post-execution repair occurred.

The later mutable **Impact Discovery SDK** was tested separately on an
authenticated archive workflow. It was not used to execute this native
pilot. This milestone does not qualify that later SDK for new native
execution or establish independent external integration.

## Recorded commitments and provenance

| Identity | Commitment |
|---|---|
| Query | `ff0c4d2749714621bf8b067f8968c923f6a71340c517379746175e1fbe1b1e99` |
| Claim | `c2ff0c94e2bc3abe6c65c0786a6f01c502b0fe99eb1b293ce79e7a52fba791d4` |
| Envelope | `d84f6dade6f6699a54a033b8f634bc67793b111510d6d458180dcb3ae6dc2ae7` |
| Payload | `3d486945fa5ccba3fad9a4d92d363fe173e11785e945afa61d14b2a6ab91d0fc` |
| Verifier profile | `ba09405360a6426dd69f6468950a3300c78b27a772ab3caa230a5967b177dcbf` |

Canonical source FREEZE SHA-256:
`1a33b9833e9cca00cd3a6c6185b41ea3e483e971b4ab3ec4cecdb1de1b83d2c4`.
Canonical source MANIFEST SHA-256:
`5053a02b2cf718df07da1fcb50762e3f54663c1f5112b6cefc106eb93589f209`.
Hashes identify sealed records; they are not execution or producer proofs.
The complete native archive and acquired-world context remain private.

## Limits and distribution

This is one exact trusted-local intervention in the fixed Chain 4663 domain.
Consumer-accepted historical control, native runner, running host, pinned
checker and admitted profile remain trust premises. The result establishes
neither arbitrary-chain/history/intervention support nor universal verifier
correctness, production readiness, cryptographic execution proof, canonical
finality or protocol-level producer authentication. It does not determine
the precise internal revert cause or an amount-dependent economic threshold.

The private Developer SDK, native provider, witness, operational records and
full scientific archives are not distributed here. Neither importing the
acquired-world context into an external consumer nor external integration
qualification was established. The later Portable Evidence Consumer is a
separate local inspection tool; it is not included in this update and does
not upgrade this recorded result into independently established semantics.
