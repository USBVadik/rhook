# Executable availability

The public repository distributes SDK source and offline tests. It contains no
Pair03 worker, sensor, Node runtime or private historical input bundle, and has
no public executable asset URL or GitHub Release.

## Locally validated private pilot

On 25 October 2026, the private developer kit passed clean installation and a
new installed native LP100→50 pair, followed by its own verify/compare commands.
Both full world files matched the accepted references. A corresponding-source
companion and recipient instructions are prepared for one private developer.
Actual external delivery and another developer's reproduction have not happened.

The separately relinked developer worker is 44,835,778 bytes, SHA-256
`09ed5608c467a330779fcb7ccb677968f17729f25113c684c89ffb5292cc0f64`.
Its source commitment is
`a61fc0b687e12d4cfab64fe64593c0d1c9081ca021bd700635e5a3e763364f60`.
It preserves the case and v2 policy while using its own artifact registration.
See the [case study](../docs/research/hookr-pair03-100-to-50.md).

## Existing public-source registration

`developer/artifacts.json` and `source-provenance.json` still describe the earlier
scientific runtime: worker SHA-256
`d7e15c1b4168da06c4f3410ff1cc9f7963e090feedb22a7405d391910942283c`.
The sanitized public source cannot impersonate its original engine commitment.
That installer requires the exact original engine and asset bundle. The newer
pilot's bundle is not a drop-in replacement for those pins.

This documentation update changes neither registration nor accepted evidence.
It does not claim that a public clone can run the private pilot.

## Conditions before delivery

Original RHOOK-owned source/docs are Apache-2.0; see [license scope](LICENSE_SCOPE.md).
The executable and historical inputs have separate conditions:

- Preserve the actual Nitro/geth/CGO/static-library notices and corresponding
  source/application-relink material. Local relinking and installation now work;
  this does not by itself settle combined-license classification or every
  source/recombination obligation. Arbitrary modified-library combinations and
  a fresh Rust-library rebuild were not demonstrated.
- Retain Node's composite notice and accurate provenance. Its unsigned content
  matched the pinned official release; signing bytes differ. The pilot does not
  silently substitute another runtime.
- Record the basis for the exact historical witness disclosure. Public onchain
  visibility establishes neither blanket permission nor a blanket prohibition.
- Select a recipient, supported platform and private channel, and approve the
  exact payload. Upstream compiler path labels are retained as nonsensitive
  dependency metadata; they do not alone require another build or block a pilot.

Pinned [Nitro terms](../examples/robinhood-v4/notices/nitro-LICENSE.md) and
[geth LGPL terms](../examples/robinhood-v4/notices/geth-COPYING.LESSER) remain
separate from RHOOK's source license. No general production grant or automated
legal-clearance finding is claimed. No private executable, witness, source
companion, authority or raw execution archive is published by this update.
