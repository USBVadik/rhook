# Developer SDK Alpha v2: saved Hookr case status

**The complete local CLI workflow passed for the saved Pair03 case on one macOS arm64 Mac. Sources and native binaries remain private.** This page documents that result; it is not an installation guide or public SDK release.

```text
doctor → prepare → replay → verify
```

The successful Acceptance03 checked the host, prepared immutable inputs, ran one ACTUAL and one conditional BRANCH, then verified the complete results against original Pair03. The case is block **93251803**, all **seven arrivals**, `RulesConfig.lpBps: 100 → 0`. ACTUAL passed the canonical stateRoot / receiptsRoot / blockHash gate before BRANCH. The workflow used the saved package with no provider RPC or WSS.

[Read the case study](hookr-pair03.md) · [Open the recorded visual](hookr-pair03/index.html)

## What was tested

- One saved input package and one declared LP Rewards intervention.
- A portable build and the full SDK CLI workflow on the developer's Mac.
- Fresh internal host admission, bounded execution and fail-closed cleanup.
- Exact comparison of saved ACTUAL and BRANCH results with the original pair.

Validation was on one macOS arm64 Mac. Other machines and operating systems have not been tested for this workflow.

## Current limits

Pair03 is the tested Hookr example. Arbitrary historical blocks, custom interventions and arbitrary contract support are not established by this acceptance. Independent Rust replay for this case is pending; economic assurance remains `UNRESOLVED` and heterogeneous agreement `NOT_EVALUATED`.

The public repository does not include this Alpha's private sources, native worker, saved witness or historical package. Its existing public quickstart and other native examples have their own scope; they do not install or reproduce SDK Alpha v2 Pair03. An ordinary sequence of shell commands alone does not reproduce the separately enforced workflow/supervisor limits.

There is no public SDK download, supported Replay button or arbitrary-rule editor in this update. A future external developer kit needs a separately reviewed package, installation path and supported execution profile.

## Next milestone: official Hookr SDK integration

The saved pool is `hookr-1` with the standard Rules core. Root and Rules runtime
hashes match the official release pins for `hookr-sdk@1.1.1`, confirming their ABI
compatibility. The next development milestone is a TypeScript adapter to the
existing Python/Go workflow. That adapter is not implemented yet.

The historical transaction used an external router rather than the current
HookrRouter. ABI compatibility does not establish compatibility with the SDK's
swap builders for that route.
