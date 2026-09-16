# Minimal branch example

The transcript contains three executed envelopes with separate divergence points:

```text
Envelope 0  state commitment diverges
Envelope 1  SUCCESS -> REVERT
Envelope 2  semantic value diverges
```

The semantic value is read from the exact envelope-2 successor state. Full evidence is retained for all three changed envelopes.

Run from the repository root:

```bash
npm run demo:generate
npm run demo:inspect
npm run demo:verify
npm run demo:tamper
```

[`generate.mjs`](generate.mjs) executes both branches through the public injected-runner host boundary and reproduces [`transcript.json`](transcript.json) byte-for-byte. The generator is a deterministic protocol-neutral lifecycle fixture, not a bundled historical EVM runner.

`transcript.json` is the only generated execution artifact copied into this repository. It is a protocol-neutral engineering fixture, not a historical incident.
