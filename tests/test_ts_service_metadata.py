#!/usr/bin/env python3
"""Offline MPEG-TS metadata and ASI pass-through gate; never opens hardware."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ts_service_metadata import values  # noqa: E402


class ServiceMetadataTest(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(values({"call": "KG6MDW", "service_name": "Trevor"}),
                         ("KG6MDW", "Trevor"))
        for cfg in ({"call": "BATC", "service_name": "Trevor"},
                    {"call": "kg6mdw", "service_name": "Trevor"},
                    {"call": "KG6MDW", "service_name": " "},
                    {"call": "KG6MDW", "service_name": "x" * 65}):
            with self.assertRaises(ValueError):
                values(cfg)

    def test_asi_file_requires_matching_saved_service_metadata(self):
        with tempfile.TemporaryDirectory(prefix="portsdown-asi-metadata-") as directory:
            temp = Path(directory)
            stream = temp / "source.ts"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "testsrc2=size=320x240:rate=10", "-t", "1", "-c:v",
                "mpeg2video", "-metadata", "service_provider=KG6MDW",
                "-metadata", "service_name=Trevor", "-muxrate", "1000000",
                "-f", "mpegts", str(stream),
            ], check=True, capture_output=True, timeout=15)
            config = temp / "config"
            config.write_text("modeoutput=DEKTEC_ASI\nmodulation=ASI\nasi_device=0\n"
                              "asi_channel=0\nasi_bitrate=1000000\ncall=KG6MDW\n"
                              "service_name=Trevor\n")
            fake_tsp = temp / "tsp"
            fake_tsp.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$TSP_ARGS_OUT"\n')
            fake_tsp.chmod(0o755)
            args_file = temp / "args"
            env = os.environ | {
                "PORTSDOWN_CONFIG": str(config), "PORTSDOWN_ASI_TS_FILE": str(stream),
                "PORTSDOWN_BOARD": "dektec_asi", "TSP_ARGS_OUT": str(args_file),
                "PATH": str(temp) + os.pathsep + os.environ["PATH"],
            }
            launcher = ROOT / "control/dektec-asi-file.sh"
            good = subprocess.run([str(launcher)], env=env, capture_output=True,
                                  text=True, timeout=15)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertIn("dektec", args_file.read_text())
            args_file.unlink()
            config.write_text(config.read_text().replace("service_name=Trevor",
                                                         "service_name=Different"))
            bad = subprocess.run([str(launcher)], env=env, capture_output=True,
                                 text=True, timeout=15)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("metadata differs", bad.stderr)
            self.assertFalse(args_file.exists(), "mismatch must not start ASI")
            config.write_text(config.read_text().replace("service_name=Different",
                                                         "service_name=Trevor").replace(
                                                             "call=KG6MDW", "call=K6SOE"))
            bad = subprocess.run([str(launcher)], env=env, capture_output=True,
                                 text=True, timeout=15)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("metadata differs", bad.stderr)
            self.assertFalse(args_file.exists(), "provider mismatch must not start ASI")


if __name__ == "__main__":
    unittest.main()
