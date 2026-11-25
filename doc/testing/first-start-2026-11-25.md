# Automated first-start acceptance — 2026-11-25

The new `scripts/first-start.sh` wraps the native installer, uses the existing
ucode configuration validator/C atomic writer, saves a small managed environment
block, and verifies an owned foreground launcher. No new application runtime
language or web framework is required.

## Native checks

| Check | TANK: Pi 4, ARM64 Trixie | VideoLP3D: x86-64 Mint 22.3 |
| --- | --- | --- |
| Configure-only workflow, real GUI/API and real FFmpeg SRT listener | Passed, slot 1 | Passed, slot 2 |
| Full installer → configuration → verification workflow | Passed | Passed |
| Initial station/source persisted; API reports TX/RX/output TS stopped | Passed | Passed |
| Owned verification instance and listener stop on completion | Passed | Passed |
| Five first-start regression tests | Passed | Passed |
| Existing two installer/launcher regression tests | Passed | Passed |

Five workflow tests cover:

- Selected listener startup with a bounded mock process and shutdown cleanup.
- Exact settings preservation on repeat configuration, private backup/access,
  and literal quotes, dollar signs, backticks and UTF-8 station text (no shell evaluation).
- Invalid station name/callsign, IP address and unsupported device-group rejection
  before configuration writes.
- Running-instance lock and armed-install refusal without resetting the operator's setup.
- Optional SSH/group command generation using a **mock sudo**, never changing
  actual SSH or permissions during the test. No implicit sudo call on configure-only runs.

Real-host workflow tests additionally used the actual `srt-slot.sh`/FFmpeg
listener, not the mock. They confirm process startup, not a decoded contribution
stream or sustained encoding performance. GUI port **18880** was used because
TANK already had another service on port 8080; it was left untouched.

Full workflow runs skipped system package installation because prerequisites
were already present. Native user-local runtime rebuilds and imports passed.
This does **not** close fresh OS-image acceptance, physical capture/audio,
RF/ASI, or device-driver work. Pi camera package selection is implemented but was
not installed by this test; SSH/group changes were only tested with command mocks.

## Reproduce regressions

With an installed native runtime and test-only Python 3:

```sh
export DIABLO_TEST_RUNTIME="$HOME/.local/share/diablo-datv-studio/runtime"
python3 -m unittest discover -s tests -p test_first_start.py -v
python3 -m unittest discover -s tests -p test_diablo_launcher.py -v
```

For the actual workflow, use a separate unarmed install prefix, your own identity,
and free GUI/preview/SRT ports. See [FIRST_START.md](../FIRST_START.md).

Host-local logs are retained under `~/diablo-install-review-20261125/` on TANK and
`~/dektec-asi/install-review-20261125/` on VideoLP3D:
`first-start-full*.log`, `first-start-tests.log`,
`first-start-launcher-regression.log` and install-prefix `logs/first-start-*.log`.
Normal installations, rover service, device permissions and hardware were not
changed. Nothing was enabled at boot; no RF, ASI or output TS was started.
