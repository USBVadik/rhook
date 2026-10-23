"""Focused Pair02 acceptance. All host/worker execution is mocked; sensor data is sealed evidence."""
import ast,copy,hashlib,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_once as r
P=r.WS/'development/rhook-saved-hookr-native-pair-01'
H=r.WS/'experiments/rhook-native-host-preflight-01'
class LauncherTests(unittest.TestCase):
 def setUp(self):
  self.b={'operationCommitment':'new-exact-fixture','binarySha256':'binary','archivePath':'/no-output/expected','executionContext':'require_escalated','limits':{}}
  self.a={'founderApproved':True,'domain':'SAVED_EXPLORATORY_NATIVE_PAIR','operationCommitment':self.b['operationCommitment'],'binarySha256':'binary','maximumInvocations':{'ACTUAL':1,'BRANCH':1,'B':0},'RPC':0,'WSS':0,'runtimePath':str(r.ROOT/'runtime'),'archivePath':self.b['archivePath'],'notBeforeUnix':1000,'expiresUnix':1500,'macOnPowerOpenLid':True,'noRetry':True,'executionContext':'require_escalated'}
 def fixture(self,root):
  a=dict(self.a);a['runtimePath']=str(root/'runtime');a['notBeforeUnix']=int(r.time.time())-1;a['expiresUnix']=int(r.time.time())+300
  path=root/'SYNTHETIC_AUTH.json';path.write_text(json.dumps(a));return path
 def fake_capture(self,stdout,stderr,exit_code=0,stop=None):
  def invoke(command,directory,timeout):
   self.assertEqual(timeout,7);self.assertEqual(command[0],'/opt/rhook/runtime/node')
   self.assertTrue((directory.parent/'STARTED.json').exists())
   directory.mkdir();(directory/'stdout.bin').write_bytes(stdout);(directory/'stderr.bin').write_bytes(stderr)
   result={'exitCode':exit_code,'stop':stop,'captureError':None,'truncated':{'stdout':False,'stderr':False},'ownedChildReaped':True}
   r.store(directory/'RESULT.json',result);return result,stdout,stderr
  return invoke
 def test_false_scope_wrong_context_and_old_authority_rejected(self):
  r.authority(json.dumps(self.a).encode(),self.b,1100)
  for key,value in [('founderApproved',False),('operationCommitment','other'),('RPC',1),('WSS',1),('maximumInvocations',{'ACTUAL':2,'BRANCH':1,'B':0}),('executionContext','use_default'),('noRetry',False)]:
   a=dict(self.a);a[key]=value
   with self.assertRaises(AssertionError,msg=key):r.authority(json.dumps(a).encode(),self.b,1100)
  old=(P/'runtime/AUTHORITY_RAW.json').read_bytes()
  with self.assertRaisesRegex(AssertionError,'EXACT_AUTHORITY_REQUIRED'):r.authority(old,self.b,r.time.time())
 def test_host_failure_stderr_warning_timeout_and_assessment_stop_block_native(self):
  diagnostic,legacy=r.host_modules();valid=(H/'NODE_SENSOR/stdout.bin').read_bytes()
  bad=json.loads(valid);bad['samples'][0]['pressureBefore']=2
  cases=[(b'partial',b'exact synthetic Node permission error',17,None,'NODE_EXIT_NONZERO_OR_NOT_STARTED'),(valid,b'synthetic warning',0,None,'NODE_STDERR_NONEMPTY'),(b'partial',b'',-9,'WALL_TIME_LIMIT','WALL_TIME_LIMIT'),(json.dumps(bad).encode(),b'',0,None,'ABNORMAL_MEMORY_PRESSURE')]
  for stdout,stderr,code,stop,cause in cases:
   with self.subTest(cause=cause),tempfile.TemporaryDirectory() as directory:
    root=Path(directory);auth=self.fixture(root)
    with patch.object(r,'ROOT',root),patch.object(r,'host_modules',return_value=(diagnostic,legacy)),patch.object(diagnostic,'capture',side_effect=self.fake_capture(stdout,stderr,code,stop)) as capture,patch.object(r,'monitored') as native:
     out=r.launch(auth,self.b);native.assert_not_called();self.assertEqual(capture.call_count,1)
     self.assertEqual(out['terminal'],'HOST_STOP');self.assertIn(cause,out['cause']);self.assertTrue(out['authorityPermanentlyClosed'])
     self.assertEqual((root/'runtime/HOST_SENSOR/stdout.bin').read_bytes(),stdout);self.assertEqual((root/'runtime/HOST_SENSOR/stderr.bin').read_bytes(),stderr)
     self.assertEqual(json.loads((root/'runtime/HOST_SENSOR/RESULT.json').read_text())['exitCode'],code)
     with self.assertRaises(FileExistsError):r.launch(auth,self.b)
     self.assertEqual(capture.call_count,1)
 def test_sealed_host_packet_passes_unchanged_assessor_then_one_worker_handoff(self):
  diagnostic,legacy=r.host_modules();valid=(H/'NODE_SENSOR/stdout.bin').read_bytes()
  expected=json.loads((H/'FINAL_RESULT.json').read_text())['admission']
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);auth=self.fixture(root)
   def worker(raw,rt,limits):
    admitted=json.loads((rt/'HOST_ADMISSION.json').read_text());self.assertTrue(admitted['accepted']);self.assertEqual(admitted['recorded']['admission'],expected)
    self.assertTrue((rt/'HOST_SENSOR/RESULT.json').exists());self.assertEqual((rt/'HOST_SENSOR/stdout.bin').read_bytes(),valid)
    r.store(rt/'NATIVE_COMPLETION.json',{'operationCommitment':self.b['operationCommitment'],'result':{'terminal':'HOST_STOP_MISSING_STATE','nativeInvocations':{'ACTUAL':1,'BRANCH':0,'B':0},'cause':'SYNTHETIC_ONLY'}})
    return {'stop':None,'resourcesReliable':True,'workerReaped':True,'exitCode':1}
   with patch.object(r,'ROOT',root),patch.object(r,'host_modules',return_value=(diagnostic,legacy)),patch.object(diagnostic,'capture',side_effect=self.fake_capture(valid,b'')) as capture,patch.object(r,'monitored',side_effect=worker) as native:
    out=r.launch(auth,self.b);self.assertEqual(capture.call_count,1);self.assertEqual(native.call_count,1);self.assertEqual(out['terminal'],'HOST_STOP_MISSING_STATE')
 def test_native_monitor_and_process_identity_code_are_byte_identical(self):
  old=(P/'tools/run_once.py').read_text();new=(r.ROOT/'tools/run_once.py').read_text()
  def function(src,name):
   tree=ast.parse(src);node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name);return ast.get_source_segment(src,node)
  for name in ['monitored','sample_owned','store']:self.assertEqual(function(old,name),function(new,name),name)
 def test_binary_package_and_plan_exact_without_rebuild_or_replay(self):
  self.assertEqual(r.sha(r.ROOT/'artifacts/rhook-saved-pair'),'f84f816b1892f336ade55b4f74c123f7a3f0eff5fe1cabf2989cf242c7129a4c')
  self.assertEqual((r.ROOT/'native/plan.json').read_bytes(),(P/'native/plan.json').read_bytes())
  plan=json.loads((r.ROOT/'native/plan.json').read_text());self.assertEqual(r.sha(plan['packagePath']),'b55ba3a6d70bd081148966f3b447135a098a26c18bae0c773f065beda807bda3')
  previous=json.loads((P/'records/FOCUSED_FINAL.json').read_text());self.assertEqual(previous['exitCode'],0);self.assertEqual(previous['scientificNativeRuns'],0)
  names=previous['passed']
  for case in ['missing','matched','state','receipts','hash','arrivals','input']:self.assertIn('TestActualFailureOrAnyCommitmentMismatchClosesBranch/'+case,names)
  self.assertIn('TestPinnedSavedPackageAdmissionAndFreshNilSourceBridges',names)
 def test_check_mode_cannot_observe_or_execute(self):
  with patch.object(r,'static',return_value=(self.b,{'fixture':'offline'})),patch.object(r.sys,'argv',['run_once.py','--check']),patch.object(r,'host_admission') as host,patch.object(r,'monitored') as native:
   r.main();host.assert_not_called();native.assert_not_called()
 def test_owned_worker_rss_limit_and_cpu_caps_remain_enforced(self):
  class Worker:
   pid=987654321
   returncode=None
   stdin=io.BytesIO()
   def __init__(self):
    self.fds=[]
    for name in ['stdout','stderr']:
     a,b=os.pipe();setattr(self,name,os.fdopen(a,'rb'));self.fds.append(b)
   def poll(self):return self.returncode
   def wait(self,timeout):self.returncode=-9;return self.returncode
  worker=Worker();limits={'pairWallSeconds':120,'workerKernelCpuSeconds':120,'workerSampledRssBytes':4<<30,'workerTelemetryMs':100,'maximumTelemetryGapSeconds':2}
  with tempfile.TemporaryDirectory() as directory:
   with patch.object(r.subprocess,'Popen',return_value=worker) as spawn,patch.object(r,'sample_owned',return_value={'rssBytes':(4<<30)+1}),patch.object(r.os,'killpg') as kill,patch.object(r.resource,'getrusage',return_value=type('Usage',(),{'ru_utime':0,'ru_stime':0})()):
    out=r.monitored(b'{}',Path(directory),limits);kill.assert_called_once_with(worker.pid,r.signal.SIGKILL)
    self.assertEqual(out['stop'],'SAMPLED_WORKER_RSS_LIMIT');self.assertTrue(out['workerReaped'])
    with patch.object(r.resource,'setrlimit') as cap:
     spawn.call_args.kwargs['preexec_fn']();self.assertIn(unittest.mock.call(r.resource.RLIMIT_CPU,(120,120)),cap.call_args_list)
   for fd in worker.fds:os.close(fd)
if __name__=='__main__':unittest.main(verbosity=2)
