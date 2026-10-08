# Bounded Generic Native Branch

Result: `BOUNDED_GENERIC_NATIVE_BRANCH_CAPABILITY_PASS`.

The bounded native provider established two alternate worlds from declared
Data-only interventions on one Chain 4663 history. Each request executed
Go/Nitro/geth and Rust/arb-revm BRANCH implementations once, with complete
heterogeneous agreement, authenticated process/job/world seals and an
EstablishedWorldPair. Each pair issued an opaque `BranchHandle` for later
questions. ACTUAL used retained authenticated controls.

The first request reproduced a known lifecycle result through an ordinary
verified Claim. Only after its full continuity PASS did the second request
execute the preserved, previously unseen intervention. Both stages passed.

## Declared domain and results

The fixed H/v011 domain contains **50 blocks / 321 arrivals in total**,
including arrivals before each intervention. It is not 321 downstream arrivals.

| Case | Target | Derived Data replacement | Prefix / target / downstream | Downstream CHANGED / UNCHANGED / UNRESOLVED |
|---|---|---|---|---|
| Continuity R | `70397229:5` | 68 bytes → `0x` | 15 / 1 / 305 | 1 / 304 / 0 |
| Previously unseen C′ | `70397230:1` | 484 bytes → `0x01` | 22 / 1 / 298 | 0 / 298 / 0 |

For R, derived Message.Data was replaced from 68 bytes to 0x.
For C′, derived Message.Data was replaced from 484 bytes to 0x01.
The original signed transaction and all non-Data fields were retained in
both cases. The declared replacement drives native execution; this is an
analytical branch under the admitted envelope policy.

Each implementation completed 50 blocks and 321 arrivals per request.
B executed only after valid A completion and seal. Both complete BRANCH
outputs agreed, and the full native authentication and consistency checks
completed before a world or handle was issued. Agreement includes the
ordered lifecycle/root, receipt/log/bloom, return/revert, gas/L1-gas/fee,
block/receipt-root, continuity and L1-history/BLOCKHASH surfaces, together
with intervention confinement and original-envelope relations.

R's complete changed-row set contains only downstream subject `70397229:10`:
ACTUAL `SUCCESS`, BRANCH `REVERT`. Its ordinary portable Claim returned
`accepted=true`, `ESTABLISHED_UNDER_PROFILE`, all four binding flags true
and all nine coverage obligations `DISCHARGED_UNDER_PROFILE`. The comparison
came from a genuine client-issued receipt.

Before C′ execution, its native invocation counts were A=0/B=0, no world
existed and its scientific outcome was unknown. Its full downstream impact
map was frozen before subject selection. The complete changed-row set is
empty, so no subject or Claim was selected and no intervention was substituted.
**UNCHANGED means lifecycle unchanged only**, without a claim of state,
gas, fee, log or execution-result equality for those rows. The downstream
map excludes the intervention target.

In total: four fresh BRANCH executions, two established worlds, two
BranchHandles and one ordinary verified Claim. Fresh ACTUAL executions,
retries, repairs, rebuilds, fallback, witness expansion, state patching,
reselection and post-freeze grant/environment/budget changes were all zero.

## Measured developer surface

World acquisition precedes subject selection. For an already configured,
authorized private deployment, the measured call shape is:

```js
const branch = await rhook.branch({
  history: rhook.admission.history,
  intervention: { target: '70397229:5', replace: { messageData: '0x' } }
})
const summary = await branch.summary()
const impact = await branch.impact({ scope: 'downstream', projection: 'lifecycle' })
const answer = await branch.claim({ subject: '70397229:10', projection: 'lifecycle' })
```

| Method | Contract |
|---|---|
| `rhook.branch(input)` | Acquires a subject-free world under an exact consumer-authorized request/profile; issues a handle only after establishment. |
| `branch.summary()` | Reports the admitted history, intervention, world/context identities and downstream lifecycle counts. Local inspection authority. |
| `branch.impact({scope, projection})` | Returns the complete ordered lifecycle map for `all` or `downstream`. Local inspection authority. |
| `branch.compare({subject, projection})` | Runs the ordinary Claim/verification path and returns receipt-derived oriented values and classification, or `UNRESOLVED`. |
| `branch.claim({subject, projection})` | Returns Query, Claim, Envelope, payload, portable packet, verification and receipt-derived comparison, or an unresolved result/error. |

Only `lifecycle` projection is admitted here. `summary()` and `impact()`
do not issue comparison receipts; `impact.claim(subject)` promotes a row
through ordinary Claim construction and full verification. The runtime
gate exercised summary, impact and Claim materialization; `compare()` is
part of the measured surface, not an additional call made by this gate.
Missing knowledge, witness, resource establishment or heterogeneous agreement
stops acquisition without a world or handle; host failure never becomes EVM
`REVERT`, and a fresh request never silently falls back to archived execution.

This is an API record for the measured private deployment. The public
checkout continues to export core/runtime/host; this checkpoint does not
ship the bounded native SDK, its private deployment or an installable native
acquisition workflow. No new implementation tree or experimental tests are
copied into this repository. Existing public tests continue to check the
shipped public stack and publication boundaries.

## Recorded identities

| Identity | R | C′ |
|---|---|---|
| Request commitment | `08a1c130f98cb6fa395d19dc69d933ab0bf8925b1944f003093c8e9be4f6fd15` | `b820718190d00ca94abcc2d2bc08bedeaf837e0565699ec4852ae829907d35c4` |
| World | `e68bb793a95f6a433c880998306169f5fb8b84ddc5255b083ab064ca9aef78ca` | `b9a6ef182364d11cc0a034dec46b7e6ec98d6e54e7e1e2720288181b51a486a3` |
| Branch context | `3c9fe7b50c909513ccab31e5a69a9edfe5cbe70a016b8dfaaaeac8df3946aa62` | `5f5640b9425cbdff709e97c57c8d2ce6023badcd30395407f2af22f714650c3b` |

R's Query commitment is
`d2e6e7121d0b26d7146776afa7193b66d37b33d11f010fa8a5d16e7a9fa28b90`;
Claim commitment is
`3fde5ae06636c3c1c27af2a144f9a5610320c34865d9c6a8461969fd31cdf11f`.
The [machine-readable summary](bounded-generic-native-branch-result.json)
also records payload, provider, verifier and model commitments and sealed
source identities. These identify recorded objects; hashes alone do not
authenticate an unavailable archive or establish execution or producer identity.

## Limits

This is bounded native continuity plus previously unseen-world acquisition
for two declared interventions in one admitted history, using fixed v011,
native implementations, profiles, witness material and lifecycle projection.
Target grammar admission does not establish successful acquisition for every
target or replacement. Zero changed downstream lifecycle rows is a valid
result, not a reason to select a different intervention.

The result establishes neither arbitrary-chain/history/intervention support,
universal generativity, production readiness, cryptographic execution proof,
canonical finality nor protocol-level producer authentication. Consumer-accepted
historical controls, native runner and running-host trust assumptions remain
applicable. Portable evidence requires its matching consumer-admitted context
and profile; the Claim alone is not an execution proof.

The private execution archives, native diagnostics, evidence directories,
tarballs and coordinator records remain excluded. This summary alone cannot
reproduce the milestone. No external application integration is established
by this result. See [limitations](../limitations.md).
