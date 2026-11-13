# RHOOK

[![CI](https://github.com/USBVadik/rhook/actions/workflows/ci.yml/badge.svg)](https://github.com/USBVadik/rhook/actions/workflows/ci.yml)

**A Counterfactual Execution protocol and developer toolkit for Arbitrum-based chains.**

## What RHOOK enables

RHOOK replays historical execution, or a scenario on an authenticated checkpoint, changes one reviewed rule of a
contract or hook, and compares what happens: receipts, logs, fees, balances and state roots of both worlds. Missing
state stops the run; nothing is guessed or fetched mid-replay. The workflow:

```text
inspect → plan → authorize → replay → verify → compare
```

**Executable download is pending.** The public clone contains source, offline tests
(`python3 -B sdk/tools/test_offline.py`) and an offline profile-descriptor preview. Native execution needs a worker
and witness that are not published.

This is for developers who need to know how a hook or protocol parameter changes the outcome of a concrete
transaction: before shipping a configuration change, while debugging a pool or when explaining a fee. Hookr is the
first supported application, on Robinhood Chain; RHOOK is the protocol and the tooling around it. The project is
moving through four stages:

**research prototype → reproducible execution workflow → descriptor-driven developer tooling → integrations and a public product**

The first two stages are done for bounded cases. Descriptor-driven tooling is now a **Developer Preview** (SDK
0.6): its offline part runs from a clone, while native execution still needs assets that are not published.
Integrations and a public product have not started.

## What has been demonstrated

| Demonstration | Result and scope |
| --- | --- |
| SDK 0.6 descriptor parity (G5) | One descriptor-driven worker ran LP Rewards 23 / Dynamic Fee ON, LP 100 / DF OFF and LP 23 / DF OFF at block 101935336. Every pre-registered field matched the accepted SDK 0.4 records; gas interaction of the two settings **+36**. Hypothetical worlds, same engine lineage. [Case study](docs/research/sdk06-g5-descriptor-parity.md). |
| Historical Hookr LP100→50 | Both Go/Nitro worlds of all seven arrivals in block 93251803 completed. Buyer RHOOK Transfer-event net increased by **0.5040100829%**; subject gas was unchanged. [Case study](docs/research/hookr-pair03-100-to-50.md). |
| Mac/Linux execution agreement | A separate Ubuntu amd64 worker reproduced the complete macOS results for this case. This is portability within the same engine lineage. |
| Installed Developer Alpha | On 25 October 2026, a separately built macOS developer worker completed a new pair through an installed CLI. Its own `verify` and `compare` passed; full world files matched the prior references. Installed replay took **6.05 seconds** on that Mac. |
| Historical Dynamic Fee OFF (Build18) | The signed 0.01 ETH purchase in block 93251803 remained SUCCESS in both Go/Nitro worlds, with LP100 and recapture retained. [Scope and assurance](sdk/SOURCE_SYNC.md). |
| Private recorder-only replay (Build26D / Build27g) | Two historical cases completed fresh ACTUAL/BRANCH pairs using recorded dependencies. Same Go/Nitro lineage; [results and limits](sdk/RECORDER_RESULTS.md). |
| Installed on-demand SDK | One local fresh-checkpoint LP100/LP50 run completed discovery and fresh offline pairs through the installed CLI; all ten declared deterministic fields matched. [Acceptance scope](sdk/SCENARIOS.md#installed-on-demand-acceptance). |

In the historical Pair03 case the ACTUAL world is a control: its stateRoot, receiptsRoot and blockHash must match
the canonical header before BRANCH runs, and BRANCH starts from a fresh copy of the original parent. The SDK 0.6
scenarios are different: both worlds execute a synthetic signed buy on the checkpoint state, so neither is a
transaction that happened on chain.

There is no independent Rust execution of these Hookr cases, economic assurance is unresolved and qualified
protocol Claims are zero. Other projects in this repository's [research index](docs/research/README.md) did compare
Go/Nitro with Rust/arb-revm on other Robinhood cases.

## What developers can use today

| Tier | What works | Entry point |
| --- | --- | --- |
| 1. Public clone only | Profile descriptor catalogue, inspection, offline planning of interventions with their storage writes and commitments, descriptor validation; Python API and CLI source; synthetic offline tests; the protocol-neutral evidence stack | [descriptor preview](sdk/QUICKSTART.md#profile-descriptor-developer-preview-sdk-06), `python3 -B sdk/tools/test_offline.py`, [evidence-stack quickstart](QUICKSTART.md) |
| 2. Recorded evidence | Offline check of a recorded ACTUAL/BRANCH pack against a block hash you trust (Node.js 24+). Only a synthetic pack ships here; the real Pair03 pack is not distributed yet and may be shared separately after approval. Offline checks of selected heterogeneous-execution artifacts | [verify-pack](sdk/verify-pack/README.md), [heterogeneous results](docs/research/robinhood-heterogeneous/README.md) |
| 3. Complete runtime and input kit on a supported host (not distributed) | Preparing a full scenario input, binding an exact operation, owner authorization and one native run, followed by verification and comparison. Needs the reviewed worker, the pinned input with its witness, the registered Node runtime and host sensor, an owner-controlled Apple Silicon Mac on AC power with the lid open, and per run the owner's authorization, one-shot consent and host admission | `rhook-cases profile-*`, `session-*`, `scenario-*` ([sessions](sdk/SESSIONS.md), [scenarios](sdk/SCENARIOS.md)); `profile_descriptor_preview.py native-requirements` |
| 4. Research-only or unsupported | Native Dynamic Fee Tuning, arbitrary pools, contracts or storage writes, caller-supplied descriptors, hosted execution, independent cross-client verification of the Hookr cases | — |

Tier 3 commands are in the public source and stop with an explicit error when an asset is missing. None of the
tier 3 assets is distributed; see [distribution status](sdk/DISTRIBUTION.md).

## Install and try

Python 3.12+ without optimization; nothing below needs a network connection, a worker or a witness.

```sh
python3 -B sdk/tools/test_offline.py
python3 -B sdk/examples/profile_descriptor_preview.py catalogue
python3 -B sdk/examples/profile_descriptor_preview.py inspect --profile hookr-1
python3 -B sdk/examples/profile_descriptor_preview.py plan --lp-bps 37 --dynamic-fee OFF
python3 -B sdk/examples/profile_descriptor_preview.py native-requirements
```

`plan` prints the masked storage writes, the changed fields and the `interventionCommitment` and `capsuleId` a
prepared input would carry. For `--lp-bps 23 --dynamic-fee OFF` these equal the values of the G5 run.

To install the CLI from source into its own prefix:

```sh
python3 -B sdk/install_cases.py --prefix /physical/path/to/new-sdk
/physical/path/to/new-sdk/bin/rhook-cases --home /physical/path/to/new-home interventions
/physical/path/to/new-sdk/bin/rhook-cases --home /physical/path/to/new-home execution-capabilities
```

The [SDK quickstart](sdk/QUICKSTART.md) covers both, the [clean-room guide](sdk/CLEAN_ROOM.md) the pinned
installation inventory. The protocol-neutral evidence stack needs Node.js 22+; it has no external npm dependencies,
so these commands also run offline (the separate Hookr adapter used by verify-pack downloads `viem` and `hookr-sdk`):

```sh
npm ci
npm run check
npm test
npm run quickstart
```

## How the descriptor architecture works

A **profile descriptor** is canonical JSON that describes one hook profile: chain and engine, contract identities and
code hashes, the pool, storage targets and their slot derivations, named bit fields, the authenticated original
words, and typed intervention kinds with parameter ranges, original-state predicates, assignments, result
invariants and conflicts. It contains no code or expressions. Its SHA-256 says which descriptor it is, not that it
is correct.

- **Review is separate from the bytes.** `descriptors/CATALOGUE.json` records the review of each descriptor and of
  each intervention kind: which purposes it admits (offline preparation, native execution). Only catalogue
  descriptors are loaded for workflows; a caller's file can be validated but is never loaded.
- **One interpreter, two languages.** The Go worker (`native/descriptor.go`) and the Python SDK
  (`rhook_alpha/profile_descriptor.py`) apply the same checks in the same order and raise the same codes.
- **Engine identity is separate again.** A native operation binds only to the reviewed worker identity (source
  commitment, binary and policy hashes) named in `profile_descriptor.PROFILE_ENGINE_RECORD`. Each run additionally
  needs the owner's authorization of that exact operation, one-shot consent and host admission.

The first descriptor, `hookr-1` revision 2, has three kinds: `LP_REWARDS_BPS` (0–99) and `DYNAMIC_FEE` (OFF), both
reviewed for native execution, and `DYNAMIC_FEE_TUNING`, reviewed for offline planning only. Details:
[Profile Descriptor specification](sdk/PROFILE_DESCRIPTOR_SPEC.md).

## Limitations and roadmap

- Native results come from one engine lineage (Go/Nitro) and a few bounded inputs; general coverage is unknown.
- Executables, witnesses and run records are private. A public clone can check descriptors, interpreters and
  commitments, not repeat a native run. The [license scope](sdk/LICENSE_SCOPE.md) and
  [distribution status](sdk/DISTRIBUTION.md) explain why.
- One reviewed descriptor exists. New hooks need new descriptors and their review, and possibly a different worker.

Next, in order: an external developer installing and using the SDK on their own machine; a distributable native
runtime with cleared terms; further reviewed descriptors. None of these is done.

## Research and contributing

The [research index](docs/research/README.md) separates the SDK results from earlier experiments, including
Go/Nitro and Rust/arb-revm agreement on other Robinhood cases. Those results do not qualify the Hookr cases on Rust.
See the [model](docs/counterfactual-model.md), [architecture](docs/architecture.md) and
[threat model](docs/threat-model.md) for protocol details.

The [Robinhood v4 example](examples/robinhood-v4/README.md) retains an explicit Docker native command; ordinary tests
never start it. The separate [Alchemix study](examples/alchemix/README.md)
has not been scientifically rerun on Alchemix by the protocol-neutral stack.

Read [CONTRIBUTING.md](CONTRIBUTING.md). Original RHOOK code and documentation use [Apache-2.0](LICENSE); the
[SDK license scope](sdk/LICENSE_SCOPE.md) and [third-party notices](THIRD_PARTY_NOTICES.md) preserve upstream terms.
The source license does not clear the combined executable or historical witness for release.

## Hookr Studio Developer Preview

Explore three saved Nitro BASELINE/VARIANT configurations and the retained Hookr
catalogue in the [runnable Studio preview](examples/studio-preview/README.md).
It uses static public datasets with explicit acceptance boundaries; edited drafts
are not executed and live Run remains unavailable.
