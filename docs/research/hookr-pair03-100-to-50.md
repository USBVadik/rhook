# Hookr Pair03: native replay with LP Rewards 100 → 50

The historical figures and original provenance below are retained. The
[installed developer pilot](#installed-developer-pilot-25-october-2026) adds a
later reproduction of the same result; [Developer Alpha](../../sdk/README.md)
describes what is available in the public clone.

RHOOK replayed a saved Hookr block on Robinhood Chain, verified the original execution against its canonical commitments, then ran the same seven ordered arrivals with `RulesConfig.lpBps` changed from 100 to 50. The selected buyer's receipt-derived RHOOK output increased by **0.5040100829%**. Both worlds completed in native Go/Nitro with no RPC or state hydration during replay.

Lower LP Rewards can suggest the direction of a fee change without executing a block. This experiment measured the consequences by running the historical transactions again: contract calls, receipts, gas and final commitments. The counterfactual figures below come from that execution.

This is a separate experiment from the earlier [100 → 0 case study](hookr-pair03.md). Its static visual and JSON summary describe the zero branch, not the 50 branch reported here.

## Historical case

| Input | Value |
|---|---|
| Network | Robinhood Chain, chain ID 4663 |
| Original-parent checkpoint | End of block 93251802 |
| Target block | 93251803, timestamp 2026-10-20 06:42:33 UTC |
| Arrivals | All seven, in historical order, including the Nitro system transaction |
| Subject | Arrival ordinal 3, counting from zero; 0.01 ETH input |
| Pool generation | `hookr-1`, standard HookrRules |

- PoolId: `0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780`
- Subject transaction: `0xbdc353fe6485a1e4e14e6d6fa358d9e7cdd333a986ce0440e7a76fcdb09aa41c`
- RHOOK token: `0x3c022d43a9f826cd206c2ba60bc753d8b36185c4`
- Parent block hash: `0x991db6ee40bd7056cfabff012763a1b75995979e5023dc010553dbc304c16016`
- Parent stateRoot: `0x9c63ad5d9c6ba4fd19c301ea35264cec28dd1ad0e951a5f5578af8a32131baa6`

The historical Root and Rules runtime hashes match the official `hookr-sdk@1.1.1` release pins; the [earlier compatibility section](hookr-pair03.md#contract-generation) lists both contracts and hashes. That establishes the applicable ABI generation. The historical external router differs from the current HookrRouter, so swap-builder compatibility for this route remains unestablished.

## Intervention and execution

The declared intervention changes only bits 160–175 of the pool's RulesConfig storage word, replacing `lpBps = 100` with `lpBps = 50`. It reduces the LP Rewards add-on and its associated protocol share. It does **not** disable the entire Hook Block, remove the hook, or remove base/dynamic fees and recapture.

This is an analytical overlay on checkpoint state. No administrative transaction was added, and this result does not establish that the pool's frozen configuration can be edited through its normal onchain interface.

The replay followed three steps:

1. Construct ACTUAL from the authenticated original-parent checkpoint and execute all seven arrivals. Compare its stateRoot, receiptsRoot and blockHash with the saved canonical target header.
2. After all three comparisons pass, construct BRANCH independently from the same original parent. Apply the single declared field change before the first arrival.
3. Execute the same seven arrivals in BRANCH, preserving transaction bytes, order, contract code and unrelated initial state. Derive observations from the newly produced results.

BRANCH starts from the original parent, not ACTUAL's end state. Both worlds use the retained partial-state package with a nil Source: missing state would stop execution rather than trigger a download. The recorded journal places `CANONICAL_ACTUAL_MATCH` before `BRANCH_ENTERED`.

## Canonical ACTUAL and counterfactual commitments

Each ACTUAL value below matched the canonical target header before BRANCH began:

| Commitment | Canonical = recorded ACTUAL |
|---|---|
| stateRoot | `0xd4ea0fe6f558cbc4a6b4161e3afc41ee4b7709001c170e32bc2144e64bdeb10b` |
| receiptsRoot | `0x920c08cb6953014f0800587bbe2c0f8db5a7855ddb9f6263d5b4e230edeba98f` |
| blockHash | `0xc73ef372869ad5bf2a664bc1bc4cbe411c3adeb1938f349dd7686d82425398cd` |

The alternative execution produced its own commitments. These describe a hypothetical block and are not canonical chain values:

| Commitment | Recorded BRANCH, lpBps = 50 |
|---|---|
| stateRoot | `0xa6bf412783c620248df6746dfb2c637a87e828481abff901797463c73b777ad2` |
| receiptsRoot | `0xc55c829dd13052c41831de4ff6518a8c62c57bdcf798e14193ca5f225ac92b1c` |
| blockHash | `0xb8bc78a61d8394f24a6a3c5bdeb79be801ec63eaa52764e814ef2a1f2a88a542` |

## Observed economics

| Selected buyer / transaction | ACTUAL | BRANCH |
|---|---:|---:|
| Buyer RHOOK Transfer-event net, base units | 291469365928126821002944 | 292938400920971228766928 |
| Outer Swap fee, pips | 11048 | 7048 |
| Subject transaction gas | 1483206 | 1483206 |
| Receipt status | 1 | 1 |

The difference is **1469034992844407763984 base units**, or approximately **+0.5040100829%**, calculated as `(BRANCH − ACTUAL) / ACTUAL × 100`. The outer Swap fee changed from 1.1048% to 0.7048%; subject gas was unchanged.

Buyer output is the net of RHOOK `Transfer` events for the selected buyer in the subject receipt. It is not independently authenticated as a final token-storage balance. Token decimals were not independently established for this report, so amounts remain in base units. These observations establish neither future profit nor a general output guarantee for other trades.

## Reproduction with the unified worker

An earlier specialized Go/Nitro worker executed this same `100 → 50` case. Unified SDK Native Acceptance02 subsequently consumed the 50 runtime plan with one shared Plan-Aware worker, without rebuilding that worker for this parameter.

The comparison covered each complete deterministic `result` object, including receipts, headers, observations and the BRANCH patch. Both ACTUAL and BRANCH were exactly equal to the earlier specialized results. Fresh execution and economic verification completed before the earlier outputs were read for this comparison.

The accepted unified run recorded:

| Measurement | Observed value |
|---|---:|
| ACTUAL / BRANCH invocations | 1 / 1 |
| RPC / WSS requests during replay | 0 / 0 |
| Retries | 0 |
| Native pair wall time | 1.265779 seconds |
| Sampled worker peak RSS | 288.796875 MiB |

These are observations from this run on one macOS arm64 machine. The RSS figure is a sampled peak, not an exact maximum or memory reservation. The timing is for the native pair, not the complete SDK workflow, and is not a general performance guarantee.

## Installed developer pilot: 25 October 2026

The private Developer Alpha subsequently reproduced this case through a clean
installation in a fresh HOME, outside the development workspace, on the same
physical Mac and OS account. The installed CLI executed a new ACTUAL/BRANCH pair,
then separate `verify` and `compare` commands checked that newly created run.
Both complete world files were byte-identical to the earlier accepted results.

This pilot used a separately relinked developer worker with its own source and
binary identity. It did not replace the original scientific worker or reuse its
closed authority. The EVM implementation, witness, intervention and v2 resource
policy were preserved. Packaging removed founder-specific source paths; native
execution still requires normal host pressure and sufficient free-page headroom.

| Installed pilot measurement | Observed value |
| --- | ---: |
| Complete installed replay command | 6.045 seconds |
| Native ACTUAL + BRANCH | 0.832 seconds |
| Separate own-run verify | 1.166 seconds |
| Separate own-run compare | 1.166 seconds |
| Sampled peak worker RSS | 145.45 MiB |
| ACTUAL / BRANCH invocations in the completed operation | 1 / 1 |
| RPC / WSS / automatic retries in that operation | 0 / 0 / 0 |

Cleanup was confirmed. These are measurements from one run, with sampled rather
than exact peak memory; they are not a controlled performance comparison.
The successful native phase used the normal owner Terminal context and the
unchanged SDK guards. Extra OS-level isolation was tested for installation and
planning, but is not claimed for this native phase. The measurements describe
the completed operation; they do not classify earlier stopped attempts as passes.

| Developer pilot identifier | SHA-256 |
| --- | --- |
| Developer worker | `09ed5608c467a330779fcb7ccb677968f17729f25113c684c89ffb5292cc0f64` |
| Developer source commitment | `a61fc0b687e12d4cfab64fe64593c0d1c9081ca021bd700635e5a3e763364f60` |
| Complete ACTUAL.json bytes | `a6858c4bc1fd7bb50b6ffc328d8351eae90f90c6747781405caff3bf31704953` |
| Complete BRANCH.json bytes | `586df83db3c4e25e71dbc01ea4083d810ddb234ec19c3f755c73202d57c1ff13` |

The full-file hashes above differ in serialization scope from the canonical
`result`-object hashes below. Both comparisons matched their respective retained
references. The raw pilot records and runtime inputs remain private; this page
reports the project-authenticated outcome, not a public independent execution.

A prior Linux amd64 worker on a separate founder-controlled Ubuntu server also
produced these full ACTUAL/BRANCH file hashes. That is same-engine portability
evidence. It does not establish another Mac installation, an externally operated
pilot, Linux support for the macOS installer, or independent Rust agreement.

## Original experiment provenance

Before publication, the complete sealed file sets and content hashes were checked for Unified Acceptance02 (99 files), the specialized 50 experiment (49 files) and the original zero experiment (50 files). The unified source inventory's 198 file hashes and the retained worker bytes also matched their commitments. This publication performed offline authentication only; it did not run another native pair.

The following identifiers bind this report to the retained private records. They are not downloadable execution inputs or authorization to run an operation.

| Identifier | Commitment |
|---|---|
| Unified operation | `a79ca0b8486ca77b91cb3f9c6d35ec5675d8bfd5afa4c821c4e71ef58b0ec42d` |
| Unified worker SHA-256 | `d7e15c1b4168da06c4f3410ff1cc9f7963e090feedb22a7405d391910942283c` |
| Unified source commitment | `5460f0c6fcf029ad09f3b12b711c3c9e34d438db4803d8ceb160263c72c7b9f1` |
| Semantic plan commitment | `51f44c52b5da5c6710a7b47845732e420aec65f4ceb7bc10c3cbea058ea7a2fc` |
| Runtime plan SHA-256 | `d54448edc0cff6786f2b00281e4d2e83dc02af83b2bf163426c88bbcc659f110` |
| Unified archive manifest SHA-256 | `851bf5d878cf94225ece0ab5201169da92e5ad766dee328006dc3672d775a757` |
| Unified archive freeze SHA-256 | `818ac66972b4a300ab9d11cc6a9ef897a336c3b4dadd4b689f18fdc0784fea20` |
| Specialized operation | `6c778828c30c57b8bc3ec798b8ca3c7d095b5489971a73f65e3bdaa4fa6b1704` |
| Specialized archive manifest SHA-256 | `145c91f73038646e70711c3da613d9ef821893fac556638b0558c36689a225da` |
| Specialized archive freeze SHA-256 | `51b7cd1cb9f0712b06c720f6772d7a226f95d272e05a952ef0ddb55631e438a0` |

The source commitment is SHA-256 over the UTF-8 file-to-SHA-256 map, sorted by key, with compact JSON separators and no trailing newline. It is not a Git commit ID. The semantic plan uses the `rhook/hookr-plan/0.2` domain followed by a newline and compact canonical JSON; the runtime plan hash covers the exact saved file bytes.

For the full deterministic-result comparison, the `result` objects were serialized as compact UTF-8 JSON with recursively sorted keys and no trailing newline. Each digest below was identical between the specialized and unified runs:

| Result object | SHA-256 |
|---|---|
| ACTUAL | `4b9182958a05bb44e1d5aa48750bde93b50e0ceb57a8822c64c2e5ca885dcdb2` |
| BRANCH | `0c434dcd9fa2a5f1ae421ed341e0568c1471463e9755641191b6bc49ec35c3e9` |

## Inspection, reproduction and qualification

Readers can inspect the case identifiers, intervention, arithmetic, execution commitments and provenance pins in this report, and compare them with the [earlier zero-branch publication](hookr-pair03.md). The authenticated internal records additionally contain the execution receipts, journal, patch observations, resource telemetry and verification results underlying these figures.

Independent native reproduction requires access to the private checkpoint/witness package, matching source and worker, runtime plans and a suitable execution environment. Those materials are not distributed here. Publishing their hashes does not make this page a standalone verifier or native replay kit.

This is one exploratory saved-block Hookr Pair03 case, using one Go/Nitro execution lineage. Independent Rust execution for this case and heterogeneous agreement are `NOT_EVALUATED`; economic assurance is `UNRESOLVED`; new qualified Claims are **0**. Reproduction with another worker build in the same engine lineage does not add an independent engine. Arbitrary blocks, pools, interventions, independent external-developer reproduction and production readiness remain unestablished.

The private executable and raw evidence remain outside this publication.
Installed local native acceptance has passed. The next product milestone is
one external developer installing the Alpha on another supported Mac and
reproducing the result. A four-file private pilot handoff is prepared but has
not been sent. This report does not announce external SDK delivery or a public
executable release. Fresh-state Hookr LaunchLab remains separate development.
