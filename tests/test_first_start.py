"""Native first-start workflow, config safety, listener-only startup and reruns."""
import fcntl
import os
from pathlib import Path
import shlex
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FirstStartTest(unittest.TestCase):
    def setUp(self):
        runtime = os.environ.get('DIABLO_TEST_RUNTIME')
        if not runtime:
            self.skipTest('Set DIABLO_TEST_RUNTIME to a native installed runtime')
        self.temp = tempfile.TemporaryDirectory(prefix='diablo-first-start-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        for name in ('state', 'logs', 'bin', 'run'):
            (self.path / name).mkdir()
        self.config = self.path / 'state/config.txt'
        self.config.write_text((ROOT / 'control/diablo-config.example').read_text() + 'operator_extra=keep\n')
        self.camera = self.path / 'state/ip-cameras.conf'
        self.camera.write_text('PRIVATE CAMERA SENTINEL\n')
        self.marker = self.path / 'listener-started'
        hook = self.path / 'mock-srt'
        hook.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> ' + shlex.quote(str(self.marker)) + '\nexec sleep 60\n')
        hook.chmod(0o700)
        for base in range(31000, 50000, 19):
            probes = []
            try:
                for offset in range(12):
                    s = socket.socket()
                    probes.append(s)
                    s.bind(('127.0.0.1', base + offset))
                break
            except OSError:
                continue
            finally:
                for s in probes:
                    s.close()
        else:
            self.fail('No test ports')
        self.values = {
            'PORTSDOWN_DIR': ROOT, 'DIABLO_RUNTIME': runtime,
            'PORTSDOWN_CONFIG': self.config, 'PORTSDOWN_RUN_DIR': self.path / 'run',
            'PORTSDOWN_PRESETS_PATH': self.path / 'state/presets.json',
            'PORTSDOWN_IPCAM_CONFIG': self.camera,
            'PORTSDOWN_HTTP_PORT': base, 'PORTSDOWN_MJPEG_PORT': base + 1,
            'PORTSDOWN_SRT_MJPEG_PORT_BASE': base + 2,
            'PORTSDOWN_SOURCE_MJPEG_PORT_BASE': base + 7,
            'PORTSDOWN_BOARD': 'none', 'PORTSDOWN_PEER_ROLE': 'STANDALONE',
            'PORTSDOWN_TX_EXEC': '', 'PORTSDOWN_RX_EXEC': '',
            'PORTSDOWN_SAFE_OFF_EXEC': '', 'PORTSDOWN_PREVIEW_EXEC': '',
            'PORTSDOWN_SOURCE_PREVIEW_EXEC': '', 'PORTSDOWN_SRT_EXEC': hook,
            'PORTSDOWN_CUSTOM_OPERATOR_SETTING': 'keep me',
        }
        self.envfile = self.path / 'diablo.env'
        self.envfile.write_text(''.join(f'export {k}={shlex.quote(str(v))}\n' for k, v in self.values.items()))
        self.envfile.chmod(0o600)

    def setup(self, *args, env=None):
        return subprocess.run(['bash', str(ROOT / 'scripts/first-start.sh'),
                               '--configure-only', '--local-only', '--non-interactive', '--prefix', str(self.path),
                               *args], env=env, capture_output=True, text=True, timeout=20)

    def good(self, *args, env=None):
        r = self.setup('--callsign', 'n0call', '--service-name', 'Station test', *args, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_verify_listener_only_and_cleanup(self):
        result = self.good('--source', 'SRT', '--srt-slot', '3', '--enable-srt',
                           '--advertise-ip', '192.0.2.10')
        self.assertIn('startup/API/shutdown check passed', result.stdout)
        self.assertEqual(self.marker.read_text(), '3\n')
        self.assertFalse((self.path / 'run/tx.sock').exists())
        self.assertIn('srt_source_slot=3', self.config.read_text())
        self.assertIn('call=N0CALL', self.config.read_text())
        self.assertEqual(self.camera.read_text(), 'PRIVATE CAMERA SENTINEL\n')
        with socket.socket() as s:
            self.assertNotEqual(s.connect_ex(('127.0.0.1', self.values['PORTSDOWN_HTTP_PORT'])), 0)
        self.assertTrue(list((self.path / 'backups').glob('first-start-*/diablo.env')))

    def test_rerun_and_literal_text(self):
        service = 'News "quotes" $HOME `id` Café'
        r = self.setup('--callsign', 'N0CALL', '--service-name', service, '--no-verify')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        config_before, env_before = self.config.read_bytes(), self.envfile.read_bytes()
        r = self.setup('--no-verify')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.config.read_bytes(), config_before)
        self.assertEqual(self.envfile.read_bytes(), env_before)
        self.assertIn('service_name=' + service, self.config.read_text())
        self.assertIn('operator_extra=keep', self.config.read_text())
        self.assertEqual(self.envfile.stat().st_mode & 0o777, 0o600)

    def test_invalid_settings_do_not_write(self):
        before = self.config.read_bytes(), self.envfile.read_bytes()
        for args in [('--callsign', 'bad!', '--service-name', 'Test'),
                     ('--callsign', 'N0CALL', '--service-name', 'x' * 65),
                     ('--callsign', 'N0CALL', '--service-name', 'Test', '--advertise-ip', '192.999.0.1'),
                     ('--callsign', 'N0CALL', '--service-name', 'Test', '--device-groups', 'sudo')]:
            r = self.setup('--no-verify', *args)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual((self.config.read_bytes(), self.envfile.read_bytes()), before)
        self.assertFalse((self.path / 'backups').exists())

    def test_active_or_armed_install_rejected(self):
        with (self.path / 'run/launcher.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.setup('--callsign', 'N0CALL', '--service-name', 'Test', '--no-verify')
            self.assertEqual(result.returncode, 2)
            self.assertIn('Stop the running', result.stderr)
        with self.envfile.open('a') as f:
            f.write('export PORTSDOWN_BOARD=express\n')
        result = self.setup('--callsign', 'N0CALL', '--service-name', 'Test', '--no-verify')
        self.assertEqual(result.returncode, 2)
        self.assertIn('left unchanged', result.stderr)

    def test_host_changes_are_explicit_and_narrow(self):
        # Capture sudo requests, never change the test host's SSH/groups.
        sudo = self.path / 'bin/sudo'
        sudo.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> ' + shlex.quote(str(self.path / 'sudo.log')) + '\n')
        sudo.chmod(0o700)
        env = {**os.environ, 'PATH': str(self.path / 'bin') + ':' + os.environ['PATH']}
        self.good('--no-verify', env=env)
        self.assertFalse((self.path / 'sudo.log').exists())
        self.good('--no-verify', '--enable-ssh', '--device-groups', 'video', env=env)
        commands = (self.path / 'sudo.log').read_text()
        self.assertIn('apt-get install -y openssh-server', commands)
        self.assertIn('systemctl enable --now ssh', commands)
        self.assertIn('usermod -aG video ', commands)
        self.assertNotIn('chmod', commands)


if __name__ == '__main__':
    unittest.main()
