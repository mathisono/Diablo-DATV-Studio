# Headless `ucode` control plane — experimental, not a transmitter release

This branch adds a **parallel** web/control implementation that does not use
`rpidatvgui`, a touchscreen, `/dev/fb0`, or `/touchscreen/`. It does **not**
remove those legacy paths yet. Do not enable it as a replacement for a working
Portsdown transmitter until board-specific launch and safe-off paths have been
verified on real hardware.

## Web GUI screenshot

![Experimental Portsdown web GUI with five enabled SRT inputs showing numbered NO SRT INPUT test cards](images/headless-web-gui-srt.png)

Captured from an isolated local run with all five SRT listeners enabled and
waiting for video. TX was disabled (`PORTSDOWN_BOARD=none`); no RF or physical
Portsdown display was involved.

## Implemented

- `control/tx-super.c`: Unix socket commands `START_TX`, `STOP_TX`, `START_RX`,
  `STOP_RX`, `START_PREVIEW`, `STOP_PREVIEW`, `STATUS`; child process groups;
  captured log lines; 500 ms TERM→KILL stop; explicit safe-off hook;
  `/dev/video0` preview handoff. A slave supervisor additionally requires
  `PEER_HB` and stops TX within 1.5 seconds of missed heartbeats.
- `control/ucode/`: persistent `uloop`/`socket` HTTP server, atomic config and
  preset updates (through the small C `config-store` helper), SSE state/log
  events, 128 KiB-capped MJPEG latest-frame fan-out, and token-protected
  Master/Slave NDJSON control. Video never uses the peer-control socket.
- `www/`: no-framework responsive dashboard, four server-side presets,
  320×240 preview with a **NO IP INPUT** placeholder, and an E-Stop button.
  An optional remote-slave preview URL can be configured separately.
- Five independently enabled SRT source slots (`control/srt-slot.sh`) each
  accept MPEG-TS over SRT, encode live video/audio to a local source-resolution
  H.264/AAC MPEG-TS output, and provide a 320×240 aspect-preserving MJPEG
  preview. Each preview serves a
  numbered **NO SRT INPUT** test card while its listener has no valid video,
  then returns to the card after input loss. The test card is **preview-only**:
  it never generates TS or satisfies a transmitter's live-input gate.
- `systemd/`: uninstalled service templates. `portsdown-tx-super.service`
  uses `ExecStopPost` as a second attempt to invoke the safe-off hook if the
  supervisor dies while systemd is alive.

The HTTP server listens on **127.0.0.1** only. It checks `Host` and requires
`X-Portsdown-Control: 1` on POST requests to block cross-origin forms and
simple DNS-rebinding attempts. Put authentication and TLS in front of it
before exposing control to another computer; set `PORTSDOWN_ALLOWED_HOST` to
the reverse proxy's exact Host value if needed, and do not add permissive CORS.
The Master/Slave
token is sent over TCP without TLS; use a private LAN/VPN or a protected
tunnel. `PORTSDOWN_PEER_BIND` defaults to loopback, so remote peers require
an explicit private-interface address.

## What is not integrated

- **No live RF launcher is provided.** `PORTSDOWN_TX_EXEC` and
  `PORTSDOWN_SAFE_OFF_EXEC` must name absolute, executable, board-verified
  programs. With either unset, `START_TX` fails closed. The C supervisor
  compares `PORTSDOWN_BOARD` with `modeoutput` on every start. Changing boards
  in the web UI requires reconfiguring/restarting the supervisor before TX.
- Existing DATV-Express, Pluto, and LimeSDR code remains in the repository,
  including legacy DVB-S/S2 paths. The new control plane does **not yet**
  drive all their source/encoder/RF paths. Existing Python interlock scripts
  are still in the legacy transmitter; this branch has no Python/Node runtime
  in the **new** control plane, but is not yet a Python-free Portsdown tree.
- A native DVB-S2 QPSK experimental DATV-Express backend exists; no
  DVB-S2X backend was found in this branch. DVB-S2X is therefore **not**
  offered by the capability map.
- The optional idle-preview launcher is provided. A **dual-output TX FFmpeg
  launcher** must still be built for each capture/backend combination to
  maintain preview during TX. It must be interlocked so RF stays off until
  valid live TS is received and stops when that input disappears.
- The five SRT encoders are **not** connected to a board or the RF TX gate.
  Their enable/disable state is held by the running supervisor (not persisted
  across its restart). Real ATEM sources and five-way on-board CPU/thermal
  performance remain unverified.
- The GPIO and DATV-Express USB/PTT behavior, Pluto/Lime safe-off hooks,
  native video devices, real RF output, and UI behavior on a complete
  Portsdown install have not been tested. Software cannot guarantee PTT-off
  after power loss, kernel failure, or a board that latches TX independently;
  a hardware interlock/watchdog is required for that guarantee.
- The code is Linux/POSIX-oriented and independent of **Buster and a physical
  display**, not independent of every operating system.

## Offline development run

The new runtime requires `ucode` with its `fs`, `socket`, and `uloop` modules,
`libubox`, FFmpeg for an actual preview, and a C compiler. `ucode` is common
on OpenWrt but is not preinstalled on the tested Debian/Ubuntu hosts. Build
`libubox` then `ucode` from their upstream sources, with `libjson-c-dev` and
CMake; ensure `ULOOP_SUPPORT=ON` and `SOCKET_SUPPORT=ON`. The local spike used
libubox commit `a396f38a8568a1d670c240465cd8d24fdfdf6463` and ucode commit
`a2c42eac6369a0bba0315007c7dc7b7130275340` in `/tmp`, without changing
the system installation. Do not infer that these commits are packaged for
Trixie.

From the checkout, this example starts an **unarmed local UI**. It does not
install a service or enable any TX backend:

```sh
make -C control
export PORTSDOWN_DIR="$PWD"
export PORTSDOWN_RUN_DIR="$(mktemp -d)"
export PORTSDOWN_TX_SOCKET="$PORTSDOWN_RUN_DIR/tx.sock"
export PORTSDOWN_HTTP_PORT=8080
export PORTSDOWN_MJPEG_PORT=8082
./control/tx-super &
ucode -L "$PORTSDOWN_DIR/control/ucode" "$PORTSDOWN_DIR/control/ucode/daemon.uc"
```

To make the five software-only SRT listeners available, export
`PORTSDOWN_SRT_EXEC="$PORTSDOWN_DIR/control/srt-slot.sh"` **before** starting
`tx-super`. The web UI has an Enable/Disable button for each slot. By default:

| Slot | SRT caller destination | Live TS output (loopback UDP) | MJPEG preview |
| --- | --- | --- | --- |
| 1 | `srt://TANK:9101?mode=caller` | `127.0.0.1:12001` | `/api/video/srt/1` |
| 2 | `srt://TANK:9102?mode=caller` | `127.0.0.1:12002` | `/api/video/srt/2` |
| 3 | `srt://TANK:9103?mode=caller` | `127.0.0.1:12003` | `/api/video/srt/3` |
| 4 | `srt://TANK:9104?mode=caller` | `127.0.0.1:12004` | `/api/video/srt/4` |
| 5 | `srt://TANK:9105?mode=caller` | `127.0.0.1:12005` | `/api/video/srt/5` |

The SRT input accepts a live MPEG-TS carrying video (audio optional). Its
**IPTS output retains the caller's raster**: synthetic H.264 inputs at
640×480/25, 1280×720/24, and 1920×1080/15 were probed at the same respective
output resolutions. The separate 320×240 MJPEG preview letterboxes 16:9
sources. TS outputs are **local-only and absent when input is absent**; they
are not automatically DVB-S2 modulated or transmitted. The software encoder
still targets 800 kbit/s H.264 video plus 64 kbit/s AAC when audio is present,
so 1080p picture quality at that bitrate may be limited. Allow for FEC/mux
overhead before using a TS in a 1000 ksym/s mode.
`PORTSDOWN_SRT_PORT_BASE`, `PORTSDOWN_SRT_TS_PORT_BASE`, and
`PORTSDOWN_SRT_MJPEG_PORT_BASE` can change the consecutive five-port blocks;
set them identically in both service processes. The listener ports bind all
interfaces, so restrict access to trusted senders with a firewall/VPN.

Open `http://127.0.0.1:8080/` locally, or tunnel the loopback port over SSH.
For a service install, create a dedicated `portsdown` user/group, copy and
edit `control/portsdown.env.example` as `/etc/portsdown/portsdown.env`, install
`ucode`/`libubox`, and only then install the two service units. **Do not enable
the services from the example env file:** its TX executable and safe-off hook
are placeholders, not board-certified paths.

Run the bounded, hardware-free tests with:

```sh
python3 -m unittest tests/test_headless_control.py -v
```

If `ucode` is installed outside `PATH`, set `UCODE` and `UCODE_MODULE_DIR`.
The standard-library Python test runner is a **development-only** dependency,
not part of the headless control runtime.

On 23 November 2026, the two C utilities also compiled natively as AArch64
ELF executables in `/tmp/portsdown-headless-control-build` on TANK (Debian 13
Trixie). TANK's rover service remained active. `ucode` and the web service
were **not** installed or run there; no TX or RF test was attempted.
The five-slot supervisor revision was separately built as AArch64 in
`/tmp/portsdown-srt-control-check`; FFmpeg on TANK lists SRT input/output
support. On the development host, 14 hardware-free tests passed, including
five concurrent synthetic callers producing distinct local TS outputs and a
single-source arrival/loss test proving the MJPEG card returns and TS stops.
The 480p25, 720p24, and 1080p15 synthetic callers decoded and produced
matching-raster H.264 TS, as confirmed by `ffprobe`.
This is **not** an on-device five-encoder performance or RF result.

## Next integration gates

1. On isolated test hardware, implement and verify board-specific TX launchers
   and safe-off hooks for DATV-Express DVB-S and experimental DVB-S2, Pluto,
   and LimeSDR. Preserve valid-TS gating and loss-triggered stop. Confirm
   that the safe-off hook really dekeys the attached board.
2. Add the per-backend dual-output FFmpeg encoder and test camera contention,
   MJPEG preview, audio/video capture, and TS timing under real source changes.
3. Test the web UI and peer link on two separate Pi systems. Exercise normal
   stop, daemon kill, cable loss, stale heartbeat, board disconnect, and
   reboot. RF tests require a dummy load/attenuated receiver.
4. Migrate the remaining legacy menu operations, receiver controls, settings,
   and installer before removing `rpidatvgui` or `/touchscreen/`.
