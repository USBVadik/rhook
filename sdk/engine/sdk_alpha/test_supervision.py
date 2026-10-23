"""Owned C fixture only: no Nitro, saved block, EVM, provider or real host sensor."""
from pathlib import Path
import os
import signal
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from sdk_alpha import kit
from sdk_alpha.common import portable


class SupervisionTests(unittest.TestCase):
    def run_fixture(self, mode, host_error=False, interrupt=False, capture_only=False):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            root=Path(tmp); (root/'runtime').mkdir(); (root/'artifacts').mkdir()
            source=root/'fixture.c'
            source.write_text('''#include <unistd.h>
#include <string.h>
int main(void) {
 char buffer[8192]; memset(buffer, 'x', sizeof buffer);
 usleep(250000);
#if MODE == 1
 for (int i=0;i<9000;i++) if (write(1,buffer,sizeof buffer)<0) return 2;
#else
 usleep(250000); write(1,"fixture done\\n",13);
#endif
 return 0;
}
''')
            built=subprocess.run(['/usr/bin/clang','-O0','-DMODE='+str(mode),str(source),'-o',str(root/'artifacts/rhook-saved-pair')],
                                 capture_output=True,text=True,timeout=20)
            self.assertEqual(built.returncode,0,built.stderr)
            if capture_only:
                (root/'KIT.json').write_text('{}')
                timer=threading.Timer(.1,lambda:os.kill(os.getpid(),signal.SIGTERM))
                with kit.operator_lock(root):
                    try:
                        timer.start()
                        portable.guards.WS=root
                        result,stdout,stderr=portable.guards.capture(
                            [str(root/'artifacts/rhook-saved-pair')],root/'sensor-fixture',1)
                    finally:
                        timer.cancel();timer.join(timeout=1)
                self.assertFalse(timer.is_alive())
                self.assertTrue(result['ownedChildReaped'])
                self.assertEqual(result['stop'],'CAPTURE_ERROR')
                self.assertIn('KeyboardInterrupt: OPERATOR_SIGNAL_15',result['captureError'])
                self.assertIsNone(result['cleanupError'])
                return result
            with patch.object(kit, 'RuntimeGuard') as guard:
                if host_error: guard.return_value.poll.side_effect=ValueError('SYNTHETIC_HOST_PRESSURE_STOP')
                if interrupt: guard.return_value.poll.side_effect=lambda: os.kill(os.getpid(),signal.SIGTERM)
                result=kit.supervise(b'{}',root,root/'unused-sensor',{})
            self.assertTrue(result['workerReaped'])
            self.assertTrue((root/'runtime/PROCESS_COMPLETION.json').is_file())
            self.assertLess(result['wallSeconds'],5)
            self.assertFalse((root/'runtime/NATIVE_COMPLETION.json').exists())
            return result

    def test_owned_fixture_success_preserves_measurements(self):
        result=self.run_fixture(0)
        self.assertIsNone(result['stop'])
        self.assertEqual(result['exitCode'],0)
        self.assertGreater(result['samples'],0)
        self.assertTrue(result['resourcesReliable'])
        self.assertGreater(result['sampledPeakWorkerRSS'],0)

    def test_resource_sensor_failure_terminates_and_reaps_only_fixture(self):
        result=self.run_fixture(0,True)
        self.assertEqual(result['stop'],'SUPERVISION_FAILURE_ValueError')
        self.assertNotEqual(result['exitCode'],0)

    def test_combined_output_overflow_is_bounded_and_reaped(self):
        result=self.run_fixture(1)
        self.assertEqual(result['stop'],'COMBINED_OUTPUT_LIMIT')
        self.assertEqual(result['stdoutStderrBytes'],64<<20)

    def test_signal_during_dispatch_stops_and_reaps_owned_fixture(self):
        result=self.run_fixture(0,interrupt=True)
        self.assertEqual(result['stop'],'EXTERNAL_SIGNAL')
        self.assertNotEqual(result['exitCode'],0)

    def test_pre_admission_signal_unwinds_capture_and_reaps_owned_fixture(self):
        result=self.run_fixture(0,capture_only=True)
        self.assertTrue(result['ownedProcessGroupKilled'])


if __name__ == '__main__': unittest.main()
