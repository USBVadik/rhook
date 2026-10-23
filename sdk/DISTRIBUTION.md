# Executable distribution pending

The accepted macOS kit is a real executable SDK. Worker, sensor, Node and saved
inputs are absent from Git. There is no public asset URL, package index or
GitHub Release for this kit.

Accepted worker SHA-256:
`d7e15c1b4168da06c4f3410ff1cc9f7963e090feedb22a7405d391910942283c`.
`developer/artifacts.json` fixes the other pins. Publishing source does not
authorize an upload or new execution.

The existing inventory covers 222 outer kit files plus 12,338 nested entries.
Original RHOOK-owned SDK source and documentation are covered by Apache-2.0;
see [license scope](LICENSE_SCOPE.md). That source decision does not clear the
combined executable or historical data. Existing notices and dependency locks
are retained. Remaining executable release work:

1. Review the actual Nitro/geth/CGO/libstylus combination and fulfill the
   applicable corresponding-source/application-relink route. A local companion
   has been assembled and authenticated from retained inputs; its build-only
   recipes have not been executed. Packaging alone is neither legal clearance
   nor proof of a successful relink.
2. Retain exact notices, including Node's composite notice. Accepted Node's
   unsigned content matches the official pinned release; signing bytes differ.
   Do not silently substitute a different binary.
3. Resolve exact witness/data-sharing rights and approve public disclosure.
   On-chain visibility and provider names establish neither blanket permission
   nor blanket prohibition.
4. Review original engine source-path disclosure, needed by the accepted
   runtime. Sanitized public source cannot impersonate its source commitment.
5. Approve exact final assets/checksums before release and validate the relink
   route before claiming it works. No relink or new native test is run here.

Pinned [Nitro terms](../examples/robinhood-v4/notices/nitro-LICENSE.md) and
[geth LGPL terms](../examples/robinhood-v4/notices/geth-COPYING.LESSER) remain
separate from the RHOOK source license. No general production grant is claimed.
