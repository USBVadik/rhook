# Saved Hookr case SDK

This local CLI prepares rule interventions for the saved Pair03 block: Robinhood
Chain 4663, block 93251803, seven ordered arrivals, standard HookrRules. It accepts
`RulesConfig.lpBps` changes from 100 to an integer from 0 through 99. The change
adjusts the LP Rewards add-on and its associated protocol share; it does not
remove base/dynamic fees, recapture or the whole Hook Block.

The unified worker is an offline-prepared candidate. Native acceptance of this
binary has not been performed. Earlier, separate workers executed values 0 and
50. Planning another value establishes neither witness sufficiency nor economics.

## Requirements

The current build profile is macOS arm64, Python 3.12 or newer without `-O`,
Node 24 or newer, and the authenticated retained Go/Nitro/libstylus and adapter
npm dependencies. There is no automatic dependency installation or download.
The saved block package is a separate private input, absent from source control.
Clean installation on another machine is not established.

## Build and register

Build explicitly, using local retained inputs. The build command compiles the
worker and runs synthetic tests; it does not launch that worker or an EVM.

```sh
python3 -B -m case_sdk.build --retained-build "$RETAINED_BUILD" \
  --output "$NEW_BUILD" --sensor "$HOST_SENSOR" --node "$NODE"
python3 -B ./rhook-case inspect --package "$PACKAGE" \
  --workspace "$CASE" --build-record "$NEW_BUILD/BUILD.json"
python3 -B ./rhook-case plan --workspace "$CASE" --expected-old 100 --lp-bps 50
```

Use a fresh workspace outside this source checkout. The CLI reports `planId`,
`bindingsPath` and proposed `runOutput`; it does not create a run or grant consent.
Package-only inspection can omit `--build-record` and select Node through
`RHOOK_NODE` or PATH. Executable request preparation requires a registered build.

The worker hash is shared across all eligible values. A plan has its own semantic
commitment and runtime-file hash. A fresh opaque plan ID also binds a distinct
run path, even when planning the same value twice. Planning never recompiles.
Paths containing spaces and Unicode are passed as arguments, not shell code.

## Separately authorized replay

Review the exported bindings before obtaining approval for that exact operation.
Approval is an external trusted-local-operator JSON artifact, not a cryptographic
signature. This SDK does not generate it or convert a flag into permission.
Old approvals and approval for another plan/output are rejected.

```sh
python3 -B ./rhook-case replay --workspace "$CASE" \
  --plan "$PLAN_ID" --authority "$APPROVAL"
python3 -B ./rhook-case verify --run "$RUN_OUTPUT"
```

Replay consumes the operation before fresh resource admission. A STOP closes it;
there is no retry, hydration, network/provider fallback or automatic next case.
Both worlds start independently from the original parent with a nil Source.
BRANCH runs only after ACTUAL matches canonical stateRoot, receiptsRoot and
blockHash. All seven arrivals are included in both worlds.

Limits retain the developer v2 policy: native CPU/wall 120 seconds, native stage
140 seconds, workflow 180 seconds; sampled worker RSS 1 GiB, admission free RAM
1.5 GiB and runtime floor 0.5 GiB, normal pressure and no swap growth. Telemetry,
output limits, child cleanup and one-shot latches remain enforced. Sampling can
miss short peaks; free RAM and the Go memory target are not memory reservations.
The native entry still requires the agreed local execution context.

## Results

`PLANNED` has no execution or economic result. `COMPLETED` requires a recorded
native pair, canonical ACTUAL gate, resources, verification and confirmed child
cleanup. Missing state produces `MISSING_WITNESS` only with typed evidence;
resource failure is `HOST_STOP`. Other failures preserve the phase and cause,
including `CANONICAL_MISMATCH`, `VERIFICATION_FAILED` and
`INTERRUPTED_UNVERIFIED`. Unknown invocation counts stay null.

Receipt REVERT, zero deltas and negative economics are valid observations, not
missing-state errors. Recorded verification returns `RECORDED_INTEGRITY_PASS`
with mode `RECORDED_VERIFICATION`; it never claims a new execution. Verification
uses the original registered local kit and source checkout and does not relocate
an arbitrary archive or independently replay/prove its final state roots.

All results remain single-engine observations: economic assurance UNRESOLVED,
heterogeneous agreement NOT_EVALUATED, qualified Claims 0. Arbitrary blocks,
other rules, current HookrRouter swap building, remote service isolation and
Rust qualification are outside this case. Public/SDK delivery remains HOLD.
