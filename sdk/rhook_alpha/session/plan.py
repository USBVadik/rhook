"""Parameterized LP Rewards plan 0.1: from a chosen lpBps to a prepared, not executed, variant.

One call composes the existing Counterfactual Session 0.1 steps: open or create the session once from
one pinned source, register the variant, evaluate static coverage of the retained witness, and prepare
the variant through the existing ExecutionSDK. It adds no session system, evidence format or authority.

It never binds an operation. Binding reads the registered runtime and runs the worker's identity check,
a native process, and needs a registered host admission profile; that is Stage B. No operationCommitment
is computed or shown here. Nothing here starts a native worker or sensor, opens a network connection,
writes a consent, attempt marker or run directory, or acquires state.
"""
import re

from .core import SessionError, check

PLAN_SCHEMA = 'rhook/parameterized-plan/0.1'
PROFILE = 'hookr-buy/0.1'
BASELINE_LP_BPS = 100
CLI_INTEGER = re.compile('-?(0|[1-9][0-9]*)')
STATIC = {'STATIC_DEPENDENCIES_COVERED': 'COVERED', 'STATIC_DEPENDENCIES_MISSING': 'MISSING'}
OPERATION_NOT_BOUND = dict(
    status='OPERATION_NOT_BOUND',
    reason='Binding an operation reads the registered runtime, runs the worker identity check (a native process) and '
           'needs a registered host admission profile. That is Stage B and needs separate authorization; no '
           'operationCommitment is computed by planning.')
REMAINING = [
    dict(stage='B', step='Register the runtime and the macos-host-admission-v4 sensor in this SDK home; worker identity check.'),
    dict(stage='B', step='execution-authenticate on the prepared directory (native input admission, no EVM).'),
    dict(stage='B', step='execution-operation --host-admission macos-host-admission-v4: exact operationCommitment.'),
    dict(stage='C', step='Exact consent for that one operationCommitment, fresh host admission, one execution-run (BASELINE + VARIANT).'),
    dict(stage='C', step='execution-verify and execution-compare on the run, then session.verify_selected(variantId, run).'),
]


def lp_bps_value(value):
    """Python API value: an int 0-99. bool, float, str and other types are refused; 100 is the baseline."""
    check(type(value) is int, 'LP_BPS_INTEGER_REQUIRED',
          'Pass lpBps as an integer (not bool, float or string), 0-99.', {'type': type(value).__name__})
    check(value != BASELINE_LP_BPS, 'BASELINE_LP100_IS_NOT_A_VARIANT',
          'LP100 is the recorded original rule and runs as SCENARIO_BASELINE in every run. Choose 0-99 for an alternative.')
    check(0 <= value <= 99, 'LP_BPS_0_TO_99_REQUIRED', 'Choose an integer replacement 0-99; the baseline is LP100.',
          {'value': value})
    return value


def lp_bps_text(text):
    """CLI value: a plain decimal integer, no sign other than '-', no leading zeros, exponent or fraction."""
    check(type(text) is str and CLI_INTEGER.fullmatch(text) is not None, 'LP_BPS_INTEGER_REQUIRED',
          'Pass --lp-bps as a plain decimal integer 0-99, for example --lp-bps 37.', {'value': str(text)[:40]})
    return lp_bps_value(int(text))


def _session(sdk, session_id, source, expected_sha256, checkpoint):
    by_id = session_id is not None
    by_source = any(x is not None for x in (source, expected_sha256, checkpoint))
    check(by_id != by_source, 'SESSION_SELECTION',
          'Name either an existing session id, or one pinned source with its SHA-256 and checkpoint, not both.')
    if by_id:
        return sdk.open_session(session_id, profile=PROFILE), False
    check(source is not None and expected_sha256 is not None and checkpoint is not None, 'SESSION_SELECTION',
          'Creating a session needs the source path, its SHA-256 and the checkpoint.')
    root = sdk.home / 'sessions'
    before = set(p.name for p in root.iterdir()) if root.is_dir() else set()
    session = sdk.create_session(source=source, expected_sha256=expected_sha256, checkpoint=checkpoint, profile=PROFILE)
    return session, session.id not in before


def plan_lp_variant(sdk, lp_bps, *, session_id=None, source=None, expected_sha256=None, checkpoint=None, node=None):
    """Plan one LP Rewards variant offline. Raises SessionError for invalid input; returns a STOP or READY plan.

    sdk: an ExecutionSDK. lp_bps: int 0-99 (validated before anything is written).
    """
    lp = lp_bps_value(lp_bps)
    return _plan(sdk, {'lpBps': lp}, dict(selectedLpBps=lp, baselineLpBps=BASELINE_LP_BPS), REMAINING,
                 session_id=session_id, source=source, expected_sha256=expected_sha256, checkpoint=checkpoint, node=node)


DYNAMIC_REMAINING = [
    dict(stage='B', step='Register the reviewed Dynamic Fee OFF derivative runtime (profile nitro-hookr-dynamic-fee-off/0.1) and '
                      'the macos-host-admission-v4 sensor in the derivative home; worker identity check.'),
    *REMAINING[1:],
]


def plan_dynamic_fee_variant(sdk, value='OFF', *, session_id=None, source=None, expected_sha256=None, checkpoint=None, node=None):
    """Plan the Dynamic Fee OFF variant offline: the same session steps, plus read-only MPT authentication of
    the original Root and Rules target leaves and a prepared input for the reviewed derivative worker."""
    from .hookr import dynamic_fee_value
    v = dynamic_fee_value(value)
    return _plan(sdk, {'dynamicFee': v}, dict(dynamicFee=v, baselineDynamicFee='ON', lpBps=BASELINE_LP_BPS), DYNAMIC_REMAINING,
                 session_id=session_id, source=source, expected_sha256=expected_sha256, checkpoint=checkpoint, node=node)


OVERLAY_REMAINING = [
    dict(stage='B', step='Register the reviewed config-overlay worker runtime (profile nitro-hookr-config-overlay/0.1) and '
                      'the macos-host-admission-v4 sensor in the overlay home; worker identity check.'),
    *REMAINING[1:],
]


def plan_config_overlay_variant(sdk, *, lp_bps=None, dynamic_fee=None, session_id=None, source=None, expected_sha256=None, checkpoint=None, node=None):
    """Plan one canonical typed intervention set (lpBps 0-99 and/or Dynamic Fee OFF) on the parameterized
    config-overlay worker: the same session steps, read-only MPT authentication of the original Root and
    Rules target leaves, and a prepared input with the derived masked overlay. Offline; no binding."""
    from .hookr import dynamic_fee_value, overlay_interventions
    parameters = {}
    if lp_bps is not None:
        parameters['lpBps'] = lp_bps_value(lp_bps)
    if dynamic_fee is not None:
        parameters['dynamicFee'] = dynamic_fee_value(dynamic_fee)
    check(parameters, 'CONFIG_OVERLAY_SETTING_REQUIRED', 'Choose lpBps 0-99, dynamicFee OFF, or both.')
    items = overlay_interventions(parameters)
    from ..config_overlay import PROFILE as OVERLAY_PROFILE
    selection = dict(interventions=items, lpBps=parameters.get('lpBps', BASELINE_LP_BPS), dynamicFee=parameters.get('dynamicFee', 'ON'),
                     baseline=dict(lpBps=BASELINE_LP_BPS, dynamicFee='ON'), backendProfile=OVERLAY_PROFILE)
    return _plan(sdk, dict(parameters, backend=OVERLAY_PROFILE), selection, OVERLAY_REMAINING,
                 session_id=session_id, source=source, expected_sha256=expected_sha256, checkpoint=checkpoint, node=node)


def _intervention_targets(session, view):
    """The committed writes of a prepared Dynamic Fee or config-overlay variant, from its retained descriptor."""
    kind = view['descriptor'].get('kind')
    if kind not in ('HOOKR_DYNAMIC_FEE', 'HOOKR_CONFIG_OVERLAY') or not view.get('preparation'):
        return None
    from developer.files import load
    d = load(session.directory / view['preparation']['preparedDirectory'] / 'INTERVENTION.json', 1 << 20)
    spec = load(session.directory / view['preparation']['preparedDirectory'] / 'SCENARIO.json', 8 << 20)
    if kind == 'HOOKR_CONFIG_OVERLAY':
        return dict(authentication='ORIGINAL_ROOT_MPT_AUTHENTICATED', scope='Root and Rules account paths, code preimages, five target storage leaves',
                    interventions=d['interventions'], writes=d['writes'], fields=d['fields'],
                    descriptorCommitment=d['interventionCommitment'], interventionCommitment=spec['configOverlay']['interventionCommitment'],
                    backendProfile=view['descriptor'].get('backendProfile'), engine=spec['engine'])
    return dict(authentication='ORIGINAL_ROOT_MPT_AUTHENTICATED', scope='Root and Rules account paths, code preimages, five target storage leaves',
                writes=[{k: w[k] for k in ('address', 'slot', 'before', 'after')} for w in d['writes']],
                descriptorCommitment=d['interventionCommitment'], interventionCommitment=spec['intervention']['interventionCommitment'],
                backendProfile=view['descriptor'].get('backendProfile'), engine=spec['engine'])


def _plan(sdk, parameters, selection, remaining, *, session_id, source, expected_sha256, checkpoint, node):
    session, created = _session(sdk, session_id, source, expected_sha256, checkpoint)
    header = session.header
    witness = dict(sourceSha256=header['source']['sha256'], sourceScenarioCommitment=header['source']['scenarioCommitment'],
                   inventoryCommitment=header['common']['witnessInventory']['commitment'],
                   inventoryCommitmentDomain='rhook/counterfactual-session/0.1/inventory',
                   nodes=header['common']['witnessInventory']['nodes'], codes=header['common']['witnessInventory']['codes'],
                   engineWitnessCommitment='RECORDED_BY_THE_NATIVE_RUN_NOT_DERIVED_OFFLINE',
                   acquisition='NOT_PERFORMED_RETAINED_WITNESS_REUSED')
    base = dict(schema=PLAN_SCHEMA, profile=PROFILE, sessionId=session.id, sessionCreated=created,
                **selection, checkpoint=header['checkpoint'],
                checkpointCanonicality=header['checkpointTrust']['canonicality'], originalWitness=witness)
    try:
        registered = session.add_variant(parameters)
    except SessionError as error:
        return dict(base, status='PLAN_STOP', variantId=None, alreadyRegistered=False, staticCoverage=None,
                    profilePreconditions='NOT_EVALUATED', prepared=None, dynamicCoverage='UNKNOWN',
                    nativeExecution='NOT_PERFORMED', operation=dict(OPERATION_NOT_BOUND),
                    readiness=dict(status='STOP', stops=[dict(code=error.code, nextStep=error.next_step)], remaining=remaining),
                    networkRequests=0, nativeExecutions=0, limitations=header['limitations'])
    vid = registered['variantId']
    report = session.coverage(node=node)
    static = STATIC.get(report.get('status'), 'NOT_EVALUATED' if report.get('status') == 'NOT_EVALUATED' else 'STOP')
    preconditions = session._preconditions(report)
    stops = []
    if static == 'MISSING':
        stops.append(dict(code='STATIC_COVERAGE_MISSING', nextStep='NEEDS_AUTHENTICATED_STATE: the retained witness does not answer every '
                          'declared original-state read; acquiring it needs separate authorization.',
                          unresolvedDependencies=report.get('unresolvedDependencies')))
    elif static != 'COVERED':
        stops.append(dict(code='STATIC_COVERAGE_' + static, nextStep='Static coverage could not be evaluated; readiness is not inferred.',
                          cause=report.get('code')))
    if static in ('COVERED', 'MISSING') and preconditions != 'SATISFIED':
        stops.append(dict(code='PROFILE_PRECONDITIONS_' + preconditions,
                          nextStep='The authenticated original state does not meet, or could not be shown to meet, this profile.',
                          failed=[c.get('id') for c in (report.get('preconditions') or {}).get('checks', []) if c.get('status') != 'SATISFIED']))
    prepared_now = None
    if not stops:
        try:
            prepared_now = session.prepare_variant(vid)
        except SessionError as error:
            stops.append(dict(code=error.code, nextStep=error.next_step, details=error.details))
    view = next(v for v in session.variants() if v['variantId'] == vid)
    if view['status'] == 'STOP':
        stops.append(dict(code=view.get('causeCode', 'PREPARED_ARTIFACT_INVALID'), nextStep=view['nextRequirement']))
    prepared = None
    if view.get('preparation'):
        p = view['preparation']
        prepared = dict(scenarioCommitment=p['scenarioCommitment'], scenarioSha256=p['scenarioSha256'],
                        preparedDirectory=f'sessions/{session.id}/' + p['preparedDirectory'],
                        alreadyPrepared=prepared_now['alreadyPrepared'] if prepared_now else True)
    if stops or prepared is None:
        status, readiness = 'PLAN_STOP', 'STOP'
    elif view['execution'] == 'RECORDED_NATIVE_RUN':
        # A variant keeps its first verified run; planning it again changes nothing.
        status, readiness = 'PLAN_ALREADY_VERIFIED', 'ALREADY_VERIFIED'
    else:
        status, readiness = 'PLAN_READY_FOR_SEPARATELY_AUTHORIZED_NATIVE_RUN', 'READY_FOR_STAGE_B'
    performed = report.get('networkRequestsPerformed')
    value = dict(base, status=status,
                 variantId=vid, alreadyRegistered=registered['alreadyRegistered'], descriptor=registered['descriptor'],
                 staticCoverage=dict(status=static, unresolvedDependencies=report.get('unresolvedDependencies'),
                                     summary=report.get('summary'), networkRequestsPerformed=performed,
                                     scope='SESSION_SOURCE_SAME_FOR_EVERY_LP_VARIANT'),
                 profilePreconditions=preconditions, prepared=prepared,
                 dynamicCoverage=view['dynamicCoverage'], nativeExecution=view['execution'],
                 operation=dict(OPERATION_NOT_BOUND),
                 readiness=dict(status=readiness, stops=stops, remaining=[] if readiness == 'ALREADY_VERIFIED' else remaining),
                 networkRequests=performed if type(performed) is int else 0, nativeExecutions=0, limitations=header['limitations'])
    if 'backend' in parameters:
        value['staticCoverage']['scope'] = 'SESSION_SOURCE_COMMON_READS; OVERLAY_TARGETS_IN_interventionTargets'
        value['interventionTargets'] = _intervention_targets(session, view)
    elif 'dynamicFee' in parameters:
        value['staticCoverage']['scope'] = 'SESSION_SOURCE_COMMON_READS; DYNAMIC_FEE_TARGETS_IN_interventionTargets'
        value['interventionTargets'] = _intervention_targets(session, view)
    return value
