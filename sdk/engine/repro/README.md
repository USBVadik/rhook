# Pair03: macOS arm64 build only

This workflow prepares a newly compiled Go/Nitro worker. It does not replay block 93251803, run EVM tests, measure host admission, issue an authority, or start a network client. A successful build is not a counterfactual execution result.

The first target is macOS on Apple silicon. Linux, Intel Macs, another physical machine, and byte-identical cross-machine builds are not qualified by this stage. The source checkpoint is `4c07186b8823a2ef3e8bfd7bade51fb4f8e87c3e`.

## Prerequisites

- Python 3.12 or newer, with HTTPS certificates installed.
- Node.js 20 or newer and npm on `PATH`.
- Xcode Command Line Tools with a functioning Apple Clang/macOS SDK.
- Internet access to the pinned public source/toolchain archives, npm, the Go module proxy/checksum database, and Cargo dependencies.

Go 1.25.12 and Rust 1.93.0 are installed locally by bootstrap. No system Go, Rust, Cargo cache, developer checkout, existing native library, credentials, provider account or saved scientific runtime is used as a build dependency. The OS, SDK, Python and Node/npm are host prerequisites; this is not a fully hermetic OS image.

## Build

These files are currently on the local portability branch; the checkpoint's remote `main` does not yet include them. After the branch is separately reviewed and made available, a developer with private repository access can clone it. No push is part of this task.

From the checkout containing this `repro/` directory:

```sh
python3 -B -m unittest discover -s repro/tests -v
python3 -B repro/build_pair03.py bootstrap
python3 -B repro/build_pair03.py build
```

For an explicit build location, pass the same `--workdir /absolute/new/build-directory` to both commands. Bootstrap requires an absent directory and does not merge into an existing cache. The default location is `.build/pair03-macos-arm64` inside the checkout and is ignored by Git. Build downloads and Rust/Go compilation can take substantial time; stdout announces stages and full compiler logs are stored under `records/`.

All dependency archives have explicit SHA256 pins. npm uses its exact integrity lock with lifecycle scripts disabled. Cargo uses its pinned version and `--locked`; Go uses the preserved module sums, `-mod=readonly`, a local toolchain, and a fresh module/build cache. Source archives are checked before safe extraction. There is no alternate provider, mutable branch fallback or archive-download retry.

Bootstrap copies the original `native/` modules into the build directory and rewrites only their copied `go.mod` replacement paths. The checked-out engine and saved-pair Go source remain byte-identical to the source checkpoint. Source additions or changes under `native/` are rejected against the explicit source lock. Historical absolute paths remain in the preserved snapshot; they are not used to resolve build dependencies.

Both bootstrap and build reject Cargo configuration in an enclosing directory. npm user/global configuration is isolated inside the build root. Before and after compilation, the staged module files are rechecked against the checkpoint with only the declared `go.mod` overlays permitted. Per-stage stdout and stderr are separate so download diagnostics cannot corrupt structured Go dependency data.

The build regenerates precompile ABI bindings, builds the upstream Stylus/Brotli static library, regenerates its C header, and compiles the Go adapter. The generated ABI Go source and C header must match recorded hashes. `GO_DEPENDENCIES_VERIFIED.json` records the compiled-source closure and rejects any Go dependency outside the new build root. The worker itself is never started, including with `--describe`.

## Result

Under the selected build directory:

```text
artifacts/rhook-saved-pair
records/BUILD_RESULT.json
records/GO_DEPENDENCIES_VERIFIED.json
records/binary-metadata.log
records/<stage>.log
records/<stage>.stderr.log
```

`BUILD_RESULT.json` is written only after compilation and dependency-path verification succeed. It records the new binary/library hashes and explicitly reports ACTUAL=BRANCH=EVM=0. The new binary hash is not substituted into any original scientific commitment.

## Saved input and the later replay stage

The scientific block package is deliberately absent from Git. If separately supplied, it can be checked without executing it:

```sh
python3 -B repro/build_pair03.py verify-input --input /path/to/BLOCK_PACKAGE.json
```

The required file is 1,417,029 bytes with SHA256 `b55ba3a6d70bd081148966f3b447135a098a26c18bae0c773f065beda807bda3`. No RPC or witness acquisition is offered. The verifier does not copy or upload the file.

The original build-only worker intentionally retains its historical embedded package location. The next local branch adds a separate [portable entrypoint and launcher](PORTABLE_PAIR03.md), compiled against the same engine and dependencies. That adapter accepts explicit package/output paths and requires a fresh one-run proposal/authority. Old authorities are consumed and cannot be reused. A matching input hash or a successful build grants no execution permission.

Public/SDK delivery remains `HOLD`; no new scientific Claim or heterogeneous agreement is asserted.

## Recorded local build validation (20 October 2026)

- A new build directory downloaded all pinned source/toolchain archives and used fresh Go, Cargo and npm caches. No prebuilt historical worker or `libstylus.a` was copied into the build.
- The 65 original files under `native/` and the 536 used Nitro/geth source files match their historical pins. All 3,059 Go dependency source files resolve inside the new build root.
- The regenerated C header and precompile Go bindings match their expected historical SHA256 values.
- All 19 synthetic Python tests pass. The corrected safe extractor also accepts all nine real pinned source/toolchain archives. Independent read-only review found no remaining actionable issues.
- Compilation produced a 129,825,202-byte worker with SHA256 `50481c94489d46daa0cda1a644daa7705d8ad34d23d5efd4cc0951c579b1ed75`.
- The first development build stopped before the final Go compilation because download diagnostics were mixed with JSON. Its logs were retained; the corrected wrapper completed the build. No Pair03/ACTUAL/BRANCH invocation occurred in either pipeline.

These observations describe a build on the original Mac with a fresh dependency environment. A second physical machine and the saved-pair runtime workflow remain untested.
