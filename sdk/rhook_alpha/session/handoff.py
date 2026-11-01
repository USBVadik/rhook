"""Session Handoff 0.1: move one Counterfactual Session between SDK installations, offline.

A package is data, not authorization. Export writes a versioned package; inspection and import
authenticate it against a manifest SHA-256 the receiver obtained separately, then rebuild an ordinary
session with the existing session API. Nothing here starts a native worker, opens RPC, requests host
admission, issues consent or turns a file hash into chain canonicality or execution evidence.

Package layout (no other entry is accepted):

    HANDOFF.json            manifest; its SHA-256 is the external pin
    source/SCENARIO.json    the pinned session source, only when exported with include_source=True
"""
import os
from pathlib import Path
import re
import secrets
import shutil
import stat

from developer.files import canonical, digest, no_links, strict, sync
from .core import (CounterfactualSession, LIMITATIONS, MAX_VARIANTS, SCHEMA, SESSION_ID, VARIANT_KEYS,
                   VARIANT_SCHEMA, HEADER_KEYS, SessionError, _unseal, check)

HANDOFF_SCHEMA = 'rhook/session-handoff/0.1'
MANIFEST = 'HANDOFF.json'
SOURCE = 'source/SCENARIO.json'
COMPLETE, METADATA = 'COMPLETE_LOCAL_HANDOFF', 'METADATA_ONLY'
LAYOUT = {COMPLETE: ({MANIFEST, SOURCE}, {'source'}), METADATA: ({MANIFEST}, set())}
MAX_MANIFEST_BYTES = 1 << 20
MAX_SOURCE_BYTES = 8 << 20
MAX_ENTRIES = 16
HEX64 = re.compile('[0-9a-f]{64}')
MANIFEST_KEYS = {'schema', 'mode', 'session', 'variants', 'files', 'sourceMaterial', 'capabilities', 'assurance', 'excluded'}
# What a handoff never carries, whatever the mode.
EXCLUDED = ['NATIVE_WORKER_AND_RUNTIME', 'PREPARED_DIRECTORIES', 'STATIC_COVERAGE_RECORD', 'VERIFICATION_RECORDS',
            'RUN_EVIDENCE', 'CONSENTS_AND_AUTHORITY', 'MACHINE_PATHS_AND_SDK_HOME']
NEXT_NATIVE = ('Running a prepared variant natively is the existing ExecutionSDK workflow and needs its own exact '
               'local consent; a handoff grants no authority.')


def policy(mode):
    """Source material, capabilities and assurance of a mode. A package must state exactly these."""
    complete = mode == COMPLETE
    capabilities = dict(
        reconstructSession=complete, prepareVariantsOffline=complete,
        staticCoverage=('RECOMPUTE_AFTER_IMPORT_REQUIRES_NODE_AND_PINNED_ADAPTER_DEPENDENCIES' if complete
                        else 'NOT_AVAILABLE_WITHOUT_SOURCE_MATERIAL'),
        nativeExecution='NOT_INCLUDED_REQUIRES_SEPARATE_AUTHORIZATION')
    assurance = dict(
        packageIntegrity='REQUIRES_EXTERNAL_MANIFEST_SHA256_PIN',
        producerIdentity='NOT_ESTABLISHED_NO_SIGNATURE',
        sourceIntegrity=('SOURCE_SHA256_AND_SCENARIO_COMMITMENT_CHECKED_ON_IMPORT' if complete
                         else 'NOT_AVAILABLE_SOURCE_MATERIAL_NOT_INCLUDED'),
        checkpointBinding=('SOURCE_DECLARES_THIS_CHECKPOINT_CHECKED_ON_IMPORT' if complete
                           else 'DECLARED_BY_MANIFEST_ONLY'),
        canonicality='NOT_ESTABLISHED_REQUIRES_AN_INDEPENDENTLY_TRUSTED_BLOCK_HASH',
        staticStateCoverage='NOT_TRANSFERRED_RECOMPUTE_LOCALLY',
        dynamicExecutionClosure='UNKNOWN', nativeExecution='NOT_PERFORMED',
        heterogeneousAgreement='NOT_EVALUATED', economicAssurance='UNRESOLVED', qualifiedClaims=0,
        exporterPreparation='REFERENCE_ONLY_RECONSTRUCT_LOCALLY_WITH_EXECUTIONSDK_PREPARE')
    material = 'INCLUDED_BY_EXPLICIT_OPT_IN' if complete else 'SOURCE_MATERIAL_NOT_INCLUDED'
    return material, capabilities, assurance


# ----- export -----------------------------------------------------------------------------------

def export(session, output, *, include_source=False):
    """Write one package for an open session into a new directory. Never overwrites anything."""
    check(type(include_source) is bool, 'HANDOFF_INCLUDE_SOURCE_FLAG',
          'Pass include_source=True to include the pinned source material, or False for metadata only.')
    info = session._retained_source()  # source pin re-checked, header re-derived
    entries = []
    for variant_id in session._variant_ids():
        record = session._load_variant(variant_id)
        preparation = session._preparation(record)  # a drifted or incomplete preparation stops the export
        session._verification(variant_id)            # so does a drifted verification record; none is exported
        entries.append(dict(record=record, exporterPreparation=None if preparation is None else dict(
            scenarioCommitment=preparation['scenarioCommitment'], scenarioSha256=preparation['scenarioSha256'])))
    entries.sort(key=lambda e: _order(session.adapter, e['record']))
    mode = COMPLETE if include_source else METADATA
    files = [dict(path=SOURCE, bytes=len(info['raw']), sha256=digest(info['raw']))] if include_source else []
    material, capabilities, assurance = policy(mode)
    manifest = dict(schema=HANDOFF_SCHEMA, mode=mode, session=session.header, variants=entries, files=files,
                    sourceMaterial=material, capabilities=capabilities, assurance=assurance, excluded=list(EXCLUDED))
    raw = canonical(manifest) + b'\n'
    check(len(raw) <= MAX_MANIFEST_BYTES, 'HANDOFF_MANIFEST_TOO_LARGE', 'The session has too many records for one package.')
    out = _path(output, 'HANDOFF_OUTPUT_PATH')
    check(out.parent.is_dir(), 'HANDOFF_OUTPUT_PARENT_MISSING', 'Create the parent directory of the export first.')
    check(not out.is_relative_to(session.directory.parent.parent), 'HANDOFF_OUTPUT_INSIDE_SDK_HOME',
          'Write the export outside the SDK home.')
    try:
        os.mkdir(out, 0o700)
    except FileExistsError as error:
        raise SessionError('HANDOFF_OUTPUT_EXISTS', 'Choose a new export directory; an export never overwrites.') from error
    try:
        if include_source:
            (out / 'source').mkdir(mode=0o700)
            _write(out / SOURCE, info['raw'])
            sync(out / 'source')
        _write(out / MANIFEST, raw)  # written last: a directory without it is not a package
        sync(out)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    sync(out.parent)
    return dict(status='SESSION_HANDOFF_EXPORTED', schema=HANDOFF_SCHEMA, mode=mode, sessionId=session.id,
                manifestSha256=digest(raw), files=sorted([MANIFEST] + [f['path'] for f in files]),
                sourceMaterial=material, variants=[e['record']['variantId'] for e in entries],
                nextStep='Send the package and, through a separate channel, its manifestSha256. The receiver imports '
                         'with that pin; the hash alone does not say who produced the package.'
                         + ('' if include_source else ' Without source material the package can be inspected, not imported.'))


def _write(path, raw):
    with path.open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    path.chmod(0o400)


# ----- authentication ---------------------------------------------------------------------------

def authenticate(home, package, expected_manifest_sha256):
    """Check one package completely without writing anything. Returns the validated parts.

    expected_manifest_sha256=None checks file hashes against an unauthenticated manifest; that result is
    reported as not pinned and can never be imported.
    """
    from . import adapter as profile_adapter
    pinned = expected_manifest_sha256 is not None
    check(not pinned or (type(expected_manifest_sha256) is str and HEX64.fullmatch(expected_manifest_sha256)),
          'HANDOFF_MANIFEST_PIN_FORMAT', 'Supply the manifest SHA-256 as 64 lowercase hex characters.')
    root = _path(package, 'HANDOFF_PACKAGE_PATH')
    try:
        info = os.lstat(root)
    except FileNotFoundError as error:
        raise SessionError('HANDOFF_PACKAGE_MISSING', 'Point at the package directory that contains HANDOFF.json.') from error
    check(stat.S_ISDIR(info.st_mode), 'HANDOFF_PACKAGE_PATH', 'A package is a directory, not a file or link.')
    files, dirs = _scan(root)
    check(MANIFEST in files, 'HANDOFF_FILE_SET', 'The package has no HANDOFF.json.', {'missing': [MANIFEST]})
    raw = _read(root / MANIFEST, MAX_MANIFEST_BYTES)
    actual = digest(raw)
    # The pin is checked before the manifest is interpreted at all.
    check(not pinned or actual == expected_manifest_sha256, 'HANDOFF_MANIFEST_PIN_MISMATCH',
          'The manifest is not the one you were told to expect. Do not replace the pin to make it pass.',
          {'manifestSha256': actual})
    try:
        manifest = strict(raw)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise SessionError('HANDOFF_MANIFEST_JSON', 'The manifest must be strict JSON without duplicate keys.',
                           {'error': str(error)[:200]}) from error
    check(type(manifest) is dict and set(manifest) == MANIFEST_KEYS and manifest['schema'] == HANDOFF_SCHEMA
          and manifest['mode'] in LAYOUT, 'HANDOFF_MANIFEST_SCHEMA', f'Only {HANDOFF_SCHEMA} packages are supported.')
    mode = manifest['mode']
    material, capabilities, assurance = policy(mode)
    check(manifest['sourceMaterial'] == material and manifest['capabilities'] == capabilities
          and manifest['assurance'] == assurance and manifest['excluded'] == EXCLUDED, 'HANDOFF_MANIFEST_CLAIMS',
          'A package states exactly the capabilities and assurance of its mode; nothing more is accepted.')
    want_files, want_dirs = LAYOUT[mode]
    check(files == want_files and dirs == want_dirs, 'HANDOFF_FILE_SET', 'The package must contain exactly its declared files.',
          {'missing': sorted((want_files | want_dirs) - (files | dirs)), 'unexpected': sorted((files | dirs) - (want_files | want_dirs))})
    header = manifest['session']
    _unseal(header, SCHEMA, 'headerCommitment', HEADER_KEYS, 'HANDOFF_SESSION_INVALID')
    source = header['source']
    check(header['schema'] == SCHEMA and type(header['profile']) is str and type(header['sessionId']) is str
          and SESSION_ID.fullmatch(header['sessionId']) and header['sessionId'] == CounterfactualSession._session_id(header)
          and header['limitations'] == LIMITATIONS and header['limits'] == dict(maxVariants=MAX_VARIANTS)
          and type(source) is dict and set(source) == {'sha256', 'bytes', 'scenarioCommitment'}
          and type(source['sha256']) is str and HEX64.fullmatch(source['sha256'])
          and type(source['bytes']) is int and 0 < source['bytes'] <= MAX_SOURCE_BYTES,
          'HANDOFF_SESSION_INVALID', 'The session header does not derive its own id, names no valid source pin or claims other limits.')
    adapter = profile_adapter(home, header['profile'])
    check(header['adapter'] == adapter.adapter_version, 'HANDOFF_ADAPTER_VERSION',
          'The package was written by another adapter version.', {'package': header['adapter'], 'installed': adapter.adapter_version})
    expected_files = [dict(path=SOURCE, bytes=source['bytes'], sha256=source['sha256'])] if mode == COMPLETE else []
    check(manifest['files'] == expected_files, 'HANDOFF_MANIFEST_FILES', 'The file list must name exactly the pinned session source.')
    content = None
    if mode == COMPLETE:
        content = _read(root / SOURCE, MAX_SOURCE_BYTES)
        check(len(content) == source['bytes'] and digest(content) == source['sha256'], 'HANDOFF_FILE_HASH_MISMATCH',
              'source/SCENARIO.json differs from the pinned session source.')
        # The existing source validation, against the same pin; a different checkpoint or commitment cannot pass.
        # It reads the file again, so it sees either these exact bytes or fails on the pin. Import uses `content`.
        try:
            fresh = CounterfactualSession._header(adapter, adapter.load_source(root / SOURCE, source['sha256']))
        except SessionError as error:
            raise SessionError('HANDOFF_SOURCE_INVALID', 'The included source is not a valid source for this session.',
                               {'cause': error.code}) from error
        check(fresh == header, 'HANDOFF_SESSION_MISMATCH',
              'The included source does not derive the declared session: checkpoint, commitment or bindings differ.')
    records = _variants(adapter, header, manifest['variants'])
    return dict(root=root, manifest=manifest, manifestSha256=actual, pinned=pinned, mode=mode, header=header,
                adapter=adapter, records=records, content=content)


def _variants(adapter, header, entries):
    check(type(entries) is list and len(entries) <= MAX_VARIANTS, 'HANDOFF_VARIANT_INVALID',
          f'A package holds a list of at most {MAX_VARIANTS} variants.')
    probe = CounterfactualSession(None, adapter, header)
    records, seen = [], set()
    for entry in entries:
        check(type(entry) is dict and set(entry) == {'record', 'exporterPreparation'}, 'HANDOFF_VARIANT_INVALID',
              'Each variant entry has a record and an exporterPreparation reference.')
        record = entry['record']
        body = _unseal(record, VARIANT_SCHEMA, 'variantCommitment', VARIANT_KEYS, 'HANDOFF_VARIANT_INVALID')
        try:
            descriptor = adapter.variant_descriptor(adapter.parameters(body['descriptor']), header)
        except SessionError as error:
            raise SessionError('HANDOFF_VARIANT_INVALID', 'A declared variant is not supported by this profile.',
                               {'cause': error.code}) from error
        except (KeyError, TypeError) as error:
            raise SessionError('HANDOFF_VARIANT_INVALID', 'A variant descriptor is incomplete.') from error
        check(probe._variant_record(descriptor) == record, 'HANDOFF_VARIANT_INVALID',
              'A variant record does not derive from this session and its declared descriptor.', {'variantId': record.get('variantId')})
        check(record['variantId'] not in seen, 'HANDOFF_VARIANT_DUPLICATE', 'Each variant appears once.')
        seen.add(record['variantId'])
        reference = entry['exporterPreparation']
        check(reference is None or (type(reference) is dict and set(reference) == {'scenarioCommitment', 'scenarioSha256'}
                                    and all(type(v) is str and HEX64.fullmatch(v) for v in reference.values())),
              'HANDOFF_VARIANT_INVALID', 'An exporter preparation reference names a commitment and a SHA-256.')
        records.append(record)
    check([_order(adapter, r) for r in records] == sorted(_order(adapter, r) for r in records), 'HANDOFF_VARIANT_ORDER',
          'Variants are listed in their canonical order; a reordered list is a different package.')
    return records


def _order(adapter, record):
    return (adapter.sort_key(record['descriptor']), record['variantId'])


# ----- inspection and import --------------------------------------------------------------------

def inspect(home, package, expected_manifest_sha256=None):
    """Read-only report on a package. Only a pinned package counts as authenticated."""
    parts = authenticate(home, package, expected_manifest_sha256)
    m, header = parts['manifest'], parts['header']
    return dict(status='HANDOFF_AUTHENTICATED' if parts['pinned'] else 'HANDOFF_NOT_PINNED',
                packageIntegrity=('MATCHES_EXTERNAL_MANIFEST_PIN' if parts['pinned']
                                  else 'FILES_MATCH_AN_UNPINNED_MANIFEST_NOT_AUTHENTICATED'),
                manifestSha256=parts['manifestSha256'], mode=parts['mode'], sourceMaterial=m['sourceMaterial'],
                sessionId=header['sessionId'], profile=header['profile'], checkpoint=header['checkpoint'],
                checkpointTrust=header['checkpointTrust'], source=header['source'], baseline=header['baseline'],
                variants=[dict(variantId=e['record']['variantId'], descriptor=e['record']['descriptor'],
                               exporterPreparation=e['exporterPreparation']) for e in m['variants']],
                capabilities=m['capabilities'], assurance=m['assurance'], excluded=m['excluded'],
                nextStep=('Import with the same pin.' if parts['pinned'] and parts['mode'] == COMPLETE else
                          'Obtain the manifest SHA-256 through a separate channel and inspect again with it.'
                          if not parts['pinned'] else 'Metadata only: review it; importing needs the source material.'))


def import_package(home, package, expected_manifest_sha256, *, prepare=False):
    """Authenticate a complete package and rebuild its session in this home. Returns (session, report).

    A new session appears in one rename, with all its variants, or not at all. An existing identical
    session is reused and gains only missing variants; conflicting records stop the import.
    """
    check(type(expected_manifest_sha256) is str, 'HANDOFF_MANIFEST_PIN_REQUIRED',
          'Import requires the manifest SHA-256 you obtained separately from the package.')
    check(type(prepare) is bool, 'HANDOFF_PREPARE_FLAG', 'Pass prepare=True or False.')
    parts = authenticate(home, package, expected_manifest_sha256)
    check(parts['mode'] == COMPLETE, 'HANDOFF_SOURCE_NOT_INCLUDED',
          'This metadata-only package can be inspected but not imported: it carries no source material. '
          'Ask for a package exported with include_source=True.')
    adapter, header, records = parts['adapter'], parts['header'], parts['records']
    root = CounterfactualSession._root(home)
    final = root / header['sessionId']
    reused = final.exists()
    if not reused:
        # Built from the authenticated bytes; the package file is not opened again.
        _stage_and_place(root, final, adapter, parts['content'], header, records)
    session = CounterfactualSession.open(home, adapter, header['sessionId'])
    check(session.header == header, 'HANDOFF_SESSION_CONFLICT', 'An existing session with this id differs; nothing was changed.')
    existing = set(session._variant_ids())
    check(len(existing | {r['variantId'] for r in records}) <= MAX_VARIANTS, 'VARIANT_LIMIT',
          f'The existing session plus this package would exceed {MAX_VARIANTS} variants; nothing was added.')
    # Every stored counterpart is checked before the first missing variant is added, so a conflict on
    # any record, including the last, leaves the existing session exactly as it was.
    for record in records:
        if record['variantId'] in existing:
            # A changed or incomplete stored record raises VARIANT_RECORD_DRIFT or VARIANT_UNKNOWN here.
            check(session._load_variant(record['variantId']) == record, 'HANDOFF_VARIANT_CONFLICT',
                  'A stored variant differs from the package; nothing was added.')
    for record in records:
        if record['variantId'] not in existing:
            added = session.add_variant(adapter.parameters(record['descriptor']))
            check(added['variantId'] == record['variantId'] and session._load_variant(record['variantId']) == record,
                  'HANDOFF_VARIANT_CONFLICT', 'A stored variant differs from the package.')
    rows = []
    references = {e['record']['variantId']: e['exporterPreparation'] for e in parts['manifest']['variants']}
    for record in records:
        reference = references[record['variantId']]
        # The exporter's reference is only reported; it is never stored in the session or treated as checked.
        row = dict(variantId=record['variantId'], descriptor=record['descriptor'], exporterPreparation=reference,
                   reconstruction='NOT_REQUESTED')
        if prepare:
            local = session.prepare_variant(record['variantId'])
            row['localPreparation'] = dict(scenarioCommitment=local['scenarioCommitment'], scenarioSha256=local['scenarioSha256'])
            row['reconstruction'] = ('NO_EXPORTER_REFERENCE' if reference is None else 'MATCHES_EXPORTER_REFERENCE'
                                     if reference == row['localPreparation'] else 'DIFFERS_FROM_EXPORTER_REFERENCE')
        rows.append(row)
    differing = [r for r in rows if r['reconstruction'] == 'DIFFERS_FROM_EXPORTER_REFERENCE']
    # An authentic package can still carry a wrong preparation reference: the pin covers the bytes, not the
    # exporter's claim. A mismatch is a stop for every caller, Python API and CLI alike.
    check(not differing, 'HANDOFF_PREPARED_RECONSTRUCTION_MISMATCH',
          'The package is authentic, but a variant prepared here from its authenticated source differs from the '
          "exporter's recorded preparation. Do not rely on the exporter's reference. The session stays imported with "
          'the local preparation; ask the exporter to re-export, or check that both installations run the same SDK.',
          dict(sessionId=session.id, manifestSha256=parts['manifestSha256'], sessionImported=True,
               localPreparationRetained=True,
               variants=[{k: r[k] for k in ('variantId', 'descriptor', 'exporterPreparation', 'localPreparation')}
                         for r in differing]))
    report = dict(status='SESSION_HANDOFF_IMPORTED', packageIntegrity='MATCHES_EXTERNAL_MANIFEST_PIN',
                  manifestSha256=parts['manifestSha256'], mode=COMPLETE, sessionId=session.id,
                  existingSessionReused=reused, checkpoint=header['checkpoint'], checkpointTrust=header['checkpointTrust'],
                  source=header['source'], variants=rows,
                  preparedReconstruction='LOCALLY_PREPARED' if prepare else 'NOT_REQUESTED',
                  assurance=parts['manifest']['assurance'], importedRecords=dict(verifications=0, preparedDirectories=0),
                  nativeExecutions=0, networkRequests=0,
                  nextStep=('Evaluate static coverage with session-coverage (needs Node.js and the pinned adapter '
                            'dependencies), then prepare variants. ' if not prepare else 'Evaluate static coverage with '
                            'session-coverage. ') + NEXT_NATIVE)
    return session, report


def _stage_and_place(root, final, adapter, content, header, records):
    """Build the complete session in a private staging home, then move it into place in one rename.

    content: the source bytes authenticate() checked. They are written into the private staging
    directory first, so the session is created from them rather than from the package.
    """
    check(root.parent.parent.is_dir(), 'SDK_HOME_PARENT_MISSING', 'Create the parent directory of the SDK home first.')
    root.parent.mkdir(mode=0o700, exist_ok=True)
    root.mkdir(mode=0o700, exist_ok=True)
    staging = root / ('.handoff-import-' + secrets.token_hex(8))  # never a valid session id, never openable
    staging.mkdir(mode=0o700)
    try:
        incoming = staging / 'incoming-SCENARIO.json'
        _write(incoming, content)
        staged = CounterfactualSession.create(staging, adapter, source=incoming, expected_sha256=header['source']['sha256'],
                                              checkpoint=header['checkpoint'])
        check(staged.header == header, 'HANDOFF_SESSION_MISMATCH', 'The rebuilt session differs from the package.')
        for record in records:
            check(staged.add_variant(adapter.parameters(record['descriptor']))['variantId'] == record['variantId'],
                  'HANDOFF_VARIANT_CONFLICT', 'A rebuilt variant differs from the package.')
        sync(staged.directory / 'variants')
        os.rename(staged.directory, final)
    except OSError:
        # Another importer placed the same session first; the caller reopens and completes it.
        if not (final / 'SESSION.json').is_file():
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    sync(root)


# ----- small hardened file helpers --------------------------------------------------------------

def _path(value, code):
    try:
        return no_links(Path(value))
    except (ValueError, TypeError) as error:
        raise SessionError(code, 'Use a plain path without symlinks or "..".') from error


def _scan(root):
    """Every entry below root, without following links. Hardlinked, linked and special files are refused."""
    files, dirs, pending = set(), set(), [(root, '')]
    while pending:
        directory, prefix = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                name = prefix + entry.name
                check(len(files) + len(dirs) < MAX_ENTRIES, 'HANDOFF_FILE_SET', 'The package has too many entries.')
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise SessionError('HANDOFF_SYMLINK', 'A package contains no symbolic links.', {'path': name})
                if stat.S_ISDIR(info.st_mode):
                    dirs.add(name)
                    pending.append((entry.path, name + '/'))
                elif stat.S_ISREG(info.st_mode):
                    check(info.st_nlink == 1, 'HANDOFF_HARDLINK', 'A package file must not be hard-linked elsewhere.', {'path': name})
                    files.add(name)
                else:
                    raise SessionError('HANDOFF_FILE_TYPE', 'A package contains only regular files and directories.', {'path': name})
    return files, dirs


def _read(path, limit):
    """Read one package file: no link following, regular, single link, bounded."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise SessionError('HANDOFF_FILE_TYPE', 'A package file must be a readable regular file.', {'error': type(error).__name__}) from error
    try:
        info = os.fstat(fd)
        check(stat.S_ISREG(info.st_mode), 'HANDOFF_FILE_TYPE', 'A package file must be a regular file.')
        check(info.st_nlink == 1, 'HANDOFF_HARDLINK', 'A package file must not be hard-linked elsewhere.')
        check(info.st_size <= limit, 'HANDOFF_FILE_SIZE', 'A package file exceeds its size limit.')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        check(len(raw) <= limit, 'HANDOFF_FILE_SIZE', 'A package file exceeds its size limit.')
        return raw
    finally:
        os.close(fd)
