# Config Overlay Engine 0.1 (SDK 0.4)

One parameterized execution profile for typed Hookr configuration interventions, instead of one worker per
setting or per combination.

| | |
|---|---|
| Worker profile | `nitro-hookr-config-overlay/0.1` |
| Input / evidence domain | `rhook/hookr-config-overlay/0.1` |
| SDK home | `HOME/profiles/hookr-config-overlay` (one SDK home holds exactly one registered runtime) |
| Baseline world | the authenticated original: LP Rewards 100, Dynamic Fee ON |
| Variant world | one canonical set of typed interventions, applied before EVM execution |

## Supported interventions

| Kind | Parameter | Original (checked against the witness) | Fields written |
|---|---|---|---|
| `LP_REWARDS_BPS` | `lpBps` integer 0..99 | Rules `lpBps` = 100 | Rules config word bits 160..175 |
| `DYNAMIC_FEE` | `dynamicFee` = `OFF` | maxFee > base fee, sensitivity > 0, Root mode = 3 | Rules bits 40..63 → base fee 3000, bits 128..143 → 0; Root record byte 31: mode 3 → 2 |

A variant is LP-only, Dynamic-only or both. Arbitrary storage writes cannot be expressed: the registry of
kinds, their targets, masks, value ranges and original-state preconditions is part of the reviewed worker
source (`native/overlay.go`) and of its Python mirror (`rhook_alpha/config_overlay.py`).

## How the overlay is composed

- Start from the authenticated original Rules config word and Root record (the profile's pinned LP100 words
  and `ROOT_ON`, which admission checks against the witness-backed StateDB).
- Each assignment replaces only the bits under its own field mask. Masks of compatible interventions are
  disjoint; an overlap, a duplicate kind or an unknown kind is refused.
- After composition the worker checks that no bit outside the declared masks changed and that every
  written field holds its assigned value. Words 1..3 of the Rules configuration never change.
- The set is canonical (sorted by kind), so the order in which descriptors are given does not change the
  result, the `interventionCommitment` or the `scenarioCommitment`.
- The prepared input carries the canonical set and the derived writes. The worker recomputes the writes and
  admits the input only when they are identical; it never takes a precomputed word on trust.
- BASELINE gets no write. VARIANT checks every original word before the first write, so a mismatch cannot
  leave a partly applied overlay. The Root write happens only with Dynamic Fee OFF.

The LP23 + Dynamic Fee OFF Rules word is
`0x0000000007d0000000000017000000000000000000000000000bb80000000000` (lpBps 23, maxFee 3000,
sensitivity 0). Applying the existing Dynamic Fee OFF write after an LP write would instead store
`…0064…0bb8…` and reset lpBps to 100; that is why composition starts from the original word.

## Commands

```sh
rhook-cases --home HOME session-plan   --lp-bps 23 --dynamic-fee OFF --session ID
rhook-cases --home HOME session-plan   --lp-bps 23 --config-overlay --session ID
rhook-cases --home HOME session-ready  --session ID --lp-bps 23 --dynamic-fee OFF --runtime OVERLAY_RUNTIME.json --sensor rhook-host-sensor
rhook-cases --home HOME session-run    --session ID --variant VARIANT_ID --operation OPERATION --local-owner --mac-ready
rhook-cases --home HOME session-result --session ID --lp-bps 23 --dynamic-fee OFF --text
```

`--lp-bps` and `--dynamic-fee` together always select the overlay worker. A single setting uses the overlay
worker only with `--config-overlay`; without it, LP-only and Dynamic-only variants keep their 0.1 / 0.3
descriptors, `variantId`s and workers. Python: `sdk.plan_config_overlay_variant(lp_bps=23, dynamic_fee='OFF',
session_id=...)`; the 0.2 methods take `lp_bps=` and `dynamic_fee=` together, or `variant_id=`.

`session-plan` is offline: static coverage of the session's common reads, read-only MPT authentication of
the original Root and Rules target leaves (`interventionTargets`), and preparation bound to the reviewed
overlay worker identity (`config_overlay.ACCEPTED_OVERLAY_ENGINE`). It binds no operation and runs nothing.

## Compatibility

- The LP worker and the Dynamic Fee OFF derivative are not changed. Their inputs, `variantId`s,
  `scenarioCommitment`s and recorded evidence are accepted by their own profiles as before; the overlay
  worker refuses them (`SCENARIO_RUNTIME_DOMAIN`), and they refuse overlay inputs.
- The supervisor, host admission v4, resource limits, operation binding, one-shot consent and the existing
  `compare` are reused unchanged.

## Not established offline

- Dynamic coverage of the variant (whether its execution reads only state inside the witness) is
  established only by a native run of that exact input.
- No result of a combination is predicted, and none is derived from the results of separate runs.
- The registry is specific to the pinned Hookr generation; this is not a general engine for other hooks.
