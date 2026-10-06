# Real-history counterfactual application

Result: `REAL_HISTORY_COUNTERFACTUAL_APPLICATION_PASS`.

For downstream subject `70397229:10` on Chain 4663, the retained authenticated
ACTUAL controls establish `SUCCESS`, while fresh, previously authorized
A/B BRANCH executions establish `REVERT`. The two heterogeneous native
implementations agree on the required surfaces for each world. A portable
RHOOK Claim was verified with `ESTABLISHED_UNDER_PROFILE`, and the consumer
result is `DOES_NOT_SURVIVE`: successful completion does not survive this
exact calldata intervention.

## Declared domain and intervention

| Parameter | Value |
|---|---|
| Chain | 4663 |
| Entire replay domain | 50 blocks / 321 arrivals |
| Intervention target | `70397229:5` |
| Downstream subject | `70397229:10` |
| ACTUAL lifecycle | `SUCCESS` |
| BRANCH lifecycle | `REVERT` |
| Consumer result | `DOES_NOT_SURVIVE` |

At target `70397229:5`, derived Message.Data was replaced from 68 bytes to 0x.
Only derived `Message.Data` changed, after original sender/message derivation
and before native validation and execution. The transaction itself, original
signed envelope and every other declared message field remained in place.
Original signed `Message.Tx` supplies declared poster-cost accounting;
replacement Data drives intrinsic gas and execution.

The 321 arrivals cover the **entire declared replay domain**, including the
prefix before the intervention; they are not 321 arrivals after it.

## Establishment and verification

ACTUAL comes from retained authenticated controls for both implementations.
BRANCH comes from their fresh, previously authorized executions, one per
implementation. The application continuation consumed the sealed observations
without new native execution.

Agreement covers the required ordered arrival identities, lifecycles and
state roots; receipt, log, return, gas and fee surfaces; block roots,
continuity and historical context; intervention confinement and the subject
projection. Producer-specific diagnostics retain their frozen comparison
semantics; agreement does not assert byte-identical heterogeneous raw logs.

Verification returned `accepted=true` and `ESTABLISHED_UNDER_PROFILE`.
All four binding flags were true and all nine coverage obligations were
`DISCHARGED_UNDER_PROFILE`. A genuine receipt issued and accepted by the same
client supported the `SUCCESS` / `REVERT` comparison and `DOES_NOT_SURVIVE`
result. Documentary receipt records are not portable verification authority.

## Recorded commitments

| Identity | Exact commitment |
|---|---|
| Query | `c2a841334d35593db31324a22edad98082272731d6634d577ea64a49e88f60a3` |
| Claim | `df5c13faf5059bfddc3de485a2dff88937aa5c31cf6784eecd5e612ed22c48c7` |
| Envelope | `416fd64755d60b9cac8271111a48608fb20d84e2c1a3e133477f57fcd5af1fe0` |

The [machine-readable summary](real-history-counterfactual-application-result.json)
records these commitments and the sealed canonical source identities.
Commitments identify the recorded objects; they do not establish producer
identity or prove execution. The internal archive and native sidecar evidence
are not distributed here. This summary alone cannot reproduce the milestone
or authenticate unavailable archive contents, and does not expand the APIs
or supported domains shipped in this public checkout.

## Limits

This is a bounded known-case integration for the exact admitted history,
profiles, subject and Data-only intervention. It is not prospective unseen-case
discovery or external organizational independence. The retained ACTUAL controls
and fresh, previously authorized A/B BRANCH executions remain distinct.

The result does not establish arbitrary-chain/intervention or subject support,
production readiness, cryptographic execution proof, canonical finality or
protocol-level producer authentication. Consumer-accepted historical control,
native runner and running-host trust premises remain applicable. It establishes
the subject's lifecycle change, without an asset-recovery or revocation claim.
