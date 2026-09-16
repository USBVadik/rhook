# Runtime

Runtime converts execution-engine output into core evidence. Raw state roots, identities, receipts, exceptions, gas, fees, logs, and semantic observations are normalized once at this boundary.

Public entry point: [`src/index.mjs`](src/index.mjs)

```bash
npm run test:runtime
```

Runtime does not schedule execution and does not decide whether evidence is valid. The core verifier owns that decision.
