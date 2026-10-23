# Private checkpoint review

Target repository: `USBVadik/privatrhook`, PRIVATE, freshly verified through authenticated GitHub metadata. Proposed branch: `codex/hookr-pair03-checkpoint`, based on `25588631de72de8673ec61d22b6965bf680f1166`, which matches current GitHub main.

The public checkout `USBVadik/rhook` is clean on `codex/amount27-workflow-checkpoint` at `6205c6780072499a2f46da6e3ba673e432d7b1ee`, matching that remote branch. Its remote main is `4fa010b1d3815d19ed556ef6bfccd58bec39d8ce`. Public files are not changed or staged.

The enclosing research workspace has an unborn main, zero tracked files and no remote. It is not a source checkpoint repository. Its untracked scope includes scientific archives, large dependencies and secret-bearing filenames. Whole-workspace staging is explicitly excluded.

## Exact source preservation

All77 copied files are byte-identical source/configuration snapshots. No refactoring or path normalization was performed. Large binaries, dependency trees, raw state/witness, runtime, grants/authority, raw demo and credentials are excluded.

Fourteen absolute local or synthetic path references remain in these eight files:

- `native/prestate/go.mod`
- `native/saved-pair/go.mod`
- `native/saved-pair/plan.json`
- `supervisor/host-capture/tools/diagnostic.py`
- `supervisor/host-capture/tools/test_diagnostic.py`
- `supervisor/pair03/tools/run_once.py`
- `supervisor/pair03/tools/test_launcher.py`
- `supervisor/pair03/tools/verify.py`

They do not turn into public data while this branch stays local in the private repository. A future push would make these source files and local paths readable to users with access to that private repository. They are not approved for public export or a clean-room SDK. Any change of destination or proposed public publication needs a separate exact-scope review.

## Two proposed commits

1. `checkpoint: preserve Go Hookr native pair source and tests` — exactly the77 copied source/configuration files in SOURCE_PROVENANCE.json.
2. `docs: record private Pair03 checkpoint scope and provenance` — source provenance, exclusions, status, validation and portability boundaries, plus a narrow root README update distinguishing engineering sources from historical encrypted backups.

No commit or push is created automatically by this proposal. The staged diff and the exact two file lists are provided for founder review. The current source snapshot is not an executable distribution; local paths and omitted private build context remain explicit.

`externalDelivery=HOLD`. STOP before push, publication, release or SDK delivery. No extra experiment, source refactoring or scientific successor follows.
