# Current capability and outstanding-work register

This is the migration's current status ledger. Completed tasks are not left as
open TODOs; unfinished hardware/integration work is **not** marked complete just
because its source was copied. Software verification is separate from capture,
card output and receiver/RF acceptance.

## Capability matrix

| Capability | Current evidence | Limit |
| --- | --- | --- |
| Persistent C/ucode web control | Native x86-64 and AArch64 C/ucode runtimes; both peer roles tested | Linux only; loopback HTTP needs tunnel/authenticated TLS proxy |
| Five SRT source encoders | Synthetic callers; arrival/loss and raster checks | Five-way hardware CPU/thermal endurance and actual ATEM pending |
| Direct SRT local TS | Selected-slot live relay tests | No headless RF/ASI connection yet |
| Two IP CAM configurations | Private URL handling and restart tests; one real camera previously checked | Two physical cameras together not tested |
| IP CAM local TS | Earlier 4K input → 480p/720p TS test | Other cameras/rates require validation |
| HDMI/Pi/IPTS previews | Real MS2109 USB-device bars in GUI; producer stall/recovery; synthetic/Pi-path and UDP tests | External HDMI picture/audio transitions, Pi capture and audio handoff pending |
| Four-source multiview | Browser layout and actual composite TS | Preview-derived, 5 fps, video only; not a production mixer |
| DVB-S portable encoder | Assembly-equivalence and offline TS tests | Pi DMA/RF acceptance pending |
| DATV-Express DVB-S2 QPSK | Native builds/offline I/Q; legacy interlock tests | USB/PTT/RF and new-GUI launcher pending |
| Pluto / Lime / Streamer | Inherited code retained | New control plane routing and safe-off not qualified |
| DTA-2145 ASI | Finite file and TANK SRT → card playout, stop/reopen and channel lock passed; pre-card TS analyzed | BNC disconnected; downstream signal/timing, full GUI routing and endurance pending |
| Service metadata | GUI validation, TS generation, best-effort ASI svrename | Legacy passthrough may retain input tags; mismatch never blocks ASI |
| Intel QSV | CQP H.264 and finite 720p TS work | Tested CBR/VBR/ICQ rejected; CQP can exceed TS budget |
| DVB-S2X | No implementation found | Not advertised or selectable |

## Closed during migration

- **M-01 Consolidation:** ancestry confirms headless contains the arm64 and Trixie
  branches; complete source history retained, no duplicate cherry-picks.
- **M-02 Packaging:** added a pinned, user-local headless bootstrap and paired
  foreground launcher. Updates preserve operator state; no default RF/ASI hooks.
- **M-03 Dependency coverage:** optional Express S2 builder fetches the pinned
  external modulation library; DekTec installers and GPU findings retained.
- **M-04 Branding/docs:** Diablo README, installation/development guides, source
  provenance and documentation index replace the Buster-first landing page.
- **M-05 Screenshots:** six real-browser fixture captures regenerated and captioned;
  missing hardware screenshots are listed in [SCREENSHOTS.md](SCREENSHOTS.md).
- **M-06 Old updater routing:** legacy install/update entrypoints are blocked so
  Diablo cannot be replaced accidentally by upstream Portsdown `master`.

## Open integration and acceptance work

### D-01 — Headless RF output launchers and interlocks

Track: https://github.com/mathisono/Diablo-DATV-Studio/issues/1

**Scope:** connect eligible live TS sources to DATV-Express DVB-S / experimental
DVB-S2 QPSK; port Pluto/Lime as separate backend implementations. Current GUI TX
is deliberately unarmed or route-blocked. Inherited Python interlocks are not
an installed C/ucode RF integration.

**Done when:** real boards prove valid-video-before-key, loss-triggered dekey,
E-Stop, process failure, disconnect, board switch and controlled shutdown; retain
appropriate hardware failsafes. Add measured receiver evidence and board-specific
setup docs. No source loss may silently substitute saved recordings.

### D-02 — Live ASI integration and physical DTA-2145 acceptance

Track: https://github.com/mathisono/Diablo-DATV-Studio/issues/2

**Scope:** feed shaped live TS from the selected source into a single-owner
TSDuck/DekTec pipeline; keep file playout supported and metadata mismatch advisory.

**Completed subset (2026-11-25):** [card-only test report and commands](asi-output.md).
VideoLP3D DTA-2145 device 0/output channel 0/physical port 2 completed finite
720p24 H.264/AAC file playout and TANK → SRT → ASI at 3,071,588 b/s. Pre-card
TS analysis matched PCR-derived bitrate, PIDs and saved service labels, with
zero sync/transport/continuity errors. Concurrent playout was rejected; sender
disconnect, explicit stop and reopen passed. Live TERM detached in 0.215 s.
Fixed a small-FIFO stall with 128-packet output batches; failed attempts and
working logs are retained. Added shared file/live ownership and a live IP/SRT
launcher; no automatic GUI hook or boot service was enabled.

**Remaining / done when:** the owner confirmed BNC output disconnected, so
independent downstream receive, physical signal/PCR accuracy and end-to-end
latency remain unverified. Complete selected-source GUI lifecycle, rate
validation/shaping, preview and valid-video/media-loss integration, then record
longer-duration and real-source acceptance. Test alternate stuffing separately.
Card/driver start/detach logs are not proof of downstream ASI reception.
External RF remains independently controlled. **D-02 stays open.**

### D-03 — Full-quality multiview and capture/audio handoff

Track: https://github.com/mathisono/Diablo-DATV-Studio/issues/3

**Scope:** replace preview-derived video-only composition with a full-quality
source graph, choose audio policy, and avoid double-opening V4L2/Pi cameras.

**Done when:** mixed-source input changes, aspect ratio, timestamps, audio sync,
loss cards and stop/restart pass bounded local TS and real-device tests. Desktop,
analog/webcam and remaining legacy capture modes need explicit new-GUI routing.

### D-04 — Real-source and endurance coverage

Track: https://github.com/mathisono/Diablo-DATV-Studio/issues/4

**Scope:** actual ATEM SRT; Elgato video/audio; free Pi Camera; two physical RTSP
cameras; five concurrent SRT encoders; source-specific reconnect behavior.

**Completed subset (2026-11-25):** [MacroSilicon MS2109 USB HDMI preview](usb-hdmi-capture.md)
on VideoLP3D: real device-generated bars displayed at 320×240, application
placeholder hidden, producer stall/fallback/resume passed. USB audio enumerates
but service-account ALSA permissions and audio capture remain unverified. This
is not an external HDMI signal-lock/arrival test or an Elgato test.

**Done when:** 480p25/720p24/1080p15 and high-resolution camera downsampling run
for a recorded duration with stable CPU/temperature/latency and valid output TS.
Synthetic caller results remain useful but are not this acceptance gate.

### D-05 — Rate-bounded Intel hardware encoding

Track: https://github.com/mathisono/Diablo-DATV-Studio/issues/5

**Scope:** determine whether compatible iHD/oneVPL/firmware can provide CBR/VBR on
Jasper Lake, or provide an explicitly budgeted alternative. QSV CQP is working;
this is not an “all QSV broken” issue.

**Done when:** representative content stays within the configured TS budget
without DTS/PCR errors, with defined fallback and measured quality/throughput.
Keep libx264 as the fixed-rate fallback. QP 24 already overran the 3.071588 Mb/s
synthetic TS; QP 30 passed only that bounded sample.

### D-06 — Platform, peer and restart acceptance

Track: https://github.com/mathisono/Diablo-DATV-Studio/issues/6

**Completed subset (2026-11-24):** [VideoLP3D MASTER → TANK SLAVE](peer-control.md)
real-network control and six UI captures; IPTS-over-SRT-only SLAVE enforcement;
finite MASTER-produced 720p24 H.264/AAC TS received by stream copy; mock TX
start/stop, local E-Stop, heartbeat-loss stop (1.246 s), disconnect stop (0.029 s),
no automatic re-key on reconnect. Bidirectional process telemetry reports SLAVE
E-Stop/exit to MASTER and clears its pending request; lost return telemetry shows
UNKNOWN and disables starts. All 31 headless-control regression tests passed again with telemetry enabled,
along with the real two-host telemetry cases.

**Additional completed subset (2026-11-25 UTC / Nov 24 PST):**
[TANK MASTER → VideoLP3D SLAVE](testing/peer-two-host-reverse-2026-11-25.json)
passed all 16 recorded checks on revision `5264929`. Native AArch64 MASTER
produced 720p24 H.264/AAC TS; x86-64 SLAVE received 6.02 seconds over SRT without
video/audio re-encoding. Reverse-role configuration locks, remote start/stop,
local SLAVE E-Stop acknowledgement, process-exit telemetry, return-telemetry
loss/UNKNOWN, watchdog stop and explicit-only restart all passed. Heartbeat-loss
stop was 1.460 s; disconnect stop was 0.031 s. These are observed software
timings, not RF measurements. Both isolated instances cleaned up all owned
processes. **Reverse-role testing is cleared**, not the complete D-06 issue.

**Remaining scope:** fresh armhf Pi image, full arm64 platform checks,
network delay/loss/endurance, service-account/device
permissions and reboot behavior. Complete the production MASTER TS → SLAVE
SRT receiver → valid-video/media-loss gate → output/preview lifecycle. Current
peer test uses separate FFmpeg media and mock TX; it is not physical RF/ASI proof.
RF power/PTT/video-validity telemetry still requires backend integration.
Authenticate replacement connections before displacing an active peer.

**Done when:** recorded fresh installs and real-network dead-man's-switch tests
pass without disturbing existing applications. Clean-checkout software tests are
not a full OS-image qualification. SRT enable state is currently runtime-only.

### D-07 — Receiver and remaining legacy operations

Track: https://github.com/mathisono/Diablo-DATV-Studio/issues/7

**Scope:** implement new-GUI RX launcher, receiver controls and remaining legacy
menu functions. Preserve working old software until each replacement is ready.

**Done when:** real receivers and stop/handoff paths are tested; unsupported
controls are clearly unavailable. The presence of a GUI button alone is not
support for a receiver or RF backend.
