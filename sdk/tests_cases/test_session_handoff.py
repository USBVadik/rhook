"""Session Handoff 0.1 tests. Synthetic inputs only; nothing here is native, EVM or chain evidence."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, unittest
from unittest.mock import patch

from developer.files import canonical, digest, load
from rhook_alpha.execution import ExecutionSDK
from rhook_alpha.session import SessionError, core, handoff, hookr
from test_session import COVERAGE, NoNativeNoNetwork, SessionTest, execution_fixture, hash_linked_fixture, recommit

SDK = Path(__file__).resolve().parents[1]
EXAMPLE = SDK / 'examples/session_handoff.py'


def reseal_header(header):
    body = {k: v for k, v in header.items() if k != 'headerCommitment'}
    body['sessionId'] = core.CounterfactualSession._session_id(body)
    return dict(body, headerCommitment=core.commit(core.SCHEMA, body))


def reseal_variant(record):
    body = {k: v for k, v in record.items() if k != 'variantCommitment'}
    return dict(body, variantCommitment=core.commit(core.VARIANT_SCHEMA, body))


def tree(directory):
    return {str(p.relative_to(directory)): p.read_bytes() for p in sorted(directory.rglob('*')) if p.is_file()}


class HandoffTest(SessionTest):
    def exported(self, *, include_source=True, lps=(50, 0), prepare=(50,), name='home', value=None, out='package'):
        s, _, _ = self.session(value, name=name)
        ids = {lp: s.add_variant({'lpBps': lp})['variantId'] for lp in lps}
        for lp in prepare:
            s.prepare_variant(ids[lp])
        return s, ids, s.export_handoff(self.root / out, include_source=include_source)

    def receiver(self, name='receiver'):
        return ExecutionSDK(self.root / name)

    @staticmethod
    def writable(package):
        for p in [package, *package.rglob('*')]:
            p.chmod(0o700 if p.is_dir() else 0o600)

    def tamper(self, package, change):
        """Edit the manifest; returns the edited manifest's own SHA-256, as an attacker would offer it."""
        path = package / 'HANDOFF.json'
        value = json.loads(path.read_bytes())
        change(value)
        path.chmod(0o600)
        path.write_bytes(canonical(value) + b'\n')
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def refused(self, package, pin, code, *, home='receiver'):
        e = self.code(lambda: self.receiver(home).import_session_handoff(package, expected_manifest_sha256=pin), code)
        self.assertFalse((self.root / home / 'sessions').exists() and any((self.root / home / 'sessions').iterdir()))
        return e

    def cli(self, home, *args, prefix=None):
        command = [sys.executable, '-I', str(prefix / 'bin/rhook-cases')] if prefix else [sys.executable, '-B', '-m', 'rhook_alpha.cases']
        r = subprocess.run([*command, '--home', str(home), *args], cwd=SDK, capture_output=True, timeout=60)
        return r.returncode, json.loads(r.stdout)


class Export(HandoffTest):
    def test_metadata_only_is_the_default_and_carries_no_source_material(self):
        s, ids, result = self.exported(include_source=False)
        package = self.root / 'package'
        self.assertEqual((result['mode'], result['sourceMaterial']), ('METADATA_ONLY', 'SOURCE_MATERIAL_NOT_INCLUDED'))
        self.assertEqual(sorted(p.name for p in package.iterdir()), ['HANDOFF.json'])
        raw = (package / 'HANDOFF.json').read_bytes()
        self.assertNotIn(b'"inventory"', raw)
        self.assertNotIn(s.source_path.read_bytes().strip(), raw)
        self.assertEqual(result['manifestSha256'], hashlib.sha256(raw).hexdigest())
        view = self.receiver().inspect_session_handoff(package, expected_manifest_sha256=result['manifestSha256'])
        self.assertEqual((view['status'], view['mode'], view['assurance']['sourceIntegrity']),
                         ('HANDOFF_AUTHENTICATED', 'METADATA_ONLY', 'NOT_AVAILABLE_SOURCE_MATERIAL_NOT_INCLUDED'))
        self.assertEqual([v['variantId'] for v in view['variants']], [ids[0], ids[50]])
        self.assertFalse(view['capabilities']['reconstructSession'])
        self.refused(package, result['manifestSha256'], 'HANDOFF_SOURCE_NOT_INCLUDED')
        self.assertFalse((self.root / 'receiver').exists())
        # The CLI export is metadata-only unless --include-source is given.
        code, out = self.cli(self.root / 'home', 'session-handoff-export', '--session', s.id, '--output', str(self.root / 'cli'))
        self.assertEqual((code, out['mode']), (0, 'METADATA_ONLY'))
        self.assertEqual(out['manifestSha256'], result['manifestSha256'])

    def test_complete_export_includes_exactly_the_pinned_source_by_opt_in(self):
        s, _, result = self.exported()
        package = self.root / 'package'
        self.assertEqual(result['files'], ['HANDOFF.json', 'source/SCENARIO.json'])
        self.assertEqual((package / 'source/SCENARIO.json').read_bytes(), s.source_path.read_bytes())
        manifest = load(package / 'HANDOFF.json', 1 << 20)
        self.assertEqual(manifest['files'], [dict(path='source/SCENARIO.json', bytes=s.header['source']['bytes'],
                                                  sha256=s.header['source']['sha256'])])
        self.assertEqual(manifest['session'], s.header)
        self.assertEqual(manifest['excluded'], handoff.EXCLUDED)
        for flag in ('yes', 1, None):
            self.code(lambda: s.export_handoff(self.root / 'x', include_source=flag), 'HANDOFF_INCLUDE_SOURCE_FLAG')
        code, out = self.cli(self.root / 'home', 'session-handoff-export', '--session', s.id, '--output', str(self.root / 'cli'), '--include-source')
        self.assertEqual((code, out['manifestSha256']), (0, result['manifestSha256']))

    def test_manifest_is_deterministic_across_homes_registration_order_and_duplicates(self):
        _, _, a = self.exported(lps=(50, 0), prepare=(), name='one', out='a')
        s, _, _ = self.session(name='two')
        for lp in (0, 50, 50, 0):
            s.add_variant({'lpBps': lp})
        b = s.export_handoff(self.root / 'b', include_source=True)
        self.assertEqual(a['manifestSha256'], b['manifestSha256'])
        self.assertEqual((self.root / 'a/HANDOFF.json').read_bytes(), (self.root / 'b/HANDOFF.json').read_bytes())
        text = (self.root / 'a/HANDOFF.json').read_text()
        for local in (str(self.root), 'one-SCENARIO', '"home"'):
            self.assertNotIn(local, text)
        # Preparation state is part of the package: a prepared variant carries its reference.
        prepared = s.prepare_variant(next(v['variantId'] for v in s.variants() if v['descriptor']['replacement'] == 50))
        c = s.export_handoff(self.root / 'c', include_source=True)
        self.assertNotEqual(c['manifestSha256'], a['manifestSha256'])
        refs = {e['record']['descriptor']['replacement']: e['exporterPreparation'] for e in load(self.root / 'c/HANDOFF.json', 1 << 20)['variants']}
        self.assertEqual(refs, {0: None, 50: dict(scenarioCommitment=prepared['scenarioCommitment'], scenarioSha256=prepared['scenarioSha256'])})

    def test_export_never_overwrites_and_stays_outside_the_home(self):
        s, _, _ = self.exported()
        self.code(lambda: s.export_handoff(self.root / 'package', include_source=True), 'HANDOFF_OUTPUT_EXISTS')
        (self.root / 'empty').mkdir()
        self.code(lambda: s.export_handoff(self.root / 'empty'), 'HANDOFF_OUTPUT_EXISTS')
        self.assertEqual(list((self.root / 'empty').iterdir()), [])
        self.code(lambda: s.export_handoff(self.root / 'home/export'), 'HANDOFF_OUTPUT_INSIDE_SDK_HOME')
        self.code(lambda: s.export_handoff(self.root / 'missing/export'), 'HANDOFF_OUTPUT_PARENT_MISSING')
        (self.root / 'link').symlink_to(self.root, target_is_directory=True)
        self.code(lambda: s.export_handoff(self.root / 'link/export'), 'HANDOFF_OUTPUT_PATH')

    def test_drifted_session_records_stop_the_export(self):
        s, ids, _ = self.exported(out='first')
        broken = s.directory / 'variants' / ids[0] / 'prepared'
        broken.mkdir(); (broken / 'SCENARIO.json').write_text('{}')
        with self.assertRaises((SessionError, ValueError)):
            s.export_handoff(self.root / 'second', include_source=True)
        self.assertFalse((self.root / 'second').exists())
        shutil.rmtree(broken)
        source = s.source_path
        source.chmod(0o600); source.write_bytes(source.read_bytes().replace(b'"nonce":0', b'"nonce":1', 1))
        self.code(lambda: s.export_handoff(self.root / 'third', include_source=True), 'SESSION_SOURCE_DRIFT')
        self.assertFalse((self.root / 'third').exists())


class Import(HandoffTest):
    def test_complete_package_rebuilds_the_same_session_in_a_fresh_home(self):
        s, ids, result = self.exported()
        header, pin = s.header, result['manifestSha256']
        expected = {lp: s.prepare_variant(v)['scenarioCommitment'] for lp, v in ids.items()}
        # Neither the exporter's home nor its source file is needed by the receiver.
        shutil.rmtree(self.root / 'home'); (self.root / 'home-SCENARIO.json').unlink()
        with NoNativeNoNetwork() as guard:
            imported, report = handoff.import_package(self.root / 'receiver', self.root / 'package', pin, prepare=True)
        self.assertEqual(guard.launched, [])
        self.assertEqual((imported.id, imported.header), (header['sessionId'], header))
        self.assertEqual({v['descriptor']['replacement']: v['variantId'] for v in imported.variants()}, ids)
        self.assertEqual(report['existingSessionReused'], False)
        rows = {r['descriptor']['replacement']: r for r in report['variants']}
        self.assertEqual({lp: r['localPreparation']['scenarioCommitment'] for lp, r in rows.items()}, expected)
        self.assertEqual((rows[50]['reconstruction'], rows[0]['reconstruction']), ('MATCHES_EXPORTER_REFERENCE', 'NO_EXPORTER_REFERENCE'))
        self.assertEqual(report['preparedReconstruction'], 'LOCALLY_PREPARED')
        self.assertEqual(report['importedRecords'], dict(verifications=0, preparedDirectories=0))
        # The rebuilt session is an ordinary one: it reopens after the package is gone.
        self.writable(self.root / 'package'); shutil.rmtree(self.root / 'package')
        again = self.receiver().open_session(imported.id)
        self.assertEqual({v['status'] for v in again.variants()}, {'PREPARED_NOT_EXECUTED'})
        self.assertEqual(sorted(p.name for p in (self.root / 'receiver/sessions').iterdir()), [imported.id])

    def test_import_api_and_cli_follow_the_same_path(self):
        _, ids, result = self.exported()
        code, out = self.cli(self.root / 'cli-home', 'session-handoff-import', '--package', str(self.root / 'package'),
                             '--manifest-sha256', result['manifestSha256'], '--prepare')
        self.assertEqual((code, out['status'], out['preparedReconstruction']), (0, 'SESSION_HANDOFF_IMPORTED', 'LOCALLY_PREPARED'))
        api = self.receiver().import_session_handoff(self.root / 'package', expected_manifest_sha256=result['manifestSha256'])
        self.assertEqual(api.id, out['sessionId'])
        code, bad = self.cli(self.root / 'cli-home-2', 'session-handoff-import', '--package', str(self.root / 'package'),
                             '--manifest-sha256', '0' * 64)
        self.assertEqual((code, bad['status'], bad['causeCode']), (1, 'SESSION_STOP', 'HANDOFF_MANIFEST_PIN_MISMATCH'))
        code, view = self.cli(self.root / 'cli-home-2', 'session-handoff-inspect', '--package', str(self.root / 'package'))
        self.assertEqual((code, view['status']), (1, 'HANDOFF_NOT_PINNED'))
        self.assertFalse((self.root / 'cli-home-2').exists())

    def test_reimport_is_deterministic_and_conflicts_are_never_overwritten(self):
        _, ids, result = self.exported()
        pin, package = result['manifestSha256'], self.root / 'package'
        first = self.receiver().import_session_handoff(package, expected_manifest_sha256=pin)
        before = tree(first.directory)
        _, report = handoff.import_package(self.root / 'receiver', package, pin)
        self.assertTrue(report['existingSessionReused'])
        self.assertEqual(tree(first.directory), before)
        # A stored variant that differs from the package stops the import and stays as it is.
        path = first.directory / 'variants' / ids[0] / 'VARIANT.json'
        value = json.loads(path.read_bytes()); value['descriptor']['replacement'] = 49
        path.chmod(0o600); path.write_bytes(canonical(reseal_variant(value)) + b'\n')
        tampered = path.read_bytes()
        self.code(lambda: self.receiver().import_session_handoff(package, expected_manifest_sha256=pin), 'VARIANT_RECORD_DRIFT')
        self.assertEqual(path.read_bytes(), tampered)
        # A stored session header that differs is not replaced either.
        manifest = first.directory / 'SESSION.json'
        changed = json.loads(manifest.read_bytes()); changed['baseline']['lpBps'] = 99
        manifest.chmod(0o600); manifest.write_bytes(canonical(changed) + b'\n')
        self.code(lambda: self.receiver().import_session_handoff(package, expected_manifest_sha256=pin), 'SESSION_MANIFEST_DRIFT')
        self.assertEqual(json.loads(manifest.read_bytes()), changed)

    def test_package_variants_beyond_the_session_limit_add_nothing(self):
        _, ids, result = self.exported()
        local, _, _ = self.session(name='receiver')
        for lp in range(1, core.MAX_VARIANTS):
            local.add_variant({'lpBps': lp})
        before = sorted(local._variant_ids())
        self.code(lambda: self.receiver().import_session_handoff(self.root / 'package', expected_manifest_sha256=result['manifestSha256']),
                  'VARIANT_LIMIT')
        self.assertEqual(sorted(local._variant_ids()), before)

    def test_an_interrupted_import_is_never_a_session(self):
        s, _, result = self.exported()
        pin, package = result['manifestSha256'], self.root / 'package'
        real = core.CounterfactualSession.add_variant
        calls = []
        def crash(self_, parameters):
            calls.append(parameters)
            if len(calls) == 2:
                raise KeyboardInterrupt('power loss')
            return real(self_, parameters)
        # Simulate a crash: the second staged variant fails and nothing gets to clean up.
        with patch.object(core.CounterfactualSession, 'add_variant', crash), patch.object(handoff.shutil, 'rmtree'):
            with self.assertRaises(KeyboardInterrupt):
                self.receiver().import_session_handoff(package, expected_manifest_sha256=pin)
        entries = sorted(p.name for p in (self.root / 'receiver/sessions').iterdir())
        self.assertEqual(len(entries), 1); self.assertTrue(entries[0].startswith('.handoff-import-'))
        self.code(lambda: self.receiver().open_session(s.id), 'SESSION_MISSING_OR_INCOMPLETE')
        # A later import is unaffected by the leftover staging directory.
        imported = self.receiver().import_session_handoff(package, expected_manifest_sha256=pin)
        self.assertEqual(len(imported.variants()), 2)


class PackageIntegrity(HandoffTest):
    def setUp(self):
        super().setUp()
        self.s, self.ids, result = self.exported()
        self.pin, self.package = result['manifestSha256'], self.root / 'package'
        self.writable(self.package)

    def test_the_external_pin_is_required_and_checked_before_anything_else(self):
        e = self.refused(self.package, '0' * 64, 'HANDOFF_MANIFEST_PIN_MISMATCH')
        self.assertEqual(e.details['manifestSha256'], self.pin)
        self.refused(self.package, 'ABC', 'HANDOFF_MANIFEST_PIN_FORMAT')
        self.code(lambda: handoff.import_package(self.root / 'receiver', self.package, None), 'HANDOFF_MANIFEST_PIN_REQUIRED')
        unpinned = self.receiver().inspect_session_handoff(self.package)
        self.assertEqual((unpinned['status'], unpinned['packageIntegrity']),
                         ('HANDOFF_NOT_PINNED', 'FILES_MATCH_AN_UNPINNED_MANIFEST_NOT_AUTHENTICATED'))
        # Garbage behind a wrong pin is never parsed.
        (self.package / 'HANDOFF.json').write_bytes(b'{"a":1,"a":2}')
        self.refused(self.package, self.pin, 'HANDOFF_MANIFEST_PIN_MISMATCH')
        self.assertFalse((self.root / 'receiver').exists())

    def test_self_consistent_edits_do_not_bypass_the_pin_or_the_identity_checks(self):
        def lp49(m):
            m['variants'][1]['record']['descriptor']['replacement'] = 49
            m['variants'][1]['record'] = reseal_variant(m['variants'][1]['record'])
        offered = self.tamper(self.package, lp49)
        self.refused(self.package, self.pin, 'HANDOFF_MANIFEST_PIN_MISMATCH')
        # Even with the edited manifest's own hash as the pin, the record no longer derives its id.
        self.refused(self.package, offered, 'HANDOFF_VARIANT_INVALID')

    def test_a_changed_source_byte_or_file_list_fails(self):
        source = self.package / 'source/SCENARIO.json'
        raw = source.read_bytes()
        source.write_bytes(raw.replace(b'"nonce":0', b'"nonce":1', 1))
        self.refused(self.package, self.pin, 'HANDOFF_FILE_HASH_MISMATCH')
        source.write_bytes(raw)
        offered = self.tamper(self.package, lambda m: m['files'][0].update(bytes=m['files'][0]['bytes'] + 1))
        self.refused(self.package, offered, 'HANDOFF_MANIFEST_FILES')

    def test_missing_extra_hidden_and_special_entries_fail(self):
        source = self.package / 'source/SCENARIO.json'
        raw = source.read_bytes()
        cases = [('missing source', lambda: source.unlink(), lambda: source.write_bytes(raw)),
                 ('extra file', lambda: (self.package / 'notes.txt').write_text('x'), lambda: (self.package / 'notes.txt').unlink()),
                 ('hidden file', lambda: (self.package / '.DS_Store').write_bytes(b''), lambda: (self.package / '.DS_Store').unlink()),
                 ('verification record', lambda: (self.package / 'source/VERIFICATION.json').write_text('{}'),
                  lambda: (self.package / 'source/VERIFICATION.json').unlink()),
                 ('extra directory', lambda: (self.package / 'variants').mkdir(), lambda: (self.package / 'variants').rmdir())]
        for name, make, undo in cases:
            make()
            self.refused(self.package, self.pin, 'HANDOFF_FILE_SET')
            undo()
        source.unlink(); os.mkfifo(source)
        self.refused(self.package, self.pin, 'HANDOFF_FILE_TYPE')
        source.unlink(); source.write_bytes(raw)
        self.assertEqual(self.receiver().inspect_session_handoff(self.package, expected_manifest_sha256=self.pin)['status'], 'HANDOFF_AUTHENTICATED')

    def test_links_hardlinks_and_traversal_fail(self):
        source = self.package / 'source/SCENARIO.json'
        outside = self.root / 'outside.json'
        shutil.copyfile(source, outside)
        source.unlink(); source.symlink_to(outside)
        self.refused(self.package, self.pin, 'HANDOFF_SYMLINK')
        source.unlink(); os.link(outside, source)
        self.refused(self.package, self.pin, 'HANDOFF_HARDLINK')
        source.unlink(); shutil.copyfile(outside, source)
        alias = self.root / 'manifest-alias'
        os.link(self.package / 'HANDOFF.json', alias)
        self.refused(self.package, self.pin, 'HANDOFF_HARDLINK')
        alias.unlink()
        (self.root / 'linked').symlink_to(self.package, target_is_directory=True)
        self.refused(self.root / 'linked', self.pin, 'HANDOFF_PACKAGE_PATH')
        self.refused(self.root / 'package/../package', self.pin, 'HANDOFF_PACKAGE_PATH')
        self.refused(self.package / 'HANDOFF.json', self.pin, 'HANDOFF_PACKAGE_PATH')
        self.refused(self.root / 'nowhere', self.pin, 'HANDOFF_PACKAGE_MISSING')

    def test_oversized_and_non_strict_manifests_fail(self):
        manifest = self.package / 'HANDOFF.json'
        raw = manifest.read_bytes()
        duplicate = raw.replace(b'{"assurance"', b'{"schema":"x","assurance"', 1)
        manifest.write_bytes(duplicate)
        self.refused(self.package, hashlib.sha256(duplicate).hexdigest(), 'HANDOFF_MANIFEST_JSON')
        big = raw + b' ' * (handoff.MAX_MANIFEST_BYTES)
        manifest.write_bytes(big)
        self.refused(self.package, hashlib.sha256(big).hexdigest(), 'HANDOFF_FILE_SIZE')
        manifest.write_bytes(raw)
        source = self.package / 'source/SCENARIO.json'
        with source.open('r+b') as f:
            f.truncate(handoff.MAX_SOURCE_BYTES + 1)
        self.refused(self.package, self.pin, 'HANDOFF_FILE_SIZE')

    def test_manifest_claims_identities_and_order_are_exact(self):
        original = (self.package / 'HANDOFF.json').read_bytes()
        def restore():
            (self.package / 'HANDOFF.json').write_bytes(original)
        def header(change):
            def apply(m):
                change(m['session']); m['session'] = reseal_header(m['session'])
            return apply
        cases = [
            ('schema', lambda m: m.update(schema='rhook/session-handoff/0.2'), 'HANDOFF_MANIFEST_SCHEMA'),
            ('native claim', lambda m: m['assurance'].update(nativeExecution='PERFORMED'), 'HANDOFF_MANIFEST_CLAIMS'),
            ('capability claim', lambda m: m['capabilities'].update(nativeExecution='INCLUDED'), 'HANDOFF_MANIFEST_CLAIMS'),
            ('fewer exclusions', lambda m: m['excluded'].remove('VERIFICATION_RECORDS'), 'HANDOFF_MANIFEST_CLAIMS'),
            ('metadata claim with source present', lambda m: m.update(
                mode='METADATA_ONLY', sourceMaterial=handoff.policy('METADATA_ONLY')[0],
                capabilities=handoff.policy('METADATA_ONLY')[1], assurance=handoff.policy('METADATA_ONLY')[2]), 'HANDOFF_FILE_SET'),
            ('different checkpoint', header(lambda h: h['checkpoint'].update(blockNumber=h['checkpoint']['blockNumber'] + 1)), 'HANDOFF_SESSION_MISMATCH'),
            ('different source commitment', header(lambda h: h['source'].update(scenarioCommitment='0' * 64)), 'HANDOFF_SESSION_MISMATCH'),
            ('session id not derived', lambda m: m['session'].update(sessionId='0' * 64), 'HANDOFF_SESSION_INVALID'),
            ('header not sealed', lambda m: m['session']['baseline'].update(lpBps=99), 'HANDOFF_SESSION_INVALID'),
            ('other limitations', header(lambda h: h['limitations'].update(qualifiedClaims=1)), 'HANDOFF_SESSION_INVALID'),
            ('unsupported profile', header(lambda h: h.update(profile='arbitrary-evm/0.1')), 'UNSUPPORTED_PROFILE'),
            ('adapter version', header(lambda h: h.update(adapter='hookr-scenario-session/0.0')), 'HANDOFF_ADAPTER_VERSION'),
            ('modified descriptor', lambda m: m['variants'][0]['record']['descriptor'].update(replacement=1), 'HANDOFF_VARIANT_INVALID'),
            ('unsupported value', lambda m: m['variants'][0]['record'].update(reseal_variant(dict(
                m['variants'][0]['record'], descriptor=dict(m['variants'][0]['record']['descriptor'], replacement=100)))), 'HANDOFF_VARIANT_INVALID'),
            ('duplicate variant', lambda m: m['variants'].append(m['variants'][1]), 'HANDOFF_VARIANT_DUPLICATE'),
            ('reordered variants', lambda m: m['variants'].reverse(), 'HANDOFF_VARIANT_ORDER'),
            ('bad reference', lambda m: m['variants'][1].update(exporterPreparation=dict(scenarioCommitment='x')), 'HANDOFF_VARIANT_INVALID'),
            ('extra key', lambda m: m.update(signature='trusted'), 'HANDOFF_MANIFEST_SCHEMA'),
        ]
        for name, change, code in cases:
            offered = self.tamper(self.package, change)
            with self.subTest(name):
                self.refused(self.package, offered, code)
            restore()
        e = self.refused(self.package, self.tamper(self.package, cases[13][1]), 'HANDOFF_VARIANT_INVALID')
        self.assertEqual(e.details['cause'], 'LP_BPS_0_TO_99_REQUIRED')
        restore()
        self.assertEqual(self.receiver().import_session_handoff(self.package, expected_manifest_sha256=self.pin).id, self.s.id)


class Boundaries(HandoffTest):
    def test_import_and_preparation_start_nothing_and_claim_nothing(self):
        _, ids, result = self.exported()
        home = self.root / 'receiver'
        with NoNativeNoNetwork() as guard:
            session = self.receiver().import_session_handoff(self.root / 'package', expected_manifest_sha256=result['manifestSha256'])
            for v in session.variants():
                session.prepare_variant(v['variantId'])
            view = session.inspect()
        self.assertEqual(guard.launched, [])
        for name in ('consents', 'runs', 'scenarios/consents', 'scenarios/runs', 'scenarios/execution-attempts'):
            self.assertFalse((home / name).exists() and any((home / name).iterdir()), name)
        self.assertEqual((view['nativeExecutions'], view['networkRequests']), (0, 0))
        self.assertEqual(view['checkpointTrust']['canonicality'], 'NOT_ESTABLISHED_REQUIRES_AN_INDEPENDENTLY_TRUSTED_BLOCK_HASH')
        self.assertEqual(view['limitations'], core.LIMITATIONS)
        for v in view['variants']:
            self.assertEqual((v['status'], v['execution'], v['dynamicCoverage']), ('PREPARED_NOT_EXECUTED', 'NOT_PERFORMED', 'UNKNOWN'))
        self.assertEqual(session.compare_verified()['status'], 'NO_VERIFIED_VARIANTS')

    def test_verification_records_and_lp50_assurance_are_not_transferred(self):
        s = self.session()[0]
        v50 = s.add_variant({'lpBps': 50})['variantId']; v0 = s.add_variant({'lpBps': 0})['variantId']
        s.prepare_variant(v50); s.prepare_variant(v0)
        run = self.root / 'run'
        spec = load(s.directory / 'variants' / v50 / 'prepared/SCENARIO.json', 8 << 20)
        (run / 'inputs').mkdir(parents=True)
        (run / 'inputs/SCENARIO.json').write_bytes(canonical(spec) + b'\n')
        sha = hashlib.sha256((run / 'inputs/SCENARIO.json').read_bytes()).hexdigest()
        op = digest(b'test-only operation')
        (run / 'BINDING.json').write_bytes(canonical(dict(profile='nitro-hookr-scenario/0.1', scenarioSha256=sha, operationCommitment=op)))
        (run / 'RESULT.json').write_bytes(canonical(dict(status='SCENARIO_COMPLETED', operationCommitment=op, scenarioCommitment=spec['scenarioCommitment'])))
        backend = lambda _: dict(status='VERIFIED_SCENARIO_COMPARISON', scenarioCommitment=spec['scenarioCommitment'],
                                 worlds=[dict(world='SCENARIO_BASELINE', receiptStatus=1, gasUsed=1, actorTargetTokenTransferNetBaseUnits='1000'),
                                         dict(world='SCENARIO_VARIANT', receiptStatus=1, gasUsed=1, actorTargetTokenTransferNetBaseUnits='1010')],
                                 targetTokenTransferNetDeltaBaseUnits='10')
        self.assertEqual(s.verify_selected(v50, run, test_only_backend=backend)['status'], 'TEST_ONLY_BINDING_CHECKED')
        result = s.export_handoff(self.root / 'package', include_source=True)
        raw = (self.root / 'package/HANDOFF.json').read_bytes()
        for word in (b'TEST_ONLY_BINDING_CHECKED', b'verificationCommitment', b'operationCommitment'):
            self.assertNotIn(word, raw)
        imported = self.receiver().import_session_handoff(self.root / 'package', expected_manifest_sha256=result['manifestSha256'])
        status = {v['variantId']: v for v in imported.variants()}
        for v in (v50, v0):
            self.assertEqual((status[v]['status'], status[v]['execution']), ('CONFIGURED', 'NOT_PERFORMED'))
            self.assertFalse((imported.directory / 'variants' / v / 'VERIFICATION.json').exists())
        self.assertEqual(imported.compare_verified()['status'], 'NO_VERIFIED_VARIANTS')

    def test_missing_node_never_becomes_covered(self):
        _, _, result = self.exported()
        session = self.receiver().import_session_handoff(self.root / 'package', expected_manifest_sha256=result['manifestSha256'])
        with patch.object(hookr.shutil, 'which', return_value=None):
            report = session.coverage()
        self.assertEqual((report['status'], report['code']), ('NOT_EVALUATED', 'NODE_NOT_FOUND'))
        self.assertFalse((session.directory / 'COVERAGE.json').exists())
        self.assertEqual({v['staticCoverage'] for v in session.variants()}, {'NOT_EVALUATED'})


@COVERAGE
class ImportedCoverage(HandoffTest):
    def test_static_coverage_is_recomputed_never_transferred(self):
        for mode, status in [('complete', 'STATIC_DEPENDENCIES_COVERED'), ('unknown-sibling', 'STATIC_DEPENDENCIES_MISSING')]:
            value, _ = hash_linked_fixture(mode)
            s, _, _ = self.session(value, name=mode)
            s.add_variant({'lpBps': 50}); s.add_variant({'lpBps': 0})
            exported = s.coverage()
            result = s.export_handoff(self.root / f'{mode}-package', include_source=True)
            imported = self.receiver(f'{mode}-receiver').import_session_handoff(self.root / f'{mode}-package',
                                                                               expected_manifest_sha256=result['manifestSha256'])
            self.assertFalse((imported.directory / 'COVERAGE.json').exists())
            self.assertEqual({v['staticCoverage'] for v in imported.variants()}, {'NOT_EVALUATED'})
            with NoNativeNoNetwork():
                report = imported.coverage()
            self.assertEqual(report, exported)
            self.assertEqual(report['status'], status, mode)
            self.assertEqual(report['networkRequestsPerformed'], 0)
            if status == 'STATIC_DEPENDENCIES_MISSING':
                self.assertTrue(all(v['nextRequirement'].startswith('NEEDS_AUTHENTICATED_STATE') for v in imported.variants()))
            else:
                self.assertEqual(report['preconditions']['status'], 'SATISFIED')


class CleanRoomInstallation(HandoffTest):
    def install(self):
        prefix = self.root / 'installed'
        p = subprocess.run([sys.executable, '-B', str(SDK / 'install_cases.py'), '--prefix', str(prefix)], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((prefix / 'lib/rhook_alpha/session/handoff.py').is_file())
        self.assertFalse((prefix / 'lib/engine/adapters/hookr-case/node_modules').exists())
        return prefix

    def test_installed_sdk_imports_reopens_and_prepares_without_the_source_tree(self):
        prefix = self.install()
        s, ids, result = self.exported()
        expected = {lp: s.prepare_variant(v)['scenarioCommitment'] for lp, v in ids.items()}
        home = self.root / 'installed-home'
        code, view = self.cli(home, 'session-handoff-inspect', '--package', str(self.root / 'package'),
                              '--manifest-sha256', result['manifestSha256'], prefix=prefix)
        self.assertEqual((code, view['status']), (0, 'HANDOFF_AUTHENTICATED'))
        code, report = self.cli(home, 'session-handoff-import', '--package', str(self.root / 'package'),
                                '--manifest-sha256', result['manifestSha256'], '--prepare', prefix=prefix)
        self.assertEqual((code, report['status'], report['sessionId']), (0, 'SESSION_HANDOFF_IMPORTED', s.id))
        self.assertEqual({r['descriptor']['replacement']: r['localPreparation']['scenarioCommitment'] for r in report['variants']}, expected)
        code, inspected = self.cli(home, 'session-inspect', '--session', s.id, prefix=prefix)
        self.assertEqual((code, inspected['checkpoint']), (0, s.header['checkpoint']))
        self.assertEqual({v['descriptor']['replacement']: v['variantId'] for v in inspected['variants']}, ids)
        self.assertEqual({v['status'] for v in inspected['variants']}, {'PREPARED_NOT_EXECUTED'})
        self.assertEqual(inspected['limitations'], core.LIMITATIONS)
        # The installation carries no adapter dependencies: coverage is not evaluated, never assumed.
        code, coverage = self.cli(home, 'session-coverage', '--session', s.id, prefix=prefix)
        self.assertEqual((code, coverage['status']), (1, 'NOT_EVALUATED'))
        self.assertIn(coverage['code'], {'RUNTIME_DEPENDENCIES_MISSING', 'NODE_NOT_FOUND'})
        self.assertFalse((home / 'scenarios/consents').exists())

    def test_example_runs_against_an_installed_sdk(self):
        prefix = self.install()
        work = self.root / 'example'
        r = subprocess.run([sys.executable, '-B', str(EXAMPLE), '--sdk-root', str(prefix / 'lib'), '--synthetic', '--work', str(work)],
                           capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr.decode()[-800:])
        out = json.loads(r.stdout)
        self.assertEqual(out['status'], 'HANDOFF_RECONSTRUCTED')
        self.assertEqual(out['sessionId']['exporter'], out['sessionId']['importer'])
        self.assertEqual(sorted(v['lpBps'] for v in out['variants']), [0, 50])
        for v in out['variants']:
            self.assertEqual(v['exporterScenarioCommitment'], v['importerScenarioCommitment'])
            self.assertEqual((v['status'], v['execution']), ('PREPARED_NOT_EXECUTED', 'NOT_PERFORMED'))
        self.assertEqual(out['staticCoverage']['status'], 'NOT_EVALUATED')
        self.assertIn(out['staticCoverage']['code'], {'RUNTIME_DEPENDENCIES_MISSING', 'NODE_NOT_FOUND'})
        self.assertEqual(out['assurance']['nativeExecution'], 'NOT_PERFORMED')
        self.assertNotIn(str(self.root), json.dumps({k: v for k, v in out.items() if k != 'checkpoint'}))


if __name__ == '__main__':
    unittest.main()
