# Developer SDK Alpha

RHOOK is a Counterfactual Execution protocol. Hookr is its first supported
application; the Alpha exposes a closed set of supported interventions.

The CLI, Python API, portable CaseSDK, historical LP / Dynamic Fee OFF adapters
and offline tests are public source.
A private executable pilot has also passed clean installation, a fresh native
LP100→50 replay and verification of its own new run on the development Mac.
Its full ACTUAL/BRANCH files matched the historical references.

**The executable pilot is not a public download.** The next product test is one
external developer installing it on another supported Mac and reporting feedback.
See the [Hookr demonstration](../docs/research/hookr-pair03-100-to-50.md) for the
result, canonical gate and distinct Mac/Linux observations.

## Run what is public

From the repository root, with Python 3.12+ without optimization:

```sh
python3 -B sdk/tools/test_offline.py
```

The tests use synthetic inputs and mocked native dispatch. They start no worker,
sensor or network client, and need no private runtime bundle or provider account.
A passing test suite is not a new EVM replay.

For source-only installation, use the [clean-room guide](CLEAN_ROOM.md) and
[case installer](install_cases.py). Its exact 317-file inventory excludes private
calibration modules and preserves the approved default resource policy. The
bootstrap authenticates its validation helper before executing it. Unknown
source files, changed policy bytes and edited inventory pins fail closed.

The maintained historical entry points are the [CaseSDK API](rhook_alpha/cases/api.py)
and [case CLI](rhook_alpha/cases/__main__.py). The older [fixed Alpha installer](install_alpha.py),
[API](rhook_alpha/api.py) and [example](examples/execute_hookr.py) retain their own
source/runtime binding. Do not combine the two installations or their assets.

## Portable cases development

The [portable case workflow](CASE_CAPSULES.md) adds source-only installation,
content-addressed capsules, multiple local cases and adapter plans. The local
[historical execution guide](HISTORICAL_EXECUTION.md) covers the maintained
ACTUAL/BRANCH path, supported LP and Dynamic Fee OFF descriptors, exact-operation
review and separate owner consent. Build18 accepted one historical Dynamic Fee
ON/OFF pair from original parent93251802 with all seven original arrivals, including the signed subject;
same-engine recorded verification is distinct from independent EVM verification.
See [source synchronization scope](SOURCE_SYNC.md) for the imported milestones,
publication adaptations and optional retained-fixture tests. The installed
[on-demand scenario path](SCENARIOS.md#installed-on-demand-acceptance) later
completed one local fresh-checkpoint LP100/LP50 discovery pair and a matching
fresh nil-Source pair. This does not qualify every exported workflow.

The two later private [recorder-only results](RECORDER_RESULTS.md) reproduced
completed historical pairs from recorded original-state dependencies. These are
same-engine observations, not an external installation test or a public recorder
runtime release. `qualifiedClaims=0`; `nativeRecorderCoverage=UNKNOWN`.

## Runtime availability

| Surface | Available now |
| --- | --- |
| Public clone | SDK/API source, adapter and offline tests. No self-contained native Pair03 replay. |
| Private developer pilot | Install → inspect → plan → local consent → replay → verify → compare passed locally on 25 October 2026. Recipient handoff is prepared, not sent. |
| Installed on-demand Scenario SDK | One local installed CLI completed fresh acquisition → discovery2 → witness freeze → offline2 → verify/compare on 30 October 2026. Worker/witness remain private; arbitrary amounts/pools are unsupported. |
| Independent developer reproduction | Not yet performed. This is the next milestone. |

The [quickstart](QUICKSTART.md) keeps private-pilot instructions separate from
this public source's original runtime registration. Follow the instructions
matching the assets you actually have; the source and binary identities differ.

`rhook_alpha/` is the installed API. `developer/` authenticates and installs the
pinned runtime. `engine/case_sdk/` implements plans and the canonical ACTUAL gate.
The other engine modules include retained dependencies and historical reference
tools. Their old milestone statements describe earlier snapshots; they are not
the current product entry point.

## Source and evidence boundary

This public import comes from checkpoint
`41ef7672094caf91009a51b197ac4c5e64c35c8d`, without private Git ancestry.
Its 198-file engine closure is retained because the manifests and native bindings
cover that source set. Seven files have path-only substitutions; it is not
byte-identical to the original scientific runtime source.

The older fixed Alpha installer still requires the original engine tree, checked against
`developer/accepted-source.json`, and its matching pinned asset bundle.
[source-provenance.json](source-provenance.json) records accepted/public hashes
and publication adaptations. No native acceptance of this adapted public
installer is claimed. The later private pilot uses a separately relinked
worker/source registration and its own bundled installer. It is not silently
registered as the older scientific binary.

The source-only case installer copies the reviewed inventory from this clone;
it does not require that private bundle. Missing native components produce
actionable errors, including `NATIVE_RUNTIME_MISSING`. Registration and replay
are separate operations: even runtime registration starts a worker identity
check. No fresh external native reproduction is claimed by source installation.

Read [compatibility](COMPATIBILITY.md), [distribution](DISTRIBUTION.md) and
[release notes](RELEASE_NOTES.md). Original RHOOK-owned source/docs use the root
[Apache-2.0 license](../LICENSE), with the third-party/data exceptions in
[LICENSE_SCOPE.md](LICENSE_SCOPE.md). No binary or witness rights follow merely
from publishing this source.
