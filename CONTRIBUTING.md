# Contributing

Start with offline tests:

```sh
npm ci
npm run check
npm test
npm run quickstart
python3 -B sdk/tools/test_offline.py
```

Node tests cover the protocol-neutral code. SDK tests use synthetic fixtures,
never the historical witness or native engine. Keep tests independent of
network, personal paths, credentials and developer caches.

Keep changes small. Describe user-visible behavior and validation. Code,
comments and documentation should be in English. Do not commit generated runs,
grants, witnesses, binaries, private archives or credentials. Report sensitive
material privately to the repository owner instead of including it in an issue.

Native logic, resource policy, authority consumption, original-parent handling
and the canonical ACTUAL gate require separate review and execution approval.
A unit test never authorizes replay. Do not alter accepted evidence or update
its hashes to make a test pass.

Changes to evidence semantics should include the malformed or previously
unsupported input, a focused regression, compatibility impact and any required
schema/domain version change. Do not weaken strict verification to accommodate
one producer. Retain third-party origin and license notices.

Contributions to original RHOOK code and documentation, including the Developer
SDK, are submitted under [Apache-2.0](LICENSE) unless explicitly stated otherwise,
as described in its contribution terms. Only contribute material you have the
right to license. Preserve the [third-party exceptions](THIRD_PARTY_NOTICES.md)
and identify the origin and applicable terms of added third-party material.

Proposed topics, to apply only after publication approval: `counterfactual-execution`,
`ethereum`, `evm`, `arbitrum-nitro`, `hookr`, `python`, `developer-tools`, `experimental`.
