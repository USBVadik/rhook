"""Synthetic pipe/exit tests only. No Node, sysctl, vm_stat or ps invocation."""
from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch
import diagnostic as d
class DiagnosticTests(unittest.TestCase):
 def test_check_never_observes_host(self):
  with patch.object(d,'verify',return_value={'operationCommitment':'synthetic'}),patch.object(d.sys,'argv',['diagnostic.py','--check']),patch.object(d,'capture') as observe:
   d.main();observe.assert_not_called()
 def run_child(self,source,**limits):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
  directory=Path(temp.name)/'capture'
  result,out,err=d.capture([sys.executable,'-B','-c',source],directory,limits.pop('timeout',2),**limits)
  self.assertEqual(json.loads((directory/'RESULT.json').read_text())['exitCode'],result['exitCode'])
  self.assertEqual((directory/'stdout.bin').read_bytes(),out);self.assertEqual((directory/'stderr.bin').read_bytes(),err)
  self.assertTrue(result['ownedChildReaped'])
  return result,out,err
 def test_success_and_pure_assessment(self):
  result,out,err=self.run_child('print(\'{"fixture":"synthetic"}\')')
  decision=d.evaluate(result,out,err,lambda raw:{'status':'ADMISSION_PASS','fixture':raw['fixture']})
  self.assertEqual(decision['status'],'LEGACY_ADMISSION_PASS');self.assertEqual(decision['admission']['fixture'],'synthetic')
 def test_nested_failure_exit_and_both_streams_preserved(self):
  result,out,err=self.run_child('import sys;print("partial nested output");print("synthetic permission error",file=sys.stderr);sys.exit(17)')
  self.assertEqual(result['exitCode'],17);self.assertIn(b'partial nested output',out);self.assertIn(b'synthetic permission error',err)
  def no_assess(_):self.fail('assessor entered after process failure')
  self.assertEqual(d.evaluate(result,out,err,no_assess)['cause'],'NODE_EXIT_NONZERO_OR_NOT_STARTED')
 def test_success_exit_with_warning_remains_rejected(self):
  result,out,err=self.run_child('import sys;print("{}");print("synthetic warning",file=sys.stderr)')
  self.assertEqual(result['exitCode'],0);self.assertEqual(d.evaluate(result,out,err,lambda _:self.fail())['cause'],'NODE_STDERR_NONEMPTY')
 def test_stdout_overflow_bounded_and_no_assessment(self):
  result,out,err=self.run_child('import os;os.write(1,b"x"*100000)',stdout_limit=128)
  self.assertEqual(len(out),128);self.assertTrue(result['truncated']['stdout']);self.assertEqual(result['stop'],'BOUNDED_STDOUT_LIMIT')
  self.assertNotEqual(d.evaluate(result,out,err,lambda _:self.fail())['status'],'LEGACY_ADMISSION_PASS')
 def test_stderr_overflow_bounded(self):
  result,out,err=self.run_child('import os;os.write(2,b"e"*100000)',stderr_limit=128)
  self.assertEqual(len(err),128);self.assertTrue(result['truncated']['stderr']);self.assertEqual(result['stop'],'BOUNDED_STDERR_LIMIT')
 def test_timeout_cleans_owned_child_and_retains_partial(self):
  result,out,err=self.run_child('import time;print("before timeout",flush=True);time.sleep(2)',timeout=0.15)
  self.assertEqual(result['stop'],'WALL_TIME_LIMIT');self.assertTrue(result['ownedProcessGroupKilled']);self.assertIn(b'before timeout',out)
 def test_spawn_failure_recorded_without_erasing_diagnostics(self):
  with tempfile.TemporaryDirectory() as t:
   result,out,err=d.capture(['/nonexistent/synthetic-command'],Path(t)/'capture',1)
   self.assertIsNone(result['exitCode']);self.assertIn('FileNotFoundError',result['captureError']);self.assertTrue((Path(t)/'capture/RESULT.json').exists())
 def test_invalid_json_and_assessment_failure_separate(self):
  result,out,err=self.run_child('print("not JSON")')
  self.assertEqual(d.evaluate(result,out,err,lambda _:self.fail())['status'],'HOST_SENSOR_JSON_REJECTED')
  def reject(_):raise AssertionError('SYNTHETIC_COUNTER_REGRESSION')
  self.assertEqual(d.evaluate(result,b'{}',b'',reject)['cause'],'AssertionError: SYNTHETIC_COUNTER_REGRESSION')
 def test_legacy_exact_65536_boundary_rejected(self):
  result,out,err=self.run_child('import os;os.write(1,b"x"*65536)')
  self.assertIsNone(result['stop']);self.assertEqual(len(out),65536)
  self.assertEqual(d.evaluate(result,out,err,lambda _:self.fail())['cause'],'NODE_STDOUT_EXCEEDS_LEGACY_STRICT_LIMIT')
 def test_false_or_scientific_permit_and_wrong_context_rejected(self):
  b={'operationCommitment':'exact','outputPath':'/private/tmp/synthetic-only'}
  a={'founderApproved':True,'domain':'HOST_DIAGNOSTIC_PREFLIGHT_ONLY','operationCommitment':'exact','executionContext':'require_escalated','ACTUAL':0,'BRANCH':0,'B':0,'RPC':0,'WSS':0,'hostNodeInvocations':1,'ownProcessQueries':1,'outputPath':b['outputPath'],'notBeforeUnix':1000,'expiresUnix':1200}
  d.permit(json.dumps(a).encode(),b,1050)
  for key,value in [('founderApproved',False),('domain','SCIENTIFIC'),('ACTUAL',1),('BRANCH',1),('hostNodeInvocations',2),('ownProcessQueries',2),('executionContext','use_default'),('outputPath','other')]:
   changed=dict(a);changed[key]=value
   with self.assertRaises(AssertionError,msg=key):d.permit(json.dumps(changed).encode(),b,1050)
if __name__=='__main__':unittest.main(verbosity=2)
