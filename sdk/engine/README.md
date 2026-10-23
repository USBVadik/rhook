# Hookr Pair03: private source checkpoint

This folder preserves the RHOOK-authored source and existing tests associated with the completed saved-block Go/Nitro Pair03. It is a source checkpoint, not a standalone SDK, native distribution, clean-room replay kit, execution authority or publication package.

The local `codex/pair03-portable-build` branch adds a [macOS arm64 build-only workflow](repro/README.md). It fetches pinned upstream sources and toolchains into a fresh build directory, generates ABI/header dependencies, and compiles working copies of the original Go modules with relative replacements. It does not execute the saved pair. See its recorded build result before making any portability claim.

The local `codex/portable-pair03-replay-01` branch adds a [portable saved-input launcher](repro/PORTABLE_PAIR03.md). It builds a new entrypoint around the unchanged engine and accepts explicit package/output paths. Preparation and synthetic tests grant no permission to execute the historical pair; a fresh, separately approved authority is required. The new worker has not replayed Pair03 yet.

## Contents

- `native/prestate/`: the complete RHOOK Go module from the frozen event-observed candidate, including original tests and the small chain-config test fixture. This preserves the package dependency closure without selecting unrelated third-party source trees.
- `native/saved-pair/`: the thin one-shot ACTUAL/BRANCH adapter, its tests and the exact embedded historical plan/configuration.
- `supervisor/pair03/`: the consumed-operation supervisor source, static verifier and existing mocked launcher tests.
- `supervisor/host-capture/` and `supervisor/legacy-admission/`: the retained bounded diagnostic capture, legacy host sensor/assessment source and local RHOOK helper modules.
- `SOURCE_PROVENANCE.json`: per-file hashes and original workspace-relative locations. All 77 copied source/configuration files are byte-identical to their authenticated local originals.

No raw scientific archive, runtime, witness, grants, real authority files, binary, credentials, raw demo ZIP or private dependency tree is included. The plan and provenance contain case identifiers/hashes, not witness bytes or permission to run.

## Known portability boundary

The copied source deliberately retains the original local build and fixture paths. There are 14 absolute-path references across eight source/configuration files. Some are synthetic test paths; others are Mac toolchain, module-replacement, original package and sealed-fixture locations. They are documented in `docs/CHECKPOINT_REVIEW.md` and remain a blocker for public distribution or a clean-room SDK claim.

Do not execute these snapshots as a new operation. The original controllers require frozen filesystem context, a native binary, external dependencies, exact sealed inputs and fresh explicit authority. None is activated or supplied by this checkpoint. Tests that refer to historical private fixtures are preserved as source and are not claimed portable.

No source refactoring, path rewrite, dependency download, native rebuild, host admission, RPC/WSS or EVM replay was performed to create this Git checkpoint. An independently runnable replay kit requires separate work and authorization.

## Recorded capability

Go/Nitro processed all seven original arrivals of block93251803 in two independent original-parent worlds. ACTUAL matched the pinned stateRoot, receiptsRoot and blockHash. Only after that match, BRANCH applied one checkpoint LP100-to-0 change at bits160–175. The selected transaction succeeded in both worlds; its receipt-derived RHOOK output increased by1.00881831355% and gas decreased by2210.

The result is `GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED`. Economic assurance remains `UNRESOLVED`; heterogeneous agreement remains `NOT_EVALUATED`; Rust/B=0; no qualified Claim is created. This observation does not qualify every acquisition/controller mode whose source is preserved in the module.

See `docs/PAIR03_STATUS.md` for the exact recorded values and `docs/VALIDATION.md` for the fresh checks and limitations.

## Repository boundary

The source checkpoint is stored in the separate private `USBVadik/rhook-source` repository. The older `USBVadik/privatrhook` repository retains its encrypted-backup role and history. `USBVadik/rhook` is public and is not modified by this preparation. This portability work is local until separately reviewed for push. No PR, release, SDK delivery or message to another person follows automatically. `externalDelivery=HOLD`.
