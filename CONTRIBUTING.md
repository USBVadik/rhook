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

Licensing for the SDK import is pending. Discuss contributions before submitting
material that would complicate that decision; no CLA or new license grant is
implied. Existing public code retains its current license and exceptions.
Contributions to that existing RHOOK-authored code remain under Apache-2.0
unless explicitly stated otherwise, as described in its contribution terms.

Proposed topics, to apply only after publication approval: `counterfactual-execution`,
`ethereum`, `evm`, `arbitrum-nitro`, `hookr`, `python`, `developer-tools`, `experimental`.
