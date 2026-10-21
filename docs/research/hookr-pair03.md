# Hookr Pair03: a real pool, two recorded worlds

On Robinhood Chain **4663**, RHOOK replayed saved block **93251803** from its original parent, processing all **seven arrivals in order**. ACTUAL matched the canonical state root, receipts root and block hash. A second Go/Nitro world changed only `RulesConfig.lpBps` from **100 to 0** in the initial checkpoint. The selected buyer received **1.0088% more RHOOK** in that recorded alternative.

[Open the read-only visual](hookr-pair03/index.html) · [Inspect the summary](hookr-pair03/summary.json) · [SDK Alpha status](sdk-alpha-v2-status.md)

Follow-up experiment: [native replay with LP Rewards 100 → 50](hookr-pair03-100-to-50.md). It records a separate branch with +0.5040100829% buyer Transfer-event net; the visual and summary linked above remain the original 100 → 0 result.

The HTML is a local static page with no scripts or remote assets. Download the repository and open `docs/research/hookr-pair03/index.html` with its adjacent CSS. GitHub's file viewer displays its source. This change does not deploy a website.

The authenticated saved header records block time **2026-10-20 06:42:33 UTC**.

## Contract generation

The saved pool is `hookr-1`, using the standard HookrRules core. The historical
Root and Rules runtime hashes match the official release pins in
[`hookr-sdk@1.1.1`](https://hookr.fun/docs/pools/sdk):

| Contract | Historical runtime keccak256 |
|---|---|
| Root `0x89c9fb50d1f03192230ffb1c279bb6e7d3fe6acc` | `0xd336de325837e60a74cea11d87b5ebd1cc8961911f611f38de0508d23b6e779f` |
| Standard Rules `0x4a71c270b1520f94064268102aebd744b0de7942` | `0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b` |

This confirms the applicable Root/Rules ABI generation. The historical external
router `0x204faca1764b154221e35c0d20abb3c525710498` is not the current HookrRouter;
swap-builder compatibility for that route is not established.

## The question and intervention

What would this same historical block have produced with the pool's LP Rewards parameter at zero?

- PoolId: `0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780`.
- RHOOK token: `0x3c022d43a9f826cd206c2ba60bc753d8b36185c4`.
- Selected purchase, zero-based native arrival ordinal **3**: `0xbdc353fe6485a1e4e14e6d6fa358d9e7cdd333a986ce0440e7a76fcdb09aa41c`.
- Native input: **0.01 ETH**.
- Parent: **93251802**, with the same original inputs and arrival order in both worlds.
- Intervention: one initial storage-field overlay, `RulesConfig.lpBps: 100 → 0` (bits 160–175). No administrative transaction was inserted.

`lpBps` is the LP Rewards parameter. The branch removes the LP Rewards add-on and its associated protocol share. It does not disable an entire Hook Block or remove the hook. The base LP fee, dynamic fee and recapture lane remain present. This is an analytical prestate change; it does not show that an existing onchain pool's frozen configuration can be edited through its normal interface.

## Observed result

| Selected buyer / transaction | ACTUAL | BRANCH |
|---|---:|---:|
| RHOOK output, exact base units | 291469365928126821002944 | 294409762269997223561475 |
| Outer Swap fee, pips | 11048 | 3048 |
| Selected transaction gas | 1483206 | 1480996 |
| Receipt status | 1 | 1 |

The receipt-derived output increased by **2940396341870402558531 base units**, or **1.00881831355%**. Transaction gas fell by **2210 units**. Outer Swap fee fell from **1.1048% to 0.3048%**; it did not become zero. `HookFee.earned` changed from **20110000000000 to 110000000000 wei**, while its refund and burn fields remained zero. The three internal arbitrage Swap events were unchanged.

Output is the net of RHOOK Transfer events for the selected buyer, not a separate token-balance storage snapshot. Token decimals were not independently established in this evidence; values remain in base units. The result describes this one saved execution domain, not future price, profit, liquidity or a general fee reduction guarantee.

## Canonical ACTUAL gate

These pinned historical commitments matched the recorded ACTUAL output before BRANCH execution:

| Commitment | Expected = recorded ACTUAL |
|---|---|
| stateRoot | `0xd4ea0fe6f558cbc4a6b4161e3afc41ee4b7709001c170e32bc2144e64bdeb10b` |
| receiptsRoot | `0x920c08cb6953014f0800587bbe2c0f8db5a7855ddb9f6263d5b4e230edeba98f` |
| blockHash | `0xc73ef372869ad5bf2a664bc1bc4cbe411c3adeb1938f349dd7686d82425398cd` |

Parent block hash: `0x991db6ee40bd7056cfabff012763a1b75995979e5023dc010553dbc304c16016`. Parent state root: `0x9c63ad5d9c6ba4fd19c301ea35264cec28dd1ad0e951a5f5578af8a32131baa6`. The changed BRANCH has its own commitments, listed in the summary; it is not expected to match the original canonical block.

## Reproduction and qualification boundary

The original pair is an exploratory, posthoc saved-block result from one Go/Nitro engine. SDK Alpha v2 Acceptance03 subsequently completed `doctor → prepare → replay → verify`, comparing the complete saved ACTUAL/BRANCH results to Pair03. Those repeats are engineering reproduction on one Mac; they do not add an independent execution engine.

**Independent Rust/arb-revm replay has not run for Pair03.** Heterogeneous agreement remains `NOT_EVALUATED`, economic assurance `UNRESOLVED`, and new qualified Claims **0**. The recorded status is `GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED`. Earlier heterogeneous results elsewhere in this repository concern different cases and do not qualify this one. Full state-diff coverage, arbitrary-pool/intervention support and production readiness are not established.

This public-facing projection carries selected figures and hashes of the internal sealed sources. It contains no raw execution records, witness, authority files, runtime archives or SDK binaries. Opening it performs no replay; it is not a standalone cryptographic or execution-verification package. The [summary](hookr-pair03/summary.json) records the source MANIFEST/FREEZE hashes without distributing those private archives.
