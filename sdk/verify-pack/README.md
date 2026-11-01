# verify-pack 0.1: check a recorded RHOOK result offline

`verify-pack` checks one recorded Hookr counterfactual result (an ACTUAL and a BRANCH world) on your own
machine. It needs no RHOOK worker, no EVM, no RPC account and no historical witness. It reports exactly
which properties it checked and which remain claims of the RHOOK engine.

It does **not** re-execute anything. A pack that passes tells you:

- the files are the ones RHOOK published (if you supply the published hashes);
- the recorded ACTUAL is the real chain block you trust (if you supply its block hash);
- the recorded BRANCH is internally consistent with the declared intervention.

It does not tell you that BRANCH is the correct EVM result. Only re-running the block with a compatible
worker, or with an independent engine, tests that.

## Quick start with the synthetic example

Requires Node.js 22 or newer (CI runs these tests on Node 24) and npm. From the repository root:

```sh
npm ci --ignore-scripts --no-audit --no-fund --prefix sdk/engine/adapters/hookr-case
node sdk/verify-pack/cli.mjs verify \
  --bundle sdk/verify-pack/examples/synthetic-lp50 \
  --pins sdk/verify-pack/examples/synthetic-lp50.pins.json \
  --trusted-block-hash 0xc4b9e0d3a8e172ae9bf83d74b2231cdc0d6acfcd75bb64f9ceec6ed4072580e5
```

The `npm ci` step installs the adapter's pinned public dependencies (`viem`, `hookr-sdk`). The example is
**synthetic test data**: a made-up block on which LP Rewards changes from 100 to 50. Its "trusted" block
hash is the fixture's own. Output:

```text
RHOOK verify-pack 0.1: recorded evidence check, no EVM re-execution
Case: chain 4663, block 1000001 (0xc4b9e0d3…2580e5), 2 arrivals, RulesConfig.lpBps 100 -> 50
Checks:
  A  Artifact integrity     MATCH_EXTERNAL_PINS
  -  Chain context          BOUND_TO_TRUSTED_BLOCK
  B  Canonical ACTUAL       RECORDED_ACTUAL_MATCHES_TRUSTED_CANONICAL_BLOCK
  C  Recorded BRANCH        RECORDED_BRANCH_INTERNALLY_CONSISTENT
...
  Delta         5000000000000000000000  (+0.5000000000%)
Outcome: CHECKS_PASSED_WITHIN_STATED_SCOPE
```

Add `--json` for the full report, or `--report FILE` to also write it. Run the tests with
`node --test sdk/tests_cases/verify-pack.test.mjs`; CI runs them with the other SDK case tests.

## Checking the real Hookr Pair03 result

The first real pack is Hookr Pair03 on Robinhood Chain: block 93251803, all seven original arrivals,
`RulesConfig.lpBps` 100 → 50. See the [case study](../../docs/research/hookr-pair03-100-to-50.md). The
pack is not in this repository; it is shared separately once its distribution is approved.

1. Check the published hashes. `pins/hookr-pair03-lp50.json` copies the three SHA-256 values printed in
   the case study. Compare them with the case study yourself; do not rely on a hash shipped inside the pack.
2. Get the block hash of block 93251803 from a source you trust, for example
   [the block explorer](https://robin.etherscan.io/block/93251803) or your own node.
3. Run:

```sh
node sdk/verify-pack/cli.mjs verify --bundle /path/to/pair03-lp50-pack \
  --pins sdk/verify-pack/pins/hookr-pair03-lp50.json \
  --trusted-block-hash 0x<hash of block 93251803 from step 2>
```

Expected result on the published pack:

| | Buyer RHOOK Transfer-event net, base units | Basis |
|---|---:|---|
| ACTUAL | 291469365928126821002944 | Canonical receipts of the trusted block |
| BRANCH | 292938400920971228766928 | RHOOK engine record, not re-executed |
| Delta | +1469034992844407763984 (+0.5040100829%) | |

Outer Swap fee changes from 11048 to 7048 pips; subject gas is unchanged. The report's economics use only
receipt data (Transfer and Swap events, status, gas), which is what the receipts root commits to.

## What a pack contains

A pack is a directory with exactly these four files. About 400 KB for Pair03.

| File | Content | How it is trusted |
|---|---|---|
| `RUNTIME_PLAN.json` | Case: checkpoint, arrivals, subject, intervention, expected roots | Published SHA-256 (pins) |
| `ACTUAL.json` | Recorded original world: receipts, produced header, observations | Published SHA-256, then the trusted block |
| `BRANCH.json` | Recorded changed world | Published SHA-256 only |
| `CHAIN_CONTEXT.json` | Public parent and target headers, and the block's raw transactions | Must hash to the trusted block |

The pack holds no state trie nodes, storage or account proofs, or contract code. `CHAIN_CONTEXT.json` needs
no pin: its headers must hash to the plan's checkpoint and block, its transactions must match the
transactions root, and the target hash must equal the one you trust.

The context is public block data, so it can also be rebuilt from a node. Each header holds exactly the
fields its hash commits to: `parentHash`, `sha3Uncles`, `miner`, `stateRoot`, `transactionsRoot`,
`receiptsRoot`, `logsBloom`, `difficulty`, `number`, `gasLimit`, `gasUsed`, `timestamp`, `extraData`,
`mixHash`, `nonce`, `baseFeePerGas`, plus `hash`. The target block also lists its transactions:
`{hash}` for the Nitro internal transaction at index 0, `{from, hash, input, to, value}` for the others.
`rawTransactions` holds every transaction's raw bytes in block order. Extra RPC fields such as
`l1BlockNumber` are rejected rather than ignored. Rebuilding the Pair03 context from a live node has not
been tested yet.

A pack producer who holds the authenticated witness package creates the context with:

```sh
node sdk/verify-pack/cli.mjs make-context --package BLOCK_PACKAGE.json --plan RUNTIME_PLAN.json --output CHAIN_CONTEXT.json
```

This authenticates the whole package first, then copies out only the header fields and transactions.

## What each level checks

| Level | Checks | Establishes | Does not establish |
|---|---|---|---|
| A. Artifact integrity | SHA-256 of plan, ACTUAL and BRANCH against `--pins` | The files are byte-identical to the published result | Anything about their content. Without `--pins`: `NOT_ANCHORED_NO_EXTERNAL_PINS` |
| Chain context | Header hashes, parent link, transactions root, arrival hashes, signatures and calldata of the signed transactions | The public block data matches the plan | That the block is canonical, unless `--trusted-block-hash` is given (`ANCHORED`) |
| B. Canonical ACTUAL | Recomputes the receipts trie from the recorded receipts, checks blooms, gas sums, header fields and roots against the block | The recorded ACTUAL receipts, stateRoot and blockHash equal the trusted block | That RHOOK computed them: they are public chain data and could have been copied. Recorded observations (RulesConfig value before the first arrival, call traces, balances) are engine records that no receipt commits to |
| C. Recorded BRANCH | Same structural checks, the declared intervention and patch, the shared starting observation | BRANCH is internally consistent | That BRANCH is the correct execution result |

Every report also carries these fixed limitations:

| Field | Value | Meaning |
|---|---|---|
| `prestateAuthentication` | `NOT_PERFORMED` | No Merkle proof of the starting state is checked; that needs the witness |
| `nativeReexecution` | `NOT_PERFORMED` | Nothing is executed |
| `heterogeneousAgreement` | `NOT_EVALUATED` | No second engine is involved |
| `economicAssurance` | `UNRESOLVED` | Buyer output is the Transfer-event net in one receipt, not a token balance |
| `qualifiedClaims` | `0` | No protocol Claim is issued |

The tests include a forged BRANCH with doubled buyer output and recomputed receipts root and header
hash. Without pins it passes level C, as stated above. With the published pins it fails level A. This is
why level C is reported as `RHOOK_ENGINE_CLAIM_NOT_REEXECUTED`.

## Report and exit codes

The JSON report (`rhook/verify-pack-report/0.1`) has sorted keys and no timestamps, so the same inputs
give the same bytes. `outcome` is `CHECKS_PASSED_WITHIN_STATED_SCOPE` or `CHECK_FAILED`; `failure` names
the level and code of the first failed check, and later levels are `NOT_EVALUATED_AFTER_FAILURE`.
Other files in the pack directory are listed under `ignoredFiles` and never used, so a hash list shipped
inside a pack cannot stand in for `--pins`.

Exit code 0: every performed check passed. 1: a check failed. 2: usage or file error.

## Supported profile

Only `rhook/hookr-runtime-plan/0.2` on Robinhood Chain (4663), with an LP Rewards intervention on
`RulesConfig.lpBps` (bits 160–175), offline `NIL_NO_HYDRATION` replay. Other plans are rejected with
`INCOMPATIBLE_PROFILE` or `UNSUPPORTED_INTERVENTION`.

## Library use

```js
import {verifyPackDirectory, renderText} from './sdk/verify-pack/verify-pack.mjs';
const report = await verifyPackDirectory('pack', {pinsFile: 'pins.json', trustedBlockHash: '0x…'});
```

`verifyPack({files, pins, trustedBlockHash})` takes file bytes in memory. The record checks reuse the
existing recorded-world verifier in `rhook_alpha/cases/adapters/hookr.mjs`; this module only replaces its
witness package with the anchored chain context.
