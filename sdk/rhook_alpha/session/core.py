"""Counterfactual Session 0.1: one authenticated checkpoint, several declared variants.

This module is profile-neutral. It owns the session lifecycle, identities, append-only storage,
status model, verification admission and comparison admission. A profile adapter (see hookr.py)
owns source validation, interventions, preparation, coverage planning and economics.

Nothing here starts a native worker, opens RPC, observes host resources or consumes authority.
Every file is written once with exclusive create; nothing previously recorded is overwritten.
"""
import os
from pathlib import Path
import re
import secrets
import shutil
import sys

from developer.files import canonical, digest, load, no_links, save, sync

SCHEMA = 'rhook/counterfactual-session/0.1'
VARIANT_SCHEMA = SCHEMA + '/variant'
VERIFICATION_SCHEMA = SCHEMA + '/verification'
COVERAGE_RECORD_SCHEMA = SCHEMA + '/coverage'
MAX_VARIANTS = 8
SESSION_ID = re.compile('[0-9a-f]{64}')

# Boundaries that hold for every session until a separately authorized run says otherwise.
LIMITATIONS = dict(nativeReexecution='NOT_PERFORMED', heterogeneousAgreement='NOT_EVALUATED',
                   economicAssurance='UNRESOLVED', qualifiedClaims=0)
HEADER_KEYS = {'schema', 'sessionId', 'profile', 'adapter', 'checkpoint', 'checkpointTrust', 'source',
               'common', 'baseline', 'limits', 'limitations', 'headerCommitment'}
VARIANT_KEYS = {'schema', 'sessionId', 'variantId', 'descriptor', 'bindings', 'variantCommitment'}


class SessionError(ValueError):
    """Stable code and next step; never a fabricated outcome."""
    def __init__(self, code, next_step, details=None):
        self.code, self.next_step, self.details = code, next_step, details or {}
        super().__init__(code)

    def as_result(self):
        return dict(status='SESSION_STOP', causeCode=self.code, nextStep=self.next_step,
                    details=self.details, automaticRetry=False)


def check(ok, code, next_step, details=None):
    if not ok:
        raise SessionError(code, next_step, details)


def commit(domain, value):
    return digest(domain.encode() + b'\n' + canonical(value))


def _sealed(domain, body, key):
    value = dict(body)
    value[key] = commit(domain, body)
    return value


def _unseal(value, domain, key, keys, code):
    check(type(value) is dict and set(value) == keys, code, 'Restore the unchanged session file.')
    body = dict(value)
    pin = body.pop(key)
    check(pin == commit(domain, body), code, 'The session file no longer matches its own commitment.')
    return body


class CounterfactualSession:
    """A persistent, append-only set of counterfactual questions against one frozen checkpoint."""

    def __init__(self, directory, adapter, header):
        self.directory, self.adapter, self.header = directory, adapter, header

    # ----- creation and reopening ---------------------------------------------------------------

    @staticmethod
    def _root(home):
        return no_links(Path(home)) / 'sessions'

    @classmethod
    def _header(cls, adapter, info):
        body = dict(
            schema=SCHEMA, profile=adapter.profile, adapter=adapter.adapter_version,
            checkpoint=info['checkpoint'], checkpointTrust=info['checkpointTrust'],
            source=dict(sha256=info['sha256'], bytes=info['bytes'], scenarioCommitment=info['scenarioCommitment']),
            common=info['common'], baseline=info['baseline'], limits=dict(maxVariants=MAX_VARIANTS),
            limitations=dict(LIMITATIONS))
        body['sessionId'] = commit(SCHEMA, dict(profile=body['profile'], adapter=body['adapter'],
                                                checkpoint=body['checkpoint'], source=body['source'],
                                                common=body['common'], baseline=body['baseline']))
        return _sealed(SCHEMA, body, 'headerCommitment')

    @classmethod
    def create(cls, home, adapter, *, source, expected_sha256, checkpoint):
        """Pin one source, bind its checkpoint and write the session once. Idempotent per identity."""
        info = adapter.load_source(source, expected_sha256)
        declared = info['checkpoint']
        check(type(checkpoint) is dict and set(checkpoint) == set(declared), 'CHECKPOINT_FIELDS',
              'Supply chainId, blockNumber, blockHash and stateRoot.')
        differing = sorted(k for k in declared if checkpoint[k] != declared[k])
        check(not differing, 'CHECKPOINT_MISMATCH',
              'A session never switches checkpoints. Use a source captured at the requested checkpoint.',
              {'differingFields': differing})
        header = cls._header(adapter, info)
        root = cls._root(home)
        final = root / header['sessionId']
        if final.exists():
            existing = cls.open(home, adapter, header['sessionId'])
            check(existing.header == header, 'SESSION_IDENTITY_COLLISION', 'Inspect the existing session directory.')
            return existing
        # The SDK home stays private (0700), as CaseSDK requires before it writes any plan.
        check(root.parent.parent.is_dir(), 'SDK_HOME_PARENT_MISSING', 'Create the parent directory of the SDK home first.')
        root.parent.mkdir(mode=0o700, exist_ok=True)
        root.mkdir(mode=0o700, exist_ok=True)
        staging = root / ('.staging-' + secrets.token_hex(8))
        staging.mkdir(mode=0o700)
        try:
            (staging / 'source').mkdir(mode=0o700)
            target = staging / 'source' / adapter.source_name
            with target.open('xb') as f:
                f.write(info['raw']); f.flush(); os.fsync(f.fileno())
            target.chmod(0o400)
            (staging / 'variants').mkdir(mode=0o700)
            save(staging / 'SESSION.json', header)
            sync(staging)
            os.rename(staging, final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            # A concurrent creator of the same identity won the rename; reopen its session below.
            if not (isinstance(sys.exc_info()[1], OSError) and (final / 'SESSION.json').is_file()):
                raise
        sync(root)
        return cls.open(home, adapter, header['sessionId'])

    @classmethod
    def open(cls, home, adapter, session_id):
        """Reopen offline, re-deriving every identity from the retained source; drift is an error."""
        check(type(session_id) is str and SESSION_ID.fullmatch(session_id), 'SESSION_ID', 'Use a 64-hex session id.')
        directory = no_links(cls._root(home) / session_id)
        check((directory / 'SESSION.json').is_file(), 'SESSION_MISSING_OR_INCOMPLETE',
              'Create the session again; an interrupted creation leaves no usable session.')
        try:
            stored = load(directory / 'SESSION.json', 1 << 20)
        except (OSError, ValueError) as error:
            raise SessionError('SESSION_MANIFEST_DRIFT', 'Restore the unchanged SESSION.json.', {'error': str(error)[:300]}) from error
        _unseal(stored, SCHEMA, 'headerCommitment', HEADER_KEYS, 'SESSION_MANIFEST_DRIFT')
        source = directory / 'source' / adapter.source_name
        check(stored.get('profile') == adapter.profile, 'WRONG_PROFILE', 'Open this session with its own profile adapter.')
        info = adapter.load_source(source, stored['source']['sha256'])
        fresh = cls._header(adapter, info)
        check(fresh == stored and fresh['sessionId'] == session_id, 'SESSION_MANIFEST_DRIFT',
              'The manifest no longer matches its retained source; it was edited or the source changed.')
        return cls(directory, adapter, stored)

    # ----- variants -----------------------------------------------------------------------------

    @property
    def id(self):
        return self.header['sessionId']

    @property
    def source_path(self):
        return self.directory / 'source' / self.adapter.source_name

    def _variant_record(self, descriptor):
        body = dict(schema=VARIANT_SCHEMA, sessionId=self.id, descriptor=descriptor,
                    bindings=dict(checkpoint=self.header['checkpoint'], source=self.header['source'],
                                  common=self.header['common'], baseline=self.header['baseline']))
        body['variantId'] = commit(VARIANT_SCHEMA, dict(sessionId=self.id, descriptor=descriptor))
        return _sealed(VARIANT_SCHEMA, body, 'variantCommitment')

    def add_variant(self, parameters):
        """Register one declared question. The same parameters always give the same variant id."""
        descriptor = self.adapter.variant_descriptor(parameters, self.header)
        record = self._variant_record(descriptor)
        directory = self.directory / 'variants' / record['variantId']
        if directory.exists():
            self._load_variant(record['variantId'])
            return dict(self._variant_view(record), alreadyRegistered=True)
        check(len(self._variant_ids()) < MAX_VARIANTS, 'VARIANT_LIMIT',
              f'A session holds at most {MAX_VARIANTS} variants; open a second session for more.')
        directory.mkdir(mode=0o700)
        save(directory / 'VARIANT.json', record)
        return dict(self._variant_view(record), alreadyRegistered=False)

    def _variant_ids(self):
        root = self.directory / 'variants'
        return sorted(p.name for p in root.iterdir() if p.is_dir() and SESSION_ID.fullmatch(p.name))

    def _load_variant(self, variant_id):
        check(type(variant_id) is str and SESSION_ID.fullmatch(variant_id), 'VARIANT_ID', 'Use a 64-hex variant id.')
        path = no_links(self.directory / 'variants' / variant_id / 'VARIANT.json')
        check(path.is_file(), 'VARIANT_UNKNOWN', 'Register the variant in this session first.')
        stored = load(path, 1 << 20)
        body = _unseal(stored, VARIANT_SCHEMA, 'variantCommitment', VARIANT_KEYS, 'VARIANT_RECORD_DRIFT')
        descriptor = self.adapter.variant_descriptor(self.adapter.parameters(body['descriptor']), self.header)
        check(self._variant_record(descriptor) == stored and stored['variantId'] == variant_id,
              'VARIANT_RECORD_DRIFT', 'The variant no longer matches this session or its declared descriptor.')
        return stored

    def _variant_view(self, record):
        return dict(variantId=record['variantId'], descriptor=record['descriptor'])

    # ----- preparation, coverage, verification --------------------------------------------------

    def _prepared_dir(self, variant_id):
        return self.directory / 'variants' / variant_id / 'prepared'

    def prepare_variant(self, variant_id):
        """Produce the existing SDK's prepared input for one variant. No native work, no acquisition."""
        record = self._load_variant(variant_id)
        out = self._prepared_dir(variant_id)
        if out.exists():
            return dict(self._preparation(record), alreadyPrepared=True)
        result = self.adapter.prepare(self.source_path, self.header, record['descriptor'], out)
        return dict(self._preparation(record), alreadyPrepared=False, sdkResult=result)

    def _preparation(self, record):
        """Validated preparation summary, or None when the variant has not been prepared."""
        out = self._prepared_dir(record['variantId'])
        if not out.exists():
            return None
        summary = self.adapter.check_prepared(out, self.header, record['descriptor'], self.source_path)
        return dict(summary, preparedDirectory=str(out.relative_to(self.directory)))

    def coverage(self, *, node=None):
        """Check which declared original-state reads the retained witness answers, offline."""
        path = self.directory / 'COVERAGE.json'
        report = self.adapter.coverage(self.source_path, node=node)
        if report.get('status') in ('STATIC_DEPENDENCIES_COVERED', 'STATIC_DEPENDENCIES_MISSING', 'STOP'):
            record = _sealed(COVERAGE_RECORD_SCHEMA, dict(schema=COVERAGE_RECORD_SCHEMA, sessionId=self.id, report=report), 'coverageCommitment')
            if path.exists():
                check(load(path, 8 << 20) == record, 'COVERAGE_RECORD_DRIFT',
                      'Static coverage is deterministic for a retained source; restore the original record.')
            else:
                save(path, record)
        return report

    def _coverage(self):
        path = self.directory / 'COVERAGE.json'
        if not path.exists():
            return None
        stored = load(path, 8 << 20)
        body = _unseal(stored, COVERAGE_RECORD_SCHEMA, 'coverageCommitment',
                       {'schema', 'sessionId', 'report', 'coverageCommitment'}, 'COVERAGE_RECORD_DRIFT')
        check(body['sessionId'] == self.id, 'COVERAGE_RECORD_DRIFT', 'Restore this session\'s coverage record.')
        return body['report']

    def verify_selected(self, variant_id, run, *, test_only_backend=None):
        """Bind one completed run to its variant, then verify it with the profile's existing verifier.

        test_only_backend replaces the verifier in offline tests. Its records are labelled TEST_ONLY
        and can never become native verification.
        """
        record = self._load_variant(variant_id)
        preparation = self._preparation(record)
        check(preparation is not None, 'VARIANT_NOT_PREPARED', 'Prepare the variant, run it under separate consent, then verify.')
        binding = self.adapter.run_binding(run, self.header)
        if binding['scenarioCommitment'] != preparation['scenarioCommitment']:
            others = [v for v in self._variant_ids() if v != variant_id]
            for other in others:
                other_prep = self._preparation(self._load_variant(other))
                check(not (other_prep and other_prep['scenarioCommitment'] == binding['scenarioCommitment']),
                      'WRONG_VARIANT_RESULT', 'This run belongs to another variant of the session.', {'belongsTo': other})
            raise SessionError('RUN_NOT_BOUND_TO_VARIANT', 'Use the run produced from this variant\'s prepared input.')
        check(binding['scenarioSha256'] == preparation['scenarioSha256'], 'RUN_NOT_BOUND_TO_VARIANT',
              'The run input bytes differ from the prepared input.')
        path = self.directory / 'variants' / variant_id / 'VERIFICATION.json'
        if path.exists():
            existing = self._verification(variant_id)
            check(existing['run']['operationCommitment'] == binding['operationCommitment'], 'VARIANT_ALREADY_VERIFIED',
                  'A variant keeps its first verified run; register a new session for another attempt.')
            return existing
        if test_only_backend is None:
            outcome, backend = self.adapter.verify_run(run), 'EXISTING_PROFILE_VERIFIER'
            status = 'RECORDED_RUN_VERIFIED'
        else:
            outcome, backend = test_only_backend(run), 'TEST_ONLY_INJECTED_BACKEND'
            status = 'TEST_ONLY_BINDING_CHECKED'
        check(type(outcome) is dict, 'VERIFIER_RESULT_SHAPE', 'The verifier must return a result object.')
        body = dict(schema=VERIFICATION_SCHEMA, sessionId=self.id, variantId=variant_id, status=status, backend=backend,
                    run=dict(binding, runDirectory=None), comparison=self.adapter.comparison_view(outcome),
                    assurance=self.adapter.verified_assurance(test_only=test_only_backend is not None))
        stored = _sealed(VERIFICATION_SCHEMA, body, 'verificationCommitment')
        save(path, stored)
        return stored

    def _verification(self, variant_id):
        path = self.directory / 'variants' / variant_id / 'VERIFICATION.json'
        if not path.exists():
            return None
        stored = load(path, 4 << 20)
        body = _unseal(stored, VERIFICATION_SCHEMA, 'verificationCommitment',
                       {'schema', 'sessionId', 'variantId', 'status', 'backend', 'run', 'comparison', 'assurance', 'verificationCommitment'},
                       'VERIFICATION_RECORD_DRIFT')
        check(body['sessionId'] == self.id and body['variantId'] == variant_id, 'VERIFICATION_RECORD_DRIFT',
              'A verification record cannot move between sessions or variants.')
        production = body['status'] == 'RECORDED_RUN_VERIFIED'
        check(body['status'] in ('RECORDED_RUN_VERIFIED', 'TEST_ONLY_BINDING_CHECKED')
              and body['backend'] == ('EXISTING_PROFILE_VERIFIER' if production else 'TEST_ONLY_INJECTED_BACKEND')
              and body['assurance'] == self.adapter.verified_assurance(test_only=not production),
              'VERIFICATION_RECORD_DRIFT', 'Status, backend and assurance of a verification record must agree.')
        return stored

    def compare_verified(self):
        """Compare only verified variants of this session, carrying the weakest assurance label."""
        rows, labels = [], set()
        for variant_id in self._variant_ids():
            record = self._load_variant(variant_id)
            verification = self._verification(variant_id)
            if verification is None:
                continue
            preparation = self._preparation(record)
            check(preparation and verification['run']['scenarioCommitment'] == preparation['scenarioCommitment'],
                  'VERIFICATION_RECORD_DRIFT', 'The verified run no longer matches the prepared variant.')
            labels.add(verification['status'])
            rows.append(dict(variantId=variant_id, descriptor=record['descriptor'], status=verification['status'],
                             comparison=verification['comparison']))
        rows.sort(key=lambda r: self.adapter.sort_key(r['descriptor']))
        if not rows:
            status = 'NO_VERIFIED_VARIANTS'
        elif labels == {'RECORDED_RUN_VERIFIED'}:
            status = 'VERIFIED_VARIANTS_COMPARED'
        else:
            status = 'TEST_ONLY_COMPARISON_NOT_EVIDENCE'
        return dict(status=status, sessionId=self.id, checkpoint=self.header['checkpoint'], variants=rows,
                    economicAssurance='UNRESOLVED', qualifiedClaims=0,
                    meaning='Each row is one independent BASELINE/VARIANT pair from the same checkpoint and common action.')

    # ----- inspection and export ----------------------------------------------------------------

    def _variant_status(self, record, coverage):
        view = self._variant_view(record)
        try:
            preparation = self._preparation(record)
        except (SessionError, ValueError, OSError, KeyError, TypeError) as error:
            code = getattr(error, 'code', 'PREPARED_ARTIFACT_INVALID')
            return dict(view, status='STOP', causeCode=code, staticCoverage='NOT_EVALUATED',
                        dynamicCoverage='UNKNOWN', execution='NOT_PERFORMED',
                        nextRequirement='Inspect the prepared directory; it is incomplete or changed after preparation.')
        verification = self._verification(record['variantId'])
        static = 'NOT_EVALUATED' if coverage is None else {'STATIC_DEPENDENCIES_COVERED': 'COVERED',
                                                           'STATIC_DEPENDENCIES_MISSING': 'MISSING'}.get(coverage.get('status'), 'STOP')
        if verification is not None:
            status = verification['status']
        elif preparation is not None:
            status = 'PREPARED_NOT_EXECUTED'
        else:
            status = 'CONFIGURED'
        production = verification is not None and verification['status'] == 'RECORDED_RUN_VERIFIED'
        if static == 'MISSING':
            nxt = 'NEEDS_AUTHENTICATED_STATE: acquire the missing original-root reads under separate authorization.'
        elif static in ('NOT_EVALUATED', 'STOP'):
            nxt = 'Evaluate static coverage offline with coverage().'
        elif preparation is None:
            nxt = 'Prepare the variant offline with prepare_variant().'
        elif not production:
            nxt = 'A separately authorized native run of this exact prepared input is required.'
        else:
            nxt = 'Verified; compare with compare_verified().'
        return dict(view, status=status, staticCoverage=static,
                    dynamicCoverage='ESTABLISHED_FOR_THIS_EXACT_INPUT_BY_VERIFIED_RUN' if production else 'UNKNOWN',
                    execution='RECORDED_NATIVE_RUN' if production else 'NOT_PERFORMED',
                    preparation=None if preparation is None else {k: preparation[k] for k in ('scenarioCommitment', 'scenarioSha256', 'preparedDirectory')},
                    nextRequirement=nxt)

    def variants(self):
        coverage = self._coverage()
        records = [self._load_variant(v) for v in self._variant_ids()]
        records.sort(key=lambda r: self.adapter.sort_key(r['descriptor']))
        return [self._variant_status(r, coverage) for r in records]

    def inspect(self):
        coverage = self._coverage()
        return dict(status='SESSION_INSPECTED', sessionId=self.id, profile=self.header['profile'],
                    checkpoint=self.header['checkpoint'], checkpointTrust=self.header['checkpointTrust'],
                    source=self.header['source'], baseline=self.header['baseline'],
                    staticCoverage=None if coverage is None else dict(status=coverage.get('status'),
                                                                      unresolvedDependencies=coverage.get('unresolvedDependencies'),
                                                                      summary=coverage.get('summary'), seed=coverage.get('seed'),
                                                                      networkRequestsPerformed=coverage.get('networkRequestsPerformed')),
                    variants=self.variants(), limitations=self.header['limitations'],
                    nativeExecutions=0, networkRequests=0)

    def manifest(self):
        """Portable view: semantic identities and relative paths only, no machine-specific locations."""
        variants = []
        for status in self.variants():
            record = self._load_variant(status['variantId'])
            verification = self._verification(status['variantId'])
            variants.append(dict(record=record, status=status,
                                 verification=None if verification is None else {k: verification[k] for k in ('status', 'backend', 'run', 'verificationCommitment')}))
        coverage = self._coverage()
        return dict(schema=SCHEMA + '/export', header=self.header, variants=variants,
                    coverage=None if coverage is None else dict(status=coverage.get('status'), summary=coverage.get('summary'),
                                                                 dynamicClosure=coverage.get('dynamicClosure')))
