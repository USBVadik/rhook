"""Case-neutral registry and planning API; execution is an explicit backend."""
from pathlib import Path
import re
import secrets
from developer.files import canonical, digest, load, read, require, save, sync
from .adapters import get_adapter
from .registry import Registry
from .capsule import validate, MAX_PACKAGE

class CaseSDK:

    def __init__(self, home):
        self.registry = Registry(home)
        self.home = self.registry.home

    def package_case(self, package, output, *, case_id, adapter, subject_index, input_commitment, witness_commitment, original_word=None):
        from developer.files import no_links
        raw = read(package, MAX_PACKAGE)
        d = get_adapter({'adapter': {'id': adapter}}).capsule(raw, case_id=case_id, subject_index=subject_index, input_commitment=input_commitment, witness_commitment=witness_commitment, original_word=original_word)
        validate(d, raw)
        output = no_links(output)
        output.mkdir(mode=0o700)
        save(output / 'CAPSULE.json', d)
        import os
        with (output / 'BLOCK_PACKAGE.json').open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        sync(output)
        sync(output.parent)
        return {'status': 'CAPSULE_PACKAGED', 'capsuleId': d['capsuleId'], 'authentication': 'UNAUTHENTICATED', 'witnessClosure': 'NOT_EVALUATED'}

    def import_case(self, directory):
        return self.registry.import_case(directory)

    def list_cases(self):
        return self.registry.list_cases()

    def inspect(self, case):
        return self.registry.inspect(case)

    def plan(self, case, intervention):
        from .admission.catalogue import resolve_plan
        _, d = self.registry.resolve(case)
        runtime = resolve_plan(d, intervention)
        self.registry._prepare()
        ref = 'c-' + secrets.token_hex(16)
        body = {'schema': 'rhook/case-plan/0.1', 'planId': ref, 'caseId': case, 'capsuleId': d['capsuleId'], 'adapter': d['adapter']['id'], 'intervention': intervention, 'runtimePlan': runtime}
        body['planCommitment'] = digest(canonical(body))
        directory = self.home / 'plans' / ref
        directory.mkdir(mode=0o700)
        sync(directory.parent)
        save(directory / 'PLAN.json', body)
        return {'status': 'PLANNED', 'planId': ref, 'capsuleId': d['capsuleId'], 'planCommitment': body['planCommitment'], 'executionAuthorized': False, 'branchResult': None, 'witnessClosure': 'NOT_EVALUATED'}

    def describe(self, ref):
        from .admission.catalogue import resolve_plan
        require(type(ref) is str and re.fullmatch('c-[0-9a-f]{32}', ref), 'PLAN_ID')
        p = load(self.home / 'plans' / ref / 'PLAN.json', 65536)
        body = dict(p)
        pin = body.pop('planCommitment')
        require(pin == digest(canonical(body)) and p['planId'] == ref and (p['schema'] == 'rhook/case-plan/0.1'), 'PLAN_INTEGRITY')
        _, d = self.registry.resolve(p['caseId'])
        require(d['capsuleId'] == p['capsuleId'] and d['adapter']['id'] == p['adapter'] and (resolve_plan(d, p['intervention']) == p['runtimePlan']), 'PLAN_CASE_OR_ADAPTER_DRIFT')
        return p

    def interventions(self):
        from .admission.catalogue import entries
        return entries()

    def admission(self, ref):
        from .admission.catalogue import describe
        p = self.describe(ref)
        _, capsule = self.registry.resolve(p['caseId'])
        return describe(capsule, p['intervention'])

    def assurance(self, ref, *, evidence=None):
        from .admission.assurance import report
        p = self.describe(ref)
        _, capsule = self.registry.resolve(p['caseId'])
        return report(capsule, p['intervention'], evidence)

    def _case_backend(self, case):
        from .backends import get_backend
        _, capsule = self.registry.resolve(case)
        return get_backend(capsule['execution']['profile'])

    def register_runtime(self, path):
        from .backends import get_backend
        configuration = load(path, 65536)
        return get_backend(configuration.get('profile')).configure(self, path)

    def authenticate(self, case, *, trusted_checkpoint=None):
        return self._case_backend(case).authenticate(self, case, trusted_checkpoint=trusted_checkpoint)

    def operation(self, ref, *, trusted_checkpoint=None):
        """Review the exact local binding without issuing consent or running EVM."""
        plan = self.describe(ref)
        return self._case_backend(plan['caseId']).operation(self, ref, trusted_checkpoint=trusted_checkpoint)

    def authorize(self, ref, *, local_owner=False, mac_ready=False, trusted_checkpoint=None, expected_operation=None):
        require(local_owner is True, 'EXPLICIT_LOCAL_OWNER_CONSENT_REQUIRED')
        plan = self.describe(ref)
        options = dict(local_owner=local_owner, mac_ready=mac_ready, trusted_checkpoint=trusted_checkpoint)
        if expected_operation is not None:
            options['expected_operation'] = expected_operation
        return self._case_backend(plan['caseId']).authorize(self, ref, **options)

    def replay(self, ref, authority):
        plan = self.describe(ref)
        return self._case_backend(plan['caseId']).replay(self, ref, authority)

    def verify(self, run):
        from .backends import get_backend
        from developer.files import no_links
        run = no_links(run)
        require(run.parent == self.home / 'runs', 'RUN_HOME_REQUIRED')
        binding = load(run / 'BINDING.json', 65536)
        return get_backend(binding.get('profile')).verify(self, run)

    def compare(self, run):
        verified = self.verify(run)
        _, d = self.registry.resolve(verified['caseId'])
        return dict(get_adapter(d).compare(verified), caseId=d['caseId'], capsuleId=d['capsuleId'])

    def capture_case(self, output, **options):
        from .forge import capture_case
        return capture_case(self, output, **options)

    def forge_case(self, package, output, **options):
        from .forge import forge_case
        return forge_case(self, package, output, **options)

    def diagnose(self, case, *, trusted_checkpoint=None):
        from .forge import diagnose
        return diagnose(self, case, trusted_checkpoint=trusted_checkpoint)

    def check_case(self, case, *, trusted_checkpoint=None):
        report = self.diagnose(case, trusted_checkpoint=trusted_checkpoint)
        if report['knownDependenciesPresent']:
            authenticated = self.authenticate(case, trusted_checkpoint=trusted_checkpoint)
            return dict(report, status='READY_FOR_BOUNDED_NATIVE_ATTEMPT', nativeAdmission=authenticated,
                        limitation='Known prerequisites passed. Dynamic reads/write closure and actual execution are untested; a fresh grant and host admission remain required.')
        return report

    def select_recent_case(self, output, *, read_only=False):
        from .forge import run
        return run(self, output, action='select', read_only=read_only)

    def capture_recent_case(self, output, **options):
        from .forge import capture_recent_case
        return capture_recent_case(self, output, **options)

    def qualify_root(self, output, *, read_only=False):
        from .forge import run
        return run(self, output, action='qualify-root', read_only=read_only)

    def watch_case(self, output, **options):
        from .forge import watch_case
        return watch_case(self, output, **options)

    def scenario_pool(self, pool_id=None):
        from .scenario.api import select_pool
        return select_pool(pool_id)

    def configure_scenario(self, **options):
        from .scenario.api import configure
        return configure(self, **options)

    def register_scenario_runtime(self, path):
        from .scenario.api import register
        return register(self, path)

    def register_scenario_host(self, sensor):
        from .scenario.api import register_host
        return register_host(self, sensor)

    def prepare_scenario(self, capture, **options):
        from .scenario.api import prepare
        return prepare(self, capture, **options)

    def acquire_scenario(self, ref, output, **options):
        from .scenario.api import acquire
        return acquire(self, ref, output, **options)

    def check_scenario(self, capture):
        from .scenario.api import check
        return check(self, capture)

    def run_scenario(self, capture, **options):
        from .scenario.api import run
        return run(self, capture, **options)

    def verify_scenario(self, run):
        from .scenario.api import verify
        return verify(self, run)

    def compare_scenario(self, run):
        from .scenario.api import compare
        return compare(self, run)

    def inspect_recorded_scenario(self, bundle):
        from .scenario.recorded import inspect_recorded
        return inspect_recorded(bundle)

    def verify_recorded_scenario(self, bundle):
        from .scenario.recorded import verify_recorded
        return verify_recorded(bundle)

    def compare_recorded_scenario(self, bundle):
        from .scenario.recorded import compare_recorded
        return compare_recorded(bundle)
