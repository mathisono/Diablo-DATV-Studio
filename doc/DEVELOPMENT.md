# Diablo development guide

## Branch and source of truth

Work from **mathisono/Diablo-DATV-Studio**, branch **Trixie**. Do not send Diablo
changes to Portsdown `master`. The source branch tips and ancestry are recorded
in [MIGRATION.md](MIGRATION.md). Do not copy ignored local builds, operator
configs, credentials, or unreviewed `/tmp` artifacts into a release.

## Layout

| Path | Role |
| --- | --- |
| `control/tx-super.c` | Process groups, stop escalation, safe-off and peer watchdog |
| `control/config-store.c` | Atomic fsync/rename state writes |
| `control/ucode/` | Persistent HTTP/SSE, config, peers, cameras and MJPEG |
| `www/` | Framework-free frontend / waiting cards |
| `control/*.sh` | Source preview, local TS, SRT slots and finite ASI file launcher |
| `scripts/install-diablo.sh`, `scripts/run-diablo.sh` | Pinned bootstrap and foreground lifecycle |
| `src/express_s2/` | Experimental QPSK TS-to-I/Q and raw-16 USB backend |
| `scripts/*interlocked*`, `scripts/*capture*` | Retained legacy TX integration |
| `src/gui/`, `scripts/a.sh` | Retained Portsdown touchscreen/transmit paths |
| `systemd/` | Advanced legacy-named service templates, not enabled by bootstrap |
| `tests/`, `scripts/dev/` | Hardware-free tests and browser-capture tools |

`PORTSDOWN_DIR` and `PORTSDOWN_*` environment names and the
`X-Portsdown-Control` request header intentionally remain compatibility interfaces.
Do not cosmetically rename them without a migration. New code must not hardcode
`/home/pi/rpidatv`; inherited untouched Pi scripts may still do so.

The new runtime uses C, ucode and POSIX shell; FFmpeg/TSDuck handle media.
Python is only needed by the development tests and retained legacy interlock
scripts. Node is optional for checking frontend JS syntax, not a server dependency.

## Build and run the software tests

Install once using [INSTALL.md](INSTALL.md). Then, in the checkout:

```sh
export DIABLO_TEST_RUNTIME="$HOME/.local/share/diablo-datv-studio/runtime"
export LD_LIBRARY_PATH="$DIABLO_TEST_RUNTIME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export UCODE="$DIABLO_TEST_RUNTIME/bin/ucode"
export UCODE_MODULE_DIR="$DIABLO_TEST_RUNTIME/lib/ucode"
make -C control
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Tests use isolated config/ports and fake RF launchers, not attached transmitters.
The Pi-4-specific revision check skips when not on a Pi 4. Review **skips**, not
just exit status: absent ucode/FFmpeg can otherwise hide missing coverage.
The launcher test checks startup, config save, duplicate rejection, unarmed TX
and complete shutdown using the real binaries. CI runs the same core software
checks; physical hardware acceptance is tracked separately.

For the optional S2 backend:

```sh
bash scripts/build-express-s2.sh
src/express_s2/express_s2 --rate-only --symbol-rate 1000000 --fec 1/2
```

This is a build/rate calculation only, not USB/RF validation.

## Screenshots

Install development-only Chromium and Python `requests` / `websockets` packages,
then use the same UCODE/UCODE_MODULE_DIR/LD_LIBRARY_PATH environment above:

```sh
python3 scripts/dev/capture-gui.py
```

It runs the actual web daemon, isolated mock source producers and synthetic
preview frames, asserts the title/two camera cards/five SRT cards and no horizontal
overflow, and writes six PNGs to `doc/images/`. It never opens a physical camera
or arms RF/ASI. Inspect captures visually as well as checking the script result.
Captions and missing real-device images belong in [SCREENSHOTS.md](SCREENSHOTS.md).
Do not put private RTSP URLs in fixtures or committed shell commands.

## Change checklist

- Preserve live-input gating, source-loss stop and owned-process cleanup.
- Keep camera secrets in the private camera store, out of API responses/logs.
- Validate config/ranges before spawning media processes; no shell interpolation
  of browser-supplied text.
- Test the changed behavior, then update its evidence/limitations in the status
  ledger. Do not mark physical output verified from a software-only test.
- Rebuild screenshots when visible controls change. Retain upstream attribution.
- Stop before physical testing when connection/test-equipment state is unknown.

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for defined completion criteria rather
than leaving old “next step” prose as an ambiguous task list.
