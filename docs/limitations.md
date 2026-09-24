# Limitations

## Qualification

- The evidence stack is engineering-conformance qualified on one protocol-neutral synthetic fixture.
- The historical Alchemix result was produced by a separate frozen apparatus. It has not been rerun through this packaged stack.
- The repository has not received a production security audit or broad EVM differential test campaign.

## Execution

- One intervention target only.
- The counterfactual branch follows a declared historical-envelope policy; it is not a claimed consensus-valid block or chain.
- The public host accepts an injected `runBlock` implementation. The private research runner is not vendored here.
- A runBlock adapter owns transaction-validation classification. Host requires an explicit structured classification and unchanged predecessor state before emitting invalidation evidence, but cannot prove that an adapter's classification policy is complete.
- No multi-chain or throughput qualification is claimed.

## Evidence

- Self-commitments prove internal consistency, not producer identity.
- Full EVM state is not embedded in transcripts.
- Unchanged envelopes may use compact commitments instead of full records.
- Resource limits for hostile input size remain the caller's responsibility.

## Scientific and product claims

- The Alchemix result supports sequential branch regeneration only for the frozen incident-level question.
- It does not establish general superiority over bespoke simulators.
- No product demand, token mechanism, attribution rule, liability decision, or recovery amount is established.

## License

RHOOK-authored code is licensed under [Apache-2.0](../LICENSE). The
[third-party boundaries](../THIRD_PARTY_NOTICES.md) remain applicable: the
derived geth adapter retains LGPL-3.0-or-later, and the pinned Nitro/native
dependencies include Business Source License 1.1 terms. The RHOOK license
does not grant unrestricted production use of those dependencies.

## Additional bounded real-chain example

The separate [Robinhood v4 example](../examples/robinhood-v4/README.md) now
qualifies the unchanged evidence/runtime stack with native Nitro on one frozen
50-block case, including continuing past 13 pre-execution invalidations. Its
[clean-checkout reproduction](../examples/robinhood-v4/REPRODUCIBILITY.md) is
qualified on Linux arm64. The earlier synthetic and Alchemix qualification
statements above retain their respective historical scope. This additional
case does not establish general Nitro compatibility, a consensus-valid fork,
LP payouts or attribution.
