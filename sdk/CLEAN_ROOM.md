# Source-only developer integration

Python 3.12+ is sufficient for installation, case import, inspection, planning,
capability reporting and the supported recorded-evidence consumer. These steps
do not download a worker, acquire RPC state or execute EVM.

```sh
python3 -I -B sdk/install_cases.py --prefix /absolute/new/sdk-prefix
RHOOK=/absolute/new/sdk-prefix/bin/rhook-cases
"$RHOOK" --home /absolute/new/case-home cases
"$RHOOK" --home /absolute/new/case-home interventions
"$RHOOK" --home /absolute/new/case-home execution-capabilities
```

The installer bootstraps with stdlib only, authenticates its pinned validation
helper before executing those exact bytes, and validates every inventory entry
before creating the prefix. It rejects modified policies, extra research modules,
symlinks and an edited inventory. `SOURCE_INSTALL_INVENTORY.json` and
`CASE_INSTALL.json` retain the installed source boundary. Use the source-only
release tree; private experiment trees are not installation sources.

The default v2 resource policy stays unchanged. The separate Scenario SDK v3
opt-in now uses `free-telemetry/0.1`: free/estimated-available RAM are telemetry
at admission and runtime; pressure, swap, freshness, RSS, CPU/wall, power/lid and
cleanup controls remain active. Fresh matching registration and exact consent
are required. This is not a RAM reservation. The private historical Build27
free-page policy and calibration module are still excluded. The inventory's
`experimentalFreeTelemetryIncluded: false` describes those excluded historical
modules; the supported scenario v3 policy is explicitly inventoried by its hash.

For an explicitly supplied case bundle containing `CAPSULE.json` and
`BLOCK_PACKAGE.json`:

```sh
"$RHOOK" --home /absolute/new/case-home import-case /absolute/case-bundle
"$RHOOK" --home /absolute/new/case-home inspect --case my-case
"$RHOOK" --home /absolute/new/case-home plan --case my-case --set lpBps=50
```

The catalogue also exposes the exact supported historical Dynamic Fee OFF
profile. Use `--set dynamicFee=OFF` only with its matching historical bundle.
Neither a content-addressed import nor a plan establishes original-root
authentication, witness completeness or an executed branch.

Python applications import `CaseSDK` from `rhook_alpha.cases.api` and
`ExecutionSDK` from `rhook_alpha.execution` using the installed `lib` directory.
`CaseSDK.import_case`, `inspect`, `plan` and `describe` share the CLI behavior.
`ExecutionSDK.capabilities()` identifies missing runtime, witness, dependencies
and unsupported hosts without observing host resources or issuing authority.
An unregistered historical runtime fails with `NATIVE_RUNTIME_MISSING`.

## Recorded evidence

The existing `scenario-evidence-inspect`, `scenario-evidence-verify` and
`scenario-evidence-compare` commands accept the complete pinned Build10/11
packet supplied with `--bundle`. Their Python equivalents are
`inspect_recorded_scenario`, `verify_recorded_scenario` and
`compare_recorded_scenario`.

They check file/evidence commitments, discovery/offline equality, the recorded
intervention and log arithmetic. They do not re-execute EVM, verify MPT proofs,
recompute receipt tries or provide independent Rust confirmation. They are not
a generic verifier for arbitrary Build26/27 archives. No private packet is
included by this installation or example.

## Integration tests

```sh
python3 -B sdk/tools/test_offline.py
```

`tests_cases/test_cleanroom_source.py` uses the real installed CLI and isolated
Python API with an empty account home, fresh case homes and a minimal environment.
Its default fixtures are synthetic and make no chain claims. Optional authorized
local inputs can be supplied through:

- `RHOOK_CLEANROOM_CASES`: a JSON list of explicit bundle paths, case IDs,
  arrival counts, supported intervention assignments and input commitments.
- `RHOOK_RECORDED_TEST_BUNDLE`: the complete pinned Build10/11 evidence directory.
- `RHOOK_CLEANROOM_LOG_DIR`: an optional local destination for command receipts.

Keep private test inputs outside the release source tree. Those environment
variables do not authorize publication, native execution or RPC acquisition.
For stronger isolation on a supported test host, run the suite inside an OS
sandbox that allows only the staged public source, explicit test inputs and
system Python libraries, while denying original home/archive paths and network.

Fresh native execution still requires separately supplied compatible runtime,
complete witness, supported host, exact consent and resource admission. Current
worker v0.2's old-case regression and external runtime distribution remain
separate work. `qualifiedClaims=0`; general recorder coverage remains unknown.
