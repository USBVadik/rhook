# RHOOK Developer Preview · first real reference

Use Node.js 24, npm and Git. Run the commands from the repository root.

The exercise is the publicly recorded Robinhood case `70397227:4`. It uses
a public, pinned reference and a locally generated inspection projection.
Both historical execution results are retained observations.

## Install from source

From the delivered root, set the software and documentation directories.
Use a fresh installation directory.

```sh
SOFTWARE="$PWD/sdk/evidence-consumer"
GUIDE="$PWD/sdk/evidence-consumer/examples"
DEMO="$(mktemp -d)"
mkdir "$DEMO/pack" "$DEMO/install"

npm pack "$SOFTWARE" --offline --ignore-scripts --pack-destination "$DEMO/pack"
npm install --prefix "$DEMO/install" --offline --ignore-scripts --no-audit --no-fund "$DEMO"/pack/*.tgz
RHOOK="$DEMO/install/node_modules/.bin/rhook-evidence"
```

## Open the public case

The only online step below fetches a public Git commit. The checkout includes
only the files used by this inspection example. Read the published notices
for the underlying material.

```sh
REV=493dc5b7a7ab101a2cfcd0be40f13eaa326405a2
git init -q "$DEMO/public-git"
git -C "$DEMO/public-git" -c credential.helper= fetch --depth=1 https://github.com/USBVadik/rhook.git "$REV"
mkdir "$DEMO/public-source"
git -C "$DEMO/public-git" archive "$REV" core/src \
  examples/robinhood-v4/scripts/artifacts.mjs \
  examples/robinhood-v4/scripts/common.mjs \
  examples/robinhood-v4/reference.json.gz THIRD_PARTY_NOTICES.md \
  | tar -xf - -C "$DEMO/public-source"

node "$GUIDE/project-public-reference.mjs" "$DEMO/public-source" "$DEMO/PUBLIC_INSPECTION.json"
"$RHOOK" "$DEMO/PUBLIC_INSPECTION.json" --json
```

Expected result for `70397227:4` is ACTUAL **SUCCESS**, BRANCH **REVERT**.
The example authenticates the exact reference file SHA-256 and checks the
local evidence format for 642 records and 321 pairs. It extracts lifecycle
observations and transaction identifiers into the existing inspection
format. It adds local summary commitments and withholds the full payload
and any verifier admission claim. The CLI shows `INSPECTED`,
`bindings.status = PARTIAL` and `verification.assurance = UNRESOLVED`.
Canonical finality, producer identity and the execution transition remain
outside this inspection. The script performs zero native replay.

[Recorded case 70397227:4](https://github.com/USBVadik/rhook/blob/493dc5b7a7ab101a2cfcd0be40f13eaa326405a2/examples/robinhood-v4/README.md#L94-L95) · [Public reference](https://github.com/USBVadik/rhook/blob/493dc5b7a7ab101a2cfcd0be40f13eaa326405a2/examples/robinhood-v4/reference.json.gz) · [Source notices](https://github.com/USBVadik/rhook/blob/493dc5b7a7ab101a2cfcd0be40f13eaa326405a2/THIRD_PARTY_NOTICES.md)

This path uses the existing file inspection command. The two exact
`rhook-evidence case --id ...` profiles still require their separately
admitted Pair03 or tx70 data. This exercise uses no wallet, service credentials,
blockchain RPC or native worker.
