# Installer / first-start review — 2026-11-25

## Scope and results

Fresh user-local prefixes were built from the revised installer working tree on
both hosts. Existing production installs, cameras, rover service and drivers were
left unchanged. No RF, ASI playout, device capture or reboot was performed.

| Check | TANK | VideoLP3D |
| --- | --- | --- |
| Platform | Raspberry Pi 4 Model B Rev 1.5, Debian 13 Trixie, ARM64 / 64-bit userspace | LattePanda 3 Delta, Mint 22.3, x86-64 / 64-bit userspace |
| Fresh private runtime + native supervisor build | Passed; AArch64 ELF confirmed | Passed; x86-64 ELF confirmed |
| Pinned ucode fs/socket/uloop imports | Passed | Passed |
| GUI API startup and saved config persistence | Passed | Passed |
| Default hardware TX rejected | Passed | Passed |
| Duplicate launcher rejected | Passed | Passed |
| Installer refused while launcher running; API stayed available | Passed | Passed |
| TERM cleanup: socket removed and HTTP port closed | Passed | Passed |
| Read-only preflight: no prefix created | Passed | Passed |
| Missing FFmpeg protocol/codec features rejected | Passed | Passed |
| Reinstall with SHA-256 comparison of env + config | Both unchanged | Both unchanged |
| Package resolution (`apt-get --simulate install …`) | Passed | Passed |

`tests/test_diablo_launcher.py`: **2 tests passed on each architecture**. These
exercise multiple assertions above. Native runtime builds used
`--skip-system-packages` because core build dependencies were already installed.
Package resolution was simulated against configured repositories; this did not
perform a package update/installation. Therefore **fresh OS-image acceptance
remains open**, including generic non-Pi ARM64 hardware and 32-bit Pi images.

## Findings incorporated

- Pi 64-bit is ARM64, not a different build architecture. Detect both kernel
  architecture and userspace bitness, and report the Pi model where available.
- Check actual FFmpeg SRT/TCP/UDP, H.264/AAC/MJPEG, scale/fps/overlay/xstack and
  MPEG-TS/V4L2/ALSA capabilities; do not infer them from the executable existing.
- Keep builds native, pinned and user-local. Force C tools to rebuild instead of
  accepting copied/stale binaries. Keep two build jobs as the small-host default.
- Serialize installer and launcher with a shared lifetime lock. No rebuild of
  the running instance; the operator stops it first.
- Preserve private state and environment. Retain timestamped installation logs
  including package steps, plus a successful-install version/architecture record.
- Include V4L2/ALSA diagnostic packages and report device access without opening
  hardware or silently granting extra group access.
- TANK has `rpicam-vid`; VideoLP3D does not need it. VideoLP3D's account lacks
  read/write access to ALSA PCM nodes owned by `audio`. The guide gives targeted
  group-change/relogin steps; this review did not change host group membership.
- First start uses a loopback web UI and SSH tunnel, one source at a time, a
  separate software TS check, explicit shutdown and Trixie-only updates.

## Reproduce

```sh
bash scripts/install-diablo.sh --prefix "$HOME/diablo-install-test" --skip-system-packages
DIABLO_TEST_RUNTIME="$HOME/diablo-install-test/runtime" \
  python3 -m unittest discover -s tests -p test_diablo_launcher.py -v
sha256sum "$HOME/diablo-install-test/diablo.env" \
  "$HOME/diablo-install-test/state/portsdown_config.txt" > /tmp/diablo-settings.sha256
bash scripts/install-diablo.sh --prefix "$HOME/diablo-install-test" --skip-system-packages
sha256sum -c /tmp/diablo-settings.sha256
```

Tests require Python 3; the application does not. Use a dedicated test prefix
and free ports. Installer refuses if an instance sharing its runtime directory
is active. Do not delete a lock file to bypass a running instance.

Host-local evidence retained:

- TANK: `~/diablo-install-review-20261125/{build,smoke,rerun,preservation}.log`
- VideoLP3D: `~/dektec-asi/install-review-20261125/{build,smoke,rerun,preservation}.log`
- Each prefix: timestamped `logs/install-*.log`, `logs/installed-version.txt`.

Hardware drivers, valid-media RF interlocks, full capture/audio acceptance,
reboot/autostart, sustained encoding load and downstream ASI measurement remain
separate gates in [KNOWN_ISSUES.md](../KNOWN_ISSUES.md). No claims of full
hardware readiness or universal ARM64 distribution support are made here.
