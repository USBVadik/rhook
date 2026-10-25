# Hookr Alpha quickstart

## Public clone: run offline tests

With Python 3.12+ without optimization, from the repository root:

```sh
python3 -B sdk/tools/test_offline.py
```

No worker, sensor, witness or RPC account is needed. These synthetic tests do
not execute the EVM. A clone alone cannot install the complete native demo.

## Private pilot: use its own kit

The private macOS developer kit completed clean installation and a new native
LP100→50 pair on 25 October 2026, then verified and compared that new run.
Its [case study](../docs/research/hookr-pair03-100-to-50.md#installed-developer-pilot-25-october-2026)
records the outcome. The external pilot is prepared but has not been sent.

If you receive that kit through an approved pilot, follow its `START_HERE.md`
and bundled `source/install_alpha.py`. It has a separately built developer
worker and its own pinned input bundle. Do not combine that bundle with the
older public installer registration below. No executable asset URL is offered
by this repository.

## Public-source installer with matching original inputs

The remaining commands document the public source's original runtime route.
They require approved access to the exact matching source and assets, not just
an arbitrary worker or the newer private pilot bundle.

Requirements: Apple Silicon Mac, macOS 15.5+, unoptimized Python 3.12+, and
space for about 295 MB of expanded original inputs plus source and a Python venv.
The newer private pilot has different artifact sizes; its own guide is authoritative.
Version and platform testing limits are in [COMPATIBILITY.md](COMPATIBILITY.md).

Supply the original 198-file engine tree and exact `pair03-inputs.tar.gz`
bundle through an approved channel. The bundle contains the pinned worker,
sensor, Node, npm dependencies and saved block package. The installer hashes
every engine file and asset, creates no execution grant and runs no host sensor.

```sh
mkdir -p .install
python3 -I -B sdk/install_alpha.py \
  --runtime-source /path/to/approved/original-engine \
  --assets /path/to/approved/pair03-inputs.tar.gz \
  --prefix "$(pwd -P)/.install/alpha"
RHOOK="$(pwd -P)/.install/alpha/bin/rhook"
CASE_HOME="$(pwd -P)/.rhook/alpha"
```

Keep installation and case paths fixed after planning. Existing prefixes are
rejected; there is no automatic repair or component upgrade.

## Inspect and plan

```sh
"$RHOOK" --home "$CASE_HOME" inspect --case hookr-pair03
"$RHOOK" --home "$CASE_HOME" plan --case hookr-pair03 --set lpBps=50
"$RHOOK" --home "$CASE_HOME" describe --plan PLAN_ID
```

Use the returned `planId`. These commands authenticate the saved case and
construct a plan. They run no EVM and predict no branch economics. Integer
values 0–99 can be planned; this release's native acceptance target is 50.
Planning support does not establish native results for every value.

## Authorize one fresh replay

Only proceed when you own/control this machine and intend one native attempt.
Connect power and leave the lid open. Existing v2 admission requires normal
pressure, no sampled swap growth and at least 1.5 GiB free-page headroom. It
is conservative and reserves no memory.

```sh
"$RHOOK" --home "$CASE_HOME" authorize --plan PLAN_ID --local-owner --mac-ready
"$RHOOK" --home "$CASE_HOME" replay --plan PLAN_ID --authority GRANT_PATH
```

Run promptly with the returned authority path. The grant expires after ten
minutes and must have at least three minutes remaining when consumed. Consent
is bound to this installation, owner, host and exact plan. It is a local HMAC mechanism, not a
remote signature or permission from a third party. Consent is consumed before
admission; a STOP closes the attempt permanently. Do not reuse a grant, rerun
a closed plan or edit thresholds to obtain PASS.

ACTUAL≤1; BRANCH≤1 only after canonical stateRoot, receiptsRoot and blockHash
match. Both worlds start from independent original-parent copies. RPC, WSS,
hydration and automatic retries are absent. Limits: native CPU/wall 120 s,
native stage 140 s, installed replay workflow 180 s, sampled worker RSS 1 GiB,
runtime free headroom at least 0.5 GiB. Sampling can miss brief peaks; this is
not a guarantee of zero impact on other applications.

## Verify and compare

Only after `COMPLETED` with confirmed cleanup:

```sh
"$RHOOK" --home "$CASE_HOME" verify --run RUN_DIRECTORY
"$RHOOK" --home "$CASE_HOME" compare --run RUN_DIRECTORY
```

These separate read-only commands are outside the replay's 180-second budget.
`verify` authenticates artifacts, proofs and execution records without EVM
re-execution. `compare` verifies first, then derives transfer, fee and gas
differences from that run. Recorded PASS is not a new native replay or an
independent-engine result.

## Python API example

Use the installed Python so imports and runtime identity agree:

```sh
.install/alpha/python/bin/python -I -B sdk/examples/execute_hookr.py \
  --home "$CASE_HOME" --lp-bps 50
```

The example defaults to planning. Only explicit `--execute --local-owner
--mac-ready` opts into a native attempt. CI never supplies these flags.

```python
from rhook_alpha import LpBps, SDK

sdk = SDK()
sdk.inspect("hookr-pair03")
plan = sdk.plan("hookr-pair03", LpBps(50))
print(sdk.describe(plan["planId"]))
# Only with explicit local consent:
# grant = sdk.authorize(plan["planId"], local_owner=True, mac_ready=True)
# run = sdk.replay(plan["planId"], grant)
# After COMPLETED and confirmed cleanup:
# print(sdk.verify(run["runDirectory"]))
# print(sdk.compare(run["runDirectory"]))
```
