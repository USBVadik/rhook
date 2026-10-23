# Acceptance03 external dispatcher: exact source reference

The four Python files `dispatch_once.py`, `staging.py`,
`authenticate_preserved.py` and `test_dispatcher.py` are byte-identical copies
from the sealed dispatcher repair used by successful acceptance03. Their exact
hashes, accepted SDK source closure and build/evidence commitments are recorded
in `docs/SDK_ALPHA_V2_PROVENANCE.json`.

This reference is not a ready-to-run acceptance distribution. The pure file
authenticator retains one founder-workspace absolute root and expects separately
held sealed histories, prepared inputs, a fresh exact plan and explicit approval.
Those histories, plans/authorities, runtime data, packages and executables are
intentionally absent. Do not invent them, repoint old records, run a historical
acceptance command or infer permission from having this source.

Trusted CLI staging uses a finite 256 MiB file limit. The unchanged SDK resets
the native worker's file limit to 64 MiB before execution. The dispatcher preserves
the 180/140 s outer workflow/replay deadlines and owned cleanup. Staging snapshots
do not replace source/build/package checks at use or the fresh internal admission.

The original regression module assumes the old sibling source layout. The small
`run_regression_tests.py` harness binds only its test SDK-path constant to this
checkout; it does not modify any copied production/test file or SDK behavior.
It exercises the exact copied production launch path, SDK copy function and
unchanged worker guard around synthetic data/children. No real host readiness
sensor, historical package, scientific authority, RPC/WSS or Go/Nitro is used:

```sh
python3 tools/sdk-alpha-v2-acceptance-reference/run_regression_tests.py
```

Future portability of this operational dispatcher is separate work. The main SDK
CLI commands and policy are documented in `SDK_ALPHA_V2_QUICKSTART.md`.
