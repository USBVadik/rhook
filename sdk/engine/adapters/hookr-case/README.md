# Hookr Case Adapter v0.1

Offline inspection and intervention planning for saved Hookr Pair03. This module
uses `hookr-sdk@1.1.1` and `viem@2.55.10`; it does not quote swaps or run EVM.

## Scope

The only supported input is the separately supplied block package for chain
4663, parent 93251802, target 93251803, SHA-256
`b55ba3a6d70bd081148966f3b447135a098a26c18bae0c773f065beda807bda3`.
The package, witness and executables are not included in this source directory.

`inspect(bytes)` authenticates Root/Rules account and requested storage proofs
against the pinned original parent, checks bytecode against official release
pins, reconstructs the pool identity and unpacks all sixteen RulesConfig fields.
The unpacked struct crosses an official SDK encode/decode round-trip. A packed
storage word is never treated as ABI data.

`plan(bytes, {caseId, ruleId, expectedOld, newValue})` accepts decimal-string BPS
values for `hookr-1.standard.RulesConfig.lpBps`. The old value must be `100`.
Supported new values are `0..99`; `100` is a no-op and is rejected. The range is
limited to reductions within this saved pool's caps. The contract's broader
`burnBps + lpBps <= 1000` limit does not mean every such value fits this pool.
SDK static rule and fee-cap checks are applied as well.

Only bits 160–175 change. Every other bit, checkpoint, account, pool and slot is
fixed. `100→0` returns exactly the accepted saved intervention object. `100→50`
creates a different plan; it has no computed economics or branch result.
Removing LP Rewards removes its associated protocol share, while base/dynamic
fees and recapture remain. This is not a live contract setter or a transaction.

Every plan is `PLANNED_NOT_EXECUTED`, with `executionAuthorized: false`,
`branchResult: null` and `witnessClosure: NOT_EVALUATED`. A commitment binds the
plan bytes; it is not an authorization or a cryptographic execution proof.

## Use

Requires Node.js 24+ with built-in TypeScript stripping. From this directory,
install the pinned dependencies with `npm ci --ignore-scripts` when dependency
installation is permitted. Offline review reproduced a clean dependency layout
from retained files, with no symlinks back to the original checkout. Exact
`npm ci --offline` remains blocked by missing cached registry tarballs for
`viem@2.55.10` and `ox@0.14.33`; no replacements were downloaded or repacked.
Set `PAIR03_PACKAGE` to the separately retained package path
and `PAIR03_PLAN` to a new plan file outside the source checkout.

```sh
node cli.ts inspect --package "$PAIR03_PACKAGE"
node cli.ts plan --package "$PAIR03_PACKAGE" --expected-old 100 --new-value 0
node cli.ts plan --package "$PAIR03_PACKAGE" --expected-old 100 --new-value 50 > "$PAIR03_PLAN"
```

Keep generated plans outside this source checkout. To validate a plan at the
Python boundary, from the repository root:

```sh
python3 -B adapters/hookr-case/validate_plan.py \
  --package "$PAIR03_PACKAGE" --plan "$PAIR03_PLAN"
```

That validator reuses the existing SDK package admission, independently derives
the case ID and intervention, and rejects changed slots, unrelated bits, extra
fields, fabricated results and rehashed tampering. It does not launch the SDK or
change its pinned execution plan. A new value still needs a reviewed execution
adapter, original-parent state coverage and separately approved native run.

## Prepare a native request

```sh
python3 -B adapters/hookr-case/native_plan.py \
  --package "$PAIR03_PACKAGE" --plan "$PAIR03_PLAN"
```

This is an admission-only command from the repository root. It independently
validates the plan and emits a request bound to the exact package, checkpoint,
ordered inputs, intervention, runtime-plan bytes and reviewed legacy source pins.
Only `100→0` and the first new `100→50` request are in this review scope.
The complete original node/code inventory must be available. That check does
not establish that additional paths needed by a new branch are present.

The output is `ADMITTED_FOR_REVIEW_NOT_EXECUTABLE`, with `canExecuteNow: false`.
It has no dispatch function or execution flag. The existing prestate validator,
embedded worker plan, v2 policy and full-baseline verifier still admit only the
saved `100→0` workload. A scoped worker/profile and plan-aware completion verifier
are required before `100→50` can run. Their eventual integration must retain the
canonical ACTUAL gate, independent original-parent worlds and nil-Source
HOST_STOP behavior for missing state. No economic result is synthesized here.

## Tests

From this directory, using the same retained input:

```sh
RHOOK_PAIR03_PACKAGE="$PAIR03_PACKAGE" node --test test/adapter.test.ts
RHOOK_PAIR03_PACKAGE="$PAIR03_PACKAGE" RHOOK_NODE="$(command -v node)" \
  python3 -B -m unittest discover -s test -p 'test_*.py' -v
```

Tests block Node socket connections and fetch, check all supported changed values
and exercise the TypeScript-to-Python boundary. They execute no historical EVM,
host-readiness sensors or provider requests. A strict no-emit TypeScript 5.9.3
compiler check passed using the retained local compiler and Node declarations.

This is repository-local TypeScript source, not an installable native SDK kit.
Node's type stripping does not support `.ts` entry points inside `node_modules`;
an emitted JavaScript/declaration distribution is separate future delivery work.

The ABI/release match covers the audited Root/Rules contracts, not every release
component. The historical external router is not the current HookrRouter;
swap-builder compatibility remains unestablished. No arbitrary-block support,
new native result, independent Rust replay or public SDK release is implied.
