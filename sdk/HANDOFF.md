# Session Handoff 0.1

A handoff package moves one [Counterfactual Session](SESSIONS.md) to another SDK installation. The
receiver authenticates the package with a manifest SHA-256 obtained separately, rebuilds the same session
and variant identities with the ordinary session API, and prepares each variant locally with
`ExecutionSDK.prepare`. Everything is offline: no native worker, RPC, host admission or consent.

A package is data, not authorization. Importing one does not run anything and grants nothing.

## What a package contains

```text
HANDOFF/
  HANDOFF.json            manifest (schema rhook/session-handoff/0.1); its SHA-256 is the pin
  source/SCENARIO.json    the pinned session source; only in a complete package
```

No other file or directory is accepted. The manifest holds the sealed session header (checkpoint,
checkpoint trust limits, source SHA-256, byte length and scenario commitment, common action, LP100
baseline), every registered variant record, the file list with exact lengths and hashes, and the fixed
capabilities and assurance of its mode. It contains no paths, user names, timestamps or SDK home.

| Mode | Source material | Can do |
|---|---|---|
| `METADATA_ONLY` (default) | `SOURCE_MATERIAL_NOT_INCLUDED` | Inspect identities, variants and the exporter's preparation references |
| `COMPLETE_LOCAL_HANDOFF` (`include_source=True`) | `INCLUDED_BY_EXPLICIT_OPT_IN` | Import, rebuild the session, prepare variants, evaluate static coverage |

`SCENARIO.json` holds the checkpoint state inventory, which may be privately acquired. It is included only
when you ask for it, and the SDK never uploads, sends or publishes a package.

Never included, in either mode: the native worker or runtime, prepared directories, the coverage record,
verification records, run evidence, consents or other authority, and machine paths. For each prepared
variant the manifest carries the exporter's prepared scenario commitment and SHA-256 as a reference only;
the receiver prepares the variant itself and compares.

## Export

```python
from rhook_alpha.execution import ExecutionSDK

session = ExecutionSDK(home).open_session(session_id)
result = session.export_handoff(Path('/new/export/dir'), include_source=True)
result['manifestSha256']   # share this through a channel other than the one carrying the package
```

```sh
rhook-cases --home HOME session-handoff-export --session ID --output DIR [--include-source]
```

Export re-checks the retained source against its pin and every variant, preparation and verification
record; drift stops it. The output directory must not exist and must be outside the SDK home. The same
session, variants, preparation state and mode give the same manifest bytes in any home.

## Inspect and import

```sh
rhook-cases --home HOME session-handoff-inspect --package DIR --manifest-sha256 HEX
rhook-cases --home HOME session-handoff-import  --package DIR --manifest-sha256 HEX [--prepare]
```

```python
sdk = ExecutionSDK(fresh_home)
sdk.inspect_session_handoff(package, expected_manifest_sha256=pin)
session = sdk.import_session_handoff(package, expected_manifest_sha256=pin)
for variant in session.variants():
    session.prepare_variant(variant['variantId'])
```

The pin is compared with the manifest bytes before the manifest is read. Then the package must hold
exactly its declared files: no extra, hidden, linked, hard-linked or special entries, each within its size
limit and with its declared SHA-256. A complete package's source must pass the existing source validation
and derive exactly the declared session header; each variant record must derive from that session and
its descriptor. Inspection without a pin reports `HANDOFF_NOT_PINNED` and cannot be imported.

The session is built from the source bytes that were authenticated, copied into a private staging
directory; the package file is not opened again. A new session appears in one rename with all its
variants, or not at all; an interrupted import leaves only a `.handoff-import-*` staging directory, which
is never a session. Importing the same package again reuses the session. Every stored counterpart of a
package variant is checked before anything is added, so a stored session or variant that differs from the
package, or is incomplete, stops the import and leaves the session unchanged. Missing variants are then
added one by one, each in one rename: if the process dies part-way, no import result is returned, the
session holds only complete variants of the package, and running the same import again completes it. A
metadata-only package is refused with `HANDOFF_SOURCE_NOT_INCLUDED`.

With `--prepare` (or by calling `prepare_variant`), each variant is prepared locally and compared with the
exporter's reference: `MATCHES_EXPORTER_REFERENCE`, `NO_EXPORTER_REFERENCE` or
`DIFFERS_FROM_EXPORTER_REFERENCE` (exit code 1). The importer never copies a prepared result.

## What an import establishes

| Level | After import |
|---|---|
| Package integrity | Files match their hashes and the external manifest pin |
| Producer identity | Not established; there is no signature |
| Source integrity | `SCENARIO.json` matches its SHA-256 and scenario commitment |
| Checkpoint binding | The source declares the session checkpoint |
| Canonicality | Not established; needs a block hash you trust independently |
| Static state coverage | Not transferred; run `session-coverage` (Node.js and the pinned adapter dependencies) |
| Dynamic execution closure | `UNKNOWN` |
| Native execution | `NOT_PERFORMED` |
| Heterogeneous agreement | `NOT_EVALUATED` |
| Economic assurance | `UNRESOLVED`; qualified claims 0 |

Matching hashes say the files are the ones you were told to expect; they do not say the checkpoint is on
the canonical chain. Compare `checkpoint.blockHash` with a block hash from a node or explorer you trust.
A prepared variant is a hypothetical question about one past checkpoint, not a prediction. Each variant
keeps its own status: a verified run of LP50 says nothing about LP0.

## Next step

Running a prepared variant natively is the existing workflow in [DEVELOPER_EXECUTION.md](DEVELOPER_EXECUTION.md)
(`execution-operation`, then `execution-run` with the exact operation and local consent flags) and needs a
registered runtime. Only a completed and verified native run of one exact prepared input establishes its
dynamic closure.

## Example

```sh
python3 -B sdk/examples/session_handoff.py --synthetic --work /new/dir
```

It creates two independent homes, exports a complete package from the first, imports it into the second
with the pin, prepares LP50 and LP0 and compares identities and prepared commitments. The synthetic
fixture is made-up test data, not chain state. Use `--sdk-root PREFIX/lib` for an installed SDK.
