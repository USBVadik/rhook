# Developer SDK license scope

Original RHOOK-owned source code and documentation in `sdk/` are licensed under
the existing root [Apache License 2.0](../LICENSE). This includes the CLI, Python
API, installer, consent handling, original case adapter/native integration,
tests, example and documentation. The grant covers rights held by RHOOK's
contributors; it does not claim ownership of dependencies or historical data.

## Exceptions

| Material | Applicable boundary |
| --- | --- |
| `engine/native/prestate/go.mod`, `go.sum`; `engine/native/saved-pair/go.mod`, `go.sum` | Metadata inherited from pinned Nitro, with RHOOK module/replacement adaptations. Retain the [Nitro BSL 1.1 notice](../examples/robinhood-v4/notices/nitro-LICENSE.md); the root Apache grant does not relicense the upstream metadata or listed modules. |
| Nitro and precompile source downloaded by the build scripts | The pinned Business Source License 1.1 texts apply. Implementation sources are fetched separately; retained module metadata is listed above. |
| geth and differently licensed derived source | Retain LGPL/GPL terms according to the source. The existing [LGPL-derived public adapter](../examples/robinhood-v4/native/bridge.go) remains LGPL-3.0-or-later, including its RHOOK adaptations; it is not relicensed by this SDK addition. |
| `rhook_alpha/cases/scenario/native/profile.json` interface/release metadata | Hookr SDK 1.1.1 ABI and release metadata retain its [MIT notice](../examples/robinhood-v4/notices/hookr-sdk-MIT.txt); no Hookr contract implementation is relicensed. RHOOK-owned profile assembly remains in the original-code scope. |
| Other downloaded libraries, Node, toolchains and npm packages | Original upstream terms and notices apply. A lockfile or ABI compatibility pin does not vendor or relicense an implementation. |
| Historical transactions, state, bytecode, witness and factual reference metadata | No new rights to third-party contracts or data are granted. The private Pair03 witness and execution archives are not part of this source release. |
| Combined worker and other executable assets | Not distributed here. The RHOOK source license does not establish the terms or clearance for a combined Nitro/geth/CGO/libstylus executable. |

The [third-party notices](../THIRD_PARTY_NOTICES.md) retain exact upstream
revision links and license texts. No upstream notice or differently licensed
file is replaced. [Executable distribution](DISTRIBUTION.md) remains a separate
decision; Apache-2.0 coverage of RHOOK source does not clear the binary or witness.
