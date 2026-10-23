# Developer SDK Alpha v2: confirmed status

Acceptance03 completed one `doctor → prepare → replay → verify` workflow on the
founder's macOS arm64 computer. All seven arrivals of saved block 93251803 were
executed in independent original-parent ACTUAL/BRANCH worlds, nil Source,
RPC=WSS=B=0. ACTUAL matched canonical stateRoot, receiptsRoot and blockHash before
BRANCH was admitted. Both full result projections, including all receipts, gas
and economic observations, matched original Pair03 and the earlier portable replay.

The single checkpoint intervention clears only the 16-bit LP field at bits
160–175, from 100 to 0. The selected transaction's receipt-derived RHOOK output
was 291469365928126821002944 base units in ACTUAL and
294409762269997223561475 in BRANCH: +1.00881831355%. Subject gas was
1483206 → 1480996 (−2210). Token decimals are not assumed. EffectiveGasPrice is
null in the saved receipts; it is not treated as zero.

## Resource policy versus observed resources

| Value | Enforced developer v2 policy | Acceptance03 observation |
| --- | --- | --- |
| Worker RSS | sampled ceiling 1 GiB | sampled peak 330104832 bytes / 314.8125 MiB |
| Initial free headroom | ≥1.5 GiB, two normal-pressure samples | doctor minimum 3916922880 bytes; fresh internal admission minimum 3561521152 bytes |
| Runtime free headroom | ≥0.5 GiB; normal pressure, no swap-out/usage growth | saved runtime samples passed |
| Worker CPU and pair wall | ≤120 s each; CPU includes owned observers | CPU 0.214788 s; wall 1.233356 s |
| Worker file / combined stdout-stderr | 64 MiB / 64 MiB | worker stdout/stderr 0 bytes |
| Trusted CLI staging per-file limit | 256 MiB, external dispatcher only | complete 129825122-byte worker copied and hashed |
| Full workflow / replay | outer bounds 180 s / 140 s, cleanup included | workflow 4.801013 s; replay CLI 3.270600 s |

The host had 24 GiB physical RAM. The developer policy has no exact-24-GiB
equality, but this run does not validate another RAM size or computer. Free
headroom is a policy threshold, not a measured minimum engine requirement.
Sampled RSS can miss short peaks; headroom checks reserve no RAM and do not bound
launcher RSS. GOMEMLIMIT=512 MiB is advisory; GOMAXPROCS=2. RSS sampling is nominal
100 ms, host sampling nominal 250 ms, maximum telemetry gap 2 s. Existing CPU,
pressure/swap, pipe/storage, owned-process identity, signal and cleanup guards
remain in force. See the exact unchanged `sdk_alpha_v2/policy.json`.

Acceptance01 stopped before native dispatch because an external CLI file limit
blocked staging. Acceptance02 stopped at doctor for insufficient free headroom.
Those operations remain closed. Acceptance03 was a separately authorized fresh
attempt; it did not reuse or reopen either operation.

## Qualification boundary

- Confirmed: this fixed-case local CLI path, original-input admission, canonical
  ACTUAL gate, conditional independent-parent BRANCH and full saved-result verification.
- Not confirmed: a clean install on another computer, other OS/cloud runners,
  arbitrary contracts/blocks/interventions, network state acquisition, independent
  Rust replay or a general-purpose SDK contract.
- Go/Nitro replay agreement with earlier Go/Nitro is reproducibility evidence.
  Rust libraries compiled for Stylus support do not constitute a Rust replay.
- Engine result: GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED. Economic assurance
  UNRESOLVED, heterogeneous agreement NOT_EVALUATED, qualified Claims=0.

The source tree and v2 preparation README are preserved byte-for-byte as used by
the accepted build. Their pre-acceptance wording is historical. New status,
Quickstart and reference tools live outside the SDK's pinned source closure.
This keeps its source commitment unchanged; no new worker build or execution
is implied by the checkpoint. Raw evidence and the build record remain separate.

Private local commit only. No GitHub push, merge, release, publication or SDK
delivery is included. `externalDelivery=HOLD`.
