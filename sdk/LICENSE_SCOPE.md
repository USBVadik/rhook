# SDK license decision pending

The root Apache-2.0 license predates this import and continues to cover the
existing public implementation. It **does not grant a new license to the
RHOOK-owned portions of `sdk/`**. No project license is selected or granted by
this candidate. Public visibility alone does not grant general modification
or redistribution rights.

Proposal for rightsholder approval: Apache-2.0 for original RHOOK-owned SDK
code and documentation, with explicit third-party/derived-source exceptions.
Contributor ownership must be confirmed first. This is a proposal, not a
license grant, and does not relicense the combined native worker.

Nitro and precompiles retain their pinned Business Source License 1.1 terms.
Geth material retains LGPL-3.0-or-later or GPL terms according to each upstream
file. Toolchains, Wasmer, Brotli, Node and npm modules retain their original
terms. The root [notices](../THIRD_PARTY_NOTICES.md) identify the dependency
boundary. A lockfile reference does not vendor or relicense a dependency.

Native module metadata copied from Nitro and any source derived from geth
remain outside the proposed RHOOK-only grant. The exact combined worker's
redistribution route requires a decision separate from source publication.
