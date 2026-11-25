"""No-hardware ASI route validation and channel ownership regression checks."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

class LiveAsiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.config = self.path / 'config'
        self.base = ('modeoutput=DEKTEC_ASI\nmodulation=ASI\nasi_device=0\n'
                     'asi_channel=0\nasi_bitrate=3071588\nsource_layout=DIRECT\n'
                     'modeinput=IPTSIN\niptransport=srt\nudpinport=28910\n'
                     'call=KJ6DZB\nservice_name=ASI Test\n')
        self.config.write_text(self.base)
        self.args = self.path / 'args'
        fake = self.path / 'tsp'
        fake.write_text('#!/bin/sh\n'
                        'if [ "$1" = -P ]; then exit 0; fi\n'
                        'printf "%s\\n" "$@" > "$ARGS_FILE"\n'
                        'if [ "${HOLD:-}" = yes ]; then exec sleep 20; fi\n')
        fake.chmod(0o755)
        self.env = os.environ | {'PATH':str(self.path)+':'+os.environ['PATH'],
                                'PORTSDOWN_CONFIG':str(self.config),
                                'PORTSDOWN_BOARD':'dektec_asi',
                                'PORTSDOWN_ASI_LOCK_DIR':str(self.path/'locks'),
                                'ARGS_FILE':str(self.args)}
        self.command = [str(ROOT/'control/dektec-asi-live.sh')]

    def run_route(self):
        return subprocess.run(self.command, env=self.env, capture_output=True,
                              text=True, timeout=5)

    def test_srt_metadata_and_low_latency_output(self):
        result = self.run_route()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.args.read_text().splitlines()
        for option,value in [('--listener','127.0.0.1:28910'),
                             ('--max-output-packets','128'),('--fifo-size','262144'),
                             ('--name','ASI Test'),('--bitrate','3071588')]:
            self.assertEqual(args[args.index(option)+1],value)
        self.assertIn('--instant-detach',args)
        self.assertNotIn('--multiple',args)  # no implicit source-loss restart

    def test_selected_srt_slot_and_udp_input(self):
        self.config.write_text(self.base.replace('modeinput=IPTSIN','modeinput=SRT')+
                               'srt_source_slot=5\n')
        self.assertEqual(self.run_route().returncode,0)
        args=self.args.read_text().splitlines()
        self.assertEqual(args[args.index('-I')+1:args.index('-I')+3],['ip','12005'])
        self.assertIn('1500',args)

    def test_bad_routes_do_not_start_output(self):
        for old,new in [('modeinput=IPTSIN','modeinput=HDMI'),
                        ('source_layout=DIRECT','source_layout=MULTIVIEW'),
                        ('udpinport=28910','udpinport=0'),
                        ('asi_bitrate=3071588','asi_bitrate=0'),
                        ('iptransport=srt','iptransport=invalid')]:
            with self.subTest(new=new):
                self.config.write_text(self.base.replace(old,new))
                self.assertNotEqual(self.run_route().returncode,0)
                self.assertFalse(self.args.exists())

    def test_duplicate_channel_rejected_then_released(self):
        first=subprocess.Popen(self.command,env=self.env|{'HOLD':'yes'},
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+3
            while not self.args.exists() and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertTrue(self.args.exists())
            second=self.run_route()
            self.assertNotEqual(second.returncode,0)
            self.assertIn('already owned',second.stderr)
        finally:
            first.terminate(); first.wait(timeout=3)
        self.assertEqual(self.run_route().returncode,0)

if __name__ == '__main__':
    unittest.main()
