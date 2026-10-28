"""Proposed admission and knowledge boundaries, with no producer/helper calls."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from developer.files import canonical, digest, save
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.adapters import get_adapter
from rhook_alpha.cases.capsule import seal
from rhook_alpha.cases.admission import CLASS, LP, OFF
from rhook_alpha.cases.admission import catalogue, assurance
from rhook_alpha.cases.__main__ import main
from test_plans import hookr


class Admission(unittest.TestCase):
    def case(self, root, value=50):
        d, raw = hookr()
        bundle = root / 'bundle'
        bundle.mkdir()
        save(bundle / 'CAPSULE.json', d)
        (bundle / 'BLOCK_PACKAGE.json').write_bytes(raw)
        sdk = CaseSDK(root / 'home')
        sdk.import_case(bundle)
        ref = sdk.plan(d['caseId'], dict(rule='lpBps', value=value))['planId']
        return sdk, ref, d

    def evidence(self, root, sdk, ref):
        """Explicit synthetic trust fixture; not an accepted scientific record."""
        directory = root / 'evidence'
        directory.mkdir()
        p = sdk.describe(ref)['runtimePlan']
        save(directory / 'plan.json', dict(plan=p))
        save(directory / 'a.json', dict(result=dict(world='ACTUAL', **{k:p[k] for k in ['stateRoot','receiptsRoot','blockHash']})))
        save(directory / 'b.json', dict(result=dict(world='BRANCH')))
        files = {n:digest((directory/n).read_bytes()) for n in ['plan.json','a.json','b.json']}
        save(directory / 'MANIFEST.json', dict(files=files))
        reference = dict(manifest=digest((directory/'MANIFEST.json').read_bytes()), count=3,
                         plan='plan.json', nested='plan', actual='a.json', branch='b.json',
                         descriptor=dict(rule='lpBps',value=50))
        return directory, reference

    def test_catalogue_is_closed_and_caller_cannot_mutate_its_definitions(self):
        result = catalogue.entries()
        self.assertEqual({x['adapter'] for x in result['entries']}, {LP, OFF})
        result['entries'][0]['values']['maximum'] = 10000
        self.assertEqual(catalogue.entries()['entries'][0]['values']['maximum'], 99)
        self.assertEqual(result['qualifiedClaims'], 0)
        self.assertFalse(result['arbitraryStorageWrites'])

    def test_lp_plan_is_exact_legacy_serialization_and_sidecar_is_separate(self):
        d, _ = hookr()
        value = dict(rule='lpBps', value=50)
        legacy = get_adapter(d).plan(d,value)
        self.assertEqual(canonical(catalogue.resolve_plan(d,value)), canonical(legacy))
        desc = catalogue.describe(d,value)
        self.assertEqual(desc['semanticClass'], CLASS)
        self.assertEqual(desc['meaning']['writes'][0]['after'], legacy['intervention']['newWord'])
        self.assertEqual(desc['artifactBindings']['legacyRuntimePlanSha256'], digest(canonical(legacy)))
        self.assertEqual(desc['identityKind'],'CATALOGUE_ARTIFACT_NOT_BRANCH_PROTOCOL_QUERY')
        self.assertEqual(desc['meaning']['initialRoots']['anchor'], desc['meaning']['initialRoots']['actual'])
        self.assertNotEqual(desc['meaning']['initialRoots']['anchor'], desc['meaning']['initialRoots']['branch'])
        self.assertFalse(desc['originalStateAuthenticated'])
        self.assertFalse(desc['lawfulEstablished'])
        self.assertFalse(desc['executionAuthorized'])

    def test_profile_generation_and_target_ambiguity_fail_closed(self):
        d, _ = hookr()
        for mutate in [lambda x:x['execution'].update(profile='unknown/profile'),
                       lambda x:x['adapter']['config'].update(rulesRuntimeHash='0x'+'f'*64),
                       lambda x:x['arrivals'].append(x['arrivals'][1]),
                       lambda x:x['adapter']['config'].update(slot='0x'+'0'*64),
                       lambda x:x.update(schema='unknown/capsule')]:
            bad = copy.deepcopy(d)
            mutate(bad)
            bad=seal(bad)
            with self.assertRaises(ValueError):catalogue.resolve_plan(bad,dict(rule='lpBps',value=50))

    def test_unknown_profile_or_arbitrary_write_descriptor_cannot_select_code(self):
        d, _ = hookr()
        for value in [dict(rule='lpBps',value=50,writes=[]),dict(rule='code',value='0x00'),
                      dict(rule='lpBps',value=True),dict(rule='lpBps',value=100),dict(rule='lpBps',value='50')]:
            with self.assertRaises(ValueError):catalogue.resolve_plan(d,value)
        d['adapter']['id']='untrusted.python.module'
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_ADAPTER'):
            catalogue.resolve_plan(seal(d),dict(rule='lpBps',value=50))

    def test_api_resolution_and_unknown_knowledge_create_no_runtime_or_consent(self):
        with tempfile.TemporaryDirectory() as tmp, patch('subprocess.Popen',side_effect=AssertionError('no helper')), \
                patch('socket.socket',side_effect=AssertionError('no network')):
            root=Path(tmp).resolve();sdk,ref,_=self.case(root)
            desc=sdk.admission(ref);report=sdk.assurance(ref)
            self.assertEqual(desc['resolution'],'DESCRIPTOR_RESOLVED_AUTHENTICATION_PENDING')
            self.assertEqual(report['status'],'UNRESOLVED')
            self.assertEqual([x['id'] for x in report['obligations']],[f'L{i}' for i in range(1,10)])
            self.assertTrue(all(x['status']=='UNRESOLVED' for x in report['obligations']))
            self.assertIsNone(report['worldOutcomes'])
            self.assertEqual(report['qualifiedClaims'],0)
            self.assertFalse((sdk.home/'RUNTIME.json').exists())
            self.assertFalse((sdk.home/'.case-consent.key').exists())
            self.assertEqual(list((sdk.home/'consents').iterdir()),[])

    def test_trusted_record_support_never_promotes_complete_lawful(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,_=self.case(root);directory,reference=self.evidence(root,sdk,ref)
            with patch.dict(assurance.REFERENCES,{LP:reference}):
                result=sdk.assurance(ref,evidence=directory)
            self.assertEqual(result['evidence']['status'],'ESTABLISHED')
            self.assertEqual(result['status'],'UNRESOLVED')
            self.assertFalse(result['lawfulEstablished'])
            self.assertEqual(result['qualifiedClaims'],0)
            self.assertIsNone(result['worldOutcomes'])

    def test_modified_evidence_is_rejected_without_turning_it_into_revert(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,_=self.case(root);directory,reference=self.evidence(root,sdk,ref)
            (directory/'b.json').write_bytes((directory/'b.json').read_bytes()+b' ')
            with patch.dict(assurance.REFERENCES,{LP:reference}):result=sdk.assurance(ref,evidence=directory)
            self.assertEqual(result['status'],'REJECTED')
            self.assertEqual(result['evidence']['reason'],'EVIDENCE_FILE_HASH_MISMATCH')
            self.assertIsNone(result['worldOutcomes'])
            self.assertFalse(result['lawfulEstablished'])

    def test_missing_evidence_is_unknown_not_authenticated_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,_=self.case(root);directory,reference=self.evidence(root,sdk,ref)
            (directory/'b.json').unlink()
            with patch.dict(assurance.REFERENCES,{LP:reference}):result=sdk.assurance(ref,evidence=directory)
            self.assertEqual(result['status'],'UNRESOLVED')
            self.assertEqual(result['evidence']['reason'],'ACCEPTED_EVIDENCE_FILE_MISSING')

    def test_records_are_parsed_from_the_exact_hashed_buffer_despite_path_replacement(self):
        from developer.files import read
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,_=self.case(root);directory,reference=self.evidence(root,sdk,ref)
            def replaced(path, limit):
                raw=read(path,limit)
                if Path(path)==directory/'b.json':
                    # Deterministic local replacement after capturing original bytes.
                    (directory/'b.json').write_text(json.dumps(dict(result=dict(world='ACTUAL',dynamicFeeOverlay=dict(initialRoot='0x'+'a'*64)))))
                return raw
            with patch.dict(assurance.REFERENCES,{LP:reference}),patch.object(assurance,'read',side_effect=replaced):
                result=sdk.assurance(ref,evidence=directory)
            self.assertEqual(result['evidence']['status'],'ESTABLISHED')
            self.assertIsNone(result['evidence']['branchInitialRoot'])
            self.assertEqual(result['status'],'UNRESOLVED')

    def test_manifest_is_parsed_from_its_exact_pinned_buffer(self):
        from developer.files import read
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,_=self.case(root);directory,reference=self.evidence(root,sdk,ref)
            def replaced(path, limit):
                raw=read(path,limit)
                if Path(path)==directory/'MANIFEST.json':
                    (directory/'MANIFEST.json').write_text('{"files":{}}')
                return raw
            with patch.dict(assurance.REFERENCES,{LP:reference}),patch.object(assurance,'read',side_effect=replaced):
                result=sdk.assurance(ref,evidence=directory)
            self.assertEqual(result['evidence']['status'],'ESTABLISHED')
            self.assertEqual(result['evidence']['pinnedFiles'],3)
            self.assertFalse(result['lawfulEstablished'])

    def test_correct_archive_for_another_value_is_not_evidence_for_this_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,d=self.case(root);directory,reference=self.evidence(root,sdk,ref)
            new=sdk.plan(d['caseId'],dict(rule='lpBps',value=49))['planId']
            with patch.dict(assurance.REFERENCES,{LP:reference}):result=sdk.assurance(new,evidence=directory)
            self.assertEqual(result['status'],'REJECTED')
            self.assertIn('DIFFERENT_INTERVENTION',result['evidence']['reason'])

    def test_symlink_evidence_path_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,_=self.case(root);directory,reference=self.evidence(root,sdk,ref)
            alias=root/'alias';alias.symlink_to(directory,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'SYMLINK_OR_TRAVERSAL'):sdk.assurance(ref,evidence=alias)

    def test_cli_admission_is_resolution_but_assurance_unknown_has_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,_=self.case(root)
            for command,expected in [(['interventions'],0),(['admission','--plan',ref],0),(['assurance','--plan',ref],2)]:
                output=io.StringIO()
                with redirect_stdout(output):code=main(['--home',str(sdk.home),*command])
                self.assertEqual(code,expected,output.getvalue())
                value=json.loads(output.getvalue());self.assertEqual(value['qualifiedClaims'],0)

    def test_clean_installed_consumer_reports_candidate_and_unresolved_without_runtime(self):
        import install_cases
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk,ref,_=self.case(root)
            command=install_cases.install(root/'installed')
            env={'PATH':os.defpath,'LANG':'C','TZ':'UTC'}
            for args,expected in [(['interventions'],0),(['admission','--plan',ref],0),(['assurance','--plan',ref],2)]:
                result=subprocess.run([str(command),'--home',str(sdk.home),*args],env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,expected,result.stderr+result.stdout)
                value=json.loads(result.stdout)
                self.assertEqual(value['qualifiedClaims'],0)
                self.assertFalse(value.get('lawfulEstablished',False))
            self.assertFalse((sdk.home/'RUNTIME.json').exists())
            self.assertFalse((sdk.home/'.case-consent.key').exists())
            self.assertEqual(list((sdk.home/'consents').iterdir()),[])

    @unittest.skipUnless(os.environ.get('RHOOK_HISTORICAL_TEST_PACKAGE'),'explicit retained fixture required')
    def test_real_off_preparation_keeps_exact_legacy_plan_and_two_changes(self):
        from rhook_alpha.cases.historical import ADAPTER
        from rhook_alpha.cases.historical.adapter import profile
        p=profile()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk=CaseSDK(root/'home')
            sdk.package_case(Path(os.environ['RHOOK_HISTORICAL_TEST_PACKAGE']),root/'bundle',case_id='off',
                             adapter=ADAPTER,subject_index=3,input_commitment=p['inputCommitment'],witness_commitment=p['witnessCommitment'])
            sdk.import_case(root/'bundle');ref=sdk.plan('off',dict(rule='dynamicFee',value='OFF'))['planId']
            desc=sdk.admission(ref)
            self.assertEqual(desc['meaning']['storageWriteCount'],2)
            self.assertEqual(desc['meaning']['applicationCount'],1)
            self.assertEqual(desc['meaning']['anchor'],p['checkpoint'])
            self.assertEqual(sdk.describe(ref)['runtimePlan'],get_adapter(sdk.registry.resolve('off')[1]).plan(sdk.registry.resolve('off')[1],dict(rule='dynamicFee',value='OFF')))
            for bad in [dict(rule='dynamicFee',value=True),dict(rule='dynamicFee',value='ON'),dict(rule='lpBps',value=50)]:
                with self.assertRaises(ValueError):sdk.plan('off',bad)


if __name__=='__main__':unittest.main()
