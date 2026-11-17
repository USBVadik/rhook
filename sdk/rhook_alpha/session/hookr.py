"""Hookr scenario profile adapter for Counterfactual Session 0.1.

Everything Hookr-specific lives here: the pinned scenario input, the LP Rewards intervention,
preparation through the existing ExecutionSDK, the static read plan and the receipt economics.
The session core never sees pool addresses, storage layouts or token details.
"""
from pathlib import Path
import re
import shutil
import subprocess

from developer.files import digest, load, no_links, sha, strict
from .. import execution
from ..execution import ExecutionError, ExecutionSDK
from .core import SessionError, check, commit

PROFILE = execution.PROFILE
ADAPTER_VERSION = 'hookr-scenario-session/0.1'
HERE = Path(__file__).resolve().parent
COVERAGE_HELPER = HERE / 'hookr-coverage-main.mjs'
# Fields a prepared variant may differ in from its source; everything else must stay byte-equal.
VARIANT_FIELDS = {'configurations', 'origin', 'scenarioCommitment'}
# Dynamic Fee OFF runs on its own reviewed derivative worker, so its input also carries a new schema,
# engine binding and the committed two-write intervention.
DYNAMIC_VARIANT_FIELDS = VARIANT_FIELDS | {'schema', 'engine'}
LP_KIND, DYNAMIC_KIND = 'HOOKR_LP_REWARDS_BPS', 'HOOKR_DYNAMIC_FEE'
# SDK 0.4: a canonical set of typed interventions on the parameterized config-overlay worker.
OVERLAY_KIND = 'HOOKR_CONFIG_OVERLAY'
OVERLAY_VARIANT_FIELDS = DYNAMIC_VARIANT_FIELDS
OVERLAY_SUBHOME = Path('profiles') / 'hookr-config-overlay'
# The derivative's registrations, plans and runs live in their own SDK home inside the session home:
# one SDK home holds exactly one registered runtime.
DYNAMIC_SUBHOME = Path('profiles') / 'hookr-dynamic-fee-off'
LP_BACKEND = 'nitro-hookr-scenario/0.1'


def dynamic_fee_value(value):
    """The one supported Dynamic Fee replacement is OFF; ON is the recorded baseline."""
    check(value != 'ON', 'DYNAMIC_FEE_ON_IS_THE_BASELINE',
          'Dynamic Fee is ON in the recorded configuration and runs as SCENARIO_BASELINE. The supported variant is OFF.')
    check(value == 'OFF', 'DYNAMIC_FEE_OFF_ONLY', 'Pass dynamicFee as the string OFF; other Dynamic Fee settings are not supported.',
          {'value': str(value)[:40]})
    return value


def overlay_interventions(parameters):
    """Session parameters -> canonical typed set. lpBps 0-99 and/or dynamicFee OFF."""
    from ..config_overlay import DYNAMIC_FEE, LP_REWARDS, canonical_interventions
    items = []
    if 'lpBps' in parameters:
        lp = parameters['lpBps']
        check(type(lp) is int and 0 <= lp <= 99, 'LP_BPS_0_TO_99_REQUIRED', 'Choose an integer replacement 0-99; the baseline is LP100.')
        items.append(dict(kind=LP_REWARDS, lpBps=lp))
    if 'dynamicFee' in parameters:
        items.append(dict(kind=DYNAMIC_FEE, dynamicFee=dynamic_fee_value(parameters['dynamicFee'])))
    check(items, 'UNSUPPORTED_VARIANT', 'A config-overlay variant changes lpBps, dynamicFee or both.')
    return _sdk_call(canonical_interventions, items)


def backend_sdk(home, descriptor):
    """The SDK that prepares, binds, runs and verifies this variant: the session home for LP, the
    derivative's own home for Dynamic Fee, the overlay worker's own home for a config-overlay set."""
    if descriptor['kind'] == OVERLAY_KIND:
        from ..config_overlay import ConfigOverlayExecutionSDK
        return ConfigOverlayExecutionSDK(no_links(home) / OVERLAY_SUBHOME)
    if descriptor['kind'] == DYNAMIC_KIND:
        from ..dynamic_fee import DynamicFeeExecutionSDK
        return DynamicFeeExecutionSDK(no_links(home) / DYNAMIC_SUBHOME)
    return ExecutionSDK(home)
PRECONDITION_STATUSES = ('SATISFIED', 'NOT_SATISFIED', 'UNKNOWN')
# The existing scenario compare returns exactly these two projections, BASELINE first; its delta is VARIANT - BASELINE.
VERIFIED_STATUS = 'VERIFIED_SCENARIO_COMPARISON'
WORLDS = ('SCENARIO_BASELINE', 'SCENARIO_VARIANT')
DECIMAL = re.compile('-?[0-9]+')


def _sdk_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ExecutionError as error:
        raise SessionError(error.code, error.next_step, error.details) from error


class HookrScenarioAdapter:
    profile = PROFILE
    adapter_version = ADAPTER_VERSION
    source_name = 'SCENARIO.json'

    def __init__(self, home):
        self.home = no_links(home)

    # ----- source -------------------------------------------------------------------------------

    def load_source(self, source, expected_sha256):
        check(type(expected_sha256) is str, 'SOURCE_SHA256_REQUIRED', 'Pin the source SCENARIO.json SHA-256 explicitly.')
        raw, spec = _sdk_call(execution._input, source, expected_sha256)
        old_lp = _sdk_call(execution._validate_spec, spec, execution._profile())
        check(old_lp is not None and (int(spec['configurations']['baseline'][0], 16) >> 160) & 65535 == 100,
              'BASELINE_LP100_REQUIRED', 'The supported profile compares against the pinned LP100 baseline.')
        checkpoint = _sdk_call(execution._checkpoint, spec['checkpoint'])
        action = spec['actions'][0]
        common = dict(
            poolId=spec['poolId'], actionId=action['id'], amountInWei=action['amountInWei'], gas=action['gas'],
            commonSetup=spec['commonSetup'], environment=spec['environment'], engine=spec['engine'],
            limits=spec['limits'], releaseManifestSha256=spec['releaseManifestSha256'],
            chainConfigSha256=digest(spec['chainConfig'].encode()),
            parentCommitment=commit('rhook/counterfactual-session/0.1/parent', spec['parent']),
            witnessInventory=dict(commitment=commit('rhook/counterfactual-session/0.1/inventory', spec['inventory']),
                                  nodes=len(spec['inventory']['nodes']), codes=len(spec['inventory']['codes'])))
        trust = dict(
            sourceBytes='SHA256_MATCHES_CALLER_PIN',
            checkpointBinding='SCENARIO_COMMITMENT_AND_DECLARED_PARENT_FIELDS',
            parentHeaderHash='RECOMPUTED_ONLY_WHEN_STATIC_COVERAGE_IS_EVALUATED',
            canonicality='NOT_ESTABLISHED_REQUIRES_AN_INDEPENDENTLY_TRUSTED_BLOCK_HASH',
            originalStateProofs='PER_DEPENDENCY_IN_STATIC_COVERAGE')
        return dict(raw=raw, sha256=digest(raw), bytes=len(raw), scenarioCommitment=spec['scenarioCommitment'],
                    checkpoint=checkpoint, checkpointTrust=trust, common=common,
                    baseline=dict(lpBps=100, configurationWords=spec['configurations']['baseline']))

    # ----- variants -----------------------------------------------------------------------------

    def variant_descriptor(self, parameters, header):
        check(type(parameters) is dict and set(parameters) <= {'lpBps', 'dynamicFee', 'backend'}, 'UNSUPPORTED_VARIANT',
              'A variant sets lpBps, dynamicFee or both (and optionally backend); other changes are not admitted.')
        explicit = 'backend' in parameters
        check(not explicit or parameters['backend'] == self.overlay_profile(), 'UNSUPPORTED_BACKEND',
              'The only selectable backend is the parameterized config-overlay worker.', {'backend': str(parameters.get('backend'))[:60]})
        settings = {k: v for k, v in parameters.items() if k != 'backend'}
        if explicit or len(settings) == 2:
            # One canonical typed set for the overlay worker. Single-setting variants without an explicit
            # backend keep their 0.1/0.3 descriptors and ids on the existing workers.
            items = overlay_interventions(settings)
            replacement = dict(lpBps=next((i['lpBps'] for i in items if 'lpBps' in i), 100),
                               dynamicFee=next((i['dynamicFee'] for i in items if 'dynamicFee' in i), 'ON'))
            return dict(kind=OVERLAY_KIND, field='RulesConfig+RootRecord', poolId=header['common']['poolId'],
                        original=dict(lpBps=header['baseline']['lpBps'], dynamicFee='ON'), replacement=replacement,
                        interventions=items, backendProfile=self.overlay_profile())
        check(len(settings) == 1, 'UNSUPPORTED_VARIANT', 'A variant changes lpBps, dynamicFee or both.')
        if 'dynamicFee' in parameters:
            value = dynamic_fee_value(parameters['dynamicFee'])
            return dict(kind=DYNAMIC_KIND, field='DynamicFee', poolId=header['common']['poolId'], original='ON',
                        replacement=value, backendProfile=self.dynamic_profile())
        lp = parameters['lpBps']
        check(type(lp) is int and 0 <= lp <= 99, 'LP_BPS_0_TO_99_REQUIRED',
              'Choose an integer replacement 0-99; the baseline is LP100.')
        # LP descriptors keep their 0.1 shape, so existing variant ids stay the same.
        return dict(kind=LP_KIND, field='RulesConfig.lpBps', poolId=header['common']['poolId'],
                    original=header['baseline']['lpBps'], replacement=lp)

    @staticmethod
    def dynamic_profile():
        from ..dynamic_fee import PROFILE as DYNAMIC_PROFILE
        return DYNAMIC_PROFILE

    @staticmethod
    def overlay_profile():
        from ..config_overlay import PROFILE as OVERLAY_PROFILE
        return OVERLAY_PROFILE

    @staticmethod
    def parameters(descriptor):
        if descriptor.get('kind') == OVERLAY_KIND:
            value = {('lpBps' if 'lpBps' in i else 'dynamicFee'): i.get('lpBps', i.get('dynamicFee')) for i in descriptor['interventions']}
            return dict(value, backend=descriptor['backendProfile']) if len(value) == 1 else value
        if descriptor.get('kind') == DYNAMIC_KIND:
            return {'dynamicFee': descriptor['replacement']}
        return {'lpBps': descriptor['replacement']}

    @staticmethod
    def sort_key(descriptor):
        if descriptor.get('kind') == OVERLAY_KIND:
            r = descriptor['replacement']
            return (2, r['lpBps'], r['dynamicFee'])
        return (1, 0) if descriptor.get('kind') == DYNAMIC_KIND else (0, descriptor['replacement'])

    # ----- preparation --------------------------------------------------------------------------

    def _sdk(self, descriptor=None):
        return backend_sdk(self.home, descriptor or dict(kind=LP_KIND))

    def prepare(self, source, header, descriptor, output, *, node=None):
        sdk = self._sdk(descriptor)
        if descriptor['kind'] == OVERLAY_KIND:
            from ..config_overlay import ACCEPTED_OVERLAY_ENGINE
            pin = header['source']['sha256']
            # Read-only MPT authentication of the original Root and Rules target leaves, then the overlay
            # preparation, bound to the reviewed overlay worker. No worker runs here.
            check(ACCEPTED_OVERLAY_ENGINE is not None, 'CONFIG_OVERLAY_ENGINE_NOT_ACCEPTED',
                  'The config-overlay worker has no accepted identity in this SDK yet; nothing was prepared.')
            plan = _sdk_call(sdk.plan_overlay, source, expected_sha256=pin, interventions=descriptor['interventions'], node=node)
            return _sdk_call(sdk.prepare_overlay, plan['descriptor'], source, expected_sha256=pin, output=output,
                             engine=ACCEPTED_OVERLAY_ENGINE, node=node)
        if descriptor['kind'] == DYNAMIC_KIND:
            from ..dynamic_fee import ACCEPTED_DERIVATIVE_ENGINE
            from ..interventions import DYNAMIC_OFF
            pin = header['source']['sha256']
            # Read-only MPT authentication of the original Root and Rules target leaves, then the existing
            # Dynamic Fee OFF preparation, bound to the reviewed derivative engine. No worker runs here.
            plan = _sdk_call(sdk.plan_intervention, source, expected_sha256=pin, kind=DYNAMIC_OFF, node=node)
            return _sdk_call(sdk.prepare_intervention, plan['descriptor'], source, expected_sha256=pin, output=output,
                             engine=ACCEPTED_DERIVATIVE_ENGINE, node=node)
        config = _sdk_call(sdk.configure, lp_bps=descriptor['replacement'], checkpoint=header['checkpoint'])
        return _sdk_call(sdk.prepare, config, source, expected_sha256=header['source']['sha256'], output=output)

    def check_prepared(self, output, header, descriptor, source_raw):
        """source_raw: the retained source bytes, already checked against the session pin."""
        _, meta = _sdk_call(self._sdk(descriptor)._prepared, output)
        if descriptor['kind'] == OVERLAY_KIND:
            return self._check_overlay(output, header, descriptor, source_raw, meta)
        dynamic = descriptor['kind'] == DYNAMIC_KIND
        check((dynamic or meta['selectedLpBps'] == descriptor['replacement']) and meta['checkpoint'] == header['checkpoint']
              and meta['sourceWitnessSha256'] == header['source']['sha256'], 'PREPARED_VARIANT_MISMATCH',
              'The prepared directory belongs to a different variant, checkpoint or source.')
        prepared = load(output / 'SCENARIO.json', 8 << 20)
        source = strict(source_raw)
        shared = sorted(set(source) - (DYNAMIC_VARIANT_FIELDS if dynamic else VARIANT_FIELDS))
        check(set(prepared) == set(source) | ({'intervention'} if dynamic else set()) and all(prepared[k] == source[k] for k in shared)
              and prepared['configurations']['baseline'] == source['configurations']['baseline'],
              'PREPARED_VARIANT_MISMATCH', 'Only the declared variant fields may differ from the session source.')
        summary = dict(scenarioCommitment=prepared['scenarioCommitment'], scenarioSha256=sha(output / 'SCENARIO.json'),
                       authentication=meta['authentication'], witnessClosure=meta['witnessClosure'],
                       nativeExecutions=meta['nativeExecutions'], sharedWithSource=shared)
        if dynamic:
            return dict(summary, dynamicFee=descriptor['replacement'], interventionCommitment=meta['interventionCommitment'],
                        backendProfile=meta['profile'])
        return dict(summary, selectedLpBps=meta['selectedLpBps'])

    @staticmethod
    def _check_overlay(output, header, descriptor, source_raw, meta):
        check(meta['interventions'] == descriptor['interventions'] and meta['checkpoint'] == header['checkpoint']
              and meta['sourceWitnessSha256'] == header['source']['sha256'], 'PREPARED_VARIANT_MISMATCH',
              'The prepared directory belongs to a different intervention set, checkpoint or source.')
        prepared = load(output / 'SCENARIO.json', 8 << 20)
        source = strict(source_raw)
        shared = sorted(set(source) - OVERLAY_VARIANT_FIELDS)
        check(set(prepared) == set(source) | {'configOverlay'} and all(prepared[k] == source[k] for k in shared)
              and prepared['configurations']['baseline'] == source['configurations']['baseline'],
              'PREPARED_VARIANT_MISMATCH', 'Only the declared variant fields may differ from the session source.')
        return dict(scenarioCommitment=prepared['scenarioCommitment'], scenarioSha256=sha(output / 'SCENARIO.json'),
                    authentication=meta['authentication'], witnessClosure=meta['witnessClosure'],
                    nativeExecutions=meta['nativeExecutions'], sharedWithSource=shared, interventions=meta['interventions'],
                    fields=meta['fields'], interventionCommitment=meta['interventionCommitment'], backendProfile=meta['profile'])

    # ----- static coverage ----------------------------------------------------------------------

    def coverage(self, raw, *, node=None):
        """raw: the retained source bytes, already checked against the session pin."""
        program = node or shutil.which('node')
        if program is None:
            return dict(status='NOT_EVALUATED', code='NODE_NOT_FOUND',
                        nextStep='Install Node.js and the pinned adapter dependencies; nothing was inferred.')
        deps = execution.SDK_ROOT / 'engine/adapters/hookr-case/node_modules'
        if not all((deps / name / 'package.json').is_file() for name in ('viem', 'hookr-sdk')):
            return dict(status='NOT_EVALUATED', code='RUNTIME_DEPENDENCIES_MISSING',
                        nextStep='Run npm ci --ignore-scripts --prefix sdk/engine/adapters/hookr-case; nothing was inferred.')
        try:
            r = subprocess.run([str(program), str(COVERAGE_HELPER)], input=raw, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            return dict(status='NOT_EVALUATED', code='COVERAGE_HELPER_FAILED', detail=str(error)[:300])
        if r.returncode != 0 or len(r.stdout) > 16 << 20:
            return dict(status='NOT_EVALUATED', code='COVERAGE_HELPER_FAILED', detail=r.stderr.decode(errors='replace')[:300])
        try:
            report = strict(r.stdout)
        except (ValueError, UnicodeError, RecursionError) as error:
            return dict(status='NOT_EVALUATED', code='COVERAGE_OUTPUT_INVALID', detail=str(error)[:300])
        check(type(report) is dict and report.get('status') in ('STATIC_DEPENDENCIES_COVERED', 'STATIC_DEPENDENCIES_MISSING', 'STOP'),
              'COVERAGE_OUTPUT_INVALID', 'The coverage helper returned an unknown status.')
        check(report.get('status') == 'STOP' or report.get('networkRequestsPerformed') == 0, 'COVERAGE_OUTPUT_INVALID',
              'Static coverage must not perform network requests.')
        if report['status'] != 'STOP':
            pre = report.get('preconditions')
            checks = pre.get('checks') if type(pre) is dict else None
            statuses = [c.get('status') for c in checks if type(c) is dict] if type(checks) is list else []
            derived = ('NOT_SATISFIED' if 'NOT_SATISFIED' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'SATISFIED')
            check(statuses and len(statuses) == len(checks) and set(statuses) <= set(PRECONDITION_STATUSES)
                  and pre.get('status') == derived, 'COVERAGE_OUTPUT_INVALID',
                  'The coverage helper must report the profile preconditions, separately from trie coverage.')
        return report

    # ----- verification -------------------------------------------------------------------------

    def run_binding(self, run, header):
        """Read-only binding of a run directory to this session before any verifier is called."""
        out = no_links(run)
        try:
            result = load(out / 'RESULT.json', 65536)
            binding = load(out / 'BINDING.json', 65536)
            spec = load(out / 'inputs/SCENARIO.json', 8 << 20)
            input_sha = sha(out / 'inputs/SCENARIO.json')
        except (OSError, ValueError) as error:
            raise SessionError('RUN_RECORD_INCOMPLETE', 'Use a completed run directory with its retained inputs.',
                               {'error': str(error)[:300]}) from error
        from ..cases.scenario.api import PROFILE as BACKEND_PROFILE
        from .. import config_overlay, dynamic_fee
        pairs = {BACKEND_PROFILE: execution.DOMAIN, dynamic_fee.PROFILE: dynamic_fee.DOMAIN, config_overlay.PROFILE: config_overlay.DOMAIN}
        check(binding.get('profile') in pairs and spec.get('schema') == pairs[binding.get('profile')], 'WRONG_PROFILE_EVIDENCE',
              'Only LP Rewards, Dynamic Fee OFF and config-overlay scenario runs of the hookr-buy/0.1 backends can be attached to this session.')
        engine = {dynamic_fee.PROFILE: dynamic_fee.ACCEPTED_DERIVATIVE_ENGINE,
                  config_overlay.PROFILE: config_overlay.ACCEPTED_OVERLAY_ENGINE}.get(binding['profile'], header['common']['engine'])
        check(spec.get('checkpoint') == header['checkpoint'], 'WRONG_SESSION_RESULT',
              'The run was produced at a different checkpoint.')
        check(binding.get('scenarioSha256') == input_sha and result.get('operationCommitment') == binding.get('operationCommitment')
              and result.get('scenarioCommitment') == spec.get('scenarioCommitment'), 'RUN_RECORD_INCONSISTENT',
              'The run record does not match its own retained input.')
        common = header['common']
        check(spec.get('poolId') == common['poolId'] and spec.get('environment') == common['environment']
              and spec.get('commonSetup') == common['commonSetup'] and spec.get('engine') == engine
              and type(spec.get('actions')) is list and len(spec['actions']) == 1 and spec['actions'][0].get('id') == common['actionId'],
              'INCOMPATIBLE_RUN_COMMON', 'The run used a different action, environment or engine binding.')
        return dict(profile=PROFILE, backendProfile=binding['profile'], operationCommitment=result['operationCommitment'],
                    scenarioCommitment=result['scenarioCommitment'], scenarioSha256=input_sha,
                    resultStatus=result.get('status'))

    def verify_run(self, run):
        # The existing scenario compare first runs the existing verifier on the retained run evidence,
        # in the SDK home that holds the run's own registered runtime.
        from .. import config_overlay, dynamic_fee
        profile = load(no_links(run) / 'BINDING.json', 65536).get('profile')
        kind = {dynamic_fee.PROFILE: DYNAMIC_KIND, config_overlay.PROFILE: OVERLAY_KIND}.get(profile, LP_KIND)
        return _sdk_call(self._sdk(dict(kind=kind)).compare, run)

    def admit_verification(self, outcome, binding):
        """Admit only the verifier's complete comparison of exactly this run; anything else records nothing."""
        check(type(outcome) is dict and outcome.get('status') == VERIFIED_STATUS, 'VERIFIER_RESULT_NOT_VERIFIED',
              f'The verifier did not return {VERIFIED_STATUS}; nothing was recorded.',
              {'status': str(outcome.get('status'))[:80] if type(outcome) is dict else type(outcome).__name__})
        check(outcome.get('scenarioCommitment') == binding['scenarioCommitment'], 'VERIFIER_RESULT_NOT_BOUND',
              'The verified comparison names a different scenario commitment than this run; nothing was recorded.')
        view = self.comparison_view(outcome)
        self.check_comparison(view, 'VERIFIER_RESULT_SHAPE')
        return view

    @staticmethod
    def check_comparison(view, code):
        worlds = view.get('worlds') if type(view) is dict else None
        check(type(view) is dict and view.get('status') == 'FROM_VERIFIER_OUTPUT' and type(worlds) is list
              and tuple(w.get('world') if type(w) is dict else None for w in worlds) == WORLDS, code,
              'A verified comparison has exactly one SCENARIO_BASELINE and one SCENARIO_VARIANT projection, in that order.')
        nets = [w.get('actorTargetTokenTransferNetBaseUnits') for w in worlds]
        delta = view.get('targetTokenTransferNetDeltaBaseUnits')
        check(all(type(n) is str and DECIMAL.fullmatch(n) for n in nets) and type(delta) is str and DECIMAL.fullmatch(delta)
              and int(delta) == int(nets[1]) - int(nets[0])
              and all(type(w.get('receiptStatus')) is int and type(w.get('gasUsed')) is int for w in worlds), code,
              'A verified comparison carries both receipt projections, both token nets and their exact difference.')

    @staticmethod
    def comparison_view(outcome):
        worlds = outcome.get('worlds')
        if type(worlds) is not list:
            return dict(status='UNRESOLVED', reason='VERIFIER_RETURNED_NO_WORLD_PROJECTIONS')
        rows = []
        for w in worlds:
            check(type(w) is dict and type(w.get('world')) is str, 'VERIFIER_RESULT_SHAPE', 'Unexpected world projection.')
            net = w.get('actorTargetTokenTransferNetBaseUnits', w.get('actorRhookTransferNetBaseUnits'))
            check(net is None or (type(net) is str and net.lstrip('-').isdigit()), 'VERIFIER_RESULT_SHAPE', 'Token amounts must be decimal strings.')
            rows.append(dict(world=w['world'], receiptStatus=w.get('receiptStatus'), gasUsed=w.get('gasUsed'),
                             actorTargetTokenTransferNetBaseUnits=net, outerSwapFeePips=w.get('outerSwapFeePips')))
        delta = outcome.get('targetTokenTransferNetDeltaBaseUnits', outcome.get('rhookTransferNetDeltaBaseUnits'))
        return dict(status='FROM_VERIFIER_OUTPUT', worlds=rows, targetTokenTransferNetDeltaBaseUnits=delta,
                    measure='ACTOR_TARGET_TOKEN_TRANSFER_EVENT_NET_IN_SUBJECT_RECEIPT')

    @staticmethod
    def verified_assurance(*, test_only):
        if test_only:
            return dict(verification='TEST_ONLY_NOT_EVIDENCE', nativeExecution='NOT_PERFORMED',
                        heterogeneousAgreement='NOT_EVALUATED', economicAssurance='UNRESOLVED', qualifiedClaims=0)
        return dict(verification='RECORDED_SCENARIO_EVIDENCE_VERIFIED_BY_EXISTING_VERIFIER',
                    nativeExecution='RECORDED_BY_THE_RUN_NOT_REPEATED_BY_VERIFICATION',
                    canonicalActualComparison='NOT_APPLICABLE_HYPOTHETICAL_SCENARIO',
                    heterogeneousAgreement='NOT_EVALUATED', economicAssurance='UNRESOLVED', qualifiedClaims=0)
