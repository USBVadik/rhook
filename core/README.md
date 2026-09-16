# Core

The core package defines typed execution evidence and the strict offline trust boundary.

Public entry point: [`src/index.mjs`](src/index.mjs)

It provides:

- canonical address, hash, quantity, bytes, presence, and result types;
- per-envelope lifecycle evidence;
- state-bound semantic extraction;
- compact branch transcripts;
- duplicate-key-safe JSON parsing;
- recursive plain-object and text verification.

Run its focused tests from the repository root:

```bash
npm run test:core
```

The core does not execute transactions or define protocol, recovery, or attribution policy.
