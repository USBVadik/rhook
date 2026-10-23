"""Owned C fixtures with synthetic RSS rows, never real host readiness readings."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from sdk_alpha_v2 import common,kit


class V2SupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(dir='/private/tmp')
        cls.root=Path(cls.tmp.name);source=cls.root/'fixture.c';cls.binary=cls.root/'fixture'
        source.write_text('''#include <unistd.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
 const char *limit=getenv("GOMEMLIMIT");
 if(limit){write(1,limit,strlen(limit));write(1,"\\n",1);}
 usleep(400000); return 0;
}
''')
        subprocess.run(['/usr/bin/clang','-O0',str(source),'-o',str(cls.binary)],check=True,capture_output=True,timeout=20)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_fixture(self,rss,interrupted=False,sensor_error=False,wall_timeout=False):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp);(root/'runtime').mkdir();(root/'artifacts').mkdir()
            worker=root/'artifacts/rhook-saved-pair';common.exact_copy(self.binary,worker);worker.chmod(0o700)
            guards=common.portable.guards
            def simulated(proc):
                return dict(pid=proc.pid,ppid=os.getpid(),pgid=proc.pid,executable=str(worker),rssBytes=rss)
            real_time=guards.time
            start=real_time.monotonic();clock_calls=[]
            def clock():
                clock_calls.append(True)
                return start if len(clock_calls)==1 else start+121
            clock_context=patch.object(guards,'time',types.SimpleNamespace(monotonic=clock)) if wall_timeout else patch.object(guards,'time',real_time)
            with patch.object(guards,'sample_owned',side_effect=simulated),patch.object(kit,'RuntimeGuard') as host,clock_context:
                if interrupted:host.return_value.poll.side_effect=lambda:os.kill(os.getpid(),signal.SIGTERM)
                if sensor_error:host.return_value.poll.side_effect=ValueError('SYNTHETIC_SENSOR_FAILURE')
                result=kit.supervise(b'{}',root,root/'unused-host-sensor',{})
            self.assertTrue(result['workerReaped'])
            self.assertTrue((root/'runtime/PROCESS_COMPLETION.json').is_file())
            self.assertFalse((root/'runtime/NATIVE_COMPLETION.json').exists())
            self.assertEqual(__import__('json').loads((root/'runtime/PROCESS_STARTED.json').read_text())['kernelCpuSeconds'],120)
            stdout=(root/'runtime/stdout.log').read_bytes()
            return result,stdout

    def test_rss_below_and_at_class_limit_are_accepted(self):
        for rss in [(1<<30)-1024,1<<30]:
            with self.subTest(rss=rss):
                result,stdout=self.run_fixture(rss)
                self.assertIsNone(result['stop'])
                self.assertEqual(result['exitCode'],0)
                self.assertEqual(result['sampledPeakWorkerRSS'],rss)
                self.assertEqual(stdout,b'536870912\n')

    def test_one_kib_above_class_limit_is_forcibly_terminated(self):
        result,_=self.run_fixture((1<<30)+1024)
        self.assertEqual(result['stop'],'SAMPLED_WORKER_RSS_LIMIT')
        self.assertNotEqual(result['exitCode'],0)

    def test_missing_or_inconsistent_sensor_data_stops_worker(self):
        result,_=self.run_fixture(400<<20,sensor_error=True)
        self.assertEqual(result['stop'],'SUPERVISION_FAILURE_ValueError')
        self.assertNotEqual(result['exitCode'],0)

    def test_signal_after_dispatch_cleans_up_owned_worker(self):
        result,_=self.run_fixture(400<<20,interrupted=True)
        self.assertEqual(result['stop'],'EXTERNAL_SIGNAL')
        self.assertNotEqual(result['exitCode'],0)

    def test_wall_deadline_keeps_original_120_second_budget(self):
        result,_=self.run_fixture(400<<20,wall_timeout=True)
        self.assertEqual(result['stop'],'PAIR_WALL_TIME_LIMIT')

    def test_signal_before_admission_reaps_owned_capture(self):
        guards=common.portable.guards
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp);(root/'KIT.json').write_text('{}')
            timer=threading.Timer(.1,lambda:os.kill(os.getpid(),signal.SIGTERM))
            with kit.operator_lock(root):
                try:
                    timer.start();guards.WS=root
                    result,_,_=guards.capture([str(self.binary)],root/'synthetic-capture',1)
                finally:
                    timer.cancel();timer.join(timeout=1)
            self.assertFalse(timer.is_alive())
            self.assertTrue(result['ownedChildReaped'])
            self.assertIsNone(result['cleanupError'])
            self.assertEqual(result['stop'],'CAPTURE_ERROR')
            self.assertIn('OPERATOR_SIGNAL_15',result['captureError'])


if __name__=='__main__':unittest.main()
