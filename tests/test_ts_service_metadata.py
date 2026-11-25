#!/usr/bin/env python3
"""Offline MPEG-TS metadata and ASI playout arguments; never opens hardware."""

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

    def test_asi_file_applies_labels_when_available_without_blocking_mismatch(self):
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
                "PORTSDOWN_ASI_LOCK_DIR": str(temp / "locks"),
                "PATH": str(temp) + os.pathsep + os.environ["PATH"],
            }
            launcher = ROOT / "control/dektec-asi-file.sh"
            good = subprocess.run([str(launcher)], env=env, capture_output=True,
                                  text=True, timeout=15)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertIn("dektec", args_file.read_text())
            self.assertIn("svrename", args_file.read_text())
            argv = args_file.read_text().splitlines()
            self.assertEqual(argv[argv.index("--max-output-packets") + 1], "128")
            self.assertIn("--wait-detach", argv)
            config.write_text(config.read_text().replace("service_name=Trevor",
                                                         "service_name=Different"))
            changed = subprocess.run([str(launcher)], env=env, capture_output=True,
                                     text=True, timeout=15)
            self.assertEqual(changed.returncode, 0, changed.stderr)
            argv = args_file.read_text().splitlines()
            self.assertEqual(argv[argv.index("--name") + 1], "Different")
            self.assertEqual(argv[argv.index("--provider") + 1], "KG6MDW")
            config.write_text(config.read_text().replace("service_name=Different",
                                                         "service_name=Trevor").replace(
                                                             "call=KG6MDW", "call=K6SOE"))
            changed = subprocess.run([str(launcher)], env=env, capture_output=True,
                                     text=True, timeout=15)
            self.assertEqual(changed.returncode, 0, changed.stderr)
            argv = args_file.read_text().splitlines()
            self.assertEqual(argv[argv.index("--provider") + 1], "K6SOE")
            config.write_text(config.read_text().replace("call=K6SOE", "call="))
            passthrough = subprocess.run([str(launcher)], env=env, capture_output=True,
                                         text=True, timeout=15)
            self.assertEqual(passthrough.returncode, 0, passthrough.stderr)
            self.assertNotIn("svrename", args_file.read_text(),
                             "missing metadata still permits original TS playout")
            config.write_text(config.read_text().replace("call=", "call=KG6MDW"))
            fake_tsp.write_text('#!/bin/sh\n'
                                'if [ "$1" = -P ] && [ "$2" = svrename ] && '
                                '[ "$3" = --help ]; then exit 1; fi\n'
                                'printf "%s\\n" "$@" > "$TSP_ARGS_OUT"\n')
            no_plugin = subprocess.run([str(launcher)], env=env, capture_output=True,
                                       text=True, timeout=15)
            self.assertEqual(no_plugin.returncode, 0, no_plugin.stderr)
            self.assertNotIn("svrename", args_file.read_text(),
                             "missing plugin still permits original TS playout")


if __name__ == "__main__":
    unittest.main()
