# Private recorded-witness replay results

RHOOK's first supported application is Hookr on Robinhood Chain. Two private
historical experiments tested whether recorded original-state dependencies were
sufficient for fresh execution without the full prepared reference package.
This page summarizes those results; it does not ship the private inputs or
make the experimental recorder part of the public installation.

| Experiment | Historical block / original arrivals | Intervention | Recorded package | Original preimages |
| --- | --- | --- | --- | --- |
| Build26D | 93251803 / 7 | Dynamic Fee OFF; LP100 and arb recapture retained | 1,248,459 B | 848 trie nodes + 26 code preimages |
| Build27g | 93249252 / 5 | LP Rewards 100→50 | 1,838,885 B | 1,214 trie/code preimages |

In each experiment, a full-reference discovery ACTUAL/BRANCH pair recorded the
required original dependencies. An original-only package was derived, then a
fresh pair ran from that reduced package with no access to the full reference.
Both worlds used separate state copies and the same Go/Nitro backend lineage;
replay used `Source=nil`, with no RPC or hydration. All four worlds per case
completed. Discovery/reduced execution fields matched the accepted case,
including state, receipts, headers, logs and observations. Witness-provenance
commitments differed as expected; entire evidence envelopes were not identical.
Cleanup was confirmed in both operations.

For Build26D, 1,248,459 B versus the 1,417,029 B prepared reference is an
11.896% package reduction. That comparison is against an already prepared
witness, not an archive node database. Neither result demonstrates general
storage/RAM savings, arbitrary-intervention closure or a minimum-size witness.
The second case changes the BRANCH state root but has no subject token-output
or gas improvement; it is a portability/closure test, not a profit demo.

## Evidence limits

- These are retained private producer results. The public repository does not
  contain their full evidence, so a reader cannot independently reproduce or
  verify them from this page or from the source-only clone.
- Both cases use Go/Nitro; no independent Rust execution is established for
  these Hookr cases. The experiments used different versioned worker snapshots,
  not one interchangeable binary qualified across every case.
- Completion establishes operational witness sufficiency for those exact
  executed plans. `nativeRecorderCoverage=UNKNOWN` globally; there is no claim
  of universal witness completeness or full `Lawful` qualification.
- `qualifiedClaims=0`. Independent external-developer native reproduction has
  not occurred. Source-only clean-room installation is a separate capability.
- Private experimental host policies are not public defaults. The approved
  source installer preserves strict resource admission and excludes private
  calibration/free-telemetry modules. No safety conclusion for arbitrary host
  pressure conditions follows from these results.

Use the [clean-room guide](CLEAN_ROOM.md) for the public install/import/plan path,
the [historical guide](HISTORICAL_EXECUTION.md) for the supported execution
boundary, and [distribution status](DISTRIBUTION.md) for unavailable assets.
No binary, witness or native execution permission is supplied by this summary.
