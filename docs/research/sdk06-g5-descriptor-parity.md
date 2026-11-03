# SDK 0.6 G5: four Hookr configurations on one descriptor-driven worker

**What this shows:** a hook profile described as reviewed data, executed by one native worker, reproduces the
four configurations that SDK 0.4 had produced with three different worker builds, field for field. It also
measures their gas interaction on a single build.

**What it does not show:** that the variants happened on chain, that another EVM client agrees, or that the
result holds for other blocks, pools or actions.

## The question

Hookr pools have two settings that SDK 0.4 could already change: the LP Rewards share (`lpBps`) and the Dynamic
Fee. SDK 0.4 ran each configuration on its own build of the native worker. SDK 0.6 replaces those
configuration-specific builds with one worker that reads a reviewed **profile descriptor** (`hookr-1`
revision 2). G5 asked whether that worker reproduces the accepted SDK 0.4 results exactly, and what the
gas interaction of the two settings is when all four configurations come from one build.

## Setup

| Item | Value |
|---|---|
| Chain | Robinhood Chain, chain id 4663 |
| Checkpoint | block 101935336, hash `0xbb9453c4…cb768d`, state root `0xa27e6a4d…45032c6` |
| Action | one synthetic signed buy of 0.001 ETH through the Hookr router, by an actor that does not exist at the checkpoint and is funded with 1 ETH in the scenario; gas limit 10,000,000 |
| Pool | `0x94d1a318…c6780` (the descriptor's pool) |
| Descriptor | `hookr-1` revision 2, SHA-256 `29f21a174b49a306737729da3ad48ef6e9438cd9a0c2a343504b8025ef9e9596`; catalogue `93a2f234…` |
| Worker | profile `nitro-hook-profile-overlay/0.1`; binary `a56db9e5…`, source commitment `4db4269a…`, policy `792b13a5…` (Go/Nitro) |
| Runs | three native operations, each executing a BASELINE world and a VARIANT world from the same checkpoint state |

Each operation needed an owner authorization record for that exact operation, one-shot consent and host admission,
and each was run once, with no retries. RPC and WebSocket requests during execution: 0.

The launch procedure was not followed perfectly, and the deviations are part of the record:

- **Run 1:** a pre-run audit passed before launch. The owner's commands ran in a different order than planned: the
  separate doctor check ran after the run (the run's own doctor had reported READY before anything was consumed),
  and the authorize-and-run step was invoked a second time. That repeat was refused before creating any
  authorization, consent or attempt, but it overwrote the saved output of the first authorization command. The
  authorization record itself is intact.
- **Run 2:** the required fresh pre-run audit right before launch was not performed; the last audit was about 45
  minutes older. After the run, the audit confirmed that the executed input, operation and worker were exactly the
  audited ones.
- **Run 3:** a fresh pre-run audit passed 36 seconds before launch; no deviation.

For Runs 2 and 3 a two-stage launcher enforced the doctor check, a fresh observation from the same terminal,
exclusive non-overwritable logs and a single invocation.

## Interventions

The descriptor turns each typed intervention into masked writes on authenticated original storage words:

| Intervention | Fields written (original → variant) | Storage words |
|---|---|---|
| `LP_REWARDS_BPS` = 23 | `lpBps` 100 → 23 | Rules config word 0 |
| `DYNAMIC_FEE` = OFF | `dynamicFeeSens` 2 → 0, `maxFeePips` 11500 → 3000, Root `rootDynamicFeeFlag` 1 → 0 | Rules config word 0, Root record word 0 |
| both | all of the above, in one merged Rules word plus the Root word | the same two words |

The descriptor also checks original-state predicates before writing and result invariants after, and refuses
conflicting kinds. You can print these writes yourself (see below).

## Results

| LP Rewards | Dynamic Fee | gasUsed | outer swap fee (pips) | actor target-token Transfer net | Source |
|---|---|---|---|---|---|
| 100 | ON | 1,646,794 | 11000 | 59085787608983877958575 | BASELINE of all three runs, identical |
| 23 | ON | 1,646,722 | 4840 | 59545408017658617127599 | Run 1 VARIANT |
| 100 | OFF | 1,590,327 | 11000 | 59085787608983877958575 | Run 2 VARIANT |
| 23 | OFF | 1,590,291 | 4840 | 59545408017658617127599 | Run 3 VARIANT |

Read across the table:

- LP 23 lowers the outer swap fee from 11000 to 4840 pips and raises the actor's Transfer-event net by
  459620408674739169024 base units (about 0.78%), with or without the Dynamic Fee.
- Dynamic Fee OFF leaves the fee and the Transfer net of this trade unchanged and lowers gas by 56,467 (LP 100)
  or 56,431 (LP 23).
- LP 23 lowers gas by 72 with the Dynamic Fee ON and by 36 with it OFF.

These are observations of one hypothetical trade at one checkpoint, not forecasts of profit.

## Gas interaction

I_gas = G(23, OFF) − G(23, ON) − G(100, OFF) + G(100, ON) = 1,590,291 − 1,646,722 − 1,590,327 + 1,646,794 = **+36**

If the two settings combined additively, LP 23 + DF OFF would use 1,590,255 gas; it uses 1,590,291. The
interaction is 0 for the fee and for the Transfer net. The actor's ETH balance interaction is −720,720,000 wei: every
balance difference between the four cells equals the gas difference times 20,020,000 wei per gas.

SDK 0.4 had measured the same +36 from three different worker builds, so a build difference could not be ruled
out as the cause. In G5 all four cells come from one build, and each equals its SDK 0.4 value. So, for this input,
the +36 does not come from the build differences. Why the two settings interact by 36 gas is not explained by this
measurement.

## Parity scope

Each run was compared with a pre-registered matrix built from the accepted SDK 0.4 records before any G5 run:

- **Required fields, per world (10):** receipt status, gasUsed, logs, full receipts, state root, receipts root,
  outer swap fee, actor Transfer net, actor balance and nonce. All 20 per run matched; a missing or empty field
  would have failed.
- **Same-input fields (10):** checkpoint, parent, chain config, inventory, common setup, actions, environment,
  limits, pool and release manifest. All matched.
- **Every other key of the recorded worlds** was compared directly with the SDK 0.4 records. Only the domain keys
  differ: the scenario commitment and the overlay record (descriptor hash and intervention commitment).

A separate offline check re-read the raw run files of all three runs. It confirmed one worker identity across
them, identical baselines and I_gas = +36, without using the SDK's own parity code.

## What kind of evidence this is

- **Same-engine historical-record parity.** The reference is RHOOK's own accepted SDK 0.4 output, also produced
  by Go/Nitro workers. This is not a comparison with another EVM client.
- **Hypothetical worlds.** Both worlds execute a synthetic signed buy on the checkpoint state. Neither the BASELINE
  nor any VARIANT is a transaction that happened on chain, and no comparison with chain history applies
  (`canonicalActualComparison: NOT_APPLICABLE`).
- **Recorded-integrity verification.** Each run's verifier re-checked the recorded files and commitments. It did not
  re-execute the EVM. The audits after each run did not re-run the worker either.
- **Authenticated starting state.** Prepared inputs carry a witness whose target words, contracts and code are
  authenticated against the checkpoint's state root. The synthetic header of the executed block is the scenario's
  own and is not a chain header.

## Reproduce what is public

From a clone, with Python 3.12+:

```sh
python3 -B sdk/examples/profile_descriptor_preview.py plan --lp-bps 23
python3 -B sdk/examples/profile_descriptor_preview.py plan --dynamic-fee OFF
python3 -B sdk/examples/profile_descriptor_preview.py plan --lp-bps 23 --dynamic-fee OFF
```

Each prints the writes, the changed fields, `interventionCommitment` and `capsuleId`. These equal the values in the
three G5 prepared inputs (`373c9466…`, `719c3dc7…` and `36738da0…` for the intervention commitments), and
`sdk/tests_cases/test_profile_descriptor_preview.py` checks them.

## What is not public

- The descriptor worker executable. Its Nitro/geth/CGO combination has distribution conditions that have not been
  cleared (`sdk/DISTRIBUTION.md`).
- The pinned SDK 0.4 input for this checkpoint, which contains the witness.
- The run records: authorization records, consent, host telemetry and the evidence directories.

Without these, a public clone cannot repeat the native runs or check their recorded output. It can check the
descriptor, the interpreters and the commitments above.

## Limits

- One checkpoint, one witness, one action, one pool and two intervention kinds.
- Dynamic Fee Tuning, the descriptor's third kind, is reviewed for offline planning only. The SDK refuses it for
  native operations, and G5 did not run it.
- Native parity is shown for these four configurations and their pre-registered fields, not in general.
