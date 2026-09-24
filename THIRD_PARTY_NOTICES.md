# License scope and third-party notices

RHOOK-authored code and documentation, including `core`, `runtime`, `host`,
tests and original example/packaging code, are licensed under
[Apache-2.0](LICENSE). This grant covers the rights held by RHOOK contributors.
It does not relicense the third-party material below or grant rights in
third-party contracts, trademarks or data.

## Material included in this repository

| Material | Origin and retained terms |
|---|---|
| [Native block orchestration](examples/robinhood-v4/native/bridge.go) | Adapted from go-ethereum `core/state_processor.go` at `dff2aadcd2e75e33923b13acce6468d847477e79`. The entire derived file remains **LGPL-3.0-or-later**, including the RHOOK adaptations for bounded execution and observation. Its copyright and license header is retained, with [LGPL](examples/robinhood-v4/notices/geth-COPYING.LESSER) and accompanying [GPL](examples/robinhood-v4/notices/geth-COPYING) texts. |
| [Native go.mod](examples/robinhood-v4/native/go.mod) and [go.sum](examples/robinhood-v4/native/go.sum) | Dependency metadata from the pinned Nitro source. `go.sum` is unchanged; `go.mod` changes the module name and local replacements and adds the Nitro requirement. The upstream [Nitro license](examples/robinhood-v4/notices/nitro-LICENSE.md) is retained for this material; the root license does not relicense the listed dependencies. |
| [Case inputs](examples/robinhood-v4/case-data.json.gz) and [comparison references](examples/robinhood-v4/reference.json.gz) | RHOOK-authored manifests, assembly and evidence accompany historical chain data, including transactions, logs, proofs and contract bytecode. Apache-2.0 applies to RHOOK-authored portions only; no new license to the embedded third-party contracts or other third-party material is asserted. |
| [License texts](examples/robinhood-v4/notices) | Preserved upstream license documents, not RHOOK-authored code. |

These are the exceptions to the root Apache-2.0 grant. The other native harness
files are original RHOOK code calling upstream APIs; this does not relicense
the libraries they use or make the combined native executable Apache-only.

## Sources downloaded for the native example

Exact source URLs, commits and SHA-256 hashes are fixed in
[dependencies.json](examples/robinhood-v4/dependencies.json). The source
bootstrap extracts the complete upstream archives, including their notices.

| Dependency | Pinned commit | Retained license text |
|---|---|---|
| Arbitrum Nitro v3.11.4, including its Stylus library | `7d5ac271b400f710f6267ad759c6afc3e12d7059` | [Business Source License 1.1](examples/robinhood-v4/notices/nitro-LICENSE.md) |
| Offchain Labs go-ethereum fork | `dff2aadcd2e75e33923b13acce6468d847477e79` | [LGPL-3.0](examples/robinhood-v4/notices/geth-COPYING.LESSER) / [GPL-3.0](examples/robinhood-v4/notices/geth-COPYING), according to each upstream file; library headers specify LGPL-3.0-or-later |
| Nitro precompile interfaces | `7e88c8cc53c2e96201a23c638f1536557b9cb68b` | [Business Source License 1.1](examples/robinhood-v4/notices/precompiles-LICENSE.md) |
| Brotli | `f4153a09f87cbb9c826d8fc12c74642bb2d879ea` | [MIT](examples/robinhood-v4/notices/brotli-LICENSE) |
| Offchain Labs Wasmer fork | `d145ce4369414c0474c1d76d1037b3e5740a86e0` | [MIT](examples/robinhood-v4/notices/wasmer-LICENSE) |

The pinned Nitro and precompile licenses specify **December 31, 2030** as
their Change Date and Apache-2.0 as their Change License. Their terms also
provide for an earlier transition on the fourth anniversary of first public
distribution of the specific version. They must not be described as Apache-2.0
today merely because Apache-2.0 is the Change License. Business Source License
1.1 is not an open-source license: its grant covers non-production use and
specified additional production uses. The frozen offline analysis demo does
not assert a general production-use grant for Nitro integrations.

Transitive Go/Rust/npm dependencies, toolchains and container base packages
retain their respective upstream terms. These notices identify the direct
source boundary; they are not an exhaustive license inventory of a built
image. This repository publishes source and bootstrap instructions, not a
prebuilt native binary or container. Redistributing a combined executable or
image requires meeting all applicable upstream conditions, including any
corresponding-source/relinking obligations. The root Apache-2.0 license is
not a substitute for those conditions.
