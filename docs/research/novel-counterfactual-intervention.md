# One amount changed; the next transaction reverted

On Robinhood Chain 4663, one preselected Data-only intervention produced a
new alternative world in the admitted history. Setting an earlier encoded
amount to zero changed the next transaction's lifecycle from `SUCCESS` to
`REVERT`. Two heterogeneous native BRANCH implementations agreed, and one
ordinary lifecycle Claim was accepted under the pinned profile.

Recorded source terminal: `NOVEL_DEVELOPER_INTERVENTION_NATIVE_EXECUTION_PASS`.

[Explore the recorded demo](https://robinhook.tech/counterfactual), or read the
[machine-readable summary](novel-counterfactual-intervention-result.json).
Opening the demo performs no fresh replay or independent verification.
The real chain was not changed.

## Exact question

| Item | Value |
|---|---|
| History | `robinhood-4663-window-01` |
| Chain | 4663 |
| Checkpoint | 70397226 |
| Window | Blocks 70397227–70397276; 50 blocks |
| Total domain | 321 arrivals: 41 before + 1 target + 279 downstream |
| Target | `70397233:4` |
| Selected subject | `70397233:5` |
| Projection | Lifecycle, after the selected envelope |
| Selected comparison | ACTUAL `SUCCESS` → BRANCH `REVERT` |

Target transaction:
`0x76dd75c882c881337da7fb4569ade2bde0bcee7cbb00af5b8c6fcdf057d1ff57`.
Subject transaction:
`0x0ca25674de4611a9e4537cd7e41371f693d45bc1119562818336d3389039a5c0`.

The intervention replaces only the final 32-byte amount word of derived
`Message.Data`, from raw uint256 `233905240858889562587707` to `0`. Both Data
values are 68 bytes. The selector `0x095ea7b3`, spender
`0x65050a9b7e5075a2ba5ced7b1b64ee66262c40dc`, original signed transaction and
every non-Data message field are retained. No transaction is removed or
re-signed. This is an analytical derived-message intervention, not a
consensus-valid alternative chain. No token decimals are asserted.

Replacement Data:

```text
0x095ea7b300000000000000000000000065050a9b7e5075a2ba5ced7b1b64ee66262c40dc0000000000000000000000000000000000000000000000000000000000000000
```

## What was established

ACTUAL uses retained authenticated controls. One fresh, authorized A BRANCH
execution and one fresh, authorized B BRANCH execution each completed the
50-block / 321-total-arrival domain. The implementations are Go/Nitro/geth
and Rust/arb-revm. There were zero fresh ACTUAL executions.

After world establishment, the consumer inspected the downstream lifecycle
map and requested one ordinary Claim for the selected subject. Its recorded
verification has `accepted=true`, assurance `ESTABLISHED_UNDER_PROFILE`,
four true binding flags and nine `DISCHARGED_UNDER_PROFILE` obligations.
The oriented comparison came from the original direct SDK-issued receipt.

The complete downstream map contains **1 CHANGED / 278 UNCHANGED /
0 UNRESOLVED**, among **279 downstream arrivals**. The only changed row is
`70397233:5`. These are local lifecycle inspection results, not 279
individually verified Claims. Thirteen downstream arrivals reverted in both
histories. UNCHANGED does not establish equal state, balances, logs, gas or
fees. Rows other than the selected subject have `NO_RECORDED_CLAIM` in the
public demo.

An accepted Claim can establish a negative lifecycle answer. It does not
mean the branch transaction succeeded or authorize an application action.
The page's `DOES_NOT_SURVIVE` policy illustration uses the recorded
comparison and accepted trust assumptions; it creates no live receipt.

There were no retries, repairs, rebuilds, witness expansions, resource
increases, intervention/subject substitutions or protocol changes in the
sealed execution. This result is separate from the earlier six-case native
conformance and clean-room verifier experiments.

## Recorded identities

| Identity | Value |
|---|---|
| Request | `566c2922b8ad77ee1bd83b7f9056bcfc06ab961403f084bedf743ed1ca869f7b` |
| World | `1b7ad048983eb4bc7bc42e41a4d93903660e354206915e7d882272510b6314e1` |
| Branch context | `83f2d9c9e8098ace069cb4313d7e5c9397dd432bb63de9f585933cc84ef5055e` |
| Query | `e7030e8d5ff7c02a63d79edce567d4532073963a19129aa3267d150b11f7f57a` |
| Claim | `a804abfd61784a8209ac7298d3c200415772061ee39eb04449390f11a3fc4978` |
| Payload | `70a38c0ce2c179c91e7df473b98beae4cc5f5d762ecddd79aa77163e7c770b7d` |
| Verifier profile | `ba09405360a6426dd69f6468950a3300c78b27a772ab3caa230a5967b177dcbf` |

The [public inspection export](https://robinhook.tech/assets/counterfactual/data/recorded.json)
is 122,324 bytes, SHA-256
`d0556d16ffbd6bdfedd99b2111b64e5bfc303087c4913e8f608b854cdb75be15`.
It includes the Query, Claim, Envelope and recorded verification report,
but excludes the original Packet and admitted acquired-world context. It is
not a standalone verification package. Hashes identify bytes; they do not
establish execution or producer identity.

The internal canonical source was sealed on
`2026-10-11T20:12:13.615445+00:00`, with FREEZE SHA-256
`aa50cac11490ff2f328f47d4a4d896b7c1f7ec96e16782ee708e151c5a8968c7`
and MANIFEST SHA-256
`6b74c78a2ade3efb1b71b661bff10a4ad16daee5416505ebbe02080babb7813d`.
The excluded original Packet is 650,698 bytes, SHA-256
`4c0b629f159770587a779eb32d8cef98104fc949a196c835a677187a35a26f84`.

## Scope and access

This is one exact new request in a fixed Chain 4663 / v011 domain. Target
admission is not universal witness sufficiency. The accepted profile proves
lifecycle; approve-shaped encoding alone does not establish deployed ERC-20
compliance, token balances/allowances or the exact internal revert cause.

Trust remains consumer-accepted: historical native anchor, retained ACTUAL
control, authenticated native runner and running host, pinned checker, and
agreeing heterogeneous observations. Canonical finality and protocol-level
producer authentication are not established. This is not cryptographic
execution proof, production readiness, arbitrary-chain/history/intervention
support or external organizational independence.

The native acquisition SDK, witnesses, sidecars and full execution archive
remain private. This repository update publishes a result, not new native
SDK exports or an arbitrary-transaction service. A Packet alone cannot
import the acquired-world verification context.

The public [Genesis Docker example](../../examples/robinhood-v4/README.md)
reproduces a different bounded router-input intervention, with 16/317
changed downstream lifecycles. Genesis illustrates propagation;
Counterfactual adds recorded world inspection and one selected verified
answer. Their interventions, denominators and evidence paths are separate.
