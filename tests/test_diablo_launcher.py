"""Real launcher lifecycle, API persistence and unarmed-start smoke test."""
import http.client
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DiabloLauncherTest(unittest.TestCase):
    def test_boot_save_duplicate_and_stop(self):
        runtime = os.environ.get('DIABLO_TEST_RUNTIME')
        if not runtime:
            self.skipTest('Set DIABLO_TEST_RUNTIME to the bootstrap runtime directory')
        subprocess.run(['make', '-C', str(ROOT / 'control')], check=True,
                       stdout=subprocess.DEVNULL)
        with tempfile.TemporaryDirectory(prefix='diablo-launch-') as scratch:
            path = Path(scratch)
            # Select a free, contiguous preview block without depending on LAN devices.
            for base in range(26000, 50000, 17):
                probes = []
                try:
                    for offset in range(12):
                        sock = socket.socket()
                        probes.append(sock)
                        sock.bind(('127.0.0.1', base + offset))
                    break
                except OSError:
                    continue
                finally:
                    for sock in probes:
                        sock.close()
            else:
                self.fail('No free test port block')
            config = path / 'config.txt'
            config.write_text((ROOT / 'control/diablo-config.example').read_text())
            values = {
                'PORTSDOWN_DIR': ROOT, 'DIABLO_RUNTIME': runtime,
                'PORTSDOWN_CONFIG': config, 'PORTSDOWN_RUN_DIR': path / 'run',
                'PORTSDOWN_PRESETS_PATH': path / 'presets.json',
                'PORTSDOWN_IPCAM_CONFIG': path / 'cameras.conf',
                'PORTSDOWN_HTTP_PORT': base, 'PORTSDOWN_MJPEG_PORT': base + 1,
                'PORTSDOWN_SRT_MJPEG_PORT_BASE': base + 2,
                'PORTSDOWN_SOURCE_MJPEG_PORT_BASE': base + 7,
                'PORTSDOWN_BOARD': 'none', 'PORTSDOWN_PEER_ROLE': 'STANDALONE',
                'PORTSDOWN_TX_EXEC': '', 'PORTSDOWN_SAFE_OFF_EXEC': '',
                'PORTSDOWN_PREVIEW_EXEC': '', 'PORTSDOWN_SOURCE_PREVIEW_EXEC': '',
            }
            envfile = path / 'diablo.env'
            envfile.write_text(''.join(f'export {k}={shlex.quote(str(v))}\n'
                                      for k, v in values.items()))

            def request(method, route, data=None):
                conn = http.client.HTTPConnection('127.0.0.1', base, timeout=2)
                try:
                    conn.request(method, route, json.dumps(data) if data else None,
                                 {'X-Portsdown-Control': '1', 'Content-Type': 'application/json'})
                    response = conn.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    conn.close()

            with (path / 'launcher.log').open('w+') as log:
                proc = subprocess.Popen(['bash', str(ROOT / 'scripts/run-diablo.sh'), str(envfile)],
                                        stdout=log, stderr=subprocess.STDOUT)
                try:
                    for _ in range(100):
                        try:
                            if request('GET', '/api/state')[0] == 200:
                                break
                        except OSError:
                            pass
                        self.assertIsNone(proc.poll(), 'launcher exited during startup')
                        time.sleep(.05)
                    else:
                        self.fail('No API after launcher start')
                    self.assertEqual(request('POST', '/api/config', {
                        'call': 'N0CALL', 'service_name': 'Install test'})[0], 200)
                    self.assertIn('service_name=Install test', config.read_text())
                    self.assertNotEqual(request('POST', '/api/tx/start')[0], 200)
                    duplicate = subprocess.run(
                        ['bash', str(ROOT / 'scripts/run-diablo.sh'), str(envfile)],
                        capture_output=True, text=True, timeout=5)
                    self.assertEqual(duplicate.returncode, 2)
                    self.assertIn('already running', duplicate.stderr)
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                        self.fail('Launcher failed to stop within eight seconds')
                self.assertFalse((path / 'run/tx.sock').exists(), 'supervisor socket left behind')
                with socket.socket() as probe:
                    self.assertNotEqual(probe.connect_ex(('127.0.0.1', base)), 0)


if __name__ == '__main__':
    unittest.main()
