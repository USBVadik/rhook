"""Public Python API for the fixed historical Hookr case."""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
import time

from developer import cli as engine
from developer.files import canonical, load, no_links, read, require, save
from . import consent, runtime

CASE = 'hookr-pair03'


@dataclass(frozen=True)
class LpBps:
    """Replace RulesConfig.lpBps=100; native support is currently 0 and 50."""
    value: int

    def __post_init__(self):
        require(type(self.value) is int and 0 <= self.value <= 99, 'LP_BPS_INTEGER_0_TO_99_REQUIRED')


class SDK:
    def __init__(self, home=None):
        self.home = no_links(home or Path.home() / '.local/share/rhook-alpha')
        self.workspace = self.home / 'cases' / CASE

    def _context(self):
        require(not self.home.is_relative_to(runtime.PREFIX), 'HOME_INSIDE_INSTALLATION')
        return runtime.context()

    def inspect(self, case=CASE):
        require(case == CASE, 'UNSUPPORTED_CASE')
        self._context()
        if self.workspace.exists():
            from case_sdk.workspace import kit, planner
            workspace, saved = kit(self.workspace)
            value = planner(saved['nodePath'], 'inspect', workspace / 'BLOCK_PACKAGE.json')
            return dict(value, workspace=str(workspace))
        self.workspace.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        return engine.ordinary(['inspect', '--workspace', str(self.workspace), '--package',
                               str(runtime.PREFIX / 'assets/BLOCK_PACKAGE.json'), '--build-record', str(runtime.PREFIX / 'BUILD.json')])

    def plan(self, case=CASE, intervention=None):
        require(case == CASE and type(intervention) is LpBps, 'TYPED_LP_BPS_INTERVENTION_REQUIRED')
        self._context()
        require(self.workspace.exists(), 'INSPECT_CASE_FIRST')
        value = engine.ordinary(['plan', '--workspace', str(self.workspace), '--expected-old', '100', '--lp-bps', str(intervention.value)])
        if value.get('status') == 'PLANNED':
            value['nativeSupported'] = intervention.value in (0, 50)
            value['lpBps'] = intervention.value
        return value

    def _resolve(self, plan_id):
        authenticated = self._context()
        from case_sdk.contract import prepare_request, validate_runtime
        from case_sdk.workspace import resolve_plan
        resolved = resolve_plan(self.workspace, plan_id)
        binding = resolved['binding']
        validated = validate_runtime(read(self.workspace / 'BLOCK_PACKAGE.json'), read(binding['runtimePlanPath'], 32768))
        paths = {key: binding[key] for key in ('workspace', 'planId', 'outputPath', 'packagePath', 'semanticPlanPath', 'runtimePlanPath')}
        expected = prepare_request(load(resolved['buildPath']), validated, paths)
        require(canonical(binding) == canonical(expected), 'PLAN_BINDING_DRIFT')
        return load(binding['semanticPlanPath']), binding, authenticated

    def describe(self, plan_id):
        semantic, binding, _ = self._resolve(plan_id)
        return {'status': 'PLAN_AUTHENTICATED', 'semantic': semantic, 'binding': binding,
                'nativeSupported': semantic['newValue'] in ('0', '50'), 'authorityIssued': False}

    def authorize(self, plan_id, *, local_owner=False, mac_ready=False):
        semantic, binding, authenticated = self._resolve(plan_id)
        require(semantic['newValue'] in ('0', '50'), 'PLANNING_ONLY_VALUE_NATIVE_NOT_SUPPORTED')
        _, context, key = authenticated
        return consent.issue(self.workspace, binding, context, key, local_owner=local_owner, mac_ready=mac_ready)

    def replay(self, plan_id, authority):
        began = time.monotonic()
        semantic, binding, authenticated = self._resolve(plan_id)
        require(semantic['newValue'] in ('0', '50'), 'PLANNING_ONLY_VALUE_NATIVE_NOT_SUPPORTED')
        _, context, key = authenticated
        internal = consent.consume(authority, self.workspace, binding, context, key)
        try:
            value = engine.replay(self.workspace, plan_id, internal, began)
        except BaseException as error:
            save(internal.parent / 'RESULT.json', {'status': 'INTERRUPTED_UNVERIFIED',
                 'causeCode': type(error).__name__ + ': ' + str(error)[:240],
                 'nativeInvocations': None, 'operationPermanentlyClosed': True, 'automaticRetry': False})
            raise
        save(internal.parent / 'RESULT.json', value)
        return dict(value, runDirectory=binding['outputPath'])

    def verify(self, run):
        pins, _, _ = self._context()
        return engine.recorded(no_links(run), pins)

    def compare(self, run):
        value = self.verify(run)
        require(value.get('status') == 'RECORDED_INTEGRITY_PASS', 'VERIFIED_RESULT_REQUIRED')
        worlds = value['worlds']
        actual, branch = worlds['ACTUAL'], worlds['BRANCH']
        a, b = (int(world['buyerRhookTransferNetBaseUnits']) for world in (actual, branch))
        gas_delta = int(branch['subjectGasUsed']) - int(actual['subjectGasUsed'])
        require(str(b - a) == value['buyerRhookTransferNetDeltaBaseUnits'] and str(gas_delta) == value['subjectGasDelta'], 'VERIFIED_ECONOMIC_DELTA_MISMATCH')
        with localcontext() as ctx:
            ctx.prec = 50
            percent = format(Decimal(b - a) * 100 / Decimal(a), 'f') if a else None
        return {'status': 'VERIFIED_COMPARISON', 'buyerTransferNetActualBaseUnits': str(a),
                'buyerTransferNetBranchBaseUnits': str(b), 'buyerTransferNetDeltaBaseUnits': str(b - a),
                'buyerTransferNetIncreasePercent': percent, 'subjectGasDelta': str(gas_delta),
                'outerSwapFeePips': {name: worlds[name]['outerSwap']['feePips'] for name in ('ACTUAL', 'BRANCH')},
                'hookFeeEvents': {name: worlds[name]['hookFeeEvents'] for name in ('ACTUAL', 'BRANCH')},
                'economicAssurance': 'UNRESOLVED', 'heterogeneousAgreement': 'NOT_EVALUATED', 'qualifiedClaims': 0,
                'limitation': 'Receipt Transfer-event net; not token storage balances or a new EVM replay. Single Go/Nitro engine.'}
