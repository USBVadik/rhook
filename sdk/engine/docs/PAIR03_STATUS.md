# Recorded Pair03 status

This is documentation of an existing sealed result, not a new execution or independently qualified scientific Claim.

- Chain4663; block93251803; parent93251802; all7 original arrivals in each world.
- ACTUAL=1, BRANCH=1, B/Rust=0; new provider acquisition during this offline pair: RPC=WSS=0. Inputs had been acquired earlier in a separate operation.
- Intervention: RulesConfig.lpBps100→0, bits160–175 only, one semantic initial write; original witness unchanged.
- ACTUAL stateRoot: `0xd4ea0fe6f558cbc4a6b4161e3afc41ee4b7709001c170e32bc2144e64bdeb10b`.
- ACTUAL receiptsRoot: `0x920c08cb6953014f0800587bbe2c0f8db5a7855ddb9f6263d5b4e230edeba98f`.
- ACTUAL blockHash: `0xc73ef372869ad5bf2a664bc1bc4cbe411c3adeb1938f349dd7686d82425398cd`.
- All three ACTUAL values matched the pre-pinned canonical block before BRANCH entry.

| Measure | ACTUAL | BRANCH |
| --- | ---: | ---: |
| Buyer RHOOK output, exact base units | 291469365928126821002944 | 294409762269997223561475 |
| Selected transaction gas | 1483206 | 1480996 |
| Outer Swap fee, pips | 11048 | 3048 |
| HookFee.earned, wei | 20110000000000 | 110000000000 |
| Selected receipt status | 1 | 1 |

Output difference:2940396341870402558531 base units (+1.00881831355%). Gas difference:−2210. Native msg.value remained0.01ETH. The three internal arbitrage Swap events and observed native-value CALL edges remained unchanged. Other six arrivals preserved their statuses, individual gasUsed and log contents. Refund and burn remained0.

Token output is a regenerated ERC20 Transfer-event net to the buyer, not a separate token-storage snapshot. Token decimals were not independently verified, and no full state diff is claimed. One Go/Nitro engine observed the result; no independent Rust/arb-revm replay was performed. Economic assurance=UNRESOLVED; heterogeneous agreement=NOT_EVALUATED; qualifiedClaims=0.

The source scientific archive stays sealed and outside Git. Its hashes, the original binary hash and the per-source-file hashes are references in SOURCE_PROVENANCE.json; no new binary commitment is asserted for these copied sources.
