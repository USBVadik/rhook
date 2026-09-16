# Security

## Reporting a vulnerability

Use GitHub's private vulnerability reporting if it is enabled. Otherwise contact the repository owner privately before opening a public issue. Do not publish exploitable verifier bypasses, secret exposure, or integrity failures before the maintainer has had a chance to respond.

A useful report includes:

- the affected API and input;
- whether all public commitments were recomputed;
- the verifier result and expected result;
- a minimal reproduction;
- impact on internal validity, authenticity, or execution semantics.

## Current security boundary

The strict verifier is designed to reject malformed self-consistent evidence from an untrusted producer. It does not authenticate the producer, sandbox an execution engine, or impose process-level resource limits on hostile input size.

Only the current `main` branch is supported. No production deployment or audit certification is claimed.
