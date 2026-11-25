# Diablo DATV Studio

**Headless video sources, MPEG transport streams, and experimental DATV control.**
A Linux-native web interface built with a persistent **ucode** daemon, a small C
process supervisor, and vanilla HTML/CSS/JavaScript. No physical touchscreen,
framebuffer, Node.js server, or Python server is required for the new GUI.

![Diablo DATV Studio — Direct SRT and transmitter preview](doc/images/diablo-srt.png)

[Install](doc/INSTALL.md) · [Screenshot gallery](doc/SCREENSHOTS.md) ·
[Development & tests](doc/DEVELOPMENT.md) · [Status / open issues](doc/KNOWN_ISSUES.md) ·
[Migration record](doc/MIGRATION.md) · [Documentation index](doc/README.md)

## What is here

- **Five SRT input encoders**, each with a listener, live-only MPEG-TS output,
  320×240 preview, and a waiting card when video is absent. Tested input modes
  include **480p25, 720p24, and 1080p15**.
- **Two RTSP IP CAM inputs**, each with Save IP / Restart controls and a preview.
  Private camera URLs are kept out of presets, API responses, and screenshots.
- **HDMI/V4L2, Pi Camera and UDP IPTS previews**, direct source selection, and a
  **four-tile multiview** with an independent source selector per quadrant.
- **Local MPEG-TS output** from a selected SRT encoder, an IP camera, or the
  low-rate multiview. CALLSIGN and service-name metadata are operator supplied.
- **DekTec DTA-2145 ASI file-output integration**, driver/environment scripts,
  metadata correction where available, and a non-blocking metadata mismatch flag.
- Presets, live status/log events, Master/Slave control and heartbeat shutdown.
- The inherited **32-bit Trixie migration**, **64-bit transmitter**, DATV-Express
  DVB-S and experimental **DVB-S2 QPSK** code, and legacy Pluto/Lime/Streamer code.

**Development release, not a hardware-qualified transmitter.** The headless
installer deliberately leaves RF/ASI TX unarmed. Software TS/preview tests are
not proof of RF or physical ASI output. There is **no DVB-S2X backend** in this
repository. The retained legacy RF paths are not all connected to the new GUI.
See the [capability and acceptance matrix](doc/KNOWN_ISSUES.md).

## Quick start — Linux, no RF/ASI output

On Debian/Raspberry Pi OS Trixie or Ubuntu 24 / Linux Mint 22, as a normal user:

```sh
git clone --branch Trixie https://github.com/mathisono/Diablo-DATV-Studio.git
cd Diablo-DATV-Studio
bash scripts/install-diablo.sh
"$HOME/.local/share/diablo-datv-studio/bin/diablo-studio"
```

The installer uses sudo only for build packages, builds pinned ucode/libubox
locally, and leaves services and hardware outputs off. Open
**http://127.0.0.1:8080/** on that machine, or use an SSH tunnel as described in
[INSTALL.md](doc/INSTALL.md). Enter your **CALLSIGN** and **service name** before
starting TS generation. Stop the foreground application with **Ctrl+C**.

Keep the checkout in place: the installed launcher uses it. Updating is an
explicit `git pull --ff-only` on **Trixie**, followed by rerunning the installer;
existing configuration and camera credentials are preserved.

The old `install_portsdown.sh`, `update.sh`, and menu updater are intentionally
blocked in this repo: they target the old Buster/Portsdown distribution. They
must not replace Diablo with an upstream `master` checkout.

## Hardware and validation

| Target | Evidence | Remaining |
| --- | --- | --- |
| x86-64 development host | C/ucode tests, FFmpeg TS, SRT and browser fixtures | Not a physical capture or RF test |
| TANK, AArch64 Trixie | Native transmitter/GUI builds and bounded offline TS/interlock tests inherited from Portsdown | No DATV-Express card/display; no RF acceptance |
| LattePanda 3 Delta, Mint 22.3 | DTA/DtaNw DKMS loaded; TSDuck enumerates DTA-2145; TS analysis; QSV CQP encode | Physical ASI, downstream receive, live ASI integration |
| Raspberry Pi OS Trixie armhf | Ported source retained | Fresh 32-bit full-system/capture/display/RF acceptance |

The **ASI card transports MPEG-TS to an external modulator**; it does not itself
supply DVB-S/S2 frequency, symbol rate, or FEC. QSV CQP encoding works on the tested
Jasper Lake GPU but cannot guarantee a fixed bitrate; libx264 remains the
fixed-rate fallback. See [the measured hardware notes](doc/lattepanda-dta-driver.md).

## Project lineage and licensing

This repo consolidates `mathisono/portsdown4_NTSC` development without dropping
its commit history. `headless-ucode-control` at `a9106a9` already contains
`arm64-transmitter` at `f0047f7` and `Trixie` at `7f1d1c3`.

Built on work from **BATC / Portsdown, KG6MDW, F5OEO, G4GUO**, and other
contributors. Existing copyright/license notices and hardware test history are
retained. See [CREDITS.md](CREDITS.md) and [LICENSE](LICENSE). Diablo is a separate
experimental project, not a BATC-endorsed release.
