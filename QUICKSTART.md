# Quickstart

Requirements: Node.js 22 or newer. No RPC endpoint, credentials, database, or network access is needed after cloning.

```bash
git clone https://github.com/USBVadik/rhook.git
cd rhook
npm ci
npm test
npm run quickstart
```

`quickstart` runs four separate commands:

1. `demo:generate` executes ACTUAL and COUNTERFACTUAL through the injected runner port and writes `.rhook/minimal-transcript.json`;
2. `demo:inspect` shows the three divergence points in that newly generated transcript;
3. `demo:verify` starts a fresh process and verifies the serialized transcript without runtime or replay state;
4. `demo:tamper` changes a nested endpoint, recomputes the public commitment, and requires strict rejection.

The deterministic generator reproduces [`examples/minimal/transcript.json`](examples/minimal/transcript.json) byte-for-byte. It is a protocol-neutral execution-port fixture for the public evidence pipeline, not a historical EVM replay distribution.

## Generate and inspect

```bash
npm run demo:generate
npm run demo:inspect
```

The three envelopes have deliberately separate divergence points:

```text
Envelope 0  successor state diverges
Envelope 1  SUCCESS -> REVERT
Envelope 2  semantic value diverges
```

## Verify offline

```bash
npm run demo:verify
```

The command parses the generated file with the strict JSON parser, validates every nested record, recomputes commitments, checks semantic state bindings, and re-derives the divergence locations. It does not execute the fixture.

To verify another transcript, pass its path explicitly:

```bash
npm run verify-transcript -- path/to/transcript.json
```

## Try a hostile transcript

```bash
npm run demo:tamper
```

The script replaces a semantic endpoint with `not-an-address`, then recomputes the transcript commitment. Rejection must come from `INVALID_SEMANTIC_ENDPOINT`, not from a stale hash.

Only the ignored `.rhook/` directory is written. The pinned example and repository sources remain unchanged.
