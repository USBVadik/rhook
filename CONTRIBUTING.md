# Contributing

RHOOK is in technical-review stage. Small, test-backed changes are preferred.

## Before opening a change

```bash
npm ci
npm run check
npm test
npm run quickstart
```

A change to evidence semantics must include:

- the malformed or previously unsupported input;
- a focused regression test;
- compatibility impact;
- any required schema or domain version change.

Do not weaken strict verification to accept a producer-specific payload. Do not change historical claims or provenance hashes to make a test pass.

## Pull requests

Keep pull requests narrow. Describe the execution or verification invariant being changed, not just the files edited. Generated research archives, local traces, credentials, and private endpoints do not belong in this repository.

Contributions to RHOOK-authored code are submitted under [Apache-2.0](LICENSE)
unless explicitly stated otherwise, as described in its contribution terms.
Preserve the [third-party license boundaries](THIRD_PARTY_NOTICES.md), including
the LGPL-derived native adapter. Include the origin and applicable license
when adding third-party material.
