# Profile Descriptor 0.1 (SDK 0.6)

`rhook/hook-profile-descriptor/0.1` describes one reviewed hook profile as canonical data. One interpreter,
in Go (`rhook_alpha/cases/scenario/native/descriptor.go`) and Python (`rhook_alpha/profile_descriptor.py`),
turns a typed intervention set into masked storage writes on authenticated original words.

The first descriptor, `hookr-1`, reproduces the SDK 0.4 Config Overlay Engine exactly. It also adds one
kind, Dynamic Fee Tuning, as data only.

**Current status (revision 2, SDK 0.6).** The descriptor is wired into admission, the worker, evidence
verification, the scenario API and the `profile-*` CLI commands through the worker profile
`nitro-hook-profile-overlay/0.1`. The catalogue reviews `hookr-1` revision 2 for offline preparation and native
execution; `LP_REWARDS_BPS` and `DYNAMIC_FEE` are reviewed for both, `DYNAMIC_FEE_TUNING` for offline preparation
only. Native operations bind only to the reviewed worker identity, and each run needs the owner's authorization of
that exact operation. G5 ran three configurations natively ([G5 case study](../docs/research/sdk06-g5-descriptor-parity.md)).
The worker and witness are not distributed, so a public clone covers the offline part
(`examples/profile_descriptor_preview.py`). Legacy workers refuse profile-overlay inputs.

The sections below specify the format. Statements about status inside them were written for G1 to G3 (revision 1,
offline only); [Later status](#later-status-g4a-to-g5) records what changed.

## Two separate entities

| | Execution engine | Profile descriptor |
|---|---|---|
| What | Checks state, admissibility, execution limits; produces evidence | Describes one contract family: identities, layout, admitted parameters, original-state predicates, measures |
| Where | Reviewed code (Go worker, Python SDK) | Data file plus its catalogue review record |
| Identity | Worker binary and source commitment | Descriptor SHA-256 |
| Trust | Code review and build provenance | SHA-256 proves only *which* descriptor. Whether it describes the contract correctly is the review status in `descriptors/CATALOGUE.json` |

The catalogue entry is separate from the descriptor bytes, so a review can be recorded after the hash is
fixed. Only RHOOK-internal descriptors listed in the catalogue are loaded, through `load_accepted` or
`LoadAcceptedDescriptor`. A file supplied by a caller is never loaded for workflow use.

| Review field | `hookr-1` revision 2 (current catalogue) | revision 1 (historical) |
|---|---|---|
| `status` | `RHOOK_REVIEWED_NATIVE_CANDIDATE` | `RHOOK_INTERNAL_OFFLINE_CANDIDATE` |
| `admits` | `OFFLINE_PREPARATION`, `NATIVE_EXECUTION` | `OFFLINE_PREPARATION` only; `NATIVE_EXECUTION` refused (`PROFILE_REVIEW_INSUFFICIENT`) |
| `independentReview` | `PASS_SEMANTIC_REVIEW_R2` with the review's SHA-256 | `PENDING` |
| `nativeExecution` | `NOT_ACCEPTED_NO_ENGINE_IDENTITY_G4B_G5_REQUIRED` (embedded text, kept unchanged because the catalogue bytes are part of the reviewed engine record; the engine identity and G5 came later) | `NOT_ACCEPTED_G4_G5_HOLD` |
| `kinds` | `LP_REWARDS_BPS` and `DYNAMIC_FEE`: `LEGACY_EQUIVALENT_SDK04`; `DYNAMIC_FEE_TUNING`: `OFFLINE_PROBE_BIND_RULES_ONLY` | the same |

## Encoding

- **Bytes.** Canonical JSON: sorted keys, no whitespace, ASCII only, exactly one trailing newline. At most
  1 MiB, nesting at most 64, no duplicate keys.
- **Integers.** Widths, offsets, words, ranges and identifiers are JSON integers ≤ 2^53 − 1. Constants and
  bounds are decimal strings.
- **Hex values.** Hashes and words are lowercase `0x` + 64 hex. Addresses are lowercase `0x` + 40 hex.
- **Order of checks.** Encoding (`DESCRIPTOR_ENCODING`), then shape (`DESCRIPTOR_SCHEMA`: unknown or missing
  keys, wrong types, out-of-schema integers), then semantics. Every key is required. Optional keys exist only
  where a closed choice needs them (operands, factors, parameter types, contract requirements, measure
  sources, slot derivations).

## Top-level keys

| Key | Content | Checked against |
|---|---|---|
| `schema`, `profileId`, `revision` | `rhook/hook-profile-descriptor/0.1`, `hookr-1`, `2` (the current catalogue revision; revision 1 was the G1 to G3 version) | version (`DESCRIPTOR_VERSION`) |
| `chain` | `chainId`, `engineFamily` (`NITRO` only), `arbosVersion`, `chainConfigSha256` (SHA-256 of the raw chain config bytes) | the input's chain config bytes; authenticated ArbOS state at admission (G4) |
| `release` | the release `manifest` verbatim, and `manifestCommitment` = `sha256("rhook/hookr-scenario/0.1/release\n" + canonical(manifest))` | recomputed (`DESCRIPTOR_RELEASE`); equals the accepted inputs' `releaseManifestSha256` |
| `contracts` | `name`, `address`, `requirement`. `CODE_HASH_EQUALS` adds `runtimeCodeHash` and `releaseRole` | each pinned contract must be exactly the manifest entry of its role (`DESCRIPTOR_CONTRACT`); at authentication, code hash and code preimage must match (`PROFILE_CODE_IDENTITY`). `CODE_PRESENT` requires code (`PROFILE_TOKEN_CODE_REQUIRED`) |
| `pool` | pool key and `hooksContract` (a code-pinned contract) | `poolId` recomputed as `keccak256(abi.encode(PoolKey))` (`DESCRIPTOR_POOL_ID`) |
| `targets` | `name`, `contract` (code-pinned), `slot`, `words` (1–8 consecutive words), `slotDerivation` | the slot is recomputed (`DESCRIPTOR_SLOT_DERIVATION`); targets must not overlap |
| `configurationTarget` | the target whose words form `configurations` in a prepared input | |
| `fields` | `name`, `target`, `word`, `offset`, `width`, `type` (`uint`, `flag` = 1 bit, `address` = 160 bits), `unit`, `semanticsSource` | inside the target and 256 bits; no overlap with another field (`DESCRIPTOR_FIELD_LAYOUT`) |
| `originalState` | `policy: EXACT_WORDS` and every word of every target | admission authenticates these words against the witness |
| `interventions` | kinds, sorted by name | see below |
| `action` | `HOOKR_ROUTER_EXACT_INPUT_BUY_V1`: code-pinned router, swap ABI, fixed amount, gas options, minimum output, price limit, `zeroForOne`, engagement, no campaigns, one `LEGACY` transaction | named action type (`DESCRIPTOR_ACTION`) |
| `setup` | `PUBLIC_SIMULATION_SIGNER_V1` actor seed, funding, nonce 0, original absence required | `DESCRIPTOR_SETUP` |
| `measures` | `SUBJECT_RECEIPT_GAS_USED`, `SUBJECT_RECEIPT_STATUS`, `WORLD_ACTOR_BALANCE_AFTER`, `EVENT_DATA_WORD` (emitter, topic0, topic1 `POOL_ID`, word), `ERC20_TRANSFER_NET` (emitter, topic0, party `ACTOR`) | closed set (`DESCRIPTOR_MEASURE`); fixed before any result |
| `witness` | `readHints` (repository path and SHA-256 of `prefetch.json`, `trace-hints.json`), `systemSubjects: NITRO_ARBOS61_SCENARIO_SYSTEM_V1`, `targetWords: ALL_DECLARED_TARGET_WORDS` | `DESCRIPTOR_WITNESS`; the tests check the hint hashes against the files |
| `provenance` | `sources` (kind, ref, SHA-256), `derivations`, `contractSources` | recorded, not trusted |

### Slot derivations

- **`ERC7201_MAPPING_POOL_ID`.** The slot is
  `keccak256(poolId ‖ erc7201(namespace)) + fieldOffset`, where
  `erc7201(n) = keccak256(uint256(keccak256(n)) − 1) & ~0xff`.
- **`FIXED`.** The slot is pinned without a derivation.
- **`hookr-1`.** Rules config is `hookr.rules` + 1; the Root record is `hookr.root` + 0. Both recompute to
  the accepted SDK 0.4 slots, and `erc7201("hookr.rules")` equals the profile's `rulesNamespace`.

### Intervention kinds

```json
{"kind": "...", "parameters": [...], "requires": [...], "assign": [...], "ensures": [...], "conflictsWith": [...]}
```

- **`parameters`.** Either `uint` with `min` and `max`, or `enum` with `values`. A caller gives exactly the
  declared parameters (`PROFILE_PARAMETER`).
- **`requires`.** Predicates on the **authenticated original** field values.
- **`assign`.** `field := {const}`, `{param}` (a `uint` parameter) or `{field}` (an original field value).
  Address fields cannot be assigned.
- **`ensures`.** Predicates on the **resulting** field values.
- **`conflictsWith`.** Must be symmetric. Masks are disjoint in any case: two assignments to the same bits
  are refused (`PROFILE_MASK_CONFLICT`).

Predicates come from a closed vocabulary, with no expressions or scripts:

- `{"compare": {"left": operand, "op": eq|ne|lt|le|gt|ge, "right": operand}}`.
- `{"productBound": {"factors": [...], "op": lt|le, "bound": "decimal"}}`, with 1 to 4 factors. Each factor
  is one of `{"field"}`, `{"square"}`, `{"diff": [a, b]}` or `{"constMinusSquare": ["c", f]}`. A negative
  factor stops with `PROFILE_NEGATIVE_FACTOR`.

## Interpretation (same order in both languages)

1. Every target word is supplied (`PROFILE_ORIGINAL_STATE_UNAVAILABLE`). Each equals the reviewed original
   (`PROFILE_ORIGINAL_WORD`).
2. The set is checked:
   - 1 to n items, each `{kind, parameters}`;
   - known kinds;
   - no duplicates;
   - no declared conflicts;
   - typed parameters within range.

   Canonical order is by kind.
3. For each kind, in canonical order:
   - its `requires` on the originals (`PROFILE_ORIGINAL_PRECONDITION`);
   - its assignments: value width (`PROFILE_VALUE_WIDTH`) and mask overlap.
4. All `ensures` on the result (`PROFILE_INVARIANT`).
5. Bits outside assigned masks are unchanged (`PROFILE_NON_TARGET_BITS`). Each field reads back its value.
6. Writes go per target word in descriptor order. A used word that does not change is `PROFILE_NO_EFFECT`.

## Safety envelope (independent of descriptor content)

- **Storage only, on declared words.** A write list is accepted only for declared target words of
  code-pinned contracts (`PROFILE_WRITE_TARGET`). The world interface exposes storage reads and writes only.
  There is no path to code, balance or nonce, and descriptor keys that would express one are unknown keys
  (`DESCRIPTOR_SCHEMA`).
- **All originals before any write.** Every original word is checked before the first write
  (`PROFILE_ORIGINAL_WORD_CHANGED`, no partial overlay).
- **BASELINE unchanged.** The baseline world never writes.
- **Missing state is never zero.** Authentication checks the state error after every read. A missing witness
  node is `PROFILE_ORIGINAL_STATE_UNAVAILABLE`, never zero code or zero storage.
- **Legacy strictness kept.** `EXACT_WORDS` keeps the SDK 0.4 rule: all four Rules words and both Root words
  must equal the reviewed original. Per-field predicates are checked **in addition**. They do not widen the
  set of admissible checkpoints.

## Root record flags: one source of field-width semantics

SDK 0.4 had two definitions of the Root "mode" byte:
- `overlay.go` treats it as an 8-bit field, with `mode == 3` and `3 → 2`;
- `interventions.py` uses the single bit 248.

`hookr-1` defines the byte once, following `INTERVENTIONS.md` ("mode 3 includes Dynamic Fee and recapture;
mode 2 retains recapture"):

- `rootDynamicFeeFlag`: bit 248;
- `rootRecaptureFlag`: bit 249;
- `rootFlagsReserved`: bits 250–255.

`DYNAMIC_FEE` requires Dynamic Fee 1, recapture 1 and reserved bits 0, which is exactly `mode == 3`. It
assigns only bit 248. The written words are identical to SDK 0.4 for all 201 configurations. The legacy
constants stay in the legacy code and are not used by the interpreter.

## Prepared-input binding (`rhook/hookr-profile-overlay/0.1`)

A prepared input is the session source with the following changes:
- `schema` is the profile-overlay schema;
- `engine` holds the engine identity;
- `configurations` holds the composed words of the configuration target;
- `origin` is `AUTHENTICATED_CHECKPOINT_PROFILE_OVERLAY`, with a capsule over the checkpoint and an intent
  that names the descriptor SHA-256;
- a new `profileOverlay` holds:
  - `descriptor {profileId, revision, sha256}`;
  - `originalStateRoot`, `poolId` and `codeHashes`;
  - the canonical `interventions` and the derived `writes`;
  - `interventionCommitment`.

**How the descriptor SHA-256 is bound:**
- the scenario commitment includes `profileOverlay`;
- the operation commitment binds the input SHA-256;
- the session variant descriptor (`HOOK_PROFILE_OVERLAY`) includes `descriptorSha256`, so the `variantId`
  changes with the descriptor.

**What validation recomputes:** commitment, descriptor identity, canonical order, the transform and its
writes, configuration words, origin, then pool, chain and release. The codes run from
`PROFILE_SPEC_COMMITMENT` to `PROFILE_SPEC_BINDING`.

The legacy `Parse`, `Admit` and `AdmitOverlay` refuse such inputs. Descriptor-based variants get new
identities; legacy identities and commitments do not change.

## Not included

- Arbitrary storage patches, expressions or scripts.
- User-loaded descriptors.
- Engines other than Nitro.
- Actions other than the Hookr router buy.
- Transaction sequences.
- Economic or result predictions.
- In the G1 to G3 version, wiring into admission, the worker entry, the evidence verifier, the session adapter
  or the CLI. G4A added that wiring (see below).

Witness sufficiency for any new kind or value is established only by a completed native run of that exact
input.

## Later status (G4A to G5)

The status lines above describe G1 to G3. Since then:

- **G4A** wired the descriptor worker profile `nitro-hook-profile-overlay/0.1` into admission, the worker,
  evidence verification and the scenario API (source and offline tests only).
- **Revision 2** of `hookr-1` bounds Dynamic Fee Tuning by the pool's Root caps (data only). Its catalogue
  entry is `RHOOK_REVIEWED_NATIVE_CANDIDATE`: LP Rewards and Dynamic Fee are `LEGACY_EQUIVALENT_SDK04`,
  Tuning stays `OFFLINE_PROBE_BIND_RULES_ONLY` and is refused for native operations.
- **G4B** built the worker twice, byte-identically, in one fixed neutral root.
- **G5 preflight** records three separate facts:
  1. build verification: the G4B records, outside the SDK;
  2. the reviewed engine identity, `profile_descriptor.PROFILE_ENGINE_RECORD`: source, binary and policy
     SHA-256, linked profile, descriptor `hookr-1` revision 2 and catalogue SHA-256. It makes an operation for
     exactly this worker bindable and authorizes nothing;
  3. execution authorization, per operation: `cases.scenario.api.authorize_profile` writes a private record
     for one exact `operationCommitment`. `api.run` and `ProfileOverlayExecutionSDK.run` refuse a
     profile-overlay operation without it (`PROFILE_NATIVE_AUTHORIZATION_REQUIRED`), before any attempt
     marker, consent key, authority or worker run. Host admission must be v4.

  The embedded catalogue text `NOT_ACCEPTED_NO_ENGINE_IDENTITY_G4B_G5_REQUIRED` is unchanged: the
  catalogue is part of the worker source commitment. Preparation (`profile_overlay.prepare`) adds static
  coverage of the source and independent trie-only authentication of every declared contract and target word.
  `profile_parity` holds the pre-registered G5 matrix and strict comparators: a missing, null or empty
  required field fails.
- **G5** (3 November 2026) ran the reviewed descriptor worker natively, once per configuration, on checkpoint
  101935336: LP23 + Dynamic Fee ON, LP100 + Dynamic Fee OFF and LP23 + Dynamic Fee OFF. Every pre-registered
  field of both worlds matched the accepted SDK 0.4 records, and the four-configuration gas interaction was
  +36 (`docs/research/sdk06-g5-descriptor-parity.md`). The catalogue text above is still the embedded one;
  that acceptance is recorded outside it. The worker, the witness and the run records are not distributed.

`examples/profile_descriptor_preview.py` exposes the offline part of this file to a public clone: the
catalogue, a descriptor's kinds and fields, planning of an intervention set with its writes and commitments,
validation of a caller's descriptor file (which is then still not loaded), and the native requirements.
