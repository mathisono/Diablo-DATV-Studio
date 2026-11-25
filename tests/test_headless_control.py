#!/usr/bin/env python3
"""Offline supervisor/control tests; test doubles only, never an RF backend."""
import http.client
import json
import os
from pathlib import Path
import random
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

    def test_dektec_asi_requires_matching_board_and_safe_off(self):
        self.config.write_text("modeoutput=DEKTEC_ASI\n")
        self.start(PORTSDOWN_BOARD="dektec_asi")
        self.assertEqual(command(self.sock, "START_TX"), "OK")
        self.assertEqual(command(self.sock, "STOP_TX"), "OK")
        self.config.write_text("modeoutput=PLUTO\n")
        self.assertIn("mismatch", command(self.sock, "START_TX"))

    def test_source_ts_monitor_is_separate_from_rf_tx(self):
        self.config.write_text("modeoutput=DATVEXPRESS\nsource_layout=MULTIVIEW\n")
        self.start(PORTSDOWN_SOURCE_TS_EXEC=str(self.tx))
        self.assertIn("source TS RF route unavailable", command(self.sock, "START_TX"))
        self.assertEqual(command(self.sock, "START_SOURCE_TS"), "OK")
        self.assertIn("source_ts=running", command(self.sock, "STATUS"))
        self.assertEqual(command(self.sock, "STOP_SOURCE_TS"), "OK")
        self.config.write_text("modeoutput=DATVEXPRESS\nsource_layout=DIRECT\nmodeinput=SRT\n")
        self.assertIn("source TS RF route unavailable", command(self.sock, "START_TX"))
        self.assertEqual(command(self.sock, "START_SOURCE_TS"), "OK")
        self.assertEqual(command(self.sock, "STOP_SOURCE_TS"), "OK")
        self.config.write_text("modeoutput=DATVEXPRESS\nsource_layout=DIRECT\nmodeinput=HDMI\n")
        self.assertIn("not selected", command(self.sock, "START_SOURCE_TS"))
        self.config.write_text("modeoutput=DATVEXPRESS\nsource_layout=DIRECT\nmodeinput=IPCAM1\n")
        self.assertIn("source TS RF route unavailable", command(self.sock, "START_TX"))
        self.assertEqual(command(self.sock, "START_SOURCE_TS"), "OK")
        self.assertEqual(command(self.sock, "STOP_SOURCE_TS"), "OK")

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
        self.config.write_text("modeoutput=DATVEXPRESS\nmodulation=S2QPSK\nfreqoutput=437\nsymbolrate=333\nfec=12\ncall=KG6MDW\nservice_name=Trevor\n")
        self.ipcam_config = self.path / "ip-cameras.conf"
        self.asi_file = self.path / "asi-source.ts"
        self.source_ts_mock = self.path / "source-ts-mock"
        self.source_ts_mock.write_text('#!/bin/sh\ntrap "exit 0" TERM\nwhile :; do sleep 1; done\n')
        self.source_ts_mock.chmod(0o755)
        self.sock = self.path / "run" / "tx.sock"
        for _ in range(50):
            base = random.randint(25000, 45000)
            probes = []
            try:
                for offset in (0, 1, 40, 41, 42, 43, 44, 50, 51, 52, 53, 54):
                    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    probes.append(probe); probe.bind(("127.0.0.1", base + offset))
                for offset in (*range(20, 25), *range(30, 35)):
                    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    probes.append(probe); probe.bind(("127.0.0.1", base + offset))
                break
            except OSError:
                pass
            finally:
                for probe in probes: probe.close()
        else:
            self.fail("No free control-test port block")
        self.port, self.video_port = base, base + 1
        self.srt_port, self.ts_port = base + 20, base + 30
        self.srt_preview_port, self.source_preview_port = base + 40, base + 50
        env = os.environ | {"PORTSDOWN_RUN_DIR": str(self.sock.parent),
                            "PORTSDOWN_DIR": str(ROOT), "PORTSDOWN_CONFIG": str(self.config),
                            "PORTSDOWN_SRT_EXEC": str(CONTROL / "srt-slot.sh"),
                            "PORTSDOWN_SRT_PORT_BASE": str(self.srt_port),
                            "PORTSDOWN_SRT_TS_PORT_BASE": str(self.ts_port),
                            "PORTSDOWN_SRT_MJPEG_PORT_BASE": str(self.srt_preview_port),
                            "PORTSDOWN_SOURCE_MJPEG_PORT_BASE": str(self.source_preview_port),
                            "PORTSDOWN_IPCAM_CONFIG": str(self.ipcam_config),
                            "PORTSDOWN_SOURCE_TS_EXEC": str(self.source_ts_mock),
                            "PORTSDOWN_FFMPEG": shutil.which("ffmpeg") or ""}
        self.supervisor = subprocess.Popen([str(CONTROL / "tx-super")], env=env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertTrue(wait_for(self.sock.exists))
        env = os.environ | {
            "PORTSDOWN_DIR": str(ROOT), "PORTSDOWN_CONFIG": str(self.config),
            "PORTSDOWN_ASI_TS_FILE": str(self.asi_file),
            "PORTSDOWN_TX_SOCKET": str(self.sock),
            "PORTSDOWN_HTTP_PORT": str(self.port),
            "PORTSDOWN_MJPEG_PORT": str(self.video_port),
            "PORTSDOWN_SRT_PORT_BASE": str(self.srt_port),
            "PORTSDOWN_SRT_TS_PORT_BASE": str(self.ts_port),
            "PORTSDOWN_SRT_MJPEG_PORT_BASE": str(self.srt_preview_port),
            "PORTSDOWN_SOURCE_MJPEG_PORT_BASE": str(self.source_preview_port),
            "PORTSDOWN_IPCAM_CONFIG": str(self.ipcam_config),
            "PORTSDOWN_SOURCE_TS_EXEC": str(self.source_ts_mock),
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

    def test_service_metadata_validation_and_persistence(self):
        for changes in ({"call": "BATC"}, {"call": "kg6mdw"},
                        {"service_name": " "}, {"service_name": "A" * 65},
                        {"service_name": "é" * 33},
                        {"service_name": "bad\tname"}):
            status, body = self.request("POST", "/api/config", changes)
            self.assertEqual(status, 400, body)
        status, body = self.request("POST", "/api/config",
                                    {"call": "K6SOE", "service_name": "DATV test 720p"})
        self.assertEqual(status, 200, body)
        saved = json.loads(self.request("GET", "/api/config")[1])["config"]
        self.assertEqual((saved["call"], saved["service_name"]),
                         ("K6SOE", "DATV test 720p"))
        self.assertEqual(self.request("POST", "/api/config",
                                      {"service_name": "é" * 32})[0], 200)

    def test_asi_settings_do_not_claim_rf_modulation(self):
        settings = {"modeoutput": "DEKTEC_ASI", "modulation": "ASI",
                    "asi_device": "0", "asi_channel": "0", "asi_bitrate": "3071588"}
        status, body = self.request("POST", "/api/config", settings)
        self.assertEqual(status, 200, body)
        status, body = self.request("POST", "/api/config", {"asi_bitrate": "0"})
        self.assertEqual(status, 400, body)
        status, body = self.request("POST", "/api/config", {"modulation": "S2QPSK"})
        self.assertEqual(status, 400, body)
        status, body = self.request("POST", "/api/tx/start")
        self.assertEqual(status, 503)
        self.assertFalse(json.loads(body)["ok"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe unavailable")
    def test_asi_file_metadata_mismatch_is_gui_status_not_tx_gate(self):
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "testsrc2=size=320x240:rate=10", "-t", "1", "-c:v",
            "mpeg2video", "-metadata", "service_provider=KG6MDW",
            "-metadata", "service_name=Original", "-f", "mpegts", str(self.asi_file),
        ], check=True, capture_output=True, timeout=15)
        status, body = self.request("GET", "/api/asi/file-status")
        self.assertEqual(status, 200, body)
        mismatch = json.loads(body)
        self.assertEqual(mismatch["state"], "mismatch")
        self.assertEqual(mismatch["observed_name"], "Original")
        status, body = self.request("POST", "/api/config", {"service_name": "Original"})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(self.request("GET", "/api/asi/file-status")[1])["state"], "match")
        self.asi_file.unlink()
        self.assertEqual(json.loads(self.request("GET", "/api/asi/file-status")[1])["state"], "unknown")

    def test_hdmi_capture_requires_video_device_and_accepts_optional_alsa(self):
        status, body = self.request("POST", "/api/config", {"modeinput": "HDMI"})
        self.assertEqual(status, 400, body)
        status, body = self.request("POST", "/api/config", {
            "modeinput": "HDMI", "expresshdmidevice": "/dev/video2",
            "expressaudiodevice": "plughw:CARD=CamLink,DEV=0"})
        self.assertEqual(status, 200, body)
        status, body = self.request("POST", "/api/config", {"expresshdmidevice": "/tmp/fake"})
        self.assertEqual(status, 400, body)
        status, body = self.request("POST", "/api/config", {"expressaudiodevice": ""})
        self.assertEqual(status, 200, body)
        status, body = self.request("GET", "/no-hdmi-input.svg")
        self.assertEqual(status, 200, body)
        self.assertIn(b"NO HDMI INPUT", body)

    def test_two_ip_cameras_use_private_urls_and_independent_previews(self):
        self.assertEqual(json.loads(self.request("GET", "/api/ipcam")[1])["configured"],
                         {"1": False, "2": False})
        self.assertEqual(self.request("POST", "/api/ipcam", {"slot": 1, "url": "file:///tmp/video.ts"})[0], 400)
        self.assertEqual(self.request("POST", "/api/config", {
            "source_layout": "MULTIVIEW", "multiview_1": "IPCAM1",
            "multiview_2": "IPCAM2", "multiview_3": "SRT3", "multiview_4": "IPTSIN"})[0], 200)
        urls = {1: "rtsp://user:p%40ss@127.0.0.1:8554/first",
                2: "rtsp://user:other@127.0.0.1:8554/second"}
        for slot, url in urls.items():
            status, body = self.request("POST", "/api/ipcam", {"slot": slot, "url": url})
            self.assertEqual(status, 200, body)
            self.assertEqual(self.request("GET", f"/no-ipcam{slot}-input.jpg")[0], 200)
        self.assertEqual(self.ipcam_config.stat().st_mode & 0o777, 0o600)
        self.assertIn(urls[1], self.ipcam_config.read_text())
        for endpoint in ("/api/config", "/api/state", "/api/ipcam"):
            self.assertNotIn(b"p%40ss", self.request("GET", endpoint)[1])
        state = json.loads(self.request("GET", "/api/state")[1])
        self.assertTrue(state["sources"]["IPCAM1"]["selected"])
        self.assertTrue(state["sources"]["IPCAM2"]["selected"])
        self.assertEqual(self.request("POST", "/api/source-ts/start")[0], 200)
        self.assertEqual(self.request("POST", "/api/source-ts/stop")[0], 200)
        with socket.create_connection(("127.0.0.1", self.source_preview_port + 3), timeout=2) as producer:
            producer.sendall((ROOT / "www/no-ipcam1-input.jpg").read_bytes())
            self.assertTrue(wait_for(lambda: json.loads(self.request("GET", "/api/state")[1])
                                     ["sources"]["IPCAM1"]["preview"]["producer"]))
            self.assertFalse(json.loads(self.request("GET", "/api/state")[1])
                             ["sources"]["IPCAM2"]["preview"]["producer"])
        self.assertTrue(wait_for(lambda: not json.loads(self.request("GET", "/api/state")[1])
                                 ["sources"]["IPCAM1"]["preview"]["producer"]))
        for slot in (1, 2):
            with socket.create_connection(("127.0.0.1", self.port), timeout=2) as viewer:
                viewer.settimeout(3)
                viewer.sendall(f"GET /api/video/source/ipcam{slot} HTTP/1.1\r\nHost: localhost:{self.port}\r\n\r\n".encode())
                data = b""
                while b"\xff\xd9" not in data: data += viewer.recv(8192)
                self.assertIn((ROOT / f"www/no-ipcam{slot}-input.jpg").read_bytes(), data)
        if shutil.which("ffmpeg") and shutil.which("ffprobe"):
            output = self.path / "ipcam-multiview.ts"
            result = subprocess.run([str(CONTROL / "source-ts.sh")], env=os.environ | {
                "PORTSDOWN_CONFIG": str(self.config), "PORTSDOWN_DIR": str(ROOT),
                "PORTSDOWN_HTTP_PORT": str(self.port),
                "PORTSDOWN_SOURCE_TS_URL": str(output),
                "PORTSDOWN_SOURCE_TS_DURATION": "2"},
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr[-1000:])
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "stream=codec_name,width,height", "-of", "json", str(output)],
                                   capture_output=True, text=True, check=True, timeout=8)
            self.assertEqual(json.loads(probe.stdout)["streams"][0],
                             {"codec_name": "h264", "width": 640, "height": 480})
        self.assertEqual(self.request("POST", "/api/config", {
            "source_layout": "DIRECT", "modeinput": "IPCAM2"})[0], 200)
        self.assertEqual(self.request("POST", "/api/tx/start")[0], 409)
        self.assertEqual(self.request("POST", "/api/source-ts/start")[0], 200)
        self.assertEqual(self.request("POST", "/api/ipcam", {"slot": 2, "url": ""})[0], 200)
        self.assertEqual(self.request("POST", "/api/source-ts/start")[0], 409)
        self.ipcam_config.chmod(0o644)
        self.assertEqual(self.request("POST", "/api/ipcam", {"slot": 2, "url": urls[2]})[0], 400)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_mixed_multiview_generates_local_ts_and_waiting_cards(self):
        choices = {"source_layout": "MULTIVIEW", "multiview_1": "HDMI",
                   "multiview_2": "CAMH264", "multiview_3": "IPTSIN",
                   "multiview_4": "SRT1", "expresshdmidevice": "/dev/video2",
                   "format": "4:3", "ipts_input_port": "10000", "picam_index": "0"}
        status, body = self.request("POST", "/api/config", choices)
        self.assertEqual(status, 200, body)
        self.assertEqual(self.request("POST", "/api/tx/start")[0], 409)
        self.assertEqual(self.request("POST", "/api/source-ts/start")[0], 200)
        self.assertIn("source_ts=running", json.loads(self.request("GET", "/api/state")[1])["supervisor"]["status"])
        self.assertEqual(self.request("POST", "/api/source-ts/stop")[0], 200)
        self.assertEqual(self.request("POST", "/api/config", {"multiview_3": "../../file"})[0], 400)
        self.assertEqual(self.request("POST", "/api/config", {"ipts_input_port": "70000"})[0], 400)
        for path in ("/api/video/source/hdmi", "/api/video/source/camera",
                     "/api/video/source/ipts", "/api/video/srt/1"):
            with socket.create_connection(("127.0.0.1", self.port), timeout=2) as viewer:
                viewer.settimeout(3)
                viewer.sendall(f"GET {path} HTTP/1.1\r\nHost: localhost:{self.port}\r\n\r\n".encode())
                data = b""
                while b"\xff\xd9" not in data:
                    data += viewer.recv(8192)
                self.assertIn(b"image/jpeg", data, path)
        output = self.path / "multiview.ts"
        env = os.environ | {"PORTSDOWN_CONFIG": str(self.config),
                            "PORTSDOWN_DIR": str(ROOT),
                            "PORTSDOWN_HTTP_PORT": str(self.port),
                            "PORTSDOWN_SOURCE_TS_URL": str(output),
                            "PORTSDOWN_SOURCE_TS_DURATION": "3"}
        result = subprocess.run([str(CONTROL / "source-ts.sh")], env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "stream=codec_name,width,height:program_tags=service_provider,service_name",
                                "-of", "json", str(output)], check=True,
                               capture_output=True, text=True, timeout=10)
        stream = json.loads(probe.stdout)
        self.assertEqual(stream["streams"][0], {"codec_name": "h264", "width": 640, "height": 480})
        self.assertEqual(stream["programs"][0]["tags"]["service_provider"], "KG6MDW")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_direct_srt_slot_selection_relays_only_selected_live_ts(self):
        status, body = self.request("POST", "/api/config", {
            "source_layout": "DIRECT", "modeinput": "SRT", "srt_source_slot": "3"})
        self.assertEqual(status, 200, body)
        output = self.path / "selected-srt.ts"
        env = os.environ | {"PORTSDOWN_CONFIG": str(self.config),
                            "PORTSDOWN_DIR": str(ROOT),
                            "PORTSDOWN_SRT_TS_PORT_BASE": str(self.ts_port),
                            "PORTSDOWN_SOURCE_TS_URL": str(output),
                            "PORTSDOWN_SOURCE_TS_DURATION": "2"}
        relay = subprocess.Popen([str(CONTROL / "source-ts.sh")], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            time.sleep(0.3)
            sender = subprocess.run([
                "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10",
                "-t", "3", "-c:v", "mpeg2video", "-f", "mpegts",
                f"udp://127.0.0.1:{self.ts_port+2}?pkt_size=1316",
            ], capture_output=True, text=True, timeout=10)
            self.assertEqual(sender.returncode, 0, sender.stderr)
            self.assertEqual(relay.wait(timeout=8), 0, relay.stderr.read().decode()[-1000:])
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "stream=codec_name,width,height:program_tags=service_provider,service_name",
                                    "-of", "json", str(output)], check=True,
                                   capture_output=True, text=True, timeout=10)
            result = json.loads(probe.stdout)
            self.assertEqual(result["streams"][0]["codec_name"], "mpeg2video")
            self.assertEqual(result["programs"][0]["tags"]["service_name"], "Trevor")
        finally:
            if relay.poll() is None:
                relay.terminate(); relay.wait(timeout=3)
            relay.stderr.close()

    def test_direct_srt_output_control_enables_selected_listener(self):
        status, body = self.request("POST", "/api/config", {
            "source_layout": "DIRECT", "modeinput": "SRT", "srt_source_slot": "4"})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.request("POST", "/api/tx/start")[0], 409)
        status, body = self.request("POST", "/api/source-ts/start")
        self.assertEqual(status, 200, body)
        state = json.loads(self.request("GET", "/api/state")[1])
        self.assertTrue(state["srt"][3]["enabled"])
        self.assertFalse(state["srt"][2]["enabled"])
        self.assertIn("source_ts=running", state["supervisor"]["status"])
        self.assertEqual(self.request("POST", "/api/source-ts/stop")[0], 200)

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
        self.assertTrue(wait_for(lambda: not json.loads(self.request("GET", "/api/state")[1])["video"]["producer"]))

    def test_hdmi_preview_uses_saved_device(self):
        fake = self.path / "ffmpeg-args"
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$PORTSDOWN_ARGS_OUT"\n')
        fake.chmod(0o755)
        args = self.path / "args.txt"
        self.config.write_text("modeinput=HDMI\nexpresshdmidevice=/dev/video2\n")
        result = subprocess.run([str(CONTROL / "idle-preview.sh")],
            env=os.environ | {"PORTSDOWN_CONFIG": str(self.config),
                              "PORTSDOWN_FFMPEG": str(fake), "PORTSDOWN_ARGS_OUT": str(args)},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = args.read_text().splitlines()
        self.assertEqual(argv[argv.index("-i") + 1], "/dev/video2")
        self.assertIn("fps=5,scale=320:240:force_original_aspect_ratio=decrease", argv[argv.index("-vf") + 1])
        self.config.write_text("modeinput=HDMI\nexpresshdmidevice=/tmp/recording.ts\n")
        result = subprocess.run([str(CONTROL / "idle-preview.sh")],
            env=os.environ | {"PORTSDOWN_CONFIG": str(self.config), "PORTSDOWN_FFMPEG": str(fake)},
            capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_independent_preview_inputs_use_saved_sources(self):
        bin_dir = self.path / "bin"
        bin_dir.mkdir()
        ffmpeg = bin_dir / "ffmpeg"
        ffmpeg.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$PORTSDOWN_ARGS_OUT"\n')
        ffmpeg.chmod(0o755)
        camera = bin_dir / "rpicam-vid"
        camera.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$PORTSDOWN_CAM_ARGS_OUT"\n')
        camera.chmod(0o755)
        args_file = self.path / "preview-args"
        cam_args = self.path / "camera-args"
        self.config.write_text("expresshdmidevice=/dev/video2\npicam_index=1\n"
                               "ipts_input_port=10123\nipts_bind_scope=LAN\n")
        env = os.environ | {"PORTSDOWN_CONFIG": str(self.config),
                            "PORTSDOWN_FFMPEG": str(ffmpeg),
                            "PORTSDOWN_ARGS_OUT": str(args_file),
                            "PORTSDOWN_CAM_ARGS_OUT": str(cam_args),
                            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
        self.ipcam_config.write_text("ipcam1=rtsp://u:p%40ss@127.0.0.1:8554/a\n"
                                     "ipcam2=rtsp://u:other@127.0.0.1:8554/b\n")
        self.ipcam_config.chmod(0o600)
        env["PORTSDOWN_IPCAM_CONFIG"] = str(self.ipcam_config)
        env["PORTSDOWN_SOURCE_MJPEG_PORT_BASE"] = str(self.source_preview_port)
        for role, expected in (("HDMI", "/dev/video2"),
                               ("IPTS", "udp://0.0.0.0:10123"),
                               ("PICAM", "-f\nmjpeg\n-i\npipe:0"),
                               ("IPCAM1", "rtsp://u:p%40ss@127.0.0.1:8554/a"),
                               ("IPCAM2", "rtsp://u:other@127.0.0.1:8554/b")):
            result = subprocess.run([str(CONTROL / "source-preview.sh"), role],
                                    env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(expected, args_file.read_text(), role)
            if role.startswith("IPCAM"):
                self.assertIn("fps=5,scale=320:240", args_file.read_text())
                self.assertIn(f"tcp://127.0.0.1:{self.source_preview_port+2+int(role[-1])}",
                              args_file.read_text())
        self.assertIn("--camera\n1", cam_args.read_text())

    def test_direct_ip_camera_ts_uses_selected_private_url_and_format(self):
        fake = self.path / "ffmpeg-capture"
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$PORTSDOWN_ARGS_OUT"\n')
        fake.chmod(0o755)
        args_file = self.path / "ts-args"
        self.ipcam_config.write_text("ipcam1=rtsp://u:p%40ss@127.0.0.1:8554/a\n"
                                     "ipcam2=rtsp://u:other@127.0.0.1:8554/b\n")
        self.ipcam_config.chmod(0o600)
        for fmt, expected in (("4:3", "scale=640:480"),
                              ("720p", "scale=1280:720"),
                              ("1080p", "scale=1920:1080")):
            self.config.write_text(f"source_layout=DIRECT\nmodeinput=IPCAM2\nformat={fmt}\n"
                                   "call=KG6MDW\nservice_name=Trevor\n")
            result = subprocess.run([str(CONTROL / "source-ts.sh")], env=os.environ | {
                "PORTSDOWN_CONFIG": str(self.config), "PORTSDOWN_DIR": str(ROOT),
                "PORTSDOWN_FFMPEG": str(fake), "PORTSDOWN_ARGS_OUT": str(args_file),
                "PORTSDOWN_IPCAM_CONFIG": str(self.ipcam_config),
                "PORTSDOWN_SOURCE_TS_DURATION": "1"}, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = args_file.read_text()
            self.assertIn("rtsp://u:other@127.0.0.1:8554/b", args)
            self.assertNotIn("p%40ss", args)
            self.assertIn(expected, args)
            self.assertIn("-rtsp_transport\ntcp", args)

    def test_selected_source_preview_returns_to_waiting_card_after_loss(self):
        status, body = self.request("POST", "/api/config", {
            "source_layout": "MULTIVIEW", "multiview_1": "HDMI",
            "multiview_2": "SRT2", "multiview_3": "SRT3",
            "multiview_4": "SRT4", "expresshdmidevice": "/dev/video2"})
        self.assertEqual(status, 200, body)
        with socket.create_connection(("127.0.0.1", self.source_preview_port), timeout=2) as source:
            source.sendall((ROOT / "www/no-hdmi-input.jpg").read_bytes())
            self.assertTrue(wait_for(lambda: json.loads(self.request("GET", "/api/state")[1])
                                     ["sources"]["HDMI"]["preview"]["producer"]))
        self.assertTrue(wait_for(lambda: not json.loads(self.request("GET", "/api/state")[1])
                                 ["sources"]["HDMI"]["preview"]["producer"]))
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as viewer:
            viewer.settimeout(3)
            viewer.sendall(f"GET /api/video/source/hdmi HTTP/1.1\r\nHost: localhost:{self.port}\r\n\r\n".encode())
            data = b""
            while b"\xff\xd9" not in data:
                data += viewer.recv(8192)
            self.assertIn((ROOT / "www/no-hdmi-input.jpg").read_bytes(), data)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg unavailable")
    def test_live_udp_ipts_decodes_to_preview_then_loses_live_state(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            input_port = probe.getsockname()[1]
        status, body = self.request("POST", "/api/config", {
            "source_layout": "MULTIVIEW", "multiview_1": "IPTSIN",
            "multiview_2": "SRT2", "multiview_3": "SRT3",
            "multiview_4": "SRT4", "ipts_input_port": str(input_port),
            "ipts_bind_scope": "LOCAL"})
        self.assertEqual(status, 200, body)
        preview = subprocess.Popen([str(CONTROL / "source-preview.sh"), "IPTS"],
            env=os.environ | {"PORTSDOWN_CONFIG": str(self.config),
                              "PORTSDOWN_SOURCE_MJPEG_PORT_BASE": str(self.source_preview_port)},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        sender = None
        try:
            time.sleep(0.3)
            sender = subprocess.Popen([
                "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10",
                "-t", "6", "-c:v", "mpeg2video", "-f", "mpegts",
                f"udp://127.0.0.1:{input_port}?pkt_size=1316",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            live = lambda: json.loads(self.request("GET", "/api/state")[1])[
                "sources"]["IPTSIN"]["preview"]["producer"]
            self.assertTrue(wait_for(live, 5), preview.stderr.read().decode() if preview.poll() is not None else '')
            self.assertEqual(sender.wait(timeout=9), 0, sender.stderr.read())
            self.assertTrue(wait_for(lambda: not live(), 5))
        finally:
            for process in (sender, preview):
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                        try: process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait(timeout=3)
                    process.stderr.close()

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
    def test_srt_480p_720p_1080p_inputs_keep_raster_in_ipts(self):
        if "  srt\n" not in subprocess.run(["ffmpeg", "-hide_banner", "-protocols"],
                                          capture_output=True, text=True).stdout:
            self.skipTest("FFmpeg lacks SRT")
        sources = [(1, "640x480", 25), (2, "1280x720", 24), (3, "1920x1080", 15)]
        receivers, senders = [], []
        try:
            for slot, _, _ in sources:
                receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                receiver.bind(("127.0.0.1", self.ts_port + slot - 1))
                receiver.settimeout(10)
                receivers.append(receiver)
                status, body = self.request("POST", f"/api/srt/{slot}/enable")
                self.assertEqual(status, 200, body)
            # Updating saved metadata restarts enabled listeners before
            # callers arrive; otherwise they would retain the old TS labels.
            status, body = self.request("POST", "/api/config",
                                        {"service_name": "Trevor Live"})
            self.assertEqual(status, 200, body)
            for slot, raster, fps in sources:
                senders.append(subprocess.Popen([
                    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re",
                    "-f", "lavfi", "-i", f"testsrc2=size={raster}:rate={fps}",
                    "-t", "7", "-threads:v", "1", "-c:v", "libx264", "-preset", "ultrafast",
                    "-f", "mpegts", f"srt://127.0.0.1:{self.srt_port+slot-1}?mode=caller&latency=200000",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
            for (slot, raster, fps), receiver in zip(sources, receivers):
                data = bytearray()
                while len(data) < 150000:
                    packet, _ = receiver.recvfrom(2048)
                    self.assertEqual(packet[0], 0x47, raster)
                    data.extend(packet)
                capture = self.path / f"synthetic-{slot}.ts"
                capture.write_bytes(data)
                probe = subprocess.run([
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=codec_name,width,height,r_frame_rate", "-of", "json", str(capture),
                ], capture_output=True, text=True, timeout=10, check=True)
                width, height = (int(value) for value in raster.split("x"))
                self.assertEqual(json.loads(probe.stdout)["streams"][0],
                                 {"codec_name": "h264", "width": width, "height": height,
                                  "r_frame_rate": f"{fps}/1"}, raster)
                service = subprocess.run([
                    "ffprobe", "-v", "error", "-show_entries",
                    "program_tags=service_provider,service_name", "-of", "json", str(capture),
                ], capture_output=True, text=True, timeout=10, check=True)
                tags = json.loads(service.stdout)["programs"][0]["tags"]
                self.assertEqual(tags["service_provider"], "KG6MDW")
                self.assertEqual(tags["service_name"], "Trevor Live")
            slots = json.loads(self.request("GET", "/api/srt")[1])["slots"]
            self.assertTrue(all(slot["live"] for slot in slots[:3]))
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
                    # Keep all callers alive while five encoders start and each
                    # UDP receiver obtains its first packet on a loaded host.
                    "-t", "12", "-threads:v", "1", "-c:v", "libx264", "-preset", "ultrafast",
                    "-f", "mpegts", f"srt://127.0.0.1:{self.srt_port+n}?mode=caller&latency=200000",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
            for n, receiver in enumerate(receivers):
                packet, _ = receiver.recvfrom(2048)
                self.assertEqual(packet[0], 0x47, f"slot {n+1}")
            self.assertTrue(wait_for(lambda: all(s["live"] for s in json.loads(
                self.request("GET", "/api/srt")[1])["slots"]), 3))
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
            for _ in range(50):
                base = random.randint(25000, 45000)
                probes = []
                try:
                    for offset in (*range(0, 5), *range(20, 25), *range(30, 35),
                                   *range(40, 43), *range(50, 53)):
                        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        probes.append(probe); probe.bind(("127.0.0.1", base + offset))
                    break
                except OSError:
                    pass
                finally:
                    for probe in probes: probe.close()
            else:
                self.fail("No free peer-test port block")
            peer_port, master_port, slave_port = base, base + 1, base + 2
            master_video, slave_video = base + 3, base + 4
            master_srt_video, slave_srt_video = base + 20, base + 30
            master_source_video, slave_source_video = base + 40, base + 50
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
                    "PORTSDOWN_SOURCE_MJPEG_PORT_BASE": str(slave_source_video),
                    "PORTSDOWN_PEER_BIND": "127.0.0.1"})
                master = start_process(daemon_args(), shared | {
                    "PORTSDOWN_TX_SOCKET": str(master_sock), "PORTSDOWN_HTTP_PORT": str(master_port),
                    "PORTSDOWN_MJPEG_PORT": str(master_video), "PORTSDOWN_PEER_ROLE": "MASTER",
                    "PORTSDOWN_SRT_MJPEG_PORT_BASE": str(master_srt_video),
                    "PORTSDOWN_SOURCE_MJPEG_PORT_BASE": str(master_source_video),
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
