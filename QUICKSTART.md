# Quickstart

Requirements: Node.js 22 or newer. The verifier needs no RPC endpoint, credentials, database, or network access.

```bash
git clone https://github.com/USBVadik/rhook.git
cd rhook
npm install
npm test
npm run quickstart
```

The repository has no runtime npm dependencies. `npm install` validates package metadata and creates the standard local install state.

## Inspect the branch

```bash
npm run inspect
```

The three-envelope fixture has deliberately separate divergence points:

```text
Envelope 0  successor state diverges
Envelope 1  SUCCESS -> REVERT
Envelope 2  semantic value diverges
```

## Verify offline

```bash
npm run verify-transcript
```

The command parses [`examples/minimal/transcript.json`](examples/minimal/transcript.json) with the strict JSON parser, validates every nested record, recomputes commitments, checks semantic state bindings, and re-derives the divergence locations. It does not execute the fixture.

## Try a hostile transcript

```bash
npm run tamper-test
```

The script replaces a semantic endpoint with `not-an-address`, then recomputes the transcript commitment. Rejection must come from `INVALID_SEMANTIC_ENDPOINT`, not from a stale hash.

Nothing is written to the repository by these commands.
