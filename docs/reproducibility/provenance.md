# Reproducibility and provenance

This repository is a curated packaging derivative of an immutable research workspace. It contains the minimum implementation needed to inspect the evidence model and run the offline verifier. The full research archive is intentionally excluded.

## Canonical component bindings

| Component | Frozen manifest SHA-256 |
|---|---|
| evidence core | `5e8e639b5b7066acef1074acf5a1f102242f6bcf4718e0f1418252136e6f4747` |
| typed runtime | `517f3c06faaabfc75df4c33478f38a35f73132044a5d33b6f7359080734b1df5` |
| execution host | `aa9917a016afef531028e1d1849faa69d84e2306c048a4f5deb9b088be94d57c` |
| historical runner | `9f1d783331b879066efc174eb287595bde2cfad674e5a157ad5fc9c7f1956dbf` |

The minimal transcript file SHA-256 is `3c13a90e29b4b52967418784b5ff544b2e7c209676550cd56acdc7d3f13bd373`. Its internal commitment is `3914ca428fc00093ae0cb78bf66f9f148a10f7de2a7c90fd9189671b872a57a9`.

## Packaging changes

The public package keeps evidence semantics intact while removing private workspace coupling:

- core-02 builders and core-03 strict verifiers now import each other locally under `core/src/`;
- internal requirement labels were removed from comments and public error names were simplified;
- the nominal brand symbol was renamed for the public package; serialized evidence is unaffected;
- runtime imports the local core entry point;
- host imports local core/runtime entry points;
- the host execution function is dependency-injected rather than imported from a private research path;
- freeze scripts, workflow logs, authorizations, provider configuration, failed attempts, and superseded versions are omitted;
- one protocol-neutral transcript is included; large execution artifacts are not.

These are packaging changes, not new scientific or execution semantics.

## Selected source hashes

[`source-hashes.json`](source-hashes.json) contains two explicit maps:

- `canonicalSourceSha256ByPublicPath` records each copied file's immutable pre-packaging source hash;
- `publicSourceSha256` records every source file currently shipped under `core/src/`, `runtime/src/`, and `host/src/`;
- `packagingAuthoredFiles` identifies the three standalone barrel entry points. They have public hashes but no pre-packaging byte identity.

Recompute the public files and the separately pinned transcript with:

```bash
shasum -a 256 core/src/*.mjs runtime/src/*.mjs host/src/*.mjs examples/minimal/transcript.json
```

The historical Alchemix adjudication SHA-256 is `96abec2c727d5aa566e214565efec78a52b641484086f0b0af80ea8808001559`. Its underlying 36,847-row archive is not published in this repository.

Canonical component and Alchemix hashes are provenance attestations for excluded artifacts. A standalone clone can verify all `publicSourceSha256` entries and the included transcript, but cannot independently rehash artifacts that are intentionally absent.
