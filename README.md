# RHOOK

[![CI](https://github.com/USBVadik/rhook/actions/workflows/ci.yml/badge.svg)](https://github.com/USBVadik/rhook/actions/workflows/ci.yml)

RHOOK replays historical execution, changes one supported rule, and compares
state, receipts, fees and transfers. Its experimental Developer Alpha has a
Python API and an installed CLI:

```text
inspect → plan → authorize → replay → verify → compare
```

The first case is Hookr Pair03: Robinhood Chain block **93251803**, all seven
arrivals, and `RulesConfig.lpBps: 100 → 50`. A fresh Go/Nitro ACTUAL must match
the canonical state root, receipts root and block hash before BRANCH starts
from an independent copy of the original parent. Replay uses saved inputs,
with no RPC or automatic state download.

## Start here

The SDK source, tests and Python example are in [sdk/](sdk/README.md).
**Executable download is pending distribution clearance.** There is no public
worker, Node runtime, historical witness or runnable input bundle in Git.

Run the offline SDK tests now with Python 3.12+:

```sh
python3 -B sdk/tools/test_offline.py
```

With separately approved runtime inputs, the [quickstart](sdk/QUICKSTART.md)
installs the executable CLI. Planning runs no EVM. `authorize` creates a local,
single-use consent; `replay` computes new ACTUAL/BRANCH results; `verify` checks
a saved run without executing the EVM. `compare` verifies first, then derives
differences from that run's receipts.

```python
from rhook_alpha import LpBps, SDK

sdk = SDK()
sdk.inspect("hookr-pair03")
plan = sdk.plan("hookr-pair03", LpBps(50))
print(sdk.describe(plan["planId"]))  # No authority or execution.
```

The [compatibility table](sdk/COMPATIBILITY.md) separates tested native results
from planning support. This Alpha targets macOS arm64. Installed replay passed
on the development Mac; installation on a second Mac is untested. The
[100→50 case study](docs/research/hookr-pair03-100-to-50.md) records the result
and the separate Linux worker comparison.

## What changed in Hookr

The intervention reduces the LP Rewards add-on and its associated protocol
share. It preserves the Hook Block, base/dynamic fees and recapture. For the
selected buyer, `100 → 50` increased RHOOK Transfer-event net output by about
**0.5040%**, with unchanged gas. The [earlier 100→0 result](docs/research/hookr-pair03.md)
increased output by about **1.0088%**. These are different interventions.

The historical pool uses `hookr-1` standard HookrRules contracts, matched to
official `hookr-sdk@1.1.1` release pins. The case-specific TypeScript
inspect/plan adapter is included in `sdk/engine/adapters/hookr-case`.
Current HookrRouter swap-builder compatibility is not established: the
historical external router differs from the current router.

Pair03 is a single-engine Go/Nitro observation. Independent Rust replay is
pending, economic assurance is unresolved, and qualified protocol Claims are
zero. Arbitrary blocks, arbitrary rules and production use are outside this Alpha.

## Protocol fixtures and research

The protocol-neutral evidence stack remains available independently of the
Alpha. It needs Node.js 22+ and has no npm dependencies:

```sh
npm ci
npm test
npm run quickstart
```

This [quickstart](QUICKSTART.md) generates and verifies a small transcript,
including a deliberate tamper rejection. It does not run Hookr or an EVM.

The [research index](docs/research/README.md), [model](docs/counterfactual-model.md),
[architecture](docs/architecture.md) and [threat model](docs/threat-model.md)
retain earlier experiments with their distinct verification boundaries.
The [Robinhood v4 example](examples/robinhood-v4/README.md) has an explicit
Docker native command; ordinary tests never start it. The
[Alchemix study](examples/alchemix/README.md) is separate; the protocol-neutral
stack has not been scientifically rerun on Alchemix.

## Contributing and licensing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Alpha notes](sdk/RELEASE_NOTES.md).
Original RHOOK code and documentation, including the Developer SDK, use
[Apache-2.0](LICENSE). The [SDK license scope](sdk/LICENSE_SCOPE.md) and
[third-party notices](THIRD_PARTY_NOTICES.md) preserve the separate terms for
Nitro/geth and other third-party material. This source license does not grant
rights to the historical witness or clear the combined executable for release.
