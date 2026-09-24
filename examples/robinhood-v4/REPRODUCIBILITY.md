# Clean-checkout reproduction — PASS

Qualified on 2026-09-24 from a fresh clone at
`b1cbd503f64ecea410d5d9cc6b99085da1c2d486`. A separate Docker BuildKit builder started with
**0 B cache**. Only `npm ci` and `npm run demo:robinhood` were needed to build
and reproduce the result. There were no predecessor-workspace mounts, copied
Go/Rust caches, local binaries or untracked source inputs.

The qualified checkout's non-Markdown file-set SHA-256 is
`cc240404332a795fbca2706b987feee7e28fe85a3739f843cd7482282566ae39`.
Subsequent publication edits add licensing/notices and documentation, update
only the project's own license metadata in npm manifests/locks, and copy root
notices into the replay image. Native source, case inputs, dependency versions
and integrity pins, build commands and replay/verifier scripts are unchanged.
The measurements and image size below describe the qualified checkout;
license files change the packaged image, not the frozen execution result.

## Environment and measurements

Linux arm64, kernel 6.12.76-linuxkit, Docker 29.5.3, BuildKit 0.32.2.
Docker VM: 15 available CPUs, 8,320,815,104 bytes RAM. Go and Rust build workers
were limited to four. Node 22.22.0, Go 1.25.12, Rust 1.93.0, cbindgen 0.29.2,
solc 0.8.30. Container images and source archives are hash-pinned; Debian build
packages come from snapshot 20260225T000000Z.

| Measurement | Observed |
|---|---:|
| Cold build, including downloads and image export | 696.74 s |
| Offline replay and verification | 7.51 s |
| Container start, replay and teardown | 8.59 s |
| Peak sampled dedicated BuildKit directory | 18.68 GiB |
| Runtime image, Docker-reported size | 160,491,548 bytes |
| Expanded minimum frozen case inputs | 16,500,708 bytes |
| Compressed case inputs | 6,385,784 bytes |
| Compressed comparison/evidence reference | 140,974 bytes |
| Public native dependency source archives | 169,489,826 bytes |
| Generated outputs, including detailed observations | 106,811,485 bytes |

Disk was sampled approximately every five seconds with `du -sk` over the
isolated builder's directory. It includes intermediate layers/cache and is an
observed sampled peak, not an exact whole-host peak. Runtime image storage and
final outputs are reported separately. Allow about 25 GiB free disk and 8 GB
Docker RAM for a cold build. Timings depend on network and host performance;
other platforms/emulation performance are not qualified.

## Result and integrity

Both roots, both exact fee-growth values, lifecycle totals, full per-block native
outputs and all **642 serialized evidence records** matched the frozen result.
All 13 real insufficient-funds invalidations were retained. ACTUAL was checked
before counterfactual execution. Native control, evidence OFF and ON agreed.

Execution ran read-only with `--network none`, dropped capabilities and only a
fresh output directory mounted at `/out`. Expected outputs are used by the
comparison process, never imported as execution state.

- Existing and new JS tests: **78/78 PASS**.
- Original synthetic quickstart: **PASS**.
- Native classifier tests: **11 cases PASS**.
- Generated-file hashes independently checked: **688/688**.
- Output `SHA256SUMS` digest:
  `21b55f0663bc1851296dbec928765980cd2817af9015289e56dd23427615f275`.
- Built runner SHA-256:
  `cbe7bbd5129d069b2e686890e2e56d9c77a2d5a6f85132f602a2ae630bad17ed`.

Runtime metrics and build/package details are saved in each generated output.
Performance metadata is expected to differ on rerun. Cross-machine bit-identical
binaries are not claimed; exact case execution/evidence is the acceptance test.

Default CI runs fast integrity/evidence checks through `npm test`. The full
cold source build remains an explicit reviewer command. No remote CI run or
Linux amd64 qualification is claimed. RHOOK-authored code is now licensed
under [Apache-2.0](../../LICENSE), with the
[upstream license boundaries](../../THIRD_PARTY_NOTICES.md) preserved.
