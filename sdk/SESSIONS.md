# Counterfactual Session 0.1

A session fixes one authenticated checkpoint and lets a developer ask several independently declared
counterfactual questions against it, without capturing the same starting state again for each one.

```text
create session from one pinned SCENARIO.json
  -> register variants (LP50, LP0, ...)
  -> check which original-state reads the retained witness answers (offline)
  -> prepare each variant with the existing ExecutionSDK (offline)
  -> run each prepared variant natively, under the existing exact consent (separate step)
  -> verify each completed run and compare verified variants
```

Creating, inspecting, covering and preparing a session are offline: they start no native worker, open no RPC
connection, request no host admission and consume no consent. Native execution of a prepared variant is the
existing `ExecutionSDK` run under exact one-shot consent; `session-ready`, `session-run` and `session-result`
(Parameterized Execution workflow 0.2 below) compose it with registration, binding and verification.

## Python API

```python
from rhook_alpha.execution import ExecutionSDK

sdk = ExecutionSDK(home)                     # private SDK home, created with mode 0700
session = sdk.create_session(
    source=path_to_SCENARIO_json, expected_sha256=pinned_sha256,
    checkpoint=dict(chainId=4663, blockNumber=..., blockHash='0x...', stateRoot='0x...'))
v50 = session.add_variant({'lpBps': 50})['variantId']
v0 = session.add_variant({'lpBps': 0})['variantId']
coverage = session.coverage()                # static original-state coverage, offline
session.prepare_variant(v50)                 # ExecutionSDK.prepare output for LP50
session.prepare_variant(v0)
session.inspect()                            # identities, coverage, per-variant status
session.manifest()                           # portable export, no machine paths
# After a separately authorized native run of the prepared LP50 input:
session.verify_selected(v50, run_directory)  # existing scenario verifier, then stored once
session.compare_verified()
```

The Python planning methods and `session.prepare_variant(variant_id, node=...)` accept an explicit
Node executable. Dynamic Fee and Config Overlay preparation use that same executable for both
original-target proof checks, including when Node is absent from `PATH`.

`sdk.open_session(session_id)` reopens a session offline. Every identity is re-derived from the retained
source; an edited manifest or source copy is reported as drift. An open session checks the retained source
against its pin again before each coverage, preparation and preparation check, and passes on exactly the
bytes it checked; a source changed after creation stops with `SESSION_SOURCE_DRIFT`. `examples/counterfactual_session.py` runs
the offline workflow end to end.

## CLI

```sh
rhook-cases --home HOME session-create --scenario SCENARIO.json --sha256 HEX --checkpoint CHECKPOINT.json
rhook-cases --home HOME session-add-variant --session ID --lp-bps 50
rhook-cases --home HOME session-coverage --session ID
rhook-cases --home HOME session-prepare --session ID --variant VARIANT_ID
rhook-cases --home HOME session-inspect --session ID
rhook-cases --home HOME session-export --session ID
rhook-cases --home HOME session-compare --session ID
```

Exit code 0 means the step succeeded. Missing static state, a stop or an empty comparison exit with 1 and
a JSON body that names the cause. `session-coverage` exits with 0 only when every declared read resolves
and the profile preconditions are `SATISFIED`.

## Parameterized LP Rewards plan 0.1

`session-plan` takes one chosen `lpBps` from 0 to 99 to a prepared input in one call. It composes the steps
above: it opens the named session, or creates it once from one pinned source, registers the variant,
evaluates static coverage of the retained witness and, only when the reads are `COVERED` and the
preconditions `SATISFIED`, prepares the variant. It does not fetch the starting state again: every value
reuses the session's retained witness.

```sh
# first value: create the session from the pinned source
rhook-cases --home HOME session-plan --lp-bps 37 --scenario SCENARIO.json --sha256 HEX --checkpoint CHECKPOINT.json
# further values in the same session
rhook-cases --home HOME session-plan --lp-bps 25 --session SESSION_ID
```

```python
plan = ExecutionSDK(home).plan_lp_variant(37, session_id=session_id)
```

The result names `sessionId`, `variantId`, `selectedLpBps`, the checkpoint, the retained witness
(`sourceSha256`, `sourceScenarioCommitment`, `inventoryCommitment`, node and code counts), `staticCoverage`,
`profilePreconditions`, the prepared `scenarioCommitment` and `scenarioSha256`, `dynamicCoverage: UNKNOWN`,
`nativeExecution: NOT_PERFORMED`, `operation: OPERATION_NOT_BOUND` and `readiness` with each stop and the
remaining Stage B and C steps. Exit code 0 means `PLAN_READY_FOR_SEPARATELY_AUTHORIZED_NATIVE_RUN`.

Rules:

- `--lp-bps` is a plain decimal integer. `100` is refused with `BASELINE_LP100_IS_NOT_A_VARIANT`: LP100 is
  the recorded original rule and runs as `SCENARIO_BASELINE` in every run. Other values outside 0 to 99,
  fractions, exponents, signs other than `-`, leading zeros and non-integer API values are refused before
  anything is written.
- Planning the same value again returns the same identities and writes nothing new. The same source,
  checkpoint and value give the same `sessionId`, `variantId` and `scenarioCommitment` in any home.
- Planning never binds an operation. Binding reads the registered runtime, runs the worker identity check
  (a native process) and needs a registered host admission profile; that is Stage B. No consent, attempt
  marker, run directory or network request is produced.
- A `COVERED` result covers the declared initial reads only. Whether the witness suffices for the execution
  of a particular value is established only by a completed native run of that exact prepared input.

Results of several values stay separate: each verified variant keeps its own run record and verification
record, and `session-compare` lists them side by side. A comparison carries no EVM check of its own.

## Parameterized Execution workflow 0.2

Four commands take a planned `lpBps` to a verified result. They compose the existing Session and
ExecutionSDK steps; the operation binding, the one-shot consent, the resource limits, the fail-closed stops
and the absence of retries are those of `ExecutionSDK.run`, unchanged.

```sh
rhook-cases --home HOME session-plan   --lp-bps 37 --scenario SCENARIO.json --sha256 HEX --checkpoint CHECKPOINT.json
rhook-cases --home HOME doctor
rhook-cases --home HOME session-ready  --session ID --lp-bps 37 --runtime RUNTIME.json --sensor rhook-host-sensor
rhook-cases --home HOME session-run    --session ID --lp-bps 37 --operation OPERATION --local-owner --mac-ready
rhook-cases --home HOME session-result --session ID --lp-bps 37 [--text]
```

| Command | What it does | Native work | Exit 0 |
|---|---|---|---|
| `doctor` | Starts `/bin/sleep` in a new session as the supervisor starts its worker, reads it with the supervisor's own `/bin/ps -p PID -o pid=,ppid=,pgid=,rss=,comm=` query, reaps it; checks macOS arm64, not root, AC power and an open lid with the installed parser; reports registration | none (no worker, sensor, consent, network) | `READY` |
| `session-ready` | Uses the home's registered runtime and `macos-host-admission-v4` sensor, or registers the given reviewed files once; authenticates the prepared input; binds the exact `operationCommitment`; includes the doctor report and the exact `session-run` command | worker identity and input checks, no EVM | `RUN_READY` |
| `session-run` | Checks `--local-owner --mac-ready` and the operation format first, then the doctor; only on `READY` calls `ExecutionSDK.run` once, then `verify` and `session.verify_selected` | one run: `SCENARIO_BASELINE` + `SCENARIO_VARIANT` | `RUN_VERIFIED` |
| `session-result` | Builds one view of a verified variant from its sealed verification record and the retained run, after checking the run against its manifest | none | `VERIFIED_RESULT` |

`--lp-bps` names the variant registered by `session-plan`; `--variant ID` works as well. Python API:
`sdk.doctor()`, `sdk.ready_lp_variant(session_id, lp_bps=37, runtime=..., sensor=...)`,
`sdk.run_lp_variant(session_id, lp_bps=37, operation=..., local_owner=True, mac_ready=True)` and
`sdk.lp_variant_result(session_id, lp_bps=37)`. `examples/parameterized_execution.py` runs the whole sequence.

Rules:

- A doctor `BLOCKED` result stops `session-run` with `RUN_STOP_ENVIRONMENT_NOT_READY` before any consent,
  attempt marker or evidence directory: nothing is consumed and the same command can be run again from a
  regular macOS Terminal. App and agent sandboxes that forbid `/bin/ps` give `BLOCKED`.
- Once `ExecutionSDK.run` starts, the operation is closed whatever the result. `RUN_STOP` keeps the cause and
  the evidence; `RUN_COMPLETED_VERIFICATION_STOP` means the run completed but the existing verifier did not
  admit it, and nothing was recorded. Neither is retried. A verified variant is not runnable again.
- Evidence goes to `HOME-evidence/OPERATION` unless `--evidence` names a fresh directory outside the home;
  `DEVELOPER_RUN.json` there holds the run summary and, after verification, the result view.
- `session-ready` reports `OPERATION_CLOSED` when the operation was already attempted in this home, and
  `RUN_READY_ENVIRONMENT_BLOCKED` when the binding is ready but the doctor is not.

The result view (`rhook/parameterized-result/0.2`) lists both worlds with `lpBps`, `receiptStatus`,
`gasUsed`, `outerSwapFeePips`, the actor's target-token Transfer-event net, `stateRoot`, `receiptsRoot` and the
actor balance before and after; the exact difference in base units, as a percentage of the baseline and in
gas; the scenario, operation, verification, evidence and original-witness commitments; and the verification
status with its assurance labels. The measure is not profit and not a final balance. Verification checks the
recorded run with the existing verifier; it does not re-execute the EVM, and economic assurance stays
`UNRESOLVED`. Other hook parameters are not supported yet; their requirements are in `HOOK_PARAMETERS.md`.

## Second intervention: Dynamic Fee OFF (0.3)

A session can also hold a Dynamic Fee variant: the pool's recorded Dynamic Fee (ON) runs as
`SCENARIO_BASELINE` and Dynamic Fee OFF as `SCENARIO_VARIANT`, with LP Rewards unchanged at 100.

```sh
rhook-cases --home HOME session-plan   --dynamic-fee OFF --session ID        # or with --scenario/--sha256/--checkpoint
rhook-cases --home HOME session-ready  --session ID --dynamic-fee OFF --runtime DYNAMIC_FEE_RUNTIME.json --sensor rhook-host-sensor
rhook-cases --home HOME session-run    --session ID --dynamic-fee OFF --operation OPERATION --local-owner --mac-ready
rhook-cases --home HOME session-result --session ID --dynamic-fee OFF --text
```

Python: `sdk.plan_dynamic_fee_variant('OFF', session_id=...)`; the 0.2 methods take `dynamic_fee='OFF'`
instead of `lp_bps`.

- **What changes.** The existing Dynamic Fee OFF transform (`DYNAMIC_FEE_NATIVE.md`): two exact ordered storage
  writes before the variant world, Rules config maxFee 11500 → 3000 and sensitivity 2 → 0, Root record mode
  3 → 2 (recapture retained). The fee, gas, receipts and token transfers are then produced by the EVM; no fee
  value is substituted.
- **Authentication of the original value.** Planning authenticates the Root and Rules account paths, their
  code preimages and the five target storage leaves against the checkpoint state root through the retained
  witness (read-only, Node, no worker). The plan reports the writes as `interventionTargets`. Planning stops
  with `HOOK_BLOCK_NOT_ACTIVE` when Dynamic Fee is not configured ON at the checkpoint.
- **Separate worker.** The variant runs on the reviewed Dynamic Fee OFF derivative worker (profile
  `nitro-hookr-dynamic-fee-off/0.1`), not on the LP worker. Its registration, plans, operation and run live in
  their own SDK home, `HOME/profiles/hookr-dynamic-fee-off`; `session-ready` refuses a runtime manifest of
  another profile (`RUNTIME_PROFILE_MISMATCH`). The prepared input binds the derivative engine identity, so
  planning needs no worker.
- **Identities.** The Dynamic Fee variant has its own `variantId`, prepared input and `scenarioCommitment`.
  LP variants keep their identities. Without an explicit backend a variant changes one setting on its 0.1 /
  0.3 worker; LP and Dynamic Fee together are one typed set on the config-overlay worker (SDK 0.4,
  `CONFIG_OVERLAY.md`).
- **Coverage.** Static coverage of the session's common reads is the same for every variant; the Dynamic Fee
  targets are authenticated separately as above. Whether the witness suffices for the changed execution
  path is established only by a completed native run of that exact input.


## Identities

- **Session id**: commitment over profile, adapter version, checkpoint, source SHA-256 and scenario
  commitment, common action and environment, and the LP100 baseline. The same source gives the same id in
  any home. A different block hash, state root, chain id or block number is a different session; a session
  never switches checkpoint.
- **Variant id**: commitment over the session id and the variant descriptor (`RulesConfig.lpBps`
  100 to the replacement). Paths, timestamps and producer plan ids are not part of it.
- **Prepared input**: the existing `ExecutionSDK.prepare` output. Only the variant configuration word, the
  intent capsule and the scenario commitment may differ from the session source; the session checks this.

## Status of a variant

| Field | Values |
|---|---|
| `status` | `CONFIGURED`, `PREPARED_NOT_EXECUTED`, `RECORDED_RUN_VERIFIED`, `TEST_ONLY_BINDING_CHECKED`, `STOP` |
| `staticCoverage` | `NOT_EVALUATED`, `COVERED`, `MISSING`, `STOP` |
| `profilePreconditions` | `NOT_EVALUATED`, `SATISFIED`, `NOT_SATISFIED`, `UNKNOWN` |
| `dynamicCoverage` | `UNKNOWN`, or `ESTABLISHED_FOR_THIS_EXACT_INPUT_BY_VERIFIED_RUN` |
| `execution` | `NOT_PERFORMED`, or `RECORDED_NATIVE_RUN` |
| `nextRequirement` | The next step, for example `NEEDS_AUTHENTICATED_STATE` when static reads are missing or `PROFILE_PRECONDITIONS_NOT_SATISFIED` when the state is known but not admitted |

A failed or incomplete preparation of one variant is that variant's `STOP`; other variants are unaffected.

## Static coverage and witness reuse

`coverage()` builds a seed from the retained inventory (hash-keyed and deduplicated) and passes it to the
existing `ProofCollector`. The collector checks the checkpoint, every node and code hash and projects
proofs from the original root. Its network function refuses every request, so a read the seed cannot answer
is reported, not fetched.

For the Hookr profile the declared reads are the same prefetch subjects that live acquisition requests
(`scenario/acquire.mjs`), built with the same exported helpers. On the accepted on-demand run's retained
capture (checkpoint 101935336) the plan equals the recorded `PREFETCH_PLAN.json`, and all 24 dependencies,
220 slots and 20 code reads resolve from 686 nodes and 14 code preimages with 0 network requests. The same
check authenticates the original RulesConfig words against the LP100 baseline, proves the simulation actor
absent and recomputes the parent header hash. That capture is not distributed with this repository; its
parity test runs only when `RHOOK_SESSION_REAL_CAPTURE` points at a local copy.

The report keeps two results apart. `status` says whether the declared trie paths resolve.
`preconditions.status` says whether the profile admits that authenticated state: for `hookr-buy/0.1` the
parent header hashes to the checkpoint, the authenticated RulesConfig equals the LP100 baseline, and the
simulation actor is proven absent. A different configuration or an existing actor is `NOT_SATISFIED` even
when every path resolves; an unresolved check is `UNKNOWN`. A variant is pointed to a native run only when
its static reads are `COVERED` and its preconditions are `SATISFIED`.

Reporting rules:

- `UNKNOWN` is never zero, empty code or absence. Proven absence and proven-zero storage are separate statuses.
- Each unknown read names the missing trie node hash and path prefix; missing code names its code hash.
- Static coverage is the same for every LP variant of this profile, because the variant changes only a
  replacement word. Reads made during execution are different per variant and stay `UNKNOWN`.
- Covering the declared initial reads does not prove that trie updates or other execution reads are
  covered. Only a completed native run of an exact input establishes that, for that input.

## Verification

`verify_selected` first binds the run read-only: profile, checkpoint, common action, environment and engine,
and the exact prepared scenario commitment and bytes. A run of another variant, checkpoint or profile is
rejected before any verifier is called. It then calls the existing scenario compare, which runs the existing
recorded verifier through the registered worker's verify helper. That path needs a registered runtime and
is not exercised by this release's tests.

The result is recorded only when it is `VERIFIED_SCENARIO_COMPARISON` for the run's own scenario commitment
and carries exactly one `SCENARIO_BASELINE` and one `SCENARIO_VARIANT` projection, in that order, with both
receipt projections, both token nets and their exact difference. An unresolved, partial or unexpected result
stops and writes nothing; the variant stays `PREPARED_NOT_EXECUTED`. The stored comparison is checked for
the same shape again whenever the record is read.

Offline tests pass `test_only_backend`. Such records have status `TEST_ONLY_BINDING_CHECKED`, assurance
`TEST_ONLY_NOT_EVIDENCE`, and their comparison is `TEST_ONLY_COMPARISON_NOT_EVIDENCE`. A stored record whose
status, backend and assurance disagree is drift. Session files are plain local files: they detect
inconsistent edits, not a deliberate forgery by the machine's owner.

The historical [verify-pack](verify-pack/README.md) is a different evidence profile and is not used here.

## Storage

```text
HOME/sessions/<sessionId>/
  SESSION.json                 header, written once
  source/SCENARIO.json         retained source bytes, read-only
  COVERAGE.json                static coverage record, written once
  variants/<variantId>/
    VARIANT.json               descriptor and bindings, written once
    prepared/                  ExecutionSDK.prepare output
    VERIFICATION.json          verified run binding, written once
```

Every file is created exclusively. Nothing is overwritten; a second verification of a variant is refused.
A variant directory appears in one rename with its `VARIANT.json` already written, so an interrupted
registration leaves only a `variants/.staging-*` directory, which is never listed as a variant; registering
the same variant again completes it. An unreadable `VARIANT.json` stops with `VARIANT_RECORD_DRIFT`.

To move a session to another installation, export a [handoff package](HANDOFF.md) and import it there with
its manifest SHA-256. An imported session uses this same storage.

## Limits

One profile (`hookr-buy/0.1`), the fixed 0.001 ETH action, `lpBps` replacements 0 to 99 against LP100, and at
most 8 variants per session. Every session reports `nativeReexecution: NOT_PERFORMED`,
`heterogeneousAgreement: NOT_EVALUATED`, `economicAssurance: UNRESOLVED` and `qualifiedClaims: 0` until a
verified run says otherwise for a specific variant. Canonicality of the checkpoint is not established by the
source file; it needs an independently trusted block hash.
