# Historical Dynamic Fee OFF — one supported saved Hookr block

Profile: `nitro-hookr-historical-dynamic-fee-off/0.1`.
Adapter: `hookr-1.historical-dynamic-fee-off/1`.

This profile prepares **real signed historical input**, not a synthetic buy.
It supports only block93251803, original parent93251802, subject
`0xbdc353fe6485a1e4e14e6d6fa358d9e7cdd333a986ce0440e7a76fcdb09aa41c`
at ordinal3. All seven original raw arrivals and their historical environment
are retained. No account is funded, re-signed, substituted or broadcast.

ACTUAL starts at the original parent without a patch. BRANCH is permitted only
after canonical stateRoot, receiptsRoot and blockHash all match. It starts again
from an independent nil-Source bridge and changes exactly two words: Rules
maxFee11500→3000/sensitivity2→0, Root mode3→2. LP100, recapture and other bits
remain fixed. The parent-level intervention has **whole-block causal scope**.
It is not an administrative transaction or an index3-only patch.

## Python and CLI preparation

The private retained `BLOCK_PACKAGE.json` is required. Its exact hash is checked
before packaging. Preparation creates no authority and starts no helper/EVM.

```python
from pathlib import Path
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.historical import ADAPTER
from rhook_alpha.cases.historical.adapter import profile

p = profile()
sdk = CaseSDK(Path("/absolute/private/new-home"))
sdk.package_case(Path("/absolute/private/BLOCK_PACKAGE.json"),
    Path("/absolute/private/new-capsule"), case_id="hookr-historical-off",
    adapter=ADAPTER, subject_index=3,
    input_commitment=p["inputCommitment"], witness_commitment=p["witnessCommitment"])
sdk.import_case(Path("/absolute/private/new-capsule"))
plan = sdk.plan("hookr-historical-off", {"rule": "dynamicFee", "value": "OFF"})
print(sdk.describe(plan["planId"]))
```

After packaging/import, the equivalent CLI planning command is:

```sh
python -m rhook_alpha.cases --home /absolute/private/new-home plan \
  --case hookr-historical-off --set dynamicFee=OFF
```

`register-runtime` requires the separately pinned historical derivative, Node,
and the existing **v2** sensor. `authenticate` checks proofs at the explicitly
trusted parent without EVM execution. Missing runtime artifacts fail closed.
`authorize` remains an explicit fresh local-owner/AC/open-lid consent action;
it is never performed by packaging or planning. `replay` requires that exact
grant, fresh measured AC/open-lid and v2 resource admission. Previous v3 scenario
consents/registrations do not silently authorize this profile.

Native execution stays limited to ACTUAL≤1/BRANCH≤1/B0, RPC/WSS/hydration/onchain0,
RSS1GiB, native CPU/wall120s, stage140s and workflow180s, with owned cleanup.
All v2 numerical bounds are retained. This SDK does not poll/retry admission.
There is no Alchemy account, provider, signer key or chain connection in this path.

## Evidence and implementation boundaries

New world/completion/verification domains cannot be relabelled as LP or synthetic
Dynamic Fee evidence. The verifier authenticates the full historical input,
signed senders, proofs/code, overlay, two independently derived initial roots,
headers, receipt roots, events and linked records. Verification is **not EVM
reexecution**, final-state transition proof or consensus/finality proof.
Token output, gas and Dynamic Fee OFF success remain unknown until a separately
authorized native acceptance. Existing witness closure only covers prior ACTUAL
and LP50; new transitive reads/final trie updates can still fail closed.

The derivative composer hash-checks the existing worker/controller and runner.
Only the staged runner gains an internal overlay callback; old LP entry points
retain their typed wrapper. Accepted engine files, workers and installations
are unchanged. Source pins make an incompatible upstream edit fail the build,
rather than silently applying a textual transform. No generic storage-write API
or arbitrary pool support is exposed.
