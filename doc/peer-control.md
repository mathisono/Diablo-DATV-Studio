# Peer control: MASTER / SLAVE

Peer mode is a **one-to-one control link**, not a video transport. MASTER sends
transmitter settings and TX requests; SLAVE operates its own configured output process.
**SLAVE has exactly one source mode: IPTS over SRT, carrying the finished MPEG-TS
produced on MASTER.** It is not a remote camera selector or a second encoder.
SRT/UDP contribution and an optional remote MJPEG preview use separate connections.

| Role | Current behavior |
| --- | --- |
| STANDALONE | Local control; no peer listener or outgoing peer connection |
| MASTER | Connects to one SLAVE; pushes a supported configuration subset, waits for acknowledgement, then permits remote TX requests |
| SLAVE | Accepts only IPTS/SRT source configuration and authenticated transmitter/TX requests; web settings and start controls are locked, including while disconnected; local E-Stop remains available |

## Configuration

Stop Diablo on both computers. In the Diablo source folder on each, run:

```sh
bash scripts/setup-access.sh
```

Choose **SLAVE** on the remote transmitter and **MASTER** on the producing
computer. On MASTER, enter SLAVE's LAN IPv4 address. Enter **exactly the same
shared password** on both; it also signs into each computer's web GUI.
Restart both with `diablo-studio`. [Step-by-step LAN access](LAN_ACCESS.md).

Peer control uses **TLS-PSK on TCP 8181**, with a key derived from that password.
Authentication happens before the SLAVE control socket is reached. There is no
second token to copy. Only one MASTER owns a SLAVE at a time: stop the old MASTER
before handing control to another matching-password MASTER. Neither a wrong
password nor a second authenticated connection displaces an active controller.
A handover or reconnection never starts TX automatically.

Allow TCP 8443 for HTTPS and TCP 8181 to SLAVE from intended LAN computers, plus
the separate SRT media port. No SSH tunnel is required. The internal HTTP and
NDJSON sockets remain loopback-only. Existing raw-token/loopback developer
harnesses are legacy test paths, not the recommended LAN deployment.
`PORTSDOWN_PEER_SRT_PORT` (default 9000) remains SLAVE's independent media setting.

Optional on MASTER: `PORTSDOWN_SLAVE_PREVIEW_URL` can point at the separately
protected SLAVE MJPEG URL reachable from the browser. Sign into SLAVE
in the same browser to authorize its preview cookie; peer authentication does
not create browser sessions. Cross-origin cookie restrictions can prevent that
optional remote preview. No authentication bypass is supplied for it.

## MASTER production versus SLAVE input

```text
MASTER: camera / HDMI / SRT inputs / multiview → encode and mux MPEG-TS
                                               │
                                         SRT (media)
                                               ▼
SLAVE:                  IPTS pass-through → transmitter/modulator

MASTER ───── password-authenticated TLS settings + TX + heartbeat ─────► SLAVE
```

MASTER's camera, mixer, selected SRT encoder and encoding selections stay local.
They are no longer forwarded as the SLAVE source. Instead, peer config fixes
`modeinput=IPTSIN`, `source_layout=DIRECT`, `encoding=IPTS in`, `iptransport=srt`.
SLAVE's local `PORTSDOWN_PEER_SRT_PORT` supplies `udpinport` (the legacy key name
is also used for an SRT port). The C supervisor rejects other SLAVE input modes,
and local RX/capture/encoder start roles are disabled. This does not restrict
normal STANDALONE source choices.

**Current integration boundary:** the port setting is configuration, not an
automatically started production receiver. There is no default live RF launcher.
MASTER's supported local TS-output helper can target an SRT caller URL via
`PORTSDOWN_SOURCE_TS_URL`, but source production, SRT delivery, valid-video gate,
preview return and transmitter lifecycle are not yet joined into a single
production peer pipeline. An operator must not infer a valid stream from
`linked` or `config ready`. RF must remain blocked until the integrated receiver
has validated live TS/video, and must stop on media loss even if control
heartbeats continue. That hardware/output integration remains outstanding.

The finite test below explicitly starts a MASTER FFmpeg producer and SLAVE
FFmpeg **stream-copy** receiver, separately from the mock control pipeline.
It validates transport delivery, not a complete armed-to-valid-video RF path.
The receiver remuxes TS; this is not bit-for-bit packet preservation or an
acceptance of final modulator pacing/muxrate.

## Start, stop and link loss

1. MASTER authenticates, sends configuration and waits for `cfg_ok`.
2. TX start sends an initial heartbeat followed by a TX request. SLAVE still
   checks its local supervisor/board/launcher requirements.
3. While TX is requested, MASTER sends a heartbeat every 500 ms.
4. Disconnect requests STOP_TX immediately. The ucode watchdog stops after
   three missed timer ticks; its observed phase-dependent delay can be shorter
   than 1.5 seconds. The C supervisor independently rejects stale starts and
   stops TX once its last heartbeat is 1.5 seconds old.
5. Stop invokes the configured safe-off hook and terminates the owned process
   group, escalating after the bounded grace period. Hardware response requires
   board-specific validation; software timers do not prove RF/PTT-off.
6. Reconnection does not automatically request TX again.

A normal install deliberately has no RF TX/safe-off launcher selected. The test
below uses substitute scripts only. Do not copy its simulated `board=express`
setting into a hardware installation as evidence of board readiness.

## Bidirectional telemetry

SLAVE sends a `state` frame after TX commands, local web E-Stop, configuration
acceptance, and every 500 ms. It contains the C supervisor's status, whether the
TX process is `running`, `stopped` or `unknown`, a reason, and the applied request
ID. Polling catches exits/stops made outside the peer command handler.

MASTER correlates the request ID before clearing a pending TX request, so an
older stopped snapshot cannot cancel a newer START in flight. Local SLAVE E-Stop
is acknowledged to MASTER without needing a second stop command from MASTER.

MASTER requires current return telemetry and a reachable SLAVE supervisor before
allowing a new start. Three missed 500 ms telemetry checks invalidate remote
state and drop the peer link/heartbeats. The GUI displays **UNKNOWN**, never a
false confirmed OFF state. SLAVE's independent watchdog remains responsible for
stopping its process if its ucode daemon or the return/control path is stalled.
This is a process-control fail-safe, not physical RF-off measurement. Both peers
must run the telemetry-aware version; an older peer without state frames cannot
authorize a new start.

## Shared-password LAN acceptance — 2026-11-25

See [HTTPS and peer TLS tests](testing/shared-password-2026-11-25.md).
The older captures below predate password/TLS access and retain their original
loopback/SSH test setup for reproducibility; they are not current setup instructions.

## Recorded two-host acceptance — 2026-11-24

**PASS for the isolated two-host control/UI capture requirement.** This closes
that screenshot gap, not all platform or physical transmitter acceptance.

| Item | Recorded setup |
| --- | --- |
| MASTER | VideoLP3D, x86-64 Linux Mint; existing private ucode runtime |
| SLAVE | TANK, AArch64 Debian Trixie; new isolated user-local ucode runtime |
| Application revision on both | `5264929a395096f97fee4050b97485ae79606550` |
| Peer transport | Direct LAN TCP, test port 28181; not an SSH-forwarded or same-host peer connection |
| Browser access | Each loopback HTTP server reached through its own SSH tunnel |
| TX substitute | Shell process that logs `MOCK TX ONLY - NO HARDWARE` and sleeps |
| Safe-off substitute | Logging-only script plus Express commands directed to a private regular file, never `/tmp/expc` |
| Media | MASTER-generated 1280×720p24 H.264 + AAC 48 kHz TS, SRT caller → SLAVE listener on UDP 28900; received file analyzed with ffprobe |
| Hardware | No capture devices, RF launchers, ASI output, or external modulator control |
| Cleanup | Both test instances, mock children, browser processes and SSH tunnels stopped; temporary configs/token removed |

TANK required `cmake`, `cmake-data`, `librhash1` and `libjson-c-dev` for the native
runtime build. No OS/kernel upgrade, reboot or boot service was performed. The
runtime remains isolated under `/home/leo/diablo-peer-test/install`; existing
VideoLP3D installation/configuration was not overwritten.

[Machine-readable results](testing/peer-two-host-2026-11-24.json) include exact
observations, including local E-Stop acknowledgement and telemetry-loss state. [Six actual UI captures](SCREENSHOTS.md#two-host-peer-control-and-link-loss)
show both roles and the two loss states. No token or camera credentials were
included in screenshots/results. The test-card / NO IPTS INPUT preview is the ordinary GUI
placeholder, **not received or encoded test video**. The finite media receiver
was not connected to the preview panel; the mock TX process does not enforce
video validity and is never installed as a hardware launcher.

Verified:

- Authentication/config-ready handshake and a changed service-name synchronized.
- MASTER kept its local test-card source; SLAVE remained IPTS/SRT pass-through.
- A finite SRT delivery produced a 6.02-second MPEG-TS capture with H.264
  1280×720 at 24 fps and AAC at 48 kHz on TANK. No video/audio re-encode on SLAVE.
- SLAVE API rejects config writes, TX start, and SRT enable with HTTP 403.
- Chromium verifies locked SLAVE settings with E-Stop still enabled.
- MASTER start runs mock TX on SLAVE while MASTER's local TX stays stopped.
- Remote stop and local SLAVE E-Stop stop mock TX; the latter clears MASTER's
  pending request and reports `stopped` with reason `local E-Stop`.
- An independently exited SLAVE TX process is reported back to MASTER.
- Freezing SLAVE ucode makes MASTER telemetry unavailable/UNKNOWN, disables
  new starts, and the still-running SLAVE C watchdog stops mock TX.
- Returning telemetry does not restart TX without an explicit request.
- Frozen MASTER (`SIGSTOP`, TCP still open) loses heartbeats and SLAVE stops
  in **1.246 seconds** in this run.
- Terminated MASTER closes TCP and SLAVE stops on disconnect in **0.029 seconds**.
- Resume/reconnect do not re-key; a subsequent explicit start/stop still works.

Timings are request-to-observed-stop measurements including SSH/API polling,
not hard real-time guarantees or RF turn-off measurements. Freezing the MASTER
models a silent control sender; no router, cable, firewall or system-wide network
configuration was altered. This does not cover sustained packet loss, jitter,
reordering, or long-duration operation.

## Reverse-role acceptance — 2026-11-25 UTC (Nov 24 PST)

**PASS:** TANK (AArch64) MASTER → VideoLP3D (x86-64) SLAVE, using the same
revision `5264929`, isolated runtimes and no-hardware substitutes. All 16 recorded
checks passed. TANK generated 720p24 H.264/AAC; VideoLP3D received a 6.02-second
TS over SRT with stream copy. Local SLAVE E-Stop cleared MASTER's pending
request; process exit and missing return telemetry were reported correctly.
Heartbeat loss stopped mock TX in **1.460 s**; disconnect stopped it in
**0.031 s**. Recovery required an explicit new start. Both workers report all
owned processes exited.

[Reverse-role results](testing/peer-two-host-reverse-2026-11-25.json) ·
[Reverse-role captures](SCREENSHOTS.md#reverse-roles-tank-master--videolp3d-slave)

This clears the reverse-role test subset. It does not close fresh-image,
permissions/reboot, impaired-network endurance, integrated media-loss gating,
preview-return or physical RF/ASI acceptance. Media delivery remains separate
from the mock TX control test, just as in the forward run.

## Reproduce the isolated test

Development dependencies on the orchestration host: Python 3, requests,
websockets, Chromium, SSH/SCP. Both targets need native Diablo C utilities and
ucode runtimes built from the revision being tested. The script does **not**
load either host's normal `diablo.env`; all hardware launchers are absent. Its explicitly bounded FFmpeg producer/receiver
are test-only; the token is never stored in the repository.

```bash
python3 scripts/dev/test-peer-two-host.py \
  --master-ssh lattepanda-asi --slave-ssh tank-rover \
  --master-repo /home/mat/dektec-asi/peer-test/repo \
  --slave-repo /home/leo/diablo-peer-test/repo \
  --master-runtime /home/mat/dektec-asi/diablo-studio/runtime \
  --slave-runtime /home/leo/diablo-peer-test/install/runtime \
  --slave-address 192.168.3.33 \
  --output /tmp/diablo-peer-evidence
```

For the reverse-role run, swap both SSH aliases, repo paths and runtime paths,
set `--slave-address 192.168.3.232`, and use a separate output directory.

These aliases/paths are the recorded lab setup; substitute your own. The script
uses temporary directories, a freshly generated token sent over SSH stdin, and
loopback HTTP port 28180. It reserves preview ports 28200, 28210–28214 and
28220–28224 without starting producers; browser tunnel ports are 29180/29182.
SRT media test port is 28900. Peer port and remote HTTP port can be overridden. Do not run two copies at once.
Review results and images before copying them into documentation.

## Known limitations retained

- Telemetry is **supervisor process state**, not measured RF power, PTT voltage,
  decoded video validity, SRT statistics or modulator lock. Those require backend
  integration. MASTER's transmitter panel now displays confirmed remote process
  state instead of its own local status; missing telemetry is UNKNOWN, not OFF.
- A connected TCP socket is not proof of healthy heartbeats. In the frozen
  MASTER screenshot, peer mode remains `linked` while supervisor `link=stale`
  and `tx=stopped`. Immediately after disconnect, cached supervisor `link=ok`
  can coexist with `not linked`; the UI needs clearer live status reconciliation.
- Remote RX, SRT enable/disable and local-TS controls are not carried by this
  peer protocol. Camera credentials stay local. Hardware device paths need to
  make sense on the SLAVE.
- Incoming connections replace the active link before authentication; hardening
  and authenticated peer replacement remain work items.
- Physical safe-off, integrated valid-TS/media-loss gate and preview return,
  source-to-output integration, actual
  impaired-network endurance, fresh armhf installs, permissions and reboot
  persistence remain outside this run. See [issue #6](https://github.com/mathisono/Diablo-DATV-Studio/issues/6)
  and the [work register](KNOWN_ISSUES.md).
