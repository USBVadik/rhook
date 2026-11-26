# Ethereum authenticated acquisition and counterfactual replay

This report summarizes an accepted private experiment on Ethereum Mainnet
block **26,486,739**. The scope is the exact retained block and intervention.

## Canonical control

The acquisition tool retrieved the block data and state dependencies through
Ethereum peers. It checked data against the retained block and parent roots.
Account and storage proofs bound reads to trie commitments. Code bytes were
checked against authenticated code hashes. Acquisition recorded a reusable
capsule for the case, with receipts and the original ordered transactions.

A separate offline ACTUAL run executed all **195** transactions from the
recorded parent state. Its receipt comparison, receipts root, state root and
requests hash matched the historical control. The capsule covered the
dependencies of this experiment. Coverage of arbitrary blocks or edits
requires separate qualification.

## tx70 exact-in intervention

The change targets transaction index **70**. The analysis substitutes the
swap input at the execution-message boundary, from **30 to 90 USDT**. The
historical signed transaction remains a reference input. BRANCH runs the
modified message and retains the declared order and the other messages.

| Observation | ACTUAL | BRANCH |
| --- | --- | --- |
| Swap input requested | 30 USDT | 90 USDT |
| USDT input observed at the selected pool | 30 USDT | 90 USDT |
| Swap lifecycle | SUCCESS | SUCCESS |

The pool-consumption row comes from retained execution observations. The
experiment did not claim general economic assurance or prove the correctness
of the BRANCH transition independently. Separately, the
[consensus procedure](ethereum-consensus-anchoring.md) authenticates the
historical target and parent state relative to an external trust anchor.

The report provides the case, method and observed result. The acquisition
tool, runtime, witness, capsule, raw receipts and execution traces remain
private. See [project status](../PROJECT_STATUS.md) for release scope.
