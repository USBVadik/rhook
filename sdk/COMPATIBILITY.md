# Supported scope

| Area | Boundary |
| --- | --- |
| Executable Alpha | macOS arm64, macOS 15.5+ Mach-O minimum; unoptimized Python 3.12+. Acceptance used macOS 26.5/Python 3.15.0 on one physical Mac. Other versions meeting the minimum are not separately tested combinations. |
| Case | Robinhood Chain 4663, block 93251803, parent 93251802, all seven arrivals. Private saved state/witness required. |
| Rule | `RulesConfig.lpBps`, bits 160–175 of the authenticated packed word. Integer 0–99 planning; native accepted at 50 and earlier at 0. Initial developer acceptance targets 50. |
| Contract generation | `hookr-1`, standard HookrRules, Root/Rules runtime hashes matched to official `hookr-sdk@1.1.1`. ABI compatibility does not establish storage layout; source/layout pins are separate. |
| Fee semantics | LP Rewards add-on and its associated protocol share change. Hook Block, base/dynamic fees and recapture remain enabled. For 100→50 outer Swap fee is 11048→7048 pips. |
| TypeScript | Case-specific inspect/plan adapter included. Current HookrRouter swap-builder compatibility is not established. |
| Linux | Separate Ubuntu amd64 worker acceptance matched Mac result bytes. This public macOS installer has no supported Linux/Windows installation path. |
| Assurance | Saved-result verify/compare or separately authorized fresh execution. No independent Rust Pair03 replay; economic assurance unresolved, heterogeneous agreement not evaluated, qualified Claims 0. |

A missing witness is not an EVM revert and never triggers an automatic download.
Local consent assumes trusted parent directories and a trusted operator. It is
not an adversarial multi-tenant authorization service. Public source differs
from accepted native source; original evidence and binary remain immutable.
