#!/usr/bin/env python3
"""Offline supervisor/control tests; test doubles only, never an RF backend."""
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "control"


def wait_for(check, seconds=3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


def command(path, text):
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(2)
        peer.connect(str(path))
        peer.sendall((text + "\n").encode())
        data = ""
        while True:
            data += peer.recv(4096).decode()
            for line in data.splitlines():
                if line == "OK" or line.startswith(("ERR ", "STATUS ")):
                    return line


class SupervisorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["make", "-C", str(CONTROL)], check=True, stdout=subprocess.DEVNULL)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="portsdown-super-test-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.config = self.path / "config.txt"
        self.config.write_text("modeoutput=DATVEXPRESS\n")
        self.control = self.path / "expctrl"
        self.control.touch()
        self.hooklog = self.path / "off.log"
        self.hook = self.path / "safe-off"
        self.hook.write_text('#!/bin/sh\necho off >> "$PORTSDOWN_OFF_LOG"\n')
        self.hook.chmod(0o755)
        self.tx = self.path / "mock-tx"
        self.tx.write_text('#!/bin/sh\necho MOCK_TX\ntrap "exit 0" TERM\nwhile :; do sleep 1; done\n')
        self.tx.chmod(0o755)
        self.sock = self.path / "run" / "tx.sock"
        self.process = None

    def tearDown(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=3)

    def start(self, **overrides):
        env = os.environ | {
            "PORTSDOWN_RUN_DIR": str(self.sock.parent),
            "PORTSDOWN_BOARD": "express",
            "PORTSDOWN_CONFIG": str(self.config),
            "PORTSDOWN_TX_EXEC": str(self.tx),
            "PORTSDOWN_SAFE_OFF_EXEC": str(self.hook),
            "PORTSDOWN_EXPRESS_CTRL": str(self.control),
            "PORTSDOWN_OFF_LOG": str(self.hooklog),
        } | overrides
        self.process = subprocess.Popen([str(CONTROL / "tx-super")], env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertTrue(wait_for(self.sock.exists))

    def test_board_mismatch_and_stop(self):
        self.start()
        self.config.write_text("modeoutput=PLUTO\n")
        self.assertIn("mismatch", command(self.sock, "START_TX"))
        self.config.write_text("modeoutput=DATVEXPRESS\n")
        self.assertEqual(command(self.sock, "START_TX"), "OK")
        self.assertIn("tx=running", command(self.sock, "STATUS"))
        self.assertEqual(command(self.sock, "STOP_TX"), "OK")
        self.assertIn("tx=stopped", command(self.sock, "STATUS"))
        self.assertIn("set ptt rx", self.control.read_text())
        self.assertGreaterEqual(self.hooklog.read_text().count("off"), 2)

    def test_missing_hook_fails_closed(self):
        self.start(PORTSDOWN_SAFE_OFF_EXEC="")
        self.assertIn("unavailable", command(self.sock, "START_TX"))
        self.assertFalse(self.hooklog.exists())

    def test_second_supervisor_cannot_replace_live_socket(self):
        self.start()
        env = os.environ | {"PORTSDOWN_RUN_DIR": str(self.sock.parent)}
        other = subprocess.run([str(CONTROL / "tx-super")], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=2)
        self.assertNotEqual(other.returncode, 0)
        self.assertIn(b"already running", other.stderr)
        self.assertIn("tx=stopped", command(self.sock, "STATUS"))

    def test_slave_heartbeat_timeout(self):
        self.start(PORTSDOWN_PEER_ROLE="SLAVE")
        self.assertIn("heartbeat stale", command(self.sock, "START_TX"))
        self.assertEqual(command(self.sock, "PEER_HB"), "OK")
        self.assertEqual(command(self.sock, "START_TX"), "OK")
        self.assertTrue(wait_for(lambda: "tx=stopped" in command(self.sock, "STATUS"), 2.5))
        self.assertGreaterEqual(self.hooklog.read_text().count("off"), 2)

    def test_preview_releases_capture_before_tx_and_returns(self):
        preview = self.path / "preview"
        preview.write_text('#!/bin/sh\necho active\ntrap "exit 0" TERM\nwhile :; do sleep 1; done\n')
        preview.chmod(0o755)
        self.start(PORTSDOWN_PREVIEW_EXEC=str(preview))
        self.assertTrue(wait_for(lambda: "preview=running" in command(self.sock, "STATUS")))
        self.assertEqual(command(self.sock, "START_TX"), "OK")
        status = command(self.sock, "STATUS")
        self.assertIn("tx=running", status)
        self.assertIn("preview=stopped", status)
        self.assertEqual(command(self.sock, "STOP_TX"), "OK")
        self.assertTrue(wait_for(lambda: "preview=running" in command(self.sock, "STATUS")))


class UcodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ucode = os.environ.get("UCODE") or "ucode"
        try:
            subprocess.run([cls.ucode, "-h"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except (OSError, subprocess.CalledProcessError):
            raise unittest.SkipTest("ucode is not installed; set UCODE and UCODE_MODULE_DIR")
        subprocess.run(["make", "-C", str(CONTROL)], check=True, stdout=subprocess.DEVNULL)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="portsdown-ucode-test-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.config = self.path / "config.txt"
        self.config.write_text("modeoutput=DATVEXPRESS\nmodulation=S2QPSK\nfreqoutput=437\nsymbolrate=333\nfec=12\n")
        self.sock = self.path / "run" / "tx.sock"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0)); self.port = probe.getsockname()[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0)); self.video_port = probe.getsockname()[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0)); self.srt_port = probe.getsockname()[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0)); self.ts_port = probe.getsockname()[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0)); self.srt_preview_port = probe.getsockname()[1]
        env = os.environ | {"PORTSDOWN_RUN_DIR": str(self.sock.parent),
                            "PORTSDOWN_SRT_EXEC": str(CONTROL / "srt-slot.sh"),
                            "PORTSDOWN_SRT_PORT_BASE": str(self.srt_port),
                            "PORTSDOWN_SRT_TS_PORT_BASE": str(self.ts_port),
                            "PORTSDOWN_SRT_MJPEG_PORT_BASE": str(self.srt_preview_port),
                            "PORTSDOWN_FFMPEG": shutil.which("ffmpeg") or ""}
        self.supervisor = subprocess.Popen([str(CONTROL / "tx-super")], env=env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertTrue(wait_for(self.sock.exists))
        env = os.environ | {
            "PORTSDOWN_DIR": str(ROOT), "PORTSDOWN_CONFIG": str(self.config),
            "PORTSDOWN_TX_SOCKET": str(self.sock),
            "PORTSDOWN_HTTP_PORT": str(self.port),
            "PORTSDOWN_MJPEG_PORT": str(self.video_port),
            "PORTSDOWN_SRT_PORT_BASE": str(self.srt_port),
            "PORTSDOWN_SRT_TS_PORT_BASE": str(self.ts_port),
            "PORTSDOWN_SRT_MJPEG_PORT_BASE": str(self.srt_preview_port),
            "PORTSDOWN_PRESETS_PATH": str(self.path / "presets.json"),
        }
        args = [self.ucode]
        if os.environ.get("UCODE_MODULE_DIR"):
            args += ["-L", os.environ["UCODE_MODULE_DIR"]]
        args += ["-L", str(CONTROL / "ucode"), str(CONTROL / "ucode" / "daemon.uc")]
        self.daemon = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE)
        self.assertTrue(wait_for(self.http_ready))

    def tearDown(self):
        for process in (self.daemon, self.supervisor):
            if process.poll() is None:
                process.terminate(); process.wait(timeout=3)
        self.daemon.stderr.close()

    def http_ready(self):
        try:
            return self.request("GET", "/api/state")[0] == 200
        except (OSError, http.client.HTTPException):
            return False

    def request(self, method, path, data=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        body = json.dumps(data) if data is not None else None
        conn.request(method, path, body, {"Content-Type": "application/json",
                                          "X-Portsdown-Control": "1"})
        reply = conn.getresponse()
        result = reply.status, reply.read()
        conn.close()
        return result

    def test_api_fails_closed_and_updates_config(self):
        status, body = self.request("POST", "/api/tx/start")
        self.assertEqual(status, 503)
        self.assertFalse(json.loads(body)["ok"])
        status, body = self.request("POST", "/api/config", {"freqoutput": "438.5"})
        self.assertEqual(status, 200, body)
        self.assertIn("freqoutput=438.5", self.config.read_text())
        status, body = self.request("POST", "/api/config", {"modeoutput": "DVB-S2X"})
        self.assertEqual(status, 400)
        self.assertNotIn("DVB-S2X", self.config.read_text())

    def test_cross_origin_form_and_dns_rebinding_are_rejected(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.request("POST", "/api/tx/start")
        reply = conn.getresponse(); self.assertEqual(reply.status, 403); reply.read(); conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.request("GET", "/api/state", headers={"Host": "attacker.example"})
        reply = conn.getresponse(); self.assertEqual(reply.status, 421); reply.read(); conn.close()

    def test_mjpeg_fanout_handles_split_jpeg_marker(self):
        with socket.create_connection(("127.0.0.1", self.video_port), timeout=2) as source:
            source.sendall(b"\xff")
            source.sendall(b"\xd8test-frame\xff\xd9")
            self.assertTrue(wait_for(lambda: json.loads(self.request("GET", "/api/state")[1])["video"]["frames"] == 1))
            with socket.create_connection(("127.0.0.1", self.port), timeout=2) as viewer:
                viewer.settimeout(2)
                viewer.sendall(f"GET /api/video HTTP/1.1\r\nHost: localhost:{self.port}\r\n\r\n".encode())
                result = b""
                while b"\xff\xd8test-frame\xff\xd9" not in result:
                    chunk = viewer.recv(4096)
                    self.assertTrue(chunk, result)
                    result += chunk
                self.assertIn(b"multipart/x-mixed-replace", result)
                self.assertIn(b"Content-Type: image/jpeg", result)

    def test_five_srt_slots_are_independent_and_offer_test_card(self):
        status, body = self.request("GET", "/api/srt")
        self.assertEqual(status, 200, body)
        slots = json.loads(body)["slots"]
        self.assertEqual([s["slot"] for s in slots], list(range(1, 6)))
        self.assertTrue(all(not s["enabled"] and not s["live"] for s in slots))
        status, body = self.request("GET", "/no-srt-input-3.jpg")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\xff\xd8"))
        for n in range(1, 6):
            status, body = self.request("POST", f"/api/srt/{n}/enable")
            self.assertEqual(status, 200, body)
        slots = json.loads(self.request("GET", "/api/srt")[1])["slots"]
        self.assertTrue(all(s["enabled"] and not s["live"] for s in slots))
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as viewer:
            viewer.settimeout(3)
            viewer.sendall(f"GET /api/video/srt/3 HTTP/1.1\r\nHost: localhost:{self.port}\r\n\r\n".encode())
            result = b""
            while b"\xff\xd9" not in result:
                result += viewer.recv(8192)
            self.assertIn(b"Content-Type: image/jpeg", result)
            self.assertIn(b"\xff\xd8", result)
        status, body = self.request("POST", "/api/srt/3/disable")
        self.assertEqual(status, 200, body)
        slots = json.loads(self.request("GET", "/api/srt")[1])["slots"]
        self.assertEqual([s["enabled"] for s in slots], [True, True, False, True, True])

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg unavailable")
    def test_srt_video_arrival_loss_and_live_ts_only(self):
        if "  srt\n" not in subprocess.run(["ffmpeg", "-hide_banner", "-protocols"],
                                          capture_output=True, text=True).stdout:
            self.skipTest("FFmpeg lacks SRT")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as ts:
            ts.bind(("127.0.0.1", self.ts_port))
            ts.settimeout(8)
            status, body = self.request("POST", "/api/srt/1/enable")
            self.assertEqual(status, 200, body)
            sender = subprocess.Popen([
                "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re",
                "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=25", "-t", "4",
                "-c:v", "libx264", "-preset", "ultrafast", "-f", "mpegts",
                f"srt://127.0.0.1:{self.srt_port}?mode=caller&latency=200000",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                packet, _ = ts.recvfrom(2048)
                self.assertEqual(packet[0], 0x47)
                self.assertTrue(wait_for(lambda: json.loads(self.request("GET", "/api/srt")[1])["slots"][0]["live"], 3))
                self.assertEqual(sender.wait(timeout=8), 0, sender.stderr.read())
                self.assertTrue(wait_for(lambda: not json.loads(self.request("GET", "/api/srt")[1])["slots"][0]["live"], 6))
                self.assertTrue(json.loads(self.request("GET", "/api/srt")[1])["slots"][0]["enabled"])
                with socket.create_connection(("127.0.0.1", self.port), timeout=2) as viewer:
                    viewer.settimeout(2)
                    viewer.sendall(f"GET /api/video/srt/1 HTTP/1.1\r\nHost: localhost:{self.port}\r\n\r\n".encode())
                    result = b""
                    while b"\xff\xd9" not in result:
                        result += viewer.recv(8192)
                    self.assertIn((ROOT / "www/no-srt-input-1.jpg").read_bytes(), result)
                ts.setblocking(False)
                while True:
                    try: ts.recvfrom(2048)
                    except BlockingIOError: break
                ts.settimeout(1)
                with self.assertRaises(socket.timeout): ts.recvfrom(2048)
                self.assertEqual(self.request("POST", "/api/srt/1/disable")[0], 200)
            finally:
                if sender.poll() is None:
                    sender.terminate(); sender.wait(timeout=3)
                sender.stderr.close()

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe unavailable")
    def test_720p_and_1080p_srt_inputs_decode_to_480p_ts(self):
        if "  srt\n" not in subprocess.run(["ffmpeg", "-hide_banner", "-protocols"],
                                          capture_output=True, text=True).stdout:
            self.skipTest("FFmpeg lacks SRT")
        sources = [(2, "1280x720", 24), (3, "1920x1080", 15)]
        receivers, senders = [], []
        try:
            for slot, _, _ in sources:
                receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                receiver.bind(("127.0.0.1", self.ts_port + slot - 1))
                receiver.settimeout(10)
                receivers.append(receiver)
                status, body = self.request("POST", f"/api/srt/{slot}/enable")
                self.assertEqual(status, 200, body)
            for slot, raster, fps in sources:
                senders.append(subprocess.Popen([
                    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re",
                    "-f", "lavfi", "-i", f"testsrc2=size={raster}:rate={fps}",
                    "-t", "5", "-threads:v", "1", "-c:v", "libx264", "-preset", "ultrafast",
                    "-f", "mpegts", f"srt://127.0.0.1:{self.srt_port+slot-1}?mode=caller&latency=200000",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
            for (slot, raster, _), receiver in zip(sources, receivers):
                data = bytearray()
                while len(data) < 150000:
                    packet, _ = receiver.recvfrom(2048)
                    self.assertEqual(packet[0], 0x47, raster)
                    data.extend(packet)
                capture = self.path / f"synthetic-{slot}.ts"
                capture.write_bytes(data)
                probe = subprocess.run([
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=codec_name,width,height", "-of", "json", str(capture),
                ], capture_output=True, text=True, timeout=10, check=True)
                self.assertEqual(json.loads(probe.stdout)["streams"][0],
                                 {"codec_name": "h264", "width": 854, "height": 480}, raster)
            slots = json.loads(self.request("GET", "/api/srt")[1])["slots"]
            self.assertTrue(slots[1]["live"] and slots[2]["live"])
        finally:
            for sender in senders:
                if sender.poll() is None:
                    sender.terminate(); sender.wait(timeout=3)
                sender.stderr.close()
            for receiver in receivers: receiver.close()

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg unavailable")
    def test_five_simultaneous_srt_sources_have_distinct_ts_outputs(self):
        if "  srt\n" not in subprocess.run(["ffmpeg", "-hide_banner", "-protocols"],
                                          capture_output=True, text=True).stdout:
            self.skipTest("FFmpeg lacks SRT")
        receivers, senders = [], []
        try:
            for n in range(5):
                receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                receiver.bind(("127.0.0.1", self.ts_port + n))
                receiver.settimeout(12)
                receivers.append(receiver)
                status, body = self.request("POST", f"/api/srt/{n+1}/enable")
                self.assertEqual(status, 200, body)
            for n in range(5):
                senders.append(subprocess.Popen([
                    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re",
                    "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=25",
                    "-t", "5", "-threads:v", "1", "-c:v", "libx264", "-preset", "ultrafast",
                    "-f", "mpegts", f"srt://127.0.0.1:{self.srt_port+n}?mode=caller&latency=200000",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
            for n, receiver in enumerate(receivers):
                packet, _ = receiver.recvfrom(2048)
                self.assertEqual(packet[0], 0x47, f"slot {n+1}")
            self.assertTrue(wait_for(lambda: all(s["live"] for s in json.loads(
                self.request("GET", "/api/srt")[1])["slots"]), 2))
        finally:
            for sender in senders:
                if sender.poll() is None:
                    sender.terminate(); sender.wait(timeout=3)
                sender.stderr.close()
            for receiver in receivers: receiver.close()

    def test_preset_is_saved_on_server(self):
        preset = {"modeoutput": "DATVEXPRESS", "modulation": "S2QPSK",
                  "freqoutput": "437", "symbolrate": "333", "fec": "12"}
        status, body = self.request("POST", "/api/presets/1", preset)
        self.assertEqual(status, 200, body)
        status, body = self.request("GET", "/api/presets/1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), preset)


class PeerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ucode = os.environ.get("UCODE") or "ucode"
        try:
            subprocess.run([cls.ucode, "-h"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except (OSError, subprocess.CalledProcessError):
            raise unittest.SkipTest("ucode is not installed")
        subprocess.run(["make", "-C", str(CONTROL)], check=True, stdout=subprocess.DEVNULL)

    def test_master_loss_stops_slave_mock_tx(self):
        def port():
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0)); return probe.getsockname()[1]

        with tempfile.TemporaryDirectory(prefix="portsdown-peer-test-") as directory:
            root = Path(directory)
            config = root / "config.txt"
            config.write_text("modeoutput=DATVEXPRESS\nmodulation=S2QPSK\nfreqoutput=437\nsymbolrate=333\nfec=12\n")
            hook = root / "safe-off"
            hook.write_text('#!/bin/sh\necho off >> "$PORTSDOWN_OFF_LOG"\n'); hook.chmod(0o755)
            tx = root / "mock-tx"
            tx.write_text('#!/bin/sh\ntrap "exit 0" TERM\nwhile :; do sleep 1; done\n'); tx.chmod(0o755)
            ctrl = root / "expctrl"; ctrl.touch()
            offlog = root / "off.log"
            peer_port, master_port, slave_port, master_video, slave_video, master_srt_video, slave_srt_video = (port() for _ in range(7))
            procs = []

            def start_process(args, env):
                process = subprocess.Popen(args, env=os.environ | env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                procs.append(process)
                return process

            def state(http_port):
                conn = http.client.HTTPConnection("127.0.0.1", http_port, timeout=1)
                conn.request("GET", "/api/state")
                reply = conn.getresponse(); result = json.loads(reply.read()); conn.close()
                return result

            try:
                master_sock = root / "master" / "tx.sock"
                slave_sock = root / "slave" / "tx.sock"
                start_process([str(CONTROL / "tx-super")], {"PORTSDOWN_RUN_DIR": str(master_sock.parent)})
                start_process([str(CONTROL / "tx-super")], {
                    "PORTSDOWN_RUN_DIR": str(slave_sock.parent), "PORTSDOWN_PEER_ROLE": "SLAVE",
                    "PORTSDOWN_BOARD": "express", "PORTSDOWN_CONFIG": str(config),
                    "PORTSDOWN_TX_EXEC": str(tx), "PORTSDOWN_SAFE_OFF_EXEC": str(hook),
                    "PORTSDOWN_EXPRESS_CTRL": str(ctrl), "PORTSDOWN_OFF_LOG": str(offlog),
                })
                self.assertTrue(wait_for(lambda: master_sock.exists() and slave_sock.exists()))
                shared = {"PORTSDOWN_DIR": str(ROOT), "PORTSDOWN_CONFIG": str(config),
                          "PORTSDOWN_CONFIG_STORE": str(CONTROL / "config-store"),
                          "PORTSDOWN_PEER_PORT": str(peer_port),
                          "PORTSDOWN_PEER_TOKEN": "local-test-token-123456789"}
                def daemon_args():
                    args = [self.ucode]
                    if os.environ.get("UCODE_MODULE_DIR"):
                        args += ["-L", os.environ["UCODE_MODULE_DIR"]]
                    return args + ["-L", str(CONTROL / "ucode"), str(CONTROL / "ucode" / "daemon.uc")]
                start_process(daemon_args(), shared | {
                    "PORTSDOWN_TX_SOCKET": str(slave_sock), "PORTSDOWN_HTTP_PORT": str(slave_port),
                    "PORTSDOWN_MJPEG_PORT": str(slave_video), "PORTSDOWN_PEER_ROLE": "SLAVE",
                    "PORTSDOWN_SRT_MJPEG_PORT_BASE": str(slave_srt_video),
                    "PORTSDOWN_PEER_BIND": "127.0.0.1"})
                master = start_process(daemon_args(), shared | {
                    "PORTSDOWN_TX_SOCKET": str(master_sock), "PORTSDOWN_HTTP_PORT": str(master_port),
                    "PORTSDOWN_MJPEG_PORT": str(master_video), "PORTSDOWN_PEER_ROLE": "MASTER",
                    "PORTSDOWN_SRT_MJPEG_PORT_BASE": str(master_srt_video),
                    "PORTSDOWN_PEER_HOST": "127.0.0.1"})
                def configured():
                    try:
                        return state(master_port)["peer"]["config_ready"]
                    except (OSError, http.client.HTTPException):
                        return False
                self.assertTrue(wait_for(configured))
                conn = http.client.HTTPConnection("127.0.0.1", master_port, timeout=2)
                conn.request("POST", "/api/tx/start", headers={"X-Portsdown-Control": "1"})
                reply = conn.getresponse(); self.assertEqual(reply.status, 200, reply.read())
                reply.read(); conn.close()
                self.assertTrue(wait_for(lambda: "tx=running" in state(slave_port)["supervisor"]["status"]))
                master.terminate(); master.wait(timeout=3)
                self.assertTrue(wait_for(lambda: "tx=stopped" in command(slave_sock, "STATUS"), 2.5))
                self.assertIn("off", offlog.read_text())
            finally:
                for process in reversed(procs):
                    if process.poll() is None:
                        process.terminate(); process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
