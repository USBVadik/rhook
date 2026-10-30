"""Real installed CLI/API in empty homes; optional private inputs stay outside SDK."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
RECORDS=os.environ.get('RHOOK_CLEANROOM_LOG_DIR')
CASES=os.environ.get('RHOOK_CLEANROOM_CASES')
EVIDENCE=os.environ.get('RHOOK_RECORDED_TEST_BUNDLE')

class CleanRoomSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='rhook-cleanroom-')
        cls.root=Path(cls.temporary.name).resolve();cls.prefix=cls.root/'installation'
        cls.account=cls.root/'empty-account';cls.account.mkdir();(cls.root/'tmp').mkdir()
        cls.env={'PATH':'/usr/bin:/bin','HOME':str(cls.account),'TMPDIR':str(cls.root/'tmp'),'LANG':'C','TZ':'UTC'}
        cls.serial=0
        result=cls.invoke([sys.executable,'-I','-S','-B',str(ROOT/'install_cases.py'),'--prefix',str(cls.prefix)])
        if result.returncode:raise AssertionError(result.stderr)
        cls.command=cls.prefix/'bin/rhook-cases'

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    @classmethod
    def invoke(cls,argv):
        result=subprocess.run(argv,cwd=cls.account,env=cls.env,capture_output=True,text=True,timeout=20)
        if RECORDS:
            cls.serial+=1;folder=Path(RECORDS);folder.mkdir(parents=True,exist_ok=True)
            (folder/f'{cls.serial:03}.json').write_text(json.dumps(dict(argv=argv,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr),indent=2)+'\n')
        return result

    def setUp(self):self.home=self.root/self.id().rsplit('.',1)[-1]

    def cli(self,*args,success=True):
        result=self.invoke([str(self.command),'--home',str(self.home),*map(str,args)])
        self.assertEqual(result.returncode==0,success,result.stderr+result.stdout)
        return json.loads(result.stdout)

    def api(self,code,*args):
        probe='import sys,json\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom rhook_alpha.cases.api import CaseSDK\nfrom rhook_alpha.execution import ExecutionSDK\nhome=Path(sys.argv[2]);sdk=CaseSDK(home)\n'+code
        result=self.invoke([sys.executable,'-I','-S','-B','-c',probe,str(self.prefix/'lib'),str(self.home),*map(str,args)])
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def synthetic(self,name):
        from test_plans import hookr
        from developer.files import save
        bundle=self.root/name;bundle.mkdir();descriptor,raw=hookr(name)
        save(bundle/'CAPSULE.json',descriptor);(bundle/'BLOCK_PACKAGE.json').write_bytes(raw)
        return bundle

    def test_installed_imports_catalogues_and_approved_default(self):
        receipt=json.loads((self.prefix/'CASE_INSTALL.json').read_bytes())
        inventory=self.prefix/'SOURCE_INSTALL_INVENTORY.json'
        self.assertEqual(hashlib.sha256(inventory.read_bytes()).hexdigest(),receipt['sourceInventorySha256'])
        self.assertFalse((self.prefix/'lib/rhook_alpha/cases/calibration25').exists())
        policy=json.loads((self.prefix/'lib/engine/case_sdk/policy.json').read_bytes())
        self.assertEqual(policy['minimumAdmissionFreeBytes'],1536<<20)
        self.assertEqual(self.cli('cases')['cases'],[])
        self.assertEqual(self.cli('interventions')['schema'],'rhook/historical-intervention-catalogue/0.1')
        result=self.api("assert not home.exists()\nprint(json.dumps(dict(cases=sdk.list_cases(),catalogue=sdk.interventions(),profiles=ExecutionSDK(home).profiles())))")
        self.assertEqual(result['cases'],[]);self.assertTrue(result['profiles'])

    def test_real_import_inspect_and_plan_keep_authentication_unclaimed(self):
        bundle=self.synthetic('cleanroom-synthetic')
        imported=self.cli('import-case',bundle);self.assertEqual(imported['authentication'],'UNAUTHENTICATED')
        inspected=self.cli('inspect','--case','cleanroom-synthetic');self.assertFalse(inspected['executionAuthorized'])
        plan=self.cli('plan','--case','cleanroom-synthetic','--set','lpBps=50')
        self.assertEqual(plan['status'],'PLANNED');self.assertIsNone(plan['branchResult'])
        result=self.api("print(json.dumps(dict(inspect=sdk.inspect('cleanroom-synthetic'),plan=sdk.describe(sys.argv[3]))))",plan['planId'])
        self.assertEqual(result['plan']['intervention'],{'rule':'lpBps','value':50})
        self.assertEqual(result['inspect']['witnessClosure'],'NOT_EVALUATED')

    def test_tampered_or_mismatched_case_is_rejected(self):
        bundle=self.synthetic('cleanroom-tampered');p=bundle/'BLOCK_PACKAGE.json';p.write_bytes(p.read_bytes()+b' ')
        failure=self.cli('import-case',bundle,success=False);self.assertEqual(failure['status'],'INPUT_OR_RUNTIME_STOP')
        self.assertFalse((self.home/'names').exists())
        bundle=self.synthetic('cleanroom-mismatched');p=bundle/'CAPSULE.json';value=json.loads(p.read_bytes());value['caseId']='changed-without-resealing';p.write_text(json.dumps(value))
        self.cli('import-case',bundle,success=False)

    def test_missing_worker_witness_and_dependencies_are_explicit(self):
        caps=self.cli('execution-capabilities');self.assertFalse(caps['nativeExecutionReady'])
        codes={v['code'] for v in caps['missing']}
        self.assertTrue({'NATIVE_RUNTIME_MISSING','PREPARED_WITNESS_MISSING','RUNTIME_DEPENDENCIES_MISSING'}<=codes)
        self.assertFalse(caps['components']['worker']['available'])
        self.assertEqual(caps['host']['resourceAdmission'],'NOT_RUN')
        self.assertEqual(caps['host']['powerAndLid'],'NOT_OBSERVED')
        configuration=self.cli('execution-configure','--lp-bps','50');path=self.root/'configuration.json';path.write_text(json.dumps(configuration))
        failure=self.cli('execution-prepare','--configuration',path,'--witness',self.root/'absent-witness','--witness-sha256','0'*64,'--output',self.root/'absent-output',success=False)
        self.assertEqual(failure['causeCode'],'PREPARED_WITNESS_MISSING')
        bundle=self.synthetic('cleanroom-no-runtime');self.cli('import-case',bundle)
        self.api("try:\n sdk.authenticate('cleanroom-no-runtime')\nexcept FileNotFoundError as e:\n assert 'NATIVE_RUNTIME_MISSING:' in str(e) and e.errno==2,str(e)\n print(json.dumps(dict(error=str(e),nativeExecutions=0)))\nelse:raise AssertionError('missing runtime unexpectedly succeeded')")
        self.assertFalse((self.home/'RUNTIME.json').exists());self.assertFalse((self.home/'.case-consent.key').exists())

    @unittest.skipUnless(CASES,'optional explicitly supplied local historical case bundles')
    def test_explicit_historical_case_bundles_import_and_plan(self):
        for row in json.loads(Path(CASES).read_bytes()):
            imported=self.cli('import-case',row['bundle']);self.assertEqual(imported['caseId'],row['caseId'])
            self.assertEqual(imported['authentication'],'UNAUTHENTICATED')
            inspected=self.cli('inspect','--case',row['caseId']);self.assertEqual(inspected['arrivals'],row['arrivals'])
            planned=self.cli('plan','--case',row['caseId'],'--set',row['intervention']);self.assertFalse(planned['executionAuthorized'])
            result=self.api('print(json.dumps(sdk.describe(sys.argv[3])))',planned['planId'])
            self.assertEqual(result['runtimePlan']['inputCommitment'],row['inputCommitment'])

    @unittest.skipUnless(EVIDENCE,'optional complete pinned Build10/11 packet supplied explicitly')
    def test_retained_evidence_integrity_cli_api_and_tamper(self):
        inspected=self.cli('scenario-evidence-inspect','--bundle',EVIDENCE)
        self.assertEqual(inspected['status'],'SCENARIO_EVIDENCE_INSPECTED')
        checked=self.cli('scenario-evidence-verify','--bundle',EVIDENCE)
        self.assertEqual(checked['status'],'SCENARIO_EVIDENCE_INTEGRITY_PASS')
        compared=self.cli('scenario-evidence-compare','--bundle',EVIDENCE)
        self.assertFalse(compared['scope']['EVMReexecution']);self.assertFalse(compared['scope']['MPTProofVerification'])
        result=self.api('print(json.dumps(sdk.verify_recorded_scenario(Path(sys.argv[3]))))',EVIDENCE)
        self.assertEqual(result['qualifiedClaims'],0)
        target=self.root/'tampered-evidence';shutil.copytree(EVIDENCE,target)
        path=target/'OFFLINE_FINAL.json';path.write_bytes(path.read_bytes()+b' ')
        failure=self.cli('scenario-evidence-verify','--bundle',target,success=False)
        self.assertIn('FILE_HASH_MISMATCH',failure['causeCode'])

if __name__=='__main__':unittest.main()
