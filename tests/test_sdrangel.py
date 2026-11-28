import importlib.util
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sdrangel_worker", ROOT / "control/sdrangel-worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SDRangelTests(unittest.TestCase):
    def profile(self):
        return json.loads((ROOT / "control/sdrangel-profile.example.json").read_text())

    def test_unconfigured_hardware_is_rejected(self):
        with self.assertRaises(ValueError):
            worker.profile_for(self.profile(), "tx", "DVB-S")

    def configured(self):
        profile = self.profile()
        for entry in list(profile["tx"].values()) + [profile["rx"]]:
            entry["device"]["serial"] = "TEST_SERIAL"
            key = next(iter(entry["deviceSettings"]))
            entry["deviceSettings"][key] = {"centerFrequency": 437000000}
        return profile

    def test_six_modes_are_muted_until_start(self):
        for mode in worker.MODES:
            device, _, channel, settings = worker.profile_for(self.configured(), "tx", mode)
            self.assertEqual(device["direction"], 1)
            self.assertEqual(settings["channelMute"], 1)
            self.assertEqual(settings["useReverseAPI"], 0)
            for name, value in worker.MODES[mode][1].items():
                self.assertEqual(settings[name], value)

    def test_udp_only_loopback(self):
        profile = self.configured()
        profile["tx"]["DVB-S"]["channelSettings"]["udpAddress"] = "0.0.0.0"
        with self.assertRaises(ValueError):
            worker.profile_for(profile, "tx", "DVB-S")

    def test_rx_direction_and_type(self):
        device, _, channel, _ = worker.profile_for(self.configured(), "rx", "DVB-S")
        self.assertEqual(device["direction"], 0)
        self.assertEqual(channel, "DATVDemod")

    def test_missing_report_metrics_are_not_invented(self):
        self.assertEqual(worker.metrics_from({}, "DATVDemod"), {})
        self.assertEqual(worker.metrics_from({"DATVDemodReport": {"mer": 12.3, "bad": 0}},
                                             "DATVDemod"), {"mer": 12.3})

    def test_ucode_pid_and_age_gate(self):
        ucode = os.environ.get("UCODE") or shutil.which("ucode")
        if not ucode:
            self.skipTest("ucode runtime not installed")
        args = [ucode]
        if os.environ.get("UCODE_MODULE_DIR"):
            args += ["-L", os.environ["UCODE_MODULE_DIR"]]
        args += ["-L", str(ROOT / "control/ucode")]
        script = """
import * as sdrangel from 'sdrangel';
let status = { ok: true, status: 'STATUS tx=running rx=stopped board=sdrangel tx_pid=123 rx_pid=0' };
print(sprintf('%J', sdrangel.status(status, { modulation: 'DVB-S2' })));
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sdrangel-tx.json"
            script_path = Path(directory) / "test.uc"
            script_path.write_text(script)
            env = dict(os.environ, PORTSDOWN_RUN_DIR=directory, PORTSDOWN_SDRANGEL_PROFILE="")
            def read():
                return json.loads(subprocess.check_output(args + [str(script_path)], env=env))
            for pid, timestamp, expected in [(123, int(time.time()), "running"),
                                             (124, int(time.time()), "unknown"),
                                             (123, int(time.time())-30, "unknown")]:
                path.write_text(json.dumps({"pid": pid, "updated": timestamp,
                                            "state": "running", "metrics": {"dataRate": 123}}))
                result = read()
                self.assertEqual(result["tx"]["state"], expected)
                self.assertEqual(result["rx"]["state"], "stopped")

    def test_atomic_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.json"
            worker.snapshot(path, "running", metrics={"mer": 1})
            result = json.loads(path.read_text())
            self.assertEqual(result["state"], "running")
            self.assertGreater(result["pid"], 0)
            self.assertEqual(len(list(path.parent.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
