# Hook parameters: what is supported and what another one requires

The parameterized workflow supports two single-setting interventions in the `hookr-buy/0.1` profile, one
buy action at one authenticated checkpoint:

| Intervention | Baseline → variant | Worker profile | Since |
|---|---|---|---|
| LP Rewards `RulesConfig.lpBps` | 100 → 0..99 | `nitro-hookr-scenario/0.1` | 0.1 |
| Dynamic Fee | ON → OFF (maxFee 11500 → 3000, sensitivity 2 → 0, Root mode 3 → 2) | `nitro-hookr-dynamic-fee-off/0.1` (separate SDK home) | 0.3 |
| LP Rewards and/or Dynamic Fee as one typed set | LP100 + ON → lpBps 0..99 and/or OFF | `nitro-hookr-config-overlay/0.1` (separate SDK home, `CONFIG_OVERLAY.md`) | 0.4 |

Single-setting variants keep their 0.1 / 0.3 workers unless `--config-overlay` is given; both settings
together run on the config-overlay worker. This file records what supporting another parameter requires;
nothing else is accepted by `session-plan`, `session-ready` or `session-run`.

## What a new parameter must define

1. **Descriptor.** The exact storage location (account, slot, bit range) or call it changes, its type and
   unit, the allowed values and the baseline value, validated before anything is written, as `lp_bps_value`
   does today. A value equal to the baseline is refused as a variant.
2. **Authenticated original value.** The baseline value is read from the authenticated checkpoint state
   through the retained witness and checked against the declared original. A parameter whose original value
   is not provable from the witness is not supported.
3. **Overlay.** One deterministic rewrite of the prepared input (today: the `configurations.variant` word),
   with a fresh `scenarioCommitment`. Baseline input, action, environment, common setup and engine binding
   stay byte-identical to the session source.
4. **Static coverage.** Declared original-state reads of the new rule path, so the existing coverage check
   can say `COVERED` or `MISSING` offline. Missing reads are `NEEDS_AUTHENTICATED_STATE`, never fetched
   automatically.
5. **Profile preconditions.** Checks that the authenticated state admits the parameter change (for example
   that the rule is enabled for the pool), reported separately from coverage.
6. **Measure.** The quantity compared between worlds, named and defined in advance, with the existing
   verifier able to produce it from the recorded receipts. No measure is added after seeing results.
7. **Identity.** Variant identity derived from the descriptor and the session header only, so the same
   source, checkpoint and value give the same `variantId` and `scenarioCommitment` in any home.

## Constraints that stay

- The supervisor, host admission v4, resource limits and consent mechanism are not changed per parameter. A
  parameter that needs a different engine binding is a new profile with its own reviewed worker and its own
  SDK home, as Dynamic Fee OFF is; one SDK home holds exactly one registered runtime.
- One run is one `SCENARIO_BASELINE` and one `SCENARIO_VARIANT`; operation binding, one-shot consent,
  fail-closed stops and no automatic retry apply unchanged.
- Witness sufficiency for a value is established only by a completed native run of that exact prepared
  input. Dynamic coverage stays `UNKNOWN` until then.
- Results carry the existing assurance labels: recorded verification without EVM re-execution, economic
  assurance `UNRESOLVED`, zero qualified claims.

## Candidate order

1. **Dynamic Fee** — supported as OFF only (0.3). Other Dynamic Fee values (a different maxFee or
   sensitivity) need a new typed transform in the derivative worker; the current worker accepts exactly the
   two committed writes.
2. **Combined variants** — supported in 0.4 for LP Rewards + Dynamic Fee OFF by the config-overlay worker:
   a canonical set of typed interventions composed by disjoint masks on the authenticated original words
   (`CONFIG_OVERLAY.md`). A further kind is added to its registry, with mask, range and original-state
   precondition, and needs a rebuilt and reviewed overlay worker.
3. **Swap amount** of the common action: changes the action, not a rule, so baseline and variant would no
   longer share the action. Needs a profile decision before it can be a session variant.
4. **Transaction sequences**: several actions per world. Needs a new scenario shape and limits; out of
   scope for the session format as it is.

With two concrete cases the session adapter now has a typed descriptor per kind, a backend SDK per kind
and a profile-checked registration. A wider interface should be extracted only when a third case needs it.
