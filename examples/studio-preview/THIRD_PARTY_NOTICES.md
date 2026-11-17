# Attribution and source lineage

RHOOK Studio frontend, adapters, tests and documentation are RHOOK-authored,
licensed under the repository's Apache-2.0 license (also included as
[LICENSE.txt](LICENSE.txt)). The public editor is adapted from the existing
Studio generic metadata renderer and draft/revision model. The
`playground-result.mjs` rendering contract is retained from the accepted 0.3
Studio source. It performs data consistency checks, never native execution.

Hookr catalogue labels, descriptions and parameter metadata are derived from
the retained `hookr-sdk` 1.6.1 package, copyright 2026 Hookr, MIT licensed.
The complete retained license is included in [HOOKR_LICENSE.txt](HOOKR_LICENSE.txt).
The catalogue commitment and source commit are in [data/catalog.json](data/catalog.json).
This is a retained version, not a claim about the latest Hookr release.

No Hookr SDK implementation, Solidity sources, ABI implementation, contract
bytecode, compiled Go/Nitro worker, native dependencies or witness is included.
Contract redistribution rights are therefore not asserted or required for this
package. Names identify the mechanisms being explored; no endorsement is implied.

The saved datasets are intentionally published, sanitized RHOOK-authored
observations from hypothetical local Playground executions. Full private
execution records, operator configuration and artifacts are excluded. Original
records remain immutable. Public hashes are provenance references, not access
links to private artifacts and not independent execution proofs.

No external fonts, images, analytics, wallet libraries or npm dependencies are
used by this preview.
