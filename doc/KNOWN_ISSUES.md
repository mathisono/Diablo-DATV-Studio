# Current capability and outstanding-work register

This is the migration's current status ledger. Completed tasks are not left as
open TODOs; unfinished hardware/integration work is **not** marked complete just
because its source was copied. Software verification is separate from capture,
card output and receiver/RF acceptance.

## Capability matrix

| Capability | Current evidence | Limit |
| --- | --- | --- |
| Persistent C/ucode web control | Native x86-64 tests; C builds on AArch64 | Linux only; loopback HTTP needs tunnel/authenticated TLS proxy |
| Five SRT source encoders | Synthetic callers; arrival/loss and raster checks | Five-way hardware CPU/thermal endurance and actual ATEM pending |
| Direct SRT local TS | Selected-slot live relay tests | No headless RF/ASI connection yet |
| Two IP CAM configurations | Private URL handling and restart tests; one real camera previously checked | Two physical cameras together not tested |
| IP CAM local TS | Earlier 4K input → 480p/720p TS test | Other cameras/rates require validation |
| HDMI/Pi/IPTS previews | Synthetic/data-path and UDP loss tests | Physical HDMI/Pi capture and audio handoff pending |
| Four-source multiview | Browser layout and actual composite TS | Preview-derived, 5 fps, video only; not a production mixer |
| DVB-S portable encoder | Assembly-equivalence and offline TS tests | Pi DMA/RF acceptance pending |
| DATV-Express DVB-S2 QPSK | Native builds/offline I/Q; legacy interlock tests | USB/PTT/RF and new-GUI launcher pending |
| Pluto / Lime / Streamer | Inherited code retained | New control plane routing and safe-off not qualified |
| DTA-2145 ASI | Dta DKMS + TSDuck card enumeration on LattePanda | Finite physical output and independent analyzer pending |
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

**Done when:** output channel/port mapping, matched bitrate, PCR/continuity,
start/stop release, bounded buffering and independent downstream receive are
verified. Test alternate stuffing separately. Driver enumeration is already done;
physical ASI output is not. External RF remains independently controlled.

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

**Remaining scope:** fresh armhf Pi image, full arm64 platform checks,
network delay/loss/endurance, reverse-role tests, service-account/device
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
