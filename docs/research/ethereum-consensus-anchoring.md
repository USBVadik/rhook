# Ethereum portable consensus anchoring

The retained inputs for Ethereum Mainnet block **26,486,739** were
authenticated offline relative to an externally selected weak-subjectivity
checkpoint at epoch **491,686**. The exact package and verifier binaries
used in the accepted run remain private.

## Verification chain

1. **Beacon consensus.** Decode the saved bootstrap and finality update.
   Check committee membership and the Merkle branches with respect to the
   trusted checkpoint. Verify the BLS sync-committee aggregate signature
   and finality to the finalized beacon block.
2. **Beacon to execution.** Recompute the SSZ hash tree root of the retained
   Fulu block message and match it to the verified beacon root. Read the
   execution block hash from that authenticated block body. This closes
   the gap where earlier retained material described a live payload proof
   without containing enough bytes for an offline recheck.
3. **Execution ancestry.** Verify **7,391** linked execution headers.
   Bind the historical target, its parent hash and the parent state root
   used by [the replay capsule](ethereum-p2p-counterfactual.md).

The local Common Developer Consumer reran these checks over the retained
bytes. The verification depends on the selected checkpoint, sync-committee
security assumptions, applicable fork rules and the admitted implementations.
It covers historical ancestry and the input state commitment. ACTUAL and
BRANCH execution records remain observations, and the BRANCH transition
has no independent execution proof in this report.

## Portability

The local Linux acceptance ran hash-pinned verifier binaries as x86-64
userspace via Rosetta on an ARM64 Linux kernel, in a network namespace with
only loopback. Native x86-64 kernel qualification is separate. Two builds
with retained inputs produced identical bytes for all three Linux ELF.
A later clean build from public dependencies matched the SSZ binding
verifier only, with a hash discrepancy for the EL anchor and consensus
verifier. Clean public rebuild parity remains open.

The [consumer report](common-developer-consumer.md) describes the distinction
between retained comparison and fresh verification. This documentation
discloses the method and observed acceptance. Verifier source publication
and evidence transfer have separate release decisions.
