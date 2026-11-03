#!/usr/bin/env python3
"""Add the Profile Descriptor 0.1 files to the dev branch's source pins (case-install-inventory.json,
install_cases.py INVENTORY_SHA256, case-source.json). Computed from the accepted SDK 0.4 pin files: new files are
appended; the existing files G4A and the G5 preflight change (MODIFIED) are re-pinned with a G4A note appended to their source-change
record; any other existing pin that changed is refused.
Usage: python3 -B tools/update_profile_descriptor_pins.py [--check]
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SDK = Path(__file__).resolve().parents[1]
BASE = 'f6134fd61560b341e7689d83ead004d18f09e943'
NEW = {
    'rhook_alpha/profile_descriptor.py': 'Add Profile Descriptor 0.1: offline loader, validator and interpreter of reviewed hook profiles as data (SDK 0.6, G1-G3), plus the G4A backend helpers (worker-bound mirror, plan intent, prepared-input data checks, native operation descriptor binding refused until review and engine acceptance); no session wiring. G5 preflight: the reviewed G4B engine identity record (an identity, not an execution authorization) and the trie-only target authentication call.',
    'rhook_alpha/cases/scenario/native/descriptor.go': 'Add the Go Profile Descriptor 0.1 interpreter and profile-overlay input binding (G4A: parsed through the shared scenario Parse); legacy profiles unchanged.',
    'rhook_alpha/cases/scenario/native/profile.go': 'Add the G4A linked profile nitro-hook-profile-overlay/0.1: fixed worker bounds, descriptor-derived admission profile over the unchanged SDK 0.4 admission, review-gated loader, derived overlay, offline --profile-state report and operation descriptor binding.',
    'rhook_alpha/cases/scenario/native/profile_test.go': 'Add G4A integration tests: worker bounds and review gate, runtime isolation, operation binding, integrated G1 on the witness, overlay safety, admission parity and evidence tamper checks.',
    'rhook_alpha/cases/scenario/native/descriptor_test.go': 'Add G1 equivalence, G2 negative, probe, binding and G3 accepted-input tests for the descriptor interpreter.',
    'rhook_alpha/cases/scenario/native/descriptors/hookr-1.json': 'Add the canonical hookr-1 profile descriptor (data only).',
    'rhook_alpha/cases/scenario/native/descriptors/CATALOGUE.json': 'Add the descriptor review catalogue: hookr-1 admitted for offline preparation only.',
    'rhook_alpha/profile_overlay.py': 'Add the SDK 0.6 G5 preflight profile-overlay workflow: offline preparation from a pinned SDK 0.4 input (static coverage, trie-only target authentication, fixed inputs), and ProfileOverlayExecutionSDK with host admission v4, an advisory authorization check and a launcher that leaves the attempt marker to the child run().',
    'rhook_alpha/profile-target-state.mjs': 'Add the offline trie-only authenticator of the descriptor contracts and target words (no transport, EVM or authority).',
    'rhook_alpha/profile_parity.py': 'Add the pre-registered G5 native parity matrix and strict comparators (a missing, null or empty required field fails); offline, recorded JSON only.',
}
# Existing pinned files G4A and the G5 preflight change, with the note appended to their source-change record.
MODIFIED = {
    'rhook_alpha/cases/scenario/native/admission.go': 'SDK 0.6 G4A: the profile-overlay domain runs the same admission with a descriptor-derived profile, plus the descriptor binding, reviewed chain-config bytes, reviewed original Root word and descriptor authentication after every legacy check; Rules/Router targets come from the profile; legacy profiles unchanged.',
    'rhook_alpha/cases/scenario/native/controller.go': 'SDK 0.6 G4A: overlay records may carry the descriptor SHA-256 (omitted for legacy evidence); the profile-overlay evidence domain is decoded.',
    'rhook_alpha/cases/scenario/native/dynamic.go': 'SDK 0.6 G4A: runtime isolation covers four linked profiles; profile-overlay admission by purpose; descriptor writes applied through the checked descriptor path; Rules target from the profile.',
    'rhook_alpha/cases/scenario/native/evidence.go': 'SDK 0.6 G4A: VerifyProfileEvidence re-derives descriptor overlays on the witness under a NATIVE_EXECUTION review; LP evidence must not carry a descriptor hash; Rules target from the profile.',
    'rhook_alpha/cases/scenario/native/overlay.go': 'SDK 0.6 G4A: the shared world-overlay derivation accepts the profile-overlay domain and takes the Rules target from the profile.',
    'rhook_alpha/cases/scenario/native/spec.go': 'SDK 0.6 G4A: optional profileOverlay body field (absent from legacy inputs, so their encodings and commitments are unchanged) and its domain rule; profile Rules/Router targets.',
    'rhook_alpha/cases/scenario/native/worker.go': 'SDK 0.6 G4A: --profile-state offline command, profile-overlay verify dispatch, offline-pair-only rule, operation descriptor binding and NATIVE_EXECUTION admission purpose on the execute path.',
    'rhook_alpha/cases/scenario/api.py': 'SDK 0.6 G4A: the nitro-hook-profile-overlay/0.1 profile and domain in plan, input, operation binding (profileDescriptor) and verification checks; legacy plans unchanged. G5 preflight: fail-closed per-operation owner authorization (authorize_profile, require_profile_authorization) checked by run() before any worker check or consent key and again under the lock, where run() opens the one-shot attempt itself; the consent grant is capped at the authorization expiry; host admission v4 only.',
    'rhook_alpha/cases/authority.py': 'SDK 0.6 G5 preflight: optional not_after caps a consent grant at the profile-overlay authorization expiry; omitted, the grant is unchanged.',
    'rhook_alpha/cases/scenario/diagnostic.py': 'SDK 0.6 G5 preflight: the diagnostic refuses any plan or registered runtime other than the LP scenario worker.',
    'rhook_alpha/cases/scenario/closure.py': 'SDK 0.6 G5 preflight: closure refuses any plan or registered runtime other than the LP scenario worker.',
    'rhook_alpha/cases/__main__.py': 'SDK 0.6 G5 preflight: profile-prepare, profile-authenticate, profile-operation, profile-authorize and profile-run commands for the descriptor worker home.',
    'tools/build_scenario_worker.py': 'SDK 0.6 G4A: links nitro-hook-profile-overlay/0.1 and stages the descriptors directory (source only; no build performed in G4A).',
}
PUBLIC_EXTRA = ['tests_cases/test_profile_descriptor.py', 'tests_cases/test_profile_preflight.py', 'tools/make_hookr1_descriptor.py', 'tools/run_descriptor_go_tests.py',
                'tools/update_profile_descriptor_pins.py', 'PROFILE_DESCRIPTOR_SPEC.md']


def sha(path):
    return hashlib.sha256((SDK / path).read_bytes()).hexdigest()


def base(name):
    """The accepted SDK 0.4 bytes of a pin file; the update is always computed from them, so it is idempotent."""
    return subprocess.run(['git', '-C', str(SDK), 'show', BASE + ':sdk/' + name], check=True, capture_output=True).stdout


def dump(value):
    return json.dumps(value, indent=2).encode() + b'\n'


def build():
    inv = json.loads(base('case-install-inventory.json'))
    files = dict(inv['files'])
    for name in NEW:
        assert name not in files, name
        files[name] = sha(name)
    inv['files'] = files
    changes = dict(inv['sourceChanges'])
    changes.update({k: v for k, v in NEW.items()})
    for name, note in MODIFIED.items():
        if name in files:
            files[name] = sha(name)
            changes[name] = (changes[name] + ' ' if name in changes else '') + note
    inv['files'] = files
    inv['sourceChanges'] = changes
    inv_raw = dump(inv)
    installer = re.sub(r"INVENTORY_SHA256 = '[0-9a-f]{64}'", "INVENTORY_SHA256 = '" + hashlib.sha256(inv_raw).hexdigest() + "'",
                       base('install_cases.py').decode(), count=1)
    src = json.loads(base('case-source.json'))
    pins = dict(src['files'])
    for name in list(NEW) + PUBLIC_EXTRA:
        if name in pins:
            assert pins[name] == sha(name) or name in PUBLIC_EXTRA, name
        pins[name] = sha(name)
    for name in MODIFIED:
        assert name in pins or name in files, name
        if name in pins:
            pins[name] = sha(name)
    # The two changed pin carriers are themselves pinned public files.
    pins['case-install-inventory.json'] = hashlib.sha256(inv_raw).hexdigest()
    pins['install_cases.py'] = hashlib.sha256(installer.encode()).hexdigest()
    src['files'] = pins
    return inv_raw, dump(src), installer


def main(argv):
    inv_raw, src_raw, pinned = build()
    installer = (SDK / 'install_cases.py').read_text()
    if '--check' in argv:
        same = ((SDK / 'case-install-inventory.json').read_bytes() == inv_raw and (SDK / 'case-source.json').read_bytes() == src_raw
                and installer == pinned)
        print('PINS_CURRENT' if same else 'PINS_STALE')
        return 0 if same else 1
    (SDK / 'case-install-inventory.json').write_bytes(inv_raw)
    (SDK / 'case-source.json').write_bytes(src_raw)
    (SDK / 'install_cases.py').write_text(pinned)
    print(json.dumps(dict(installInventorySha256=hashlib.sha256(inv_raw).hexdigest(), caseSourceSha256=hashlib.sha256(src_raw).hexdigest())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
