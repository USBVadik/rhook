# Developer Alpha source

This executable SDK source candidate comes from checkpoint
`41ef7672094caf91009a51b197ac4c5e64c35c8d`, imported without private Git history.
It includes the CLI, Python API, consent boundary, installer, native worker
source, case-specific Hookr adapter and offline tests.

Binary distribution is pending. From the repository root, using Python 3.12+:

```sh
python3 -B sdk/tools/test_offline.py
```

This starts no worker, sensor or network client. See [QUICKSTART.md](QUICKSTART.md)
for the real CLI/API workflow with approved runtime inputs.

Source entry points: [CLI](rhook_alpha/cli.py), [Python API](rhook_alpha/api.py),
[installer](install_alpha.py), and [Hookr example](examples/execute_hookr.py).
The example defaults to planning. A public clone provides source and offline
tests; it is not a self-contained native kit.

`rhook_alpha/` is the installed API. `developer/` authenticates and installs the
pinned runtime. `engine/case_sdk/` implements plans and the canonical ACTUAL gate.
The remaining engine modules are retained dependencies and historical reference
tools, not extra supported entry points. The full 198-file engine snapshot is
retained because its manifests and native bindings cover that closure.

Seven historical engine files have path-only substitutions. Public source is
**not byte-identical** to the accepted native build. Installation requires an
explicit original engine tree, checked against `developer/accepted-source.json`,
alongside the pinned assets. It never registers the sanitized tree as the
accepted binary's source. `source-provenance.json` records accepted/public hashes,
including the installer adaptation and portable test correction. No original
personal path values or recovery data are published.

The accepted binary is unchanged. No native acceptance of this adapted public
installer is claimed; offline installation/planning checks are reported separately.
Read [compatibility](COMPATIBILITY.md), [licensing](LICENSE_SCOPE.md) and
[distribution requirements](DISTRIBUTION.md).

Original RHOOK-owned SDK source and documentation use the existing root
[Apache-2.0 license](../LICENSE), with the explicit third-party/data exceptions
in [LICENSE_SCOPE.md](LICENSE_SCOPE.md). Executable availability remains pending.
