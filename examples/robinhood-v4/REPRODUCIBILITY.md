# Reproduction environment

Qualification is in progress. No clean-environment PASS is claimed in this draft.

The documented command builds from public immutable source archives and pinned
container images. The execution container has no network, no source-workspace
mount, and only a fresh output directory mounted at `/out`.

Input data: 16,500,708 bytes expanded; 6,385,784 bytes compressed.
Frozen comparison/evidence archive: 140,974 bytes compressed.
Nitro/geth/Brotli/Wasmer/precompile source archives: 169,489,826 bytes total.
Generated outputs and measured build/replay/disk use will be recorded after the
clean-checkout gate. Default CI performs fast artifact checks only.
