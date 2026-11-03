"""Descriptor-driven profile-overlay inputs and their owner-gated native workflow (SDK 0.6, nitro-hook-profile-overlay/0.1).

Preparation (offline) from a retained, SHA-pinned SDK 0.4 source input (rhook/hookr-scenario/0.1: checkpoint,
witness, signed buy, environment) prepares one profile-overlay input for the reviewed engine identity:

1. the accepted descriptor and catalogue, exactly those the reviewed engine embeds (PROFILE_ENGINE_RECORD);
2. the canonical intervention set, every kind reviewed for NATIVE_EXECUTION (Tuning is refused here);
3. static coverage of the retained source (trie paths and profile preconditions; Node, offline);
4. independent trie-only authentication of every declared contract and target word (Node, offline);
5. the prepared input bound to the descriptor SHA-256 and the reviewed engine identity, then the data checks the
   scenario API applies before any worker is called. Checkpoint, witness, signed action, environment and limits
   stay byte-equal to the source.

It writes SCENARIO.json, SDK_RESULT.json and PREPARATION.json into a fresh directory and a plan into the SDK home.
It runs no worker, EVM, network or authority.

The native workflow (ProfileOverlayExecutionSDK) uses the unchanged ExecutionSDK operation/run/verify path with
host admission v4. A run needs, in this order: a READY doctor, the exact operation commitment, and the owner's
authorization record of that one operation (cases.scenario.api.authorize_profile) with at least 15 minutes left.
The attempt marker is opened by the child run() under the operation lock right after its authoritative
authorization check, so an authorization refusal consumes nothing; from the marker on, the operation is closed
whatever happens. One run per operation, never retried.
"""
import copy
from pathlib import Path
import re
import shutil
from developer.files import canonical, digest, load, no_links, save, sha, sync
from . import profile_descriptor as pd
from .execution import ExecutionError, ExecutionSDK, check, _input, _profile, _validate_spec

SCHEMA = 'rhook/hookr-profile-overlay/0.1/prepared'
HOST_PROFILE = 'macos-host-admission-v4'
FIXED_INPUTS = ('checkpoint', 'parent', 'chainConfig', 'inventory', 'commonSetup', 'actions', 'environment', 'limits', 'poolId',
                'releaseManifestSha256')
RUN_SCHEMA = 'rhook/hookr-profile-overlay/0.1/run'


def _descriptor_error(error):
    return ExecutionError(error.code, 'Use the reviewed descriptor, catalogue and engine identity unchanged; nothing was consumed.',
                          dict(detail=str(error)[:400]))


def _gate(call):
    """Run an authorization step; a refusal keeps its stable code. Nothing is consumed by a refusal."""
    try:
        return call()
    except pd.DescriptorError as error:
        raise _descriptor_error(error) from error
    except ValueError as error:
        if isinstance(error, ExecutionError):
            raise
        code = str(error).split(':')[0]
        if re.fullmatch('[A-Z][A-Z0-9_]+', code) is None:
            raise
        details = dict(detail=str(error)[:400])
        if type(getattr(error, 'report', None)) is dict:
            details['report'] = error.report
        raise ExecutionError(code, 'Nothing was consumed. Review the exact operation and the owner authorization record.', details) from error


def static_coverage(home, raw, *, node=None):
    """Static coverage of the retained source bytes (the same SDK 0.4 helper the session uses); offline."""
    from .session.hookr import HookrScenarioAdapter
    report = HookrScenarioAdapter(home).coverage(raw, node=node)
    pre = report.get('preconditions') if type(report) is dict else None
    check(report.get('status') == 'STATIC_DEPENDENCIES_COVERED' and type(pre) is dict and pre.get('status') == 'SATISFIED',
          'PROFILE_STATIC_COVERAGE_REQUIRED', 'The retained source must be statically covered with satisfied profile preconditions; '
          'nothing was prepared.', dict(status=report.get('status'), code=report.get('code'),
                                         preconditions=pre.get('status') if type(pre) is dict else None))
    return report


def prepare(sdk, witness, *, expected_sha256, interventions, output, node=None, descriptor='hookr-1'):
    from .cases.scenario import api
    raw_input, original = _input(no_links(witness), expected_sha256)
    _validate_spec(original, _profile())
    try:
        d, raw, entry = pd.load_accepted(descriptor, 'NATIVE_EXECUTION')
        pd.validate_worker_bounds(d)
        record = pd.require_engine_record(raw)
        engine = pd.require_engine_for_native()
        canon = pd.canonical_interventions(d, interventions)
        check(canon == interventions, 'PROFILE_CANONICAL_SET_REQUIRED', 'Pass the canonical intervention set (pd.canonical_interventions).')
        pd.require_kind_review(entry, canon, 'NATIVE_EXECUTION')
    except pd.DescriptorError as error:
        raise _descriptor_error(error) from error
    out = no_links(output)
    check(not out.exists(), 'FRESH_PREPARED_OUTPUT_REQUIRED', 'Choose a fresh prepared directory.')
    # One Node binary for both offline checks: the explicit one, else the one on PATH.
    program = node if node is not None else shutil.which('node')
    check(program is not None and Path(program).is_file(), 'PROFILE_NODE_REQUIRED',
          'Install Node.js or pass --node; static coverage and target authentication need it. Nothing was prepared.')
    coverage = static_coverage(sdk.home, raw_input, node=program)
    try:
        targets = pd.authenticate_targets(original, raw, node=program)
        spec = pd.build_spec(original, raw, canon, engine)
        pd.validate_input(spec, raw)
    except pd.DescriptorError as error:
        raise _descriptor_error(error) from error
    check({k: spec[k] for k in FIXED_INPUTS} == {k: original[k] for k in FIXED_INPUTS}, 'PROFILE_FIXED_INPUTS',
          'The checkpoint, witness, signed action, environment and limits must stay those of the retained source.')
    plan = api.configure(sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor=d['profileId'], interventions=canon)
    out.mkdir(mode=0o700, parents=True)
    sync(out.parent)
    save(out / 'SCENARIO.json', spec)
    save(out / 'SDK_RESULT.json', dict(status='PREPARED_SCENARIO_INPUT', authentication='PENDING_NATIVE_ADMISSION', nativeExecutions=0, cleanupConfirmed=True,
                                       planId=plan['planId'], planCommitment=plan['planCommitment'], scenarioSha256=sha(out / 'SCENARIO.json'),
                                       scenarioCommitment=spec['scenarioCommitment']))
    api._input(sdk, out)
    o = spec['profileOverlay']
    summary = dict(status=coverage['status'], preconditions=coverage['preconditions']['status'],
                   networkRequestsPerformed=coverage.get('networkRequestsPerformed'), profile=coverage.get('profile'),
                   reportSha256=digest(canonical(coverage)))
    result = dict(schema=SCHEMA, status='EXECUTION_CANDIDATE_PREPARED', profile=api.PROFILE_OVERLAY_PROFILE, prepared=str(out), planId=plan['planId'],
                  planCommitment=plan['planCommitment'], checkpoint=spec['checkpoint'], scenarioSha256=sha(out / 'SCENARIO.json'),
                  scenarioCommitment=spec['scenarioCommitment'], descriptor=o['descriptor'], interventions=canon,
                  interventionCommitment=o['interventionCommitment'], writes=copy.deepcopy(o['writes']), configurations=copy.deepcopy(spec['configurations']),
                  engine=dict(engine), engineRecordStatus=record['status'], catalogueSha256=record['catalogueSha256'], sourceWitnessSha256=digest(raw_input),
                  fixedInputs=list(FIXED_INPUTS), staticCoverage=summary, targetAuthentication=targets, authentication='PENDING_NATIVE_ADMISSION',
                  nativeRunDirectory=str(sdk.home / 'scenarios/runs' / plan['planId']), nativeExecutions=0, executionAuthorized=False, network='none')
    save(out / 'PREPARATION.json', result)
    return result


class ProfileOverlayExecutionSDK(ExecutionSDK):
    """Prepared profile-overlay workflow on the separately registered descriptor worker, in its own SDK home.

    Inherits operation/verify/compare of ExecutionSDK. run() launches the same child command as ExecutionSDK.run
    but writes no attempt marker itself: the child scenario-run opens it after its authorization check. It
    refuses early unless host admission is v4 and the owner authorized exactly this operation.
    """
    def profiles(self):
        p = _profile()
        return [dict(id=pd.BACKEND_PROFILE, backend=pd.BACKEND_PROFILE, chainId=4663, poolId=p['poolId'], descriptor=pd.PROFILE_ENGINE_RECORD['descriptor'],
                     engineRecord=pd.PROFILE_ENGINE_RECORD['status'], nativeAuthorization='PER_OPERATION_OWNER_RECORD', hostAdmission=HOST_PROFILE,
                     livePreparation='UNSUPPORTED', witnessCoverage='ONLY_ESTABLISHED_BY_COMPLETED_NATIVE_EXECUTION')]

    def configure(self, **kwargs):
        raise ExecutionError('PROFILE_OVERLAY_USE_PROFILE_API', 'Use prepare_profile with the separately registered descriptor worker.')

    def prepare(self, *args, **kwargs):
        raise ExecutionError('PROFILE_OVERLAY_USE_PROFILE_API', 'Prepare the canonical intervention set through prepare_profile.')

    def prepare_profile(self, witness, *, expected_sha256, interventions, output, node=None):
        return prepare(self._sdk(), witness, expected_sha256=expected_sha256, interventions=interventions, output=output, node=node)

    def _prepared(self, prepared):
        from .cases.scenario import api
        path = no_links(prepared)
        try:
            meta = load(path / 'PREPARATION.json', 1 << 20)
            _, capture, plan, spec = api._input(self._sdk(), path)
            o = spec['profileOverlay']
            check(meta['schema'] == SCHEMA and meta['profile'] == plan['profile'] == pd.BACKEND_PROFILE and meta['planId'] == plan['planId']
                  and meta['planCommitment'] == plan['planCommitment'] and meta['scenarioSha256'] == capture['scenarioSha256']
                  and meta['scenarioCommitment'] == spec['scenarioCommitment'] and meta['checkpoint'] == spec['checkpoint']
                  and meta['descriptor'] == o['descriptor'] == pd.PROFILE_ENGINE_RECORD['descriptor']
                  and meta['interventions'] == o['interventions'] == plan['intent']['interventions']
                  and meta['interventionCommitment'] == o['interventionCommitment'] and meta['engine'] == spec['engine'],
                  'PROFILE_PREPARATION_DRIFT', 'Use the exact prepared input of this profile home and worker.')
            return path, meta
        except ExecutionError:
            raise
        except pd.DescriptorError as error:
            raise _descriptor_error(error) from error
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ExecutionError('PROFILE_PREPARATION_DRIFT', 'Restore the exact prepared profile-overlay input.', dict(error=str(error)[:400])) from error

    def _backend(self, call):
        def keep_codes():
            try:
                return call()
            except pd.DescriptorError as error:
                raise _descriptor_error(error) from error
        return super()._backend(keep_codes)

    def profile_state(self, prepared):
        """The worker's offline --profile-state: descriptor authentication on the witness and both derived initial
        worlds. No EVM, consent or network."""
        from .cases.scenario import api
        self._host()
        path, _ = self._prepared(prepared)
        return self._backend(lambda: api._helper(self._sdk(), ['--profile-state', path / 'SCENARIO.json'], 60))

    def operation(self, prepared, *, host_profile=HOST_PROFILE):
        check(host_profile == HOST_PROFILE, 'PROFILE_NATIVE_HOST_V4_REQUIRED', 'Profile-overlay operations bind host admission v4.')
        return super().operation(prepared, host_profile=host_profile)

    def authorize(self, prepared, *, operation, local_owner=False):
        """Owner authorization of one exact operation (written once). Runs worker identity and input checks only."""
        from .cases.scenario import api
        check(local_owner is True, 'EXACT_LOCAL_OWNER_REQUIRED', 'Review the exact operation and pass local_owner explicitly.')
        self._host()
        path, _ = self._prepared(prepared)
        return _gate(lambda: api.authorize_profile(self._sdk(), path, expected_operation=operation, local_owner=True))

    def run(self, prepared, *, operation, evidence, local_owner=False, mac_ready=False, host_profile=HOST_PROFILE):
        from .cases.scenario import api
        check(local_owner is True and mac_ready is True, 'EXACT_LOCAL_CONSENT_REQUIRED',
              'Review the exact operation, confirm AC/open lid and pass explicit local_owner/mac_ready consent.')
        self._host()
        check(host_profile == HOST_PROFILE, 'PROFILE_NATIVE_HOST_V4_REQUIRED', 'Profile-overlay runs use host admission v4.')
        path, _ = self._prepared(prepared)
        op = self.operation(path, host_profile=host_profile)
        check(op['operationCommitment'] == operation, 'OPERATION_MISMATCH', 'Stop: use only the exact reviewed binding.')
        # Advisory early refusal (nothing written). The attempt marker is not written here: the child run() opens it
        # itself under the operation lock right after its own authorization check, so a refusal there consumes
        # nothing either.
        _gate(lambda: api.require_profile_authorization(self._sdk(), op['binding'], host_profile, remaining=api.PROFILE_LAUNCH_MARGIN_SECONDS))
        return self._launch(path, op, operation, evidence, host_profile)

    def _launch(self, path, op, operation, evidence, host_profile):
        """ExecutionSDK.run without the parent-side attempt marker: same child command, capture and result linking."""
        import sys
        from .cases import native
        from .execution import SDK_ROOT
        out, evidence = no_links(op['outputPath']), no_links(evidence)
        marker = no_links(self.home / 'scenarios/execution-attempts') / (operation + '.json')
        check(not marker.exists(), 'OPERATION_ALREADY_ATTEMPTED', 'This attempt is permanently closed. Any successor needs a fresh plan and separate exact consent.')
        check(not out.exists(), 'OPERATION_ALREADY_CLOSED_OR_STARTED', 'Do not retry an existing native operation.')
        check(not evidence.exists(), 'FRESH_EVIDENCE_DIRECTORY_REQUIRED', 'Choose a fresh workflow evidence directory.')
        check(not any(evidence == p or evidence.is_relative_to(p) or p.is_relative_to(evidence) for p in (path, self.home, out)),
              'EVIDENCE_PATH_OVERLAP', 'Keep workflow evidence separate from prepared input and SDK home.')
        evidence.mkdir(mode=0o700, parents=True)
        sync(evidence.parent)
        bootstrap = 'import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);from rhook_alpha.cases.__main__ import main;raise SystemExit(main(sys.argv[2:]))'
        command = [sys.executable, '-I', '-c', bootstrap, str(SDK_ROOT), '--home', str(self.home), 'scenario-run', str(path),
                   '--local-owner', '--mac-ready', '--host-admission', host_profile, '--operation', operation]
        result = dict(status='EXECUTION_STOP', operationCommitment=operation, runDirectory=str(out), evidenceDirectory=str(evidence), automaticRetry=False,
                      operationPermanentlyClosed=None, cleanupConfirmed=False, nativeResult=None, externalDelivery='HOLD')
        try:
            process, stdout, stderr = native.capture_workflow(command, evidence / 'workflow', 180, 1 << 20, 1 << 20)
            result['workflow'] = process
            from developer.files import strict
            try:
                child = strict(stdout)
            except (ValueError, UnicodeError, RecursionError):
                child = None
            linked = False
            if type(child) is dict and (out / 'RESULT.json').is_file() and (out / 'BINDING.json').is_file():
                linked = (load(out / 'RESULT.json', 65536) == child and child.get('operationCommitment') == operation
                          and load(out / 'BINDING.json', 65536).get('operationCommitment') == operation)
            diagnostic = child if type(child) is dict else {}
            if diagnostic and not linked:
                result['childDiagnostics'] = diagnostic
                result['childDiagnosticsScope'] = 'UNLINKED_STDOUT_NOT_NATIVE_EXECUTION_EVIDENCE'
            if linked:
                result['nativeResult'] = child
                if child.get('primaryStop'):
                    result['primaryStop'] = child['primaryStop']
            workflow_clean = process.get('ownedChildReaped') is True and process.get('workflowGroupGone') is True and process.get('cleanupError') is None
            result['cleanupConfirmed'] = workflow_clean and linked and child.get('cleanupConfirmed') is True
            completed = (linked and child.get('status') == 'SCENARIO_COMPLETED' and type(child.get('producerInvocations')) is int
                         and child['producerInvocations'] == 2 and child.get('RPC') == 0 and child.get('WSS') == 0
                         and process.get('exitCode') == 0 and not process.get('stop') and result['cleanupConfirmed'])
            if completed:
                result['status'] = 'EXECUTION_COMPLETED'
            else:
                child_cause = diagnostic.get('causeCode') if diagnostic.get('status') != 'SCENARIO_COMPLETED' else None
                result['causeCode'] = child_cause or process.get('stop') or ('NATIVE_STOP' if linked else 'UNLINKED_NATIVE_RESULT')
                result['nextStep'] = diagnostic.get('nextStep') or 'Preserve raw workflow/native diagnostics. Do not retry this operation or fabricate missing observations.'
        except BaseException as error:
            result.update(causeCode=type(error).__name__ + ': ' + str(error)[:1024],
                          nextStep='Inspect retained workflow evidence; cleanup is unconfirmed.')
        # Whether the one shot was consumed is decided by the child's marker alone.
        closed = marker.exists()
        result['operationPermanentlyClosed'] = closed
        if not closed and result['status'] != 'EXECUTION_COMPLETED':
            result['attemptConsumed'] = False
            result['nextStep'] = ('The attempt was not opened, so nothing was consumed. Fix the cause (for example renew the owner '
                                  'authorization), then launch again with a fresh evidence directory.')
        save(evidence / 'EXECUTION_RESULT.json', result)
        return result

    def run_profile(self, prepared, *, operation, evidence, local_owner=False, mac_ready=False):
        """Doctor first (nothing consumed when it fails), then one run() of the exact operation, then verify() and
        compare(). Never retried."""
        from .session.workflow import doctor
        check(local_owner is True and mac_ready is True, 'EXACT_LOCAL_CONSENT_REQUIRED',
              'Review the exact operation, confirm AC power and an open lid, and pass --local-owner --mac-ready.')
        base = dict(schema=RUN_SCHEMA, prepared=str(no_links(prepared)), operationCommitment=operation, automaticRetry=False)
        environment = doctor(self)
        base['environment'] = environment
        if environment['status'] != 'READY':
            return dict(base, status='RUN_STOP_ENVIRONMENT_NOT_READY', operationPermanentlyClosed=False, consumed=dict(authorization=False, consent=False, attemptMarker=False),
                        nextStep='Nothing was consumed. Fix the failed doctor checks, then run the same command from a regular Terminal.')
        execution = self.run(prepared, operation=operation, evidence=evidence, local_owner=True, mac_ready=True)
        base.update(operationPermanentlyClosed=execution.get('operationPermanentlyClosed') is True, evidenceDirectory=execution.get('evidenceDirectory'),
                    runDirectory=execution.get('runDirectory'),
                    execution={k: execution.get(k) for k in ('status', 'causeCode', 'cleanupConfirmed', 'primaryStop', 'attemptConsumed')})
        if execution['status'] != 'EXECUTION_COMPLETED':
            if not base['operationPermanentlyClosed']:
                return dict(base, status='RUN_STOP_NOT_STARTED', causeCode=execution.get('causeCode'), nextStep=execution.get('nextStep'))
            return dict(base, status='RUN_STOP', causeCode=execution.get('causeCode'),
                        nextStep='Preserve the evidence. This operation is closed and is not retried; investigate before anything else.')
        try:
            verified = self.verify(execution['runDirectory'])
            check(verified.get('status') == 'SCENARIO_RECORDED_INTEGRITY_PASS', 'RECORDED_INTEGRITY_NOT_PASSED', 'The verifier did not pass the run.')
            comparison = self.compare(execution['runDirectory'])
        except (ExecutionError, ValueError, OSError, KeyError, TypeError) as error:
            return dict(base, status='RUN_COMPLETED_VERIFICATION_STOP', causeCode=getattr(error, 'code', None) or f'{type(error).__name__}: {error}'[:400],
                        nextStep='The run completed and stays closed. Inspect the retained run; verification is not retried automatically.')
        return dict(base, status='RUN_VERIFIED', verification=verified['status'], comparison=comparison)


def describe(prepared):
    """Read back a prepared directory's record; no authentication."""
    try:
        return load(no_links(prepared) / 'PREPARATION.json', 1 << 20)
    except (OSError, ValueError) as error:
        raise ExecutionError('PROFILE_PREPARATION_MISSING', 'Use a directory written by profile_overlay.prepare.') from error
