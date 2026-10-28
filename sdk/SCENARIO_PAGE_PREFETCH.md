# Bounded executor pages

The supported Hookr scenario preserves its 27-key initial executor prefetch.
During discovery, an unresolved original-root key in the fixed executor's
observed storage-key family can fetch one aligned page of eight keys. The
collector authenticates every path, including absence, against the same pinned
root and returns only the worker's requested subjects. No state value is guessed.

At most four pages and 32 additional page keys are allowed. Unrelated mappings
use exact reads. The shared limit remains 64 RPC, with at most 63 ordinary
requests and one reserved final pinned-header recheck; acquisition remains 30s,
3s per request, 8MiB total, bounded responses and at most two in flight. A STOP
closes the operation. These limits do not guarantee sufficient witness coverage.

The Go worker, overlay mechanism and independent final nil-Source worlds are
unchanged. Every changed SDK version requires new exact bindings/authorization.
Retained-trace models and StateDB unit tests are not a successful native swap.

## Exact external-venue hints (Build08)

The fixed case also batches sixteen observed storage identities for
`0xd8b750f564321ce68b4b3d8498616da96fad798d` through the existing trace-hint
mechanism. Run07 fetched eleven subjects, read four more from authenticated cache
and requested one unresolved key before its budget STOP. The hints contain keys
only; the missing old proof is
still unavailable. Every value and account/code binding must be authenticated
at the newly selected root. There is no exemption for the expected pool code.

Offline analysis matched retained runtime bytes to the Uniswap V3 pool artifact
after its 27 immutable substitutions. Exact layout derivations identify slot0,
liquidity, four words of one tick record and ten bitmap words. This explains the
hint identities; it introduces no V3-specific runtime interpretation or scans
across hashed keys. The executor page8 mechanism remains separate and unchanged.

A retained-source-lookup model with the eleven available paths reduces the
successful Run07 prefix from 63 ordinary RPC to 52. One final header would make
53 total, but it was not fetched in this offline model. The candidate's sixteen
keys fit one proof batch; its full proof size, live savings, unseen continuation
and VARIANT coverage have not been measured. Neither a complete witness nor a
completed BASELINE is established. Caps and fresh authorization requirements are
unchanged; another RUN requires its own exact proposal and consent.

## Recorded-read batching (Build09 repair)

The closed Build08 live trace supplies additional exact account/storage identities.
The catalogue now holds176unique storage hints across18accounts; all are retained
proof subjects or actual native missing lookups, never guessed values or ranges.
HistoryStorage and transaction-filter subjects are excluded and derived afresh.
The venue retains its derived16-key core and now has23recorded identities.

These hints use the existing512-key/64-account catalogue bounds and48-key proof
batches. Some accounts require two batches. The executor's dynamic read-ahead
remains limited to four pages/32new page keys. Exact prefetched subjects and
dynamic-page accounting are distinct; the reported27+32window counter describes
that page mechanism, not every original-root path already in cache. No page,
RPC, byte, time, RSS or policy limit is increased.

A fixed-lookup replay from Run03's prefetch inventory models63→41ordinaryRPC
for the retained successful prefix. The sole unresolved actual key…e644 is a hint
only; its proof is absent from the old root. Fresh-root dynamic keys, continuation
and VARIANT remain unknown. This is a collection-schedule repair, not execution
closure, and the original science and accepted worker remain unchanged.
