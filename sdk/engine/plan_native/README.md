# Scoped Hookr plan worker

This candidate supports one reviewed plan: `RulesConfig.lpBps 100 -> 50` on
saved block 93251803, including all seven original arrivals. It is not a generic
storage override API. Preparation does not authorize execution.

The semantic plan, native request and serialized runtime plan are checked in
separately. `core.py` pins their reviewed commitments. `legacy-pins.json` records
the preserved 07cabff source baseline and the reviewed adapter files, rather
than treating the current local source as previously approved.

## Build and tests

Use an already authenticated Pair03 build root. The builder has no download or
bootstrap path:

```sh
python3 -B -m plan_native.build --retained-build /local/build-root --output /fresh/build-directory
python3 -B -m unittest discover -s plan_native/test -v
RHOOK_PAIR03_FIXTURE=/local/sealed-pair03 node --import ./adapters/hookr-case/test/no-network.mjs --test plan_native/test/verify.test.mjs
```

The build stages a separate prestate module. Its only semantic source change is
the hash-checked replacement of the LP replacement byte from zero to fifty.
The full-word check, slot/account/code bindings, patch finalization, original
witness preservation, nil Source and pair controller remain intact. The
original prestate module and all previous profiles are unchanged. Go tests use
fake worlds and invalid bytes; the historical admission test is excluded.
The production worker is compiled and hashed but never invoked during build.

## Execution boundary

`launch.py` is a future one-shot entry, requiring an exact newly approved binding
and authority file before any sensors or native dispatch. It does not issue
authority. Approval binds the source closure, binary, policy, runtime plan,
semantic plan, native request, verifier dependencies, paths and operation ID.
An old Pair03 or SDK v2 authorization is rejected. The operation directory and
its parent are fsynced before fresh admission; a STOP consumes the operation.

The new policy preserves every v2 numerical ceiling: 1 GiB sampled worker RSS,
1.5 GiB free admission RAM, 0.5 GiB runtime floor, native CPU/wall 120 seconds,
64 MiB worker output, 128 MiB sampled runtime storage, GOMAXPROCS=2 and advisory
GOMEMLIMIT=512 MiB. RSS is sampled, not a memory reservation or exact peak.
Admission and runtime use the preserved sensor and predicates. A 135 second
stage interrupt reserves five seconds for owned-worker cleanup inside 140
seconds. Completion verification receives the remainder of a 180 second
workflow limit. Failure or uncertain cleanup never produces PASS or permits
retry. These are enforced process deadlines, not a guarantee against OS hangs.

The worker constructs separate original-parent worlds from authenticated actual
package bytes. ACTUAL must match canonical stateRoot, receiptsRoot and blockHash
before BRANCH entry. Missing state is HOST_STOP; there is no hydration, provider
or alternate input. Only ACTUAL<=1, BRANCH<=1, B=RPC=WSS=0 are permitted.

## Completion verification

The verifier authenticates the original package, headers, raw arrivals, proofs,
loaded node/code content and witness commitment. It checks recorded worlds,
intervention, call-tree structure, seven receipts, gas accumulation, blooms,
receipt trie roots, produced header hashes, canonical ACTUAL and original-parent
observations. The launcher additionally checks the completion journal, process
exit/resources, input copies and raw comparison linkage.

Buyer token nets, all ERC20 Transfer events, Swap events, HookFee events and
observed account/storage deltas are reconstructed from the new records. Unknown
events remain raw. Unchanged economics and EVM failure receipts are retained;
no output, improvement, fee or gas value is predicted for fifty. The old zero
branch is a verifier test fixture only, never the new branch's expected output.

This validates recorded-result integrity in a trusted local execution workflow.
It does not independently prove an arbitrary fabricated branch state root or
call/state trace. Those remain Go/Nitro observations: economic assurance
UNRESOLVED, heterogeneous agreement NOT_EVALUATED, qualified Claims=0.
Historical router identity is preserved; current HookrRouter swap-builder
compatibility is not asserted.

The retained npm dependency tree is explicitly hashed for the reviewed local
operation. An exact clean npm installation remains unverified because required
registry tarballs are absent locally. No second-machine, hermetic OS/toolchain,
generic block or external SDK delivery claim follows from this preparation.
`externalDelivery=HOLD`.
