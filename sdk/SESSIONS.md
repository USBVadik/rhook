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

This release implements the offline part. Creating, inspecting, covering and preparing a session start no
native worker, open no RPC connection, request no host admission and consume no consent. Native execution of
a prepared variant is the existing `ExecutionSDK` workflow and is not run or qualified by this release.

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

`sdk.open_session(session_id)` reopens a session offline. Every identity is re-derived from the retained
source; an edited manifest or source copy is reported as drift. `examples/counterfactual_session.py` runs
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
a JSON body that names the cause.

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
| `dynamicCoverage` | `UNKNOWN`, or `ESTABLISHED_FOR_THIS_EXACT_INPUT_BY_VERIFIED_RUN` |
| `execution` | `NOT_PERFORMED`, or `RECORDED_NATIVE_RUN` |
| `nextRequirement` | The next step, for example `NEEDS_AUTHENTICATED_STATE` when static reads are missing |

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

## Limits

One profile (`hookr-buy/0.1`), the fixed 0.001 ETH action, `lpBps` replacements 0 to 99 against LP100, and at
most 8 variants per session. Every session reports `nativeReexecution: NOT_PERFORMED`,
`heterogeneousAgreement: NOT_EVALUATED`, `economicAssurance: UNRESOLVED` and `qualifiedClaims: 0` until a
verified run says otherwise for a specific variant. Canonicality of the checkpoint is not established by the
source file; it needs an independently trusted block hash.
