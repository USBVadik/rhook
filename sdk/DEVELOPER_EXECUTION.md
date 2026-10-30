# Developer Execution SDK Alpha — prepared Hookr scenarios

`ExecutionSDK` exposes native execution, distinct from Build10/11 recorded previews.
It imports a prepared witness into a new local home, validates a bounded scenario,
prepares an exact operation and owns the existing native CLI workflow. It never
substitutes recorded receipts for execution or automatically fetches missing data.

## Supported profile

`hookr-buy/0.1` maps to backend`nitro-hookr-scenario/0.1`: one fixed Hookr pool on
Robinhood Chain4663, pinned contracts and ArbOS61 configuration. BASELINE is LP100;
VARIANT may be configured to an integer0–99. The retained LP50 example at
checkpoint99236464 is a prepared reference. A later local
[installed on-demand acceptance](SCENARIOS.md#installed-on-demand-acceptance)
completed a fresh-checkpoint LP100/LP50 discovery pair and a matching fresh offline
pair. That path obtains state through `CaseSDK`/`scenario-close`; this prepared
`ExecutionSDK` facade still requires an explicit local witness. Other values may
need additional witness; a configuration value is not a coverage guarantee.

The action is fixed: one hypothetical0.001ETH exact-input buy, public simulation
actor/nonce0, common modeled1ETH funding, gas cap10000000, minimum output1base unit,
sqrtPriceLimitX96=4295128740, deadline child timestamp+300s. Environment is derived
from the selected parent: child number/time+1 and explicit L1 base fee1Gwei.
The existing signed action is preserved; arbitrary calldata, pools, signers, gas
limits or transfers are not exposed. Never fund or broadcast from the public actor.

## Install the local source interface

Requires unoptimized Python3.12+. Use physical absolute paths without symlink
parents. Source-only installation and planning need no worker, account or memory
admission:

```sh
python3 -B sdk/install_cases.py --prefix /physical/path/to/new-sdk
/physical/path/to/new-sdk/bin/rhook-cases --home /physical/path/to/new-home execution-profiles
/physical/path/to/new-sdk/bin/rhook-cases --home /physical/path/to/new-home execution-capabilities
```

The home remains uncreated during those reads. The report distinguishes supported
chain/pool, worker/Node/sensor registration and static hashes, Node dependency
presence, prepared witness, recorded verifier and current host compatibility.
`nativeExecutionReady=false` remains honest: exact consent and fresh resource /
power/lid admission have not happened. A present file is not proof authentication.
The report does not read provider credentials or a local consent key. Its
`host.admissionProfiles` distinguishes default v2 runtime files from separately
registered, statically validated v3 sensor/code pins; neither is a live resource
observation. Use a fresh home when changing SDK versions instead of reusing
old registration, grants or input-home links.

For private native use, install the already pinned dependency directory with
`install_cases.py --dependencies /trusted/existing/node_modules` and explicitly
register the compatible runtime through existing `scenario-register-runtime`.
Runtime registration runs bounded `--identity`, not a producer. Optional
`scenario-register-host` registers the separate experimental v3 sensor. Neither
registration is permission to execute. No artifacts are downloaded automatically.

## Python: configure and import prepared witness

```python
from pathlib import Path
from rhook_alpha.execution import ExecutionSDK

sdk = ExecutionSDK(Path('/physical/path/to/new-home'))
configuration = sdk.configure(
    profile='hookr-buy/0.1', lp_bps=50,
    checkpoint={
        'chainId': 4663, 'blockNumber': 99236464,
        'blockHash': '0x3d8a7eff122421e924553d9ca0949e10c919da1703b3ddd07f8433999e6d0fd9',
        'stateRoot': '0x7a947171a7c1620561d1ea629e1233d078518f422ddcb9ff8dcff346ae3624be',
    },
)
prepared = sdk.prepare(
    configuration, Path('/private/prepared/SCENARIO.json'),
    expected_sha256='EXACT_REVIEWED_INPUT_SHA256',
    output=Path('/physical/path/to/fresh-prepared'),
)
```

`transaction` is optional; when supplied its exact supported fields are
`amountInWei:'1000000000000000'`, `gas:10000000`,
`fundingWei:'1000000000000000000'`. Unsupported settings fail with a stable cause
and nextStep. If checkpoint is omitted, the explicitly SHA-pinned input selects it;
that does not establish consensus trust. Inputs are bounded strict JSON with safe
integer encoding. No arbitrary nested configuration editing is offered.

The prepared directory contains fresh local plan/capture links; it does not need
the old home, authority or source path. The original witness file is never edited.
For a changed LP the importer changes only the allowed variant bits, checkpoint /
intent commitment and scenario commitment. Root, inventory, signed action, engine
pins, common setup and limits remain unchanged. Output reports
`PENDING_NATIVE_ADMISSION` and `witnessClosure:NOT_EVALUATED`.
SHA/shape validation is never labelled Merkle authentication or completed EVM.

CLI equivalent:

```sh
rhook-cases --home HOME execution-configure --lp-bps 50 --checkpoint CHECKPOINT.json > configuration.json
rhook-cases --home HOME execution-prepare --configuration configuration.json \
  --witness SCENARIO.json --witness-sha256 EXACT_PIN --output FRESH_PREPARED
```

One runnable example is [execute_prepared_hookr.py](examples/execute_prepared_hookr.py).
It defaults to capability reporting/preparation. `--sdk-root PREFIX/lib` selects
an installed source SDK explicitly. It cannot run without exact consent flags.

## Authenticate, review and execute once

```python
admission = sdk.authenticate(Path(prepared['prepared']))  # bounded Go helper; producer0
proposal = sdk.operation(Path(prepared['prepared']), host_profile='v2')
# Stop for operator review here; the hashable native binding is proposal['binding'].
# After direct approval of proposal['operationCommitment'] and current AC/open lid:
result = sdk.run(
    Path(prepared['prepared']), operation=APPROVED_EXACT_OPERATION,
    evidence=Path('/physical/path/to/fresh-workflow-evidence'),
    local_owner=True, mac_ready=True, host_profile='v2',
)
```

Native authentication rechecks original root/header, transaction signature/calldata,
profile and required initial state. Its scope is KNOWN_PREREQUISITES_ONLY. Dynamic
read/trie-update closure is established only when both worlds complete from nil
Source. Missing nodes/code/slots must remain missing; no hydration, zero invention
or borrowed result is permitted. Exact helper stderr and its retained file/digest
are reported when admission stops; native failed-world/lookup diagnostics remain
in the linked native result.

CLI sequence:

```sh
rhook-cases --home HOME execution-authenticate --prepared PREPARED
rhook-cases --home HOME execution-operation --prepared PREPARED --host-admission v2
# Only after reviewing the exact returned operation and confirming current readiness:
rhook-cases --home HOME execution-run --prepared PREPARED --operation EXACT_OPERATION \
  --host-admission v2 --evidence FRESH_EVIDENCE --local-owner --mac-ready
```

V3 is opt-in via `--host-admission macos-host-admission-v3` after separate host
registration; it is experimental, not a reservation or guarantee of no impact on
other applications. Both v2 and v3 recheck the exact operation inside the child.
The v3 `free-telemetry/0.1` revision records immediate free pages and estimated
available RAM without blocking admission or runtime on those values. Pressure,
sample validity/freshness, swap, RSS, CPU/wall, power and cleanup checks remain
active. Its distinct policy/code hashes require fresh host/runtime registration
and a newly bound operation. Previously sealed strict-v3 evidence is unchanged.
The outer SDK workflow owns/reaps the complete process group; the original native
supervisor enforces RSS≤1GiB, native CPU/wall≤120s, stage≤140s, workflow≤180s,
fresh power/lid/resource checks and owned cleanup. V2 and the native worker are unchanged.

A permanent developer-attempt marker prevents repeating the same operation even
if the outer workflow stops before grant issuance. The native layer issues and
consumes its operation-bound authority only after prerequisites. Local consent
assumes a trusted local operator; flags/HMAC are not a founder digital signature.
Any STOP closes this attempt. A successor is a new explicit plan/operation and
requires its own approval; the SDK never creates one automatically.

The native run is bound under `HOME/scenarios/runs/PLAN_ID` and returned explicitly.
Choose HOME to control that root. Prepared input and workflow evidence directories
are caller-selected; evidence must be fresh and separate from HOME/prepared input.
The wrapper accepts success only from the new linked RESULT/BINDING and confirmed
process-group/native cleanup. A failed process or uncertain cleanup cannot return
`EXECUTION_COMPLETED`.

## Verify and compare the new run

```python
if result['status'] == 'EXECUTION_COMPLETED':
    verified = sdk.verify(Path(result['runDirectory']))
    comparison = sdk.compare(Path(result['runDirectory']))
```

Or use `execution-verify --run NEW_RUN` / `execution-compare --run NEW_RUN`.
These are separate bounded read-only helper commands, not part of the180-second
replay workflow. They use existing native original-input/evidence authentication,
then derive token Transfer net, Swap fees and gas. Accurate target-token aliases
are added while legacy comparison keys remain compatible. No symbol/decimals/USD
price or profitable arbitrage is assumed. Pre-native child failures remain labelled
unlinked diagnostics, preserving their original cause without claiming execution.
The example also preserves a completed native result if a later read-only verify
or compare fails, identifying that later stage separately.

## Capability matrix and remaining scope

| Capability | This Alpha |
| --- | --- |
| Configure selected pool/profile, LP0–99 |Offline; no runtime or grant needed. |
| Import local prepared witness into fresh home |Offline SHA/shape checks; no old home or authority needed. |
| Authenticate original state |Compatible registered native helper required; known prerequisites only. |
| Execute independent BASELINE/VARIANT |Existing nil-Source Go/Nitro pair; exact consent and fresh host admission required. |
| Native host |macOS arm64 for this scenario backend. Linux can plan/inspect; native Linux scenario integration is not claimed. |
| Runtime redistribution |Not provided; accepted worker/Node/sensor/dependencies and witness remain private/HOLD. |
| Optional live-assisted preparation |Existing separately authorized CaseSDK scenario acquisition/closure; never automatic in this offline facade. |
| Provider account for complete offline input |Not required. No credential is read by this facade. |
| Recorded Build10/11 evidence |Existing scenario-evidence-* API/CLI unchanged and distinct. |
| Arbitrary pool/action/contract |Unsupported; explicit actionable error. |
| Other LP values with same witness |May reveal missing dependencies; no closure claim from successful configuration. |
| Independent EVM/Rust/consensus |Not established by this interface; qualified Claims0. |

Fresh Build12 native producer acceptance is a separate exact operation. Offline
integration fixtures are explicit test doubles, not proof of new Nitro execution.
Retained checkpoint input preparation can be tested without executing a producer.
Current engineering status and native acceptance/remaining blockers must be read
from the local Build12 report, not inferred from the presence of these APIs.

For a fresh checkpoint, the installed [scenario closure CLI](SCENARIOS.md#execution-guided-witness-closure)
combines bounded acquisition, both discovery worlds, a frozen witness and a new
nil-Source pair, followed by verification/comparison. It owns its existing process
workflow directly. This remains a separately reviewed live/native operation;
`ExecutionSDK.run()` continues to be the offline prepared-witness path and never
acquires state implicitly. A retained successful witness does not guarantee that
a fresh root will close within the acquisition budget.
