"""SDK 0.6 G5 preflight: reviewed engine identity, the per-operation native gate, offline preparation and the
pre-registered parity comparators. Offline only: no worker, EVM, network, consent or authority.

Optional environment:
  RHOOK_ACCEPTED_RECORDS  records/{lp23,dynamic-fee-off,combined} of the accepted SDK 0.4 runs (private; read-only).
  RHOOK_PROFILE_NODE      a Node binary; with the pinned adapter node_modules present, runs the trie-only target
                          authenticator on the accepted lp23 input.
"""
import copy
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from developer.files import canonical, digest
from rhook_alpha import profile_descriptor as pd
from rhook_alpha import profile_overlay as po
from rhook_alpha import profile_parity as pp
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.scenario import api
from rhook_alpha.execution import ExecutionError, ExecutionSDK
from tests_cases.test_profile_descriptor import (DYN_OFF, RAW, D, SYNTHETIC_CONFIG, _accepting, _capture, _test_catalogue, lp, mutate,
                                                 synthetic_source, tuning)

REC = Path(os.environ['RHOOK_ACCEPTED_RECORDS']) if os.environ.get('RHOOK_ACCEPTED_RECORDS') else None
NODE = os.environ.get('RHOOK_PROFILE_NODE')
DEPS = pd.SDK_ROOT / 'engine/adapters/hookr-case/node_modules'
G4B = dict(sourceSha256='4db4269aad9e28970eb3b13508366771c12827aa8fc5687399e28ff418251546',
           binarySha256='a56db9e53a13331e21c8e45fbb20632a7bc13ef12c864afedf4169a90b35ae04',
           policySha256='792b13a533f79d8d66ade565a5ad41cdb45bd1da4684e06dcdc1825c1a04abc6')
HOST = dict(profile=api.PROFILE_HOST, policySha256='9' * 64, sensor=dict(path='/nonexistent', sha256='8' * 64), sdkFilesCommitment='7' * 64)
COVERED = dict(status='STATIC_DEPENDENCIES_COVERED', networkRequestsPerformed=0, profile=dict(id='hookr-buy/0.1'),
               preconditions=dict(status='SATISFIED', checks=[dict(status='SATISFIED')]))
TARGETS = dict(status='PROFILE_TARGETS_MPT_AUTHENTICATED', schema='rhook/profile-target-state/0.1', contracts={}, targets={})


def runtime_of(engine, profile=api.PROFILE_OVERLAY_PROFILE):
    return dict(schema='rhook/scenario-runtime/0.1', profile=profile, sourceCommitment=engine['sourceSha256'], policySha256=engine['policySha256'],
                files=dict(worker=dict(path='/nonexistent', sha256=engine['binarySha256']), node=dict(path='/nonexistent', sha256='5' * 64),
                           sensor=dict(path='/nonexistent', sha256='6' * 64)))


class Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rhook-g5-')
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir(mode=0o700)
        self.sdk = CaseSDK(self.home)

    def tearDown(self):
        self.tmp.cleanup()


class EngineIdentity(Home):
    def test_record_is_the_g4b_identity_and_the_embedded_descriptor_and_catalogue(self):
        rec = pd.PROFILE_ENGINE_RECORD
        self.assertEqual(pd.ACCEPTED_PROFILE_ENGINE, G4B)
        self.assertEqual((rec['engine'], rec['profile'], rec['status']), (G4B, api.PROFILE_OVERLAY_PROFILE, 'REVIEWED_ENGINE_IDENTITY_NOT_EXECUTION_AUTHORIZATION'))
        self.assertEqual(rec['descriptor'], dict(profileId='hookr-1', revision=2, sha256=digest(RAW)))
        self.assertEqual(rec['catalogueSha256'], digest((pd.DESCRIPTOR_DIR / 'CATALOGUE.json').read_bytes()))
        self.assertEqual(G4B['policySha256'], api.POLICY_SHA)
        # The embedded catalogue keeps its pre-G4B text; it is part of the worker source commitment.
        entry = json.loads((pd.DESCRIPTOR_DIR / 'CATALOGUE.json').read_bytes())['entries'][0]
        self.assertEqual(entry['review']['nativeExecution'], 'NOT_ACCEPTED_NO_ENGINE_IDENTITY_G4B_G5_REQUIRED')

    def test_record_refuses_other_descriptor_catalogue_or_inconsistent_record(self):
        self.assertEqual(pd.require_engine_record(RAW)['catalogueSha256'], pd.PROFILE_ENGINE_RECORD['catalogueSha256'])
        other = mutate(lambda d: d.update(revision=3))
        with self.assertRaises(pd.DescriptorError) as caught:
            pd.require_engine_record(other)
        self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_RECORD')
        cat = _test_catalogue(self.home / 'cat', RAW, ['OFFLINE_PREPARATION', 'NATIVE_EXECUTION'])
        with unittest.mock.patch.object(pd, 'DESCRIPTOR_DIR', cat):
            with self.assertRaises(pd.DescriptorError) as caught:
                pd.require_engine_record(RAW)
            self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_RECORD')
        for patch in (dict(PROFILE_ENGINE_RECORD=dict(pd.PROFILE_ENGINE_RECORD, engine=dict(G4B, binarySha256='f' * 64))),
                      dict(PROFILE_ENGINE_RECORD=dict(pd.PROFILE_ENGINE_RECORD, profile=api.OVERLAY_PROFILE)),
                      dict(PROFILE_ENGINE_RECORD=dict(pd.PROFILE_ENGINE_RECORD, status='EXECUTION_AUTHORIZED')),
                      dict(PROFILE_ENGINE_RECORD=dict(pd.PROFILE_ENGINE_RECORD, buildVerification='NOT_VERIFIED')),
                      dict(PROFILE_ENGINE_RECORD={k: v for k, v in pd.PROFILE_ENGINE_RECORD.items() if k != 'buildVerification'}),
                      dict(PROFILE_ENGINE_RECORD=dict(pd.PROFILE_ENGINE_RECORD, executionAuthorized=True)),
                      dict(PROFILE_ENGINE_RECORD=dict(pd.PROFILE_ENGINE_RECORD, descriptor=dict(pd.PROFILE_ENGINE_RECORD['descriptor'], note='x'))),
                      dict(PROFILE_ENGINE_RECORD=None)):
            with unittest.mock.patch.multiple(pd, **patch):
                with self.assertRaises(pd.DescriptorError) as caught:
                    pd.require_engine_record(RAW)
                self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_RECORD')

    def test_shipped_operation_matrix_with_the_reviewed_identity(self):
        """Shipped descriptor, catalogue and the reviewed identity: LP23, DF OFF and both bind; Tuning stays
        refused; any other identity field is refused. A binding is a proposal, not an authorization."""
        v = dict(scenarioCommitment='3' * 64, scenarioSha256='4' * 64)
        for items in ([lp(23)], [DYN_OFF], [DYN_OFF, lp(23)]):
            plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=items)
            b = api.operation_binding(self.sdk, plan, v, runtime_of(G4B), HOST, host_profile=api.PROFILE_HOST)
            self.assertEqual(b['profileDescriptor'], pd.PROFILE_ENGINE_RECORD['descriptor'])
            self.assertEqual((b['hostAdmission']['profile'], b['maximumInvocations'], b['automaticRetry']),
                             (api.PROFILE_HOST, {'SCENARIO_BASELINE': 1, 'SCENARIO_VARIANT': 1}, False))
            # The binding takes source and binary from the registered runtime and the policy from this SDK
            # (registration already requires runtime policy == POLICY_SHA); a different policy is the patched case.
            for field in ('sourceSha256', 'binarySha256'):
                r = runtime_of(dict(G4B, **{field: 'f' * 64}))
                with self.assertRaises(pd.DescriptorError) as caught:
                    api.operation_binding(self.sdk, plan, v, r, HOST, host_profile=api.PROFILE_HOST)
                self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_NOT_ACCEPTED', field)
            with unittest.mock.patch.object(api, 'POLICY_SHA', 'f' * 64):
                r = runtime_of(dict(G4B, policySha256='f' * 64))
                with self.assertRaises(pd.DescriptorError) as caught:
                    api.operation_binding(self.sdk, plan, v, r, HOST, host_profile=api.PROFILE_HOST)
                self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_NOT_ACCEPTED', 'policySha256')
        for items in ([tuning(8000, 1)], [lp(23), tuning(8000, 1)]):
            plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=pd.canonical_interventions(D, items))
            with self.assertRaises(pd.DescriptorError) as caught:
                api.operation_binding(self.sdk, plan, v, runtime_of(G4B), HOST, host_profile=api.PROFILE_HOST)
            self.assertEqual(caught.exception.code, 'PROFILE_KIND_REVIEW_INSUFFICIENT')


class NativeGate(Home):
    """api.run and ProfileOverlayExecutionSDK.run refuse a profile-overlay operation without the owner's record of
    that exact operation, before any check, attempt marker, consent key, authority or worker."""

    ENGINE = dict(sourceSha256='1' * 64, binarySha256='2' * 64, policySha256=api.POLICY_SHA)

    def setUp(self):
        super().setUp()
        self.raw = mutate(lambda d: d['chain'].update(chainConfigSha256=SYNTHETIC_CONFIG))
        self.cat = _test_catalogue(self.home / 'cat', self.raw, ['OFFLINE_PREPARATION', 'NATIVE_EXECUTION'])
        self.patches = [unittest.mock.patch.dict(pd.WORKER_BOUNDS, chainConfigSha256=SYNTHETIC_CONFIG),
                        unittest.mock.patch.object(pd, 'DESCRIPTOR_DIR', self.cat), _accepting(self.ENGINE, self.raw, self.cat),
                        unittest.mock.patch.object(api, 'runtime', return_value=runtime_of(self.ENGINE)),
                        unittest.mock.patch.object(api, 'select_host', return_value=HOST),
                        unittest.mock.patch('rhook_alpha.cases.workflow.active_group', return_value=4321),
                        unittest.mock.patch.object(sys, 'platform', 'darwin'), unittest.mock.patch('platform.machine', return_value='arm64')]
        for p in self.patches:
            p.start()
        self.plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=[DYN_OFF, lp(23)])
        self.capture, _ = _capture(self.sdk, self.plan, pd.build_spec(synthetic_source(), self.raw, [DYN_OFF, lp(23)], self.ENGINE))
        self.b = api.prepare(self.sdk, self.capture, host_profile=api.PROFILE_HOST)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        super().tearDown()

    def _no_authority(self):
        return [unittest.mock.patch.object(api, 'check', side_effect=AssertionError('no worker check before the gate')),
                unittest.mock.patch.object(api.authority, 'issue', side_effect=AssertionError('no authority')),
                unittest.mock.patch.object(api.native, 'guards', side_effect=AssertionError('no guards'))]

    def _run(self, **kw):
        options = dict(local_owner=True, mac_ready=True, host_profile=api.PROFILE_HOST, expected_operation=self.b['operationCommitment'])
        options.update(kw)
        return api.run(self.sdk, self.capture, **options)

    def _authorize(self, now=None):
        with unittest.mock.patch.object(api, 'check', return_value=dict(status='AUTHENTICATED_SCENARIO_INPUT', nativeExecutions=0)):
            return api.authorize_profile(self.sdk, self.capture, expected_operation=self.b['operationCommitment'], local_owner=True, now=now)

    def test_run_without_authorization_stops_before_anything(self):
        stops = self._no_authority()
        for p in stops:
            p.start()
        try:
            with self.assertRaises(ValueError) as caught:
                self._run()
            self.assertIn('PROFILE_NATIVE_AUTHORIZATION_REQUIRED', str(caught.exception))
            with self.assertRaises(ValueError) as caught:
                self._run(host_profile='v2', expected_operation=None)
            self.assertIn('PROFILE_NATIVE_HOST_V4_REQUIRED', str(caught.exception))
        finally:
            for p in stops:
                p.stop()
        for name in ('scenarios/consents', 'scenarios/runs', 'scenarios/preflight', 'scenarios/execution-attempts'):
            self.assertFalse((self.home / name).exists(), name)

    def test_authorization_is_exact_private_once_and_bounded(self):
        with self.assertRaises(ValueError) as caught:
            api.authorize_profile(self.sdk, self.capture, expected_operation=self.b['operationCommitment'])
        self.assertIn('EXPLICIT_LOCAL_OWNER_REQUIRED', str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            api.authorize_profile(self.sdk, self.capture, expected_operation='0' * 64, local_owner=True)
        self.assertIn('EXACT_PROFILE_OPERATION_REQUIRED', str(caught.exception))
        value = self._authorize(now=1000)
        path = Path(value['authorization'])
        self.assertEqual((value['status'], value['consent'], value['nativeExecutions']), ('PROFILE_NATIVE_AUTHORIZATION_RECORDED', 'NOT_CREATED', 0))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(api.require_profile_authorization(self.sdk, self.b, api.PROFILE_HOST, now=1000)['operationCommitment'], self.b['operationCommitment'])
        with self.assertRaises(ValueError) as caught:
            self._authorize(now=1001)
        self.assertIn('PROFILE_NATIVE_AUTHORIZATION_EXISTS', str(caught.exception))
        end = 1000 + api.PROFILE_AUTHORIZATION_SECONDS
        # run() needs more remaining lifetime than the 600 s consent grant; the facade needs its larger launch margin.
        self.assertEqual(api.require_profile_authorization(self.sdk, self.b, api.PROFILE_HOST, now=end - api.PROFILE_RUN_MARGIN_SECONDS)['expiresUnix'], end)
        self.assertGreater(api.PROFILE_RUN_MARGIN_SECONDS, 600)
        self.assertGreater(api.PROFILE_LAUNCH_MARGIN_SECONDS, api.PROFILE_RUN_MARGIN_SECONDS)
        for now, code in [(999, 'PROFILE_NATIVE_AUTHORIZATION_EXPIRED'), (end, 'PROFILE_NATIVE_AUTHORIZATION_EXPIRED'),
                          (end - api.PROFILE_RUN_MARGIN_SECONDS + 1, 'PROFILE_NATIVE_AUTHORIZATION_EXPIRED')]:
            with self.assertRaises(ValueError) as caught:
                api.require_profile_authorization(self.sdk, self.b, api.PROFILE_HOST, now=now)
            self.assertIn(code, str(caught.exception))
        # Another binding (any field) is not authorized by this record.
        for field, value_ in [('scenarioSha256', '0' * 64), ('binarySha256', '0' * 64), ('planId', 'c-' + '0' * 32)]:
            other = dict(self.b, **{field: value_})
            with self.assertRaises(ValueError) as caught:
                api.require_profile_authorization(self.sdk, other, api.PROFILE_HOST, now=1000)
            self.assertIn('PROFILE_NATIVE_AUTHORIZATION_REQUIRED', str(caught.exception))
        original = path.read_bytes()
        for edit in (lambda v: v.update(maximumRuns=2), lambda v: v.update(automaticRetry=True), lambda v: v.update(extra=1),
                     lambda v: v.update(expiresUnix=v['notBeforeUnix'] + api.PROFILE_AUTHORIZATION_SECONDS + 1)):
            v = json.loads(original)
            edit(v)
            path.write_bytes(canonical(v) + b'\n')
            with self.assertRaises(ValueError):
                api.require_profile_authorization(self.sdk, self.b, api.PROFILE_HOST, now=1000)
        path.write_bytes(original)
        path.chmod(0o644)
        with self.assertRaises(ValueError) as caught:
            api.require_profile_authorization(self.sdk, self.b, api.PROFILE_HOST, now=1000)
        self.assertIn('PROFILE_NATIVE_AUTHORIZATION_REQUIRED', str(caught.exception))
        path.chmod(0o600)
        path.rename(path.with_suffix('.real'))
        path.symlink_to(path.with_suffix('.real'))
        with self.assertRaises(ValueError):
            api.require_profile_authorization(self.sdk, self.b, api.PROFILE_HOST, now=1000)

    def test_authorization_refused_for_a_started_or_closed_operation(self):
        marker = self.home / 'scenarios/execution-attempts' / (self.b['operationCommitment'] + '.json')
        marker.parent.mkdir(mode=0o700, parents=True)
        marker.write_text('{}\n')
        with self.assertRaises(ValueError) as caught:
            self._authorize()
        self.assertIn('OPERATION_ALREADY_CLOSED_OR_STARTED', str(caught.exception))
        self.assertFalse((self.home / api.PROFILE_AUTHORIZATIONS).exists())

    def _key(self):
        key = self.home / 'scenarios/.consent.key'
        key.write_bytes(os.urandom(32))
        key.chmod(0o600)

    def _child(self, observe):
        """api.run of the child with the native guards, host power observation and execution stubbed."""
        import contextlib
        return [unittest.mock.patch.object(api, 'check', return_value=dict(status='AUTHENTICATED_SCENARIO_INPUT')),
                unittest.mock.patch.object(api.native, 'guards', return_value=(lambda home: contextlib.nullcontext(), None, None, None)),
                unittest.mock.patch('rhook_alpha.cases.scenario.power.observe', side_effect=observe),
                unittest.mock.patch.object(api, '_execute', side_effect=lambda sdk, capture, out, b, r, body, *a, **k: dict(status='EXECUTE_STUB', body=body))]

    def _with(self, patches, fn):
        for p in patches:
            p.start()
        try:
            return fn()
        finally:
            for p in reversed(patches):
                p.stop()

    def test_child_opens_the_attempt_only_after_its_authorization_check(self):
        self._key()
        marker = self.home / 'scenarios/execution-attempts' / (self.b['operationCommitment'] + '.json')
        # No record: refused before the marker, so nothing is consumed.
        with self.assertRaises(ValueError) as caught:
            self._with(self._child(lambda d: None), self._run)
        self.assertIn('PROFILE_NATIVE_AUTHORIZATION_REQUIRED', str(caught.exception))
        self.assertFalse(marker.exists())
        # With the record: the marker exists before host observation, and names the record.
        record = self._authorize()
        seen = {}
        def observe(directory):
            seen['markerAtObservation'] = marker.exists()
            raise RuntimeError('SENTINEL_AT_POWER')
        with self.assertRaises(RuntimeError):
            self._with(self._child(observe), self._run)
        stored = json.loads(marker.read_bytes())
        value = json.loads(Path(record['authorization']).read_bytes())
        self.assertEqual((seen['markerAtObservation'], stored['openedBy'], stored['profileAuthorizationSha256'], stored['profileAuthorizationExpiresUnix']),
                         (True, 'cases.scenario.api.run', digest(canonical(value)), value['expiresUnix']))
        self.assertFalse((self.home / 'scenarios/consents').exists())
        # A second launch of the same operation is refused at the marker, before any consent.
        with self.assertRaises(ValueError) as caught:
            self._with(self._child(lambda d: None), self._run)
        self.assertIn('OPERATION_ALREADY_ATTEMPTED', str(caught.exception))
        self.assertFalse((self.home / 'scenarios/consents').exists())

    def test_record_changed_after_the_marker_stops_before_consent(self):
        self._key()
        record = Path(self._authorize()['authorization'])
        def observe(directory):
            v = json.loads(record.read_bytes())
            v['expiresUnix'] -= 1
            record.write_bytes(canonical(v) + b'\n')
        with self.assertRaises(ValueError) as caught:
            self._with(self._child(observe), self._run)
        self.assertIn('PROFILE_NATIVE_AUTHORIZATION_CHANGED', str(caught.exception))
        self.assertFalse((self.home / 'scenarios/consents').exists())

    def test_consent_grant_never_outlives_the_authorization(self):
        import time
        self._key()
        now = int(time.time())
        self._authorize(now=now - api.PROFILE_AUTHORIZATION_SECONDS + 700)
        end = now + 700
        # 150 s pass between the in-lock checks and authority.issue/consume (their clock only).
        issue, consume = api.authority.issue, api.authority.consume
        later = lambda: int(time.time()) + 150
        with unittest.mock.patch.object(api.authority, 'issue', side_effect=lambda root, b, key, **k: issue(root, b, key, now=later(), **k)), \
                unittest.mock.patch.object(api.authority, 'consume', side_effect=lambda g, root, b, key, **k: consume(g, root, b, key, now=later(), **k)):
            value = self._with(self._child(lambda d: None), self._run)
        self.assertEqual(value['status'], 'EXECUTE_STUB')
        self.assertLessEqual(value['body']['expiresUnix'], end)
        self.assertLess(value['body']['expiresUnix'], value['body']['notBeforeUnix'] + 600)
        from rhook_alpha.cases import authority
        with tempfile.TemporaryDirectory() as tmp:
            b = dict(self.b, planId='c-' + 'e' * 32)
            with self.assertRaises(ValueError) as caught:
                authority.issue(Path(tmp), b, b'k' * 32, now=1000, not_after=1179)
            self.assertIn('CONSENT_AUTHORIZATION_WINDOW', str(caught.exception))
            self.assertFalse((Path(tmp) / b['planId']).exists())
            grant = authority.issue(Path(tmp), b, b'k' * 32, now=1000)
            self.assertEqual(json.loads(grant.read_bytes())['body']['expiresUnix'], 1600)

    def test_execution_sdk_refuses_before_the_attempt_marker(self):
        sdk = po.ProfileOverlayExecutionSDK(self.home)
        op = dict(operationCommitment=self.b['operationCommitment'], binding=self.b)
        with unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, '_prepared', return_value=(self.capture, {})), \
                unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, 'operation', return_value=op), \
                unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, '_launch', side_effect=AssertionError('no launch')), \
                unittest.mock.patch.object(ExecutionSDK, 'run', side_effect=AssertionError('never the parent-marker runner')):
            with self.assertRaises(ExecutionError) as caught:
                sdk.run(self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / 'evidence', local_owner=True, mac_ready=True)
            self.assertEqual(caught.exception.code, 'PROFILE_NATIVE_AUTHORIZATION_REQUIRED')
            with self.assertRaises(ExecutionError) as caught:
                sdk.run(self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / 'evidence', local_owner=True, mac_ready=True,
                        host_profile='v2')
            self.assertEqual(caught.exception.code, 'PROFILE_NATIVE_HOST_V4_REQUIRED')
            with self.assertRaises(ExecutionError) as caught:
                sdk.run(self.capture, operation='0' * 64, evidence=self.home.parent / 'evidence', local_owner=True, mac_ready=True)
            self.assertEqual(caught.exception.code, 'OPERATION_MISMATCH')
        self.assertFalse((self.home / 'scenarios/execution-attempts').exists())
        self.assertFalse((self.home.parent / 'evidence').exists())

    def test_launcher_writes_no_marker_and_reports_consumption_from_the_child(self):
        import time
        now = int(time.time())
        self._authorize(now=now - api.PROFILE_AUTHORIZATION_SECONDS + (api.PROFILE_RUN_MARGIN_SECONDS + api.PROFILE_LAUNCH_MARGIN_SECONDS) // 2)
        sdk = po.ProfileOverlayExecutionSDK(self.home)
        op = dict(operationCommitment=self.b['operationCommitment'], binding=self.b, outputPath=self.b['outputPath'])
        marker = self.home / 'scenarios/execution-attempts' / (self.b['operationCommitment'] + '.json')
        fixed = [unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, '_prepared', return_value=(self.capture, {})),
                 unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, 'operation', return_value=op)]
        # Less than the launch margin left: advisory refusal, nothing written.
        with self.assertRaises(ExecutionError) as caught:
            self._with(fixed + [unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, '_launch', side_effect=AssertionError('no launch'))],
                       lambda: sdk.run(self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / 'e0', local_owner=True, mac_ready=True))
        self.assertEqual(caught.exception.code, 'PROFILE_NATIVE_AUTHORIZATION_EXPIRED')
        self.assertFalse(marker.exists() or (self.home.parent / 'e0').exists())
        (self.home / api.PROFILE_AUTHORIZATIONS / (self.b['operationCommitment'] + '.json')).unlink()
        self._authorize()
        refusal = json.dumps(dict(status='INPUT_OR_RUNTIME_STOP', causeCode='PROFILE_NATIVE_AUTHORIZATION_EXPIRED', automaticRetry=False)).encode()
        process = dict(ownedChildReaped=True, workflowGroupGone=True, cleanupError=None, exitCode=1, stop=None)
        launched = []
        def child_refuses(command, *a, **k):
            launched.append(command)
            return process, refusal, b''
        value = self._with(fixed + [unittest.mock.patch.object(api.native, 'capture_workflow', side_effect=child_refuses)],
                           lambda: sdk.run(self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / 'e1', local_owner=True, mac_ready=True))
        self.assertEqual((value['status'], value['operationPermanentlyClosed'], value['attemptConsumed'], value['causeCode']),
                         ('EXECUTION_STOP', False, False, 'PROFILE_NATIVE_AUTHORIZATION_EXPIRED'))
        self.assertFalse(marker.exists())
        self.assertEqual(launched[0][launched[0].index('scenario-run'):],
                         ['scenario-run', str(self.capture), '--local-owner', '--mac-ready', '--host-admission', api.PROFILE_HOST,
                          '--operation', self.b['operationCommitment']])
        self.assertEqual(launched[0][launched[0].index('--operation') + 1], self.b['operationCommitment'])
        self.assertTrue((self.home.parent / 'e1/EXECUTION_RESULT.json').is_file())
        # Once the child opened the attempt, the launch reports the operation closed.
        def child_opens(command, *a, **k):
            marker.parent.mkdir(mode=0o700, exist_ok=True)
            marker.write_text('{}\n')
            return process, refusal, b''
        value = self._with(fixed + [unittest.mock.patch.object(api.native, 'capture_workflow', side_effect=child_opens)],
                           lambda: sdk.run(self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / 'e2', local_owner=True, mac_ready=True))
        self.assertEqual((value['status'], value['operationPermanentlyClosed']), ('EXECUTION_STOP', True))
        self.assertNotIn('attemptConsumed', value)
        with self.assertRaises(ExecutionError) as caught:
            self._with(fixed, lambda: sdk.run(self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / 'e3', local_owner=True, mac_ready=True))
        self.assertEqual(caught.exception.code, 'OPERATION_ALREADY_ATTEMPTED')
        self.assertFalse((self.home.parent / 'e3').exists())

    def test_launcher_matches_execution_sdk_run_on_the_same_child_outcomes(self):
        """_launch duplicates ExecutionSDK.run without the parent marker: on the same child outcome (linked completed,
        linked stop, cleanup failure, unlinked refusal) both report the same status, cause, cleanup and native result."""
        self._authorize()
        base_home = self.home.parent / 'base-home'
        base_home.mkdir(mode=0o700)
        profile, base = po.ProfileOverlayExecutionSDK(self.home), ExecutionSDK(base_home)
        completed = dict(status='SCENARIO_COMPLETED', operationCommitment=self.b['operationCommitment'], producerInvocations=2, RPC=0, WSS=0,
                         cleanupConfirmed=True)
        stopped = dict(completed, status='SCENARIO_STOP', producerInvocations=1, causeCode='NATIVE_X', cleanupConfirmed=True)
        clean = dict(ownedChildReaped=True, workflowGroupGone=True, cleanupError=None, exitCode=0, stop=None)
        cases = [('completed', completed, clean, True), ('stopped', stopped, dict(clean, exitCode=1), True),
                 ('cleanup', completed, dict(clean, workflowGroupGone=False), True),
                 ('refused', dict(status='INPUT_OR_RUNTIME_STOP', causeCode='PROFILE_NATIVE_AUTHORIZATION_EXPIRED'), dict(clean, exitCode=1), False)]
        drop = {'runDirectory', 'evidenceDirectory', 'operationPermanentlyClosed', 'attemptConsumed', 'nextStep'}
        for i, (label, child, process, linked) in enumerate(cases):
            outs = {}
            for name, sdk, home in (('profile', profile, self.home), ('base', base, base_home)):
                out = home / 'runs' / f'{label}-{name}'
                op = dict(operationCommitment=self.b['operationCommitment'], binding=self.b, outputPath=str(out))
                def capture(command, *a, out=out, child=child, linked=linked, **k):
                    if linked:
                        out.mkdir(mode=0o700, parents=True)
                        (out / 'RESULT.json').write_bytes(canonical(child) + b'\n')
                        (out / 'BINDING.json').write_bytes(canonical(dict(operationCommitment=self.b['operationCommitment'])) + b'\n')
                    return dict(process), json.dumps(child).encode(), b''
                cls = type(sdk)
                patches = [unittest.mock.patch.object(cls, '_prepared', return_value=(self.capture, {})),
                           unittest.mock.patch.object(cls, 'operation', return_value=op),
                           unittest.mock.patch.object(api.native, 'capture_workflow', side_effect=capture)]
                if name == 'base':
                    patches.append(unittest.mock.patch.object(ExecutionSDK, '_host'))
                attempts = home / 'scenarios/execution-attempts'
                if attempts.exists():
                    for f in attempts.iterdir():
                        f.unlink()
                outs[name] = self._with(patches, lambda sdk=sdk, i=i, name=name: sdk.run(
                    self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / f'ev-{name}-{i}', local_owner=True, mac_ready=True))
            p, q = ({k: v for k, v in outs[n].items() if k not in drop} for n in ('profile', 'base'))
            self.assertEqual(p, q, label)
            expected = dict(completed=('EXECUTION_COMPLETED', None, True), stopped=('EXECUTION_STOP', 'NATIVE_X', True),
                            cleanup=('EXECUTION_STOP', 'NATIVE_STOP', False), refused=('EXECUTION_STOP', 'PROFILE_NATIVE_AUTHORIZATION_EXPIRED', False))[label]
            self.assertEqual((p['status'], p.get('causeCode'), p['cleanupConfirmed']), expected, label)
            self.assertEqual(p['nativeResult'] is not None, linked, label)
            self.assertEqual(outs['base']['operationPermanentlyClosed'], True)
            # The profile launcher wrote no marker; in these stubs no child opened one either.
            self.assertFalse(outs['profile']['operationPermanentlyClosed'], label)
        self.assertEqual(outs['profile']['attemptConsumed'], False)

    def test_launcher_matches_execution_sdk_run_on_malformed_stdout_and_capture_exception(self):
        """The two defensive paths of the same comparison: child stdout that is not JSON, and capture_workflow raising."""
        self._authorize()
        base_home = self.home.parent / 'base-home-2'
        base_home.mkdir(mode=0o700)
        profile, base = po.ProfileOverlayExecutionSDK(self.home), ExecutionSDK(base_home)
        clean = dict(ownedChildReaped=True, workflowGroupGone=True, cleanupError=None, exitCode=0, stop=None)
        drop = {'runDirectory', 'evidenceDirectory', 'operationPermanentlyClosed', 'attemptConsumed', 'nextStep'}
        for label, behaviour in (('malformed', lambda *a, **k: (dict(clean), b'{"status": "SCENARIO_COMPLETED"', b'')),
                                 ('exception', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('capture_workflow failed')))):
            outs = {}
            for name, sdk, home in (('profile', profile, self.home), ('base', base, base_home)):
                out = home / 'runs' / f'{label}-{name}'
                op = dict(operationCommitment=self.b['operationCommitment'], binding=self.b, outputPath=str(out))
                cls = type(sdk)
                patches = [unittest.mock.patch.object(cls, '_prepared', return_value=(self.capture, {})),
                           unittest.mock.patch.object(cls, 'operation', return_value=op),
                           unittest.mock.patch.object(api.native, 'capture_workflow', side_effect=behaviour)]
                if name == 'base':
                    patches.append(unittest.mock.patch.object(ExecutionSDK, '_host'))
                attempts = home / 'scenarios/execution-attempts'
                if attempts.exists():
                    for f in attempts.iterdir():
                        f.unlink()
                outs[name] = self._with(patches, lambda sdk=sdk, name=name, label=label: sdk.run(
                    self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / f'ev2-{name}-{label}', local_owner=True, mac_ready=True))
                self.assertTrue((self.home.parent / f'ev2-{name}-{label}' / 'EXECUTION_RESULT.json').is_file(), (label, name))
            p, q = ({k: v for k, v in outs[n].items() if k not in drop} for n in ('profile', 'base'))
            self.assertEqual(p, q, label)
            self.assertEqual((p['status'], p['cleanupConfirmed'], p['nativeResult']), ('EXECUTION_STOP', False, None), label)
            if label == 'malformed':
                self.assertEqual(p['causeCode'], 'UNLINKED_NATIVE_RESULT')
            else:
                self.assertEqual(p['causeCode'], 'RuntimeError: capture_workflow failed')
            self.assertFalse(outs['profile']['operationPermanentlyClosed'], label)

    def test_doctor_blocked_consumes_nothing(self):
        sdk = po.ProfileOverlayExecutionSDK(self.home)
        with unittest.mock.patch('rhook_alpha.session.workflow.doctor', return_value=dict(status='BLOCKED', checks=[])), \
                unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, 'run', side_effect=AssertionError('no run')):
            value = sdk.run_profile(self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / 'e', local_owner=True, mac_ready=True)
        self.assertEqual((value['status'], value['operationPermanentlyClosed']), ('RUN_STOP_ENVIRONMENT_NOT_READY', False))
        stop = dict(status='EXECUTION_STOP', operationPermanentlyClosed=False, attemptConsumed=False, causeCode='PROFILE_NATIVE_AUTHORIZATION_EXPIRED',
                    nextStep='renew', evidenceDirectory='e', runDirectory='r')
        for closed, status in ((False, 'RUN_STOP_NOT_STARTED'), (True, 'RUN_STOP')):
            with unittest.mock.patch('rhook_alpha.session.workflow.doctor', return_value=dict(status='READY', checks=[])), \
                    unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, 'run', return_value=dict(stop, operationPermanentlyClosed=closed)), \
                    unittest.mock.patch.object(po.ProfileOverlayExecutionSDK, 'verify', side_effect=AssertionError('no verify')):
                value = sdk.run_profile(self.capture, operation=self.b['operationCommitment'], evidence=self.home.parent / 'e', local_owner=True, mac_ready=True)
            self.assertEqual((value['status'], value['operationPermanentlyClosed']), (status, closed))

    def test_lp_only_diagnostic_and_closure_refuse_the_profile_runtime(self):
        from rhook_alpha.cases.scenario import closure, diagnostic
        scenario = self.home / 'lp.json'
        scenario.write_bytes(canonical(synthetic_source()) + b'\n')
        with self.assertRaises(ValueError) as caught:
            diagnostic.prepare(self.sdk, self.plan['planId'], scenario, self.home / 'diag')
        self.assertIn('DIAGNOSTIC_LP_RUNTIME_REQUIRED', str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            closure.prepare(self.sdk, self.plan['planId'], self.home / 'close')
        self.assertIn('CLOSURE_LP_RUNTIME_REQUIRED', str(caught.exception))


def _log(address, topics, data):
    return dict(address=address, topics=topics, data=data)


def synthetic_world(name, *, gas=1000, root='11', fee=3000, net=5):
    c = pp.constants_from_descriptor(D)
    actor = '0x' + pp.ACTOR[2:].rjust(64, '0')
    zero = '0x' + '00' * 32
    logs = [_log(c['token'], [pp.TRANSFER, zero, actor], '0x' + hex(net)[2:].rjust(64, '0')),
            _log(c['pool_manager'], [pp.SWAP, c['pool_id'], zero], '0x' + '00' * 160 + hex(fee)[2:].rjust(64, '0'))]
    return dict(world=name, receipts=[dict(status='0x1', gasUsed='0x0', logs=[]), dict(status='0x1', gasUsed=hex(gas), logs=logs)],
                stateRoot='0x' + root * 32, receiptsRoot='0x' + root[::-1] * 32, actorBalanceAfter='1', actorNonceAfter=1,
                overlay=dict(commonSetupRoot='0x' + 'aa' * 32, worldInitialRoot='0x' + root * 32))


class Comparators(unittest.TestCase):
    def test_missing_required_field_fails_the_initial_world_comparison(self):
        """Regression (G4B): a comparison over keys absent on both sides once reported equality."""
        overlay = dict(commonSetupRoot='0x' + 'aa' * 32, worldInitialRoot='0x' + 'bb' * 32, commonSimulationSetup=dict(actor=pp.ACTOR),
                       configurationAccount='0x' + '01' * 20, configurationSlot='0x' + '02' * 32, originalWord='0x' + '03' * 32, initialWord='0x' + '04' * 32)
        reference = dict(worlds=[dict(world=w, overlay=dict(overlay)) for w in pp.WORLDS])
        state = dict(baseline=dict(overlay), variant=dict(overlay))
        self.assertEqual(pp.compare_initial_worlds(state, reference)['status'], 'PASS')
        for key in pp.INITIAL_KEYS:
            for side in ('state', 'reference'):
                s, r = copy.deepcopy(state), copy.deepcopy(reference)
                if side == 'state':
                    del s['variant'][key]
                else:
                    del r['worlds'][0]['overlay'][key]
                out = pp.compare_initial_worlds(s, r)
                self.assertEqual(out['status'], 'FAIL', (key, side))
                self.assertIn('MISSING', [row['result'] for w in out['worlds'] for row in w['rows']])
            for empty in (None, '', [], {}):
                s = copy.deepcopy(state)
                s['baseline'][key] = empty
                self.assertEqual(pp.compare_initial_worlds(s, reference)['status'], 'FAIL', (key, empty))
        s = copy.deepcopy(state)
        s['variant']['initialWord'] = '0x' + '05' * 32
        self.assertEqual(pp.compare_initial_worlds(s, reference)['status'], 'FAIL')
        # The exact G4B false positive: comparing keys that neither record has.
        self.assertEqual(pp.compare_fields({}, {}, ['worldRoot'])['status'], 'FAIL')
        self.assertEqual(pp.compare_fields({'a': 1}, {'a': 1}, [])['status'], 'FAIL')
        # storageWrites is required exactly when the reference records it.
        r = copy.deepcopy(reference)
        r['worlds'][1]['overlay']['storageWrites'] = [dict(slot='0x01')]
        self.assertEqual(pp.compare_initial_worlds(state, r)['status'], 'FAIL')
        s = copy.deepcopy(state)
        s['variant']['storageWrites'] = [dict(slot='0x01')]
        self.assertEqual(pp.compare_initial_worlds(s, r)['status'], 'PASS')
        self.assertEqual(pp.compare_initial_worlds(state, dict(worlds=list(reversed(reference['worlds']))))['status'], 'FAIL')

    def test_projection_never_defaults_a_missing_field(self):
        c = pp.constants_from_descriptor(D)
        good = synthetic_world('SCENARIO_VARIANT')
        p = pp.project_world(good, **c)
        self.assertEqual((p['gasUsed'], p['outerSwapFeePips'], p['actorTargetTokenTransferNetBaseUnits'], p['receiptStatus']), (1000, [3000], '5', 1))
        for edit in (lambda w: w.pop('stateRoot'), lambda w: w.pop('receiptsRoot'), lambda w: w.update(stateRoot=None),
                     lambda w: w.pop('actorBalanceAfter'), lambda w: w.pop('actorNonceAfter'), lambda w: w['receipts'].pop(),
                     lambda w: w['receipts'][1].pop('gasUsed'), lambda w: w['receipts'][1].pop('status'), lambda w: w['receipts'][1].pop('logs'),
                     lambda w: w['receipts'][1]['logs'].pop()):
            w = copy.deepcopy(good)
            edit(w)
            with self.assertRaises(pp.ParityError) as caught:
                pp.project_world(w, **c)
            self.assertEqual(caught.exception.code, 'PARITY_REQUIRED_FIELD_MISSING')

    def test_i_gas_formula(self):
        self.assertEqual(pp.i_gas(1590291, 1646722, 1590327, 1646794), 36)


@unittest.skipUnless(REC, 'accepted run records not supplied')
class Matrix(unittest.TestCase):
    def setUp(self):
        self.refs = {}
        for name in ('lp23', 'dynamic-fee-off', 'combined'):
            raw = (REC / name / 'runtime/scenario/FINAL.json').read_bytes()
            self.refs[name] = (json.loads((REC / name / 'inputs/SCENARIO.json').read_bytes()), json.loads(raw), hashlib.sha256(raw).hexdigest())
        self.m = pp.matrix(REC, D)
        self.src = json.loads((REC / 'lp23/inputs/SCENARIO.json').read_bytes())

    def _as_new(self, run):
        name, items, ref = next(r for r in pp.RUNS if r[0] == run)
        spec = pd.build_spec(self.src, RAW, items, G4B)
        final = copy.deepcopy(self.refs[ref][1])
        final['scenarioCommitment'] = spec['scenarioCommitment']
        return spec, final

    def test_preregistered_expectations(self):
        self.assertEqual(pp.check_matrix(self.m)['iGas']['expected'], 36)
        self.assertEqual([r['run'] for r in self.m['runs']], ['LP23_DF_ON', 'LP100_DF_OFF', 'LP23_DF_OFF'])
        self.assertEqual(self.m['iGas']['referenceGas'], dict(LP23_DF_ON=1646722, LP100_DF_OFF=1590327, LP23_DF_OFF=1590291, LP100_DF_ON=1646794))
        self.assertEqual(self.m['matrixCommitment'], pp.EXPECTED_MATRIX_COMMITMENT)
        self.assertEqual([(r['referenceInputSha256'], r['referenceFinalSha256']) for r in self.m['runs']],
                         [(pp.REFERENCES[n]['inputSha256'], pp.REFERENCES[n]['finalSha256']) for n in ('lp23', 'dynamic-fee-off', 'combined')])
        # A changed expectation is refused even when its self-hash is recomputed.
        tampered = copy.deepcopy(self.m)
        tampered['runs'][0]['expected']['SCENARIO_VARIANT']['gasUsed'] += 1
        body = dict(tampered)
        body.pop('matrixCommitment')
        tampered['matrixCommitment'] = digest(pp.MATRIX_SCHEMA.encode() + b'\n' + canonical(body))
        for value in (tampered, dict(self.m, matrixCommitment='0' * 64)):
            with self.assertRaises(pp.ParityError) as caught:
                pp.check_matrix(value)
            self.assertEqual(caught.exception.code, 'PARITY_MATRIX_DRIFT')
            with self.assertRaises(pp.ParityError):
                pp.evaluate(value, 'LP23_DF_ON', {}, {})

    def test_fabricated_reference_records_are_refused(self):
        import shutil
        with tempfile.TemporaryDirectory(prefix='rhook-g5-ref-') as tmp:
            fake = Path(tmp) / 'records'
            for name in ('lp23', 'dynamic-fee-off', 'combined'):
                (fake / name / 'inputs').mkdir(parents=True)
                (fake / name / 'runtime/scenario').mkdir(parents=True)
                shutil.copyfile(REC / name / 'inputs/SCENARIO.json', fake / name / 'inputs/SCENARIO.json')
                shutil.copyfile(REC / name / 'runtime/scenario/FINAL.json', fake / name / 'runtime/scenario/FINAL.json')
            self.assertEqual(pp.matrix(fake, D)['matrixCommitment'], pp.EXPECTED_MATRIX_COMMITMENT)
            final = json.loads((fake / 'combined/runtime/scenario/FINAL.json').read_bytes())
            final['worlds'][1]['receipts'][1]['gasUsed'] = hex(1590291 + 36)
            (fake / 'combined/runtime/scenario/FINAL.json').write_bytes(canonical(final) + b'\n')
            with self.assertRaises(pp.ParityError) as caught:
                pp.matrix(fake, D)
            self.assertEqual(caught.exception.code, 'PARITY_REFERENCE_PIN')
            (fake / 'combined/runtime/scenario/FINAL.json').unlink()
            with self.assertRaises(OSError):
                pp.matrix(fake, D)

    def test_evaluate_matches_fails_on_missing_or_changed_fields_and_unlinked_input(self):
        results = {}
        for run, _, _ in pp.RUNS:
            spec, final = self._as_new(run)
            results[run] = pp.evaluate(self.m, run, spec, final)
            self.assertEqual(results[run]['status'], 'PARITY_FIELDS_MATCH', run)
        runs = {run: self._as_new(run) for run, _, _ in pp.RUNS}
        seq = pp.evaluate_runs(self.m, runs)
        self.assertEqual(seq['iGas'], dict(status='I_GAS_MATCH', measured=36, expected=36, allRunsParity=True))
        self.assertEqual(seq['runs'], results)
        # I_gas is measured from the recorded runs themselves: a changed variant gas changes it.
        s3, f3 = runs['LP23_DF_OFF']
        f3 = copy.deepcopy(f3)
        f3['worlds'][1]['receipts'][1]['gasUsed'] = hex(1590291 + 7)
        seq = pp.evaluate_runs(self.m, dict(runs, LP23_DF_OFF=(s3, f3)))
        self.assertEqual(seq['iGas'], dict(status='I_GAS_MISMATCH', measured=43, expected=36, allRunsParity=False))
        # Not the three planned runs, or a run of another input: not evaluated.
        with self.assertRaises(pp.ParityError):
            pp.evaluate_runs(self.m, {k: v for k, v in runs.items() if k != 'LP23_DF_OFF'})
        swapped = dict(runs, LP23_DF_OFF=runs['LP23_DF_ON'])
        self.assertEqual(pp.evaluate_runs(self.m, swapped)['iGas']['status'], 'NOT_EVALUATED')
        self.assertFalse(hasattr(pp, 'evaluate_i_gas'))
        spec, final = self._as_new('LP23_DF_OFF')
        for edit in (lambda f: f['worlds'][1].pop('receiptsRoot'), lambda f: f['worlds'][0]['receipts'][1].update(gasUsed=hex(1)),
                     lambda f: f['worlds'][1]['receipts'][1]['logs'].reverse(), lambda f: f.update(scenarioCommitment='0' * 64),
                     lambda f: f['worlds'].reverse()):
            f = copy.deepcopy(final)
            edit(f)
            self.assertEqual(pp.evaluate(self.m, 'LP23_DF_OFF', spec, f)['status'], 'PARITY_FAIL')
        other = dict(spec, environment=dict(spec['environment'], l2Timestamp=spec['environment']['l2Timestamp'] + 1))
        self.assertEqual(pp.evaluate(self.m, 'LP23_DF_OFF', other, final)['status'], 'PARITY_FAIL')
        wrong = pd.build_spec(self.src, RAW, [lp(23)], G4B)
        f = dict(final, scenarioCommitment=wrong['scenarioCommitment'])
        self.assertEqual(pp.evaluate(self.m, 'LP23_DF_OFF', wrong, f)['status'], 'PARITY_FAIL')


@unittest.skipUnless(REC, 'accepted run records not supplied')
class Preparation(Home):
    def setUp(self):
        super().setUp()
        self.source = REC / 'lp23/inputs/SCENARIO.json'
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.stack = [unittest.mock.patch.object(po, 'static_coverage', return_value=COVERED),
                      unittest.mock.patch.object(pd, 'authenticate_targets', return_value=TARGETS)]
        for p in self.stack:
            p.start()

    def tearDown(self):
        for p in reversed(self.stack):
            p.stop()
        super().tearDown()

    def test_prepare_three_inputs_keep_fixed_inputs_and_bind_the_reviewed_identity(self):
        src = json.loads(self.source.read_bytes())
        seen = set()
        for i, (run, items, _) in enumerate(pp.RUNS):
            out = self.home.parent / f'prepared-{i}'
            value = po.prepare(self.sdk, self.source, expected_sha256=self.sha, interventions=items, output=out, node=sys.executable)
            spec = json.loads((out / 'SCENARIO.json').read_bytes())
            self.assertEqual((value['status'], value['nativeExecutions'], value['executionAuthorized']), ('EXECUTION_CANDIDATE_PREPARED', 0, False))
            self.assertEqual({k: spec[k] for k in po.FIXED_INPUTS}, {k: src[k] for k in po.FIXED_INPUTS})
            self.assertEqual((spec['engine'], spec['profileOverlay']['descriptor'], spec['profileOverlay']['interventions']),
                             (G4B, pd.PROFILE_ENGINE_RECORD['descriptor'], items))
            self.assertEqual(value['sourceWitnessSha256'], self.sha)
            path, meta = po.ProfileOverlayExecutionSDK(self.home)._prepared(out)
            self.assertEqual(meta['scenarioCommitment'], spec['scenarioCommitment'])
            seen.add(spec['scenarioCommitment'])
        self.assertEqual(len(seen), 3)
        self.assertFalse((self.home / 'scenarios/runs').exists())

    def test_refusals_write_nothing(self):
        cases = [(dict(interventions=[tuning(8000, 1)]), 'PROFILE_KIND_REVIEW_INSUFFICIENT'),
                 (dict(interventions=[lp(23), DYN_OFF]), 'PROFILE_CANONICAL_SET_REQUIRED'),
                 (dict(interventions=[lp(100)]), None),
                 (dict(interventions=[lp(23)], expected_sha256='0' * 64), 'PREPARED_WITNESS_HASH_MISMATCH')]
        for i, (kw, code) in enumerate(cases):
            out = self.home.parent / f'refused-{i}'
            options = dict(expected_sha256=self.sha, output=out, node=sys.executable)
            options.update(kw)
            with self.assertRaises(ExecutionError) as caught:
                po.prepare(self.sdk, self.source, **options)
            if code:
                self.assertEqual(caught.exception.code, code)
            self.assertFalse(out.exists())
        with unittest.mock.patch.object(po, 'static_coverage', side_effect=ExecutionError('PROFILE_STATIC_COVERAGE_REQUIRED', 'x')):
            with self.assertRaises(ExecutionError):
                po.prepare(self.sdk, self.source, expected_sha256=self.sha, interventions=[lp(23)], output=self.home.parent / 'nocov', node=sys.executable)
        self.assertFalse((self.home.parent / 'nocov').exists())
        self.assertFalse((self.home / 'scenarios/plans').exists())

    def test_one_node_binary_resolved_from_path_for_both_checks(self):
        with unittest.mock.patch.object(po.shutil, 'which', return_value=sys.executable):
            po.prepare(self.sdk, self.source, expected_sha256=self.sha, interventions=[lp(23)], output=self.home.parent / 'path-node')
        self.assertEqual(po.static_coverage.call_args.kwargs['node'], sys.executable)
        self.assertEqual(pd.authenticate_targets.call_args.kwargs['node'], sys.executable)
        with unittest.mock.patch.object(po.shutil, 'which', return_value=None):
            with self.assertRaises(ExecutionError) as caught:
                po.prepare(self.sdk, self.source, expected_sha256=self.sha, interventions=[lp(23)], output=self.home.parent / 'no-node')
        self.assertEqual(caught.exception.code, 'PROFILE_NODE_REQUIRED')
        self.assertFalse((self.home.parent / 'no-node').exists())
        self.stack[1].stop()
        try:
            with self.assertRaises(pd.DescriptorError) as caught:
                pd.authenticate_targets(json.loads(self.source.read_bytes()), RAW, node=None)
            self.assertEqual(caught.exception.code, 'PROFILE_TARGET_AUTHENTICATOR_UNAVAILABLE')
        finally:
            self.stack[1].start()

    def test_static_coverage_requires_covered_and_satisfied(self):
        self.stack[0].stop()
        try:
            for report in (dict(COVERED, status='STATIC_DEPENDENCIES_MISSING'), dict(COVERED, preconditions=dict(status='UNKNOWN', checks=[])),
                           dict(status='NOT_EVALUATED', code='NODE_NOT_FOUND')):
                with unittest.mock.patch('rhook_alpha.session.hookr.HookrScenarioAdapter.coverage', return_value=report):
                    with self.assertRaises(ExecutionError) as caught:
                        po.static_coverage(self.home, b'{}')
                    self.assertEqual(caught.exception.code, 'PROFILE_STATIC_COVERAGE_REQUIRED')
        finally:
            self.stack[0].start()

    def test_prepared_drift_is_refused(self):
        out = self.home.parent / 'drift'
        po.prepare(self.sdk, self.source, expected_sha256=self.sha, interventions=[lp(23)], output=out, node=sys.executable)
        meta = json.loads((out / 'PREPARATION.json').read_bytes())
        for edit in (lambda m: m.update(interventions=[DYN_OFF]), lambda m: m.update(engine=dict(G4B, binarySha256='0' * 64)),
                     lambda m: m.update(schema='other'), lambda m: m.update(descriptor=dict(m['descriptor'], revision=1))):
            m = copy.deepcopy(meta)
            edit(m)
            (out / 'PREPARATION.json').write_bytes(canonical(m) + b'\n')
            with self.assertRaises(ExecutionError) as caught:
                po.ProfileOverlayExecutionSDK(self.home)._prepared(out)
            self.assertEqual(caught.exception.code, 'PROFILE_PREPARATION_DRIFT')


@unittest.skipUnless(REC and NODE and all((DEPS / n / 'package.json').is_file() for n in ('viem', 'hookr-sdk')), 'node and adapter dependencies not supplied')
class TargetAuthenticator(unittest.TestCase):
    def setUp(self):
        self.src = json.loads((REC / 'lp23/inputs/SCENARIO.json').read_bytes())

    def _mjs(self, spec, descriptor):
        r = subprocess.run([NODE, str(pd.TARGET_AUTHENTICATOR)], input=canonical(dict(spec=spec, descriptor=descriptor)), capture_output=True, timeout=60)
        return r.returncode, json.loads(r.stdout)

    def test_accepted_input_targets_are_the_reviewed_originals(self):
        value = pd.authenticate_targets(self.src, RAW, node=NODE)
        self.assertEqual(value['status'], 'PROFILE_TARGETS_MPT_AUTHENTICATED')
        self.assertEqual(value['targets'], {n: [pd._word(v) for v in w] for n, w in pd.originals_from_descriptor(D).items()})
        self.assertEqual({c['name'] for c in D['contracts']}, set(value['contracts']))

    def test_missing_node_or_code_and_wrong_identity_stop(self):
        missing = copy.deepcopy(self.src)
        root = self.src['checkpoint']['stateRoot']
        missing['inventory']['nodes'] = [n for n in missing['inventory']['nodes'] if '0x' + pd.keccak256(bytes.fromhex(n[2:])).hex() != root]
        self.assertEqual(len(missing['inventory']['nodes']), len(self.src['inventory']['nodes']) - 1)
        code, out = self._mjs(missing, D)
        self.assertEqual((code, out.get('causeCode')), (1, 'MISSING_TRIE_NODE'))
        nocode = copy.deepcopy(self.src)
        nocode['inventory']['codes'] = []
        code, out = self._mjs(nocode, D)
        self.assertEqual((code, out.get('causeCode')), (1, 'CODE_PREIMAGE_MISSING'))
        d = copy.deepcopy(D)
        d['contracts'][0]['runtimeCodeHash'] = '0x' + '00' * 32
        code, out = self._mjs(self.src, d)
        self.assertEqual((code, out.get('causeCode')), (1, 'CONTRACT_CODE_IDENTITY'))
        # Python side: an authenticator report whose words, checkpoint or code identity differ is refused.
        code, real = self._mjs(self.src, D)
        self.assertEqual(code, 0)
        for edit, expected in [(lambda v: v['targets']['rulesConfig'].__setitem__(0, '0x' + '00' * 32), 'PROFILE_ORIGINAL_WORD'),
                               (lambda v: v['checkpoint'].update(blockNumber=v['checkpoint']['blockNumber'] + 1), 'PROFILE_ORIGINAL_WORD'),
                               (lambda v: v['contracts']['root'].update(codeHash='0x' + '00' * 32), 'PROFILE_CODE_IDENTITY'),
                               (lambda v: v['contracts']['targetToken'].update(codeBytes=0), 'PROFILE_CODE_IDENTITY'),
                               (lambda v: v.update(schema='other'), 'PROFILE_TARGET_AUTHENTICATION')]:
            v = copy.deepcopy(real)
            edit(v)
            fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=canonical(v) + b'\n', stderr=b'')
            with unittest.mock.patch('subprocess.run', return_value=fake):
                with self.assertRaises(pd.DescriptorError) as caught:
                    pd.authenticate_targets(self.src, RAW, node=NODE)
            self.assertEqual(caught.exception.code, expected)


if __name__ == '__main__':
    unittest.main()
