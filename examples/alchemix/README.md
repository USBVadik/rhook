# Alchemix historical case

A frozen historical study replaced one call at Ethereum block `12645422`, transaction `24`:

```text
harvest(0) -> harvest(2)
```

Starting from parent block `12645421`, the apparatus regenerated the ordered transaction domain through block `12645608`.

| Observation | Result |
|---|---:|
| Blocks | 187 |
| Transactions | 36,847 |
| Historical-control divergences | 0 |
| Counterfactual status changes | 96 |
| `SUCCESS -> REVERT` | 93 |
| `PRE_EXECUTION_INVALIDATED` | 3 |
| First material branch flip | block `12645438`, transaction `229` |

The adjudication classified the case as Outcome C and supported sequential branch regeneration for that incident and question. It did not establish Claim P, a universal need for full replay, or an account-level recovery amount.

## Provenance

- final adjudication SHA-256: `96abec2c727d5aa566e214565efec78a52b641484086f0b0af80ea8808001559`
- 36,847-row transaction comparison SHA-256: `f84d62649323ce56831357ee8d4d29c6343ea3fe894f0bc2e1e5313644d6f371`
- outcome vector SHA-256: `b439fda731663126a55e828109f61b170b442b1680383611042593ee4acf51b6`
- causal closure SHA-256: `6adaf08e34170b6c820a5d0331065dd8e385ba4c34fb680c927478dbbd6f5c29`

The large research archive is deliberately not included here. This summary records the pinned result and integrity anchors only.

The evidence stack in this repository was qualified separately on [`../minimal/transcript.json`](../minimal/transcript.json). Alchemix has not been rerun through the packaged stack.
