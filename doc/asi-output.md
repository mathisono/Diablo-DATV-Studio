# DekTec ASI output — bounded card tests and live IP input

## Recorded result: 2026-11-25

**Card-only PASS; D-02 remains partially open.** The owner confirmed physical
output BNC port 2 was disconnected. TSDuck reported transmitting through the
DTA-2145 and releasing its output channel. This is **not** independent evidence
of a valid signal at the BNC or a locked downstream modulator/receiver. No
external RF controls, drivers, firmware, boot services or production GUI config
were changed. All test playout is stopped.

| Check | Result |
| --- | --- |
| Hardware | VideoLP3D, x86-64, DTA-2145 Rev 2; device 0, output channel 0, physical port 2 |
| Runtime | Kernel 6.14.0-37-generic; Dta 4.28.15.294; DTAPI 6.13.0.242; TSDuck 3.45-4798; FFmpeg 6.1.1 |
| File playout | Finite 12-second 720p24 H.264/AAC test; card start/drain/detach completed, exit 0 |
| Live input | TANK generated moving 720p24 H.264/AAC, SRT caller → VideoLP3D listener → ASI; both processes exited 0 |
| Matched TS/ASI rate | 3,071,588 b/s; PCR-derived rate in both analyzed input files exactly matched |
| Pre-card TS errors | Zero invalid syncs, transport errors, PID continuity discontinuities or PCR/PTS/DTS leaps reported |
| Metadata | Live input N0CALL / TANK-Test-Input changed to configured KJ6DZB / Diablo Live ASI; service 1, PMT 4096, video/PCR 256, audio 257 |
| Ownership | Concurrent file request rejected while live ASI held the shared channel lock |
| Input ends | Sender disconnect stopped live playout and detached; no replay or automatic retry |
| Explicit stop | Live TERM → exit/detach in 0.215 s, no forced kill; file drain took 1.823 s |
| Reopen | File output reopened and completed after stop; no channel-busy error |
| Software regressions | Four live-route/locking tests plus two service-metadata tests passed |

The live packet tap is **before the card**, not an ASI receiver capture. It
contained 24,167 packets; the original file contained 24,471. They are different
synthetic sources, not a packet-equivalence comparison. Input media was finite;
this is not long-duration, thermal or impaired-network acceptance.

[Evidence directory](testing/d02-2026-11-25/) includes analysis/probe JSON,
failed and successful playout logs, stop timings, host inventory and a summary
with source hashes. Test files and isolated launcher copies remain under
`/home/mat/dektec-asi/tests/d02-20261125/`; no normal installation was overwritten.

## Repeat card test — 2026-11-25, revision `27c2ed9`

**PASS, card/driver level.** The latest launchers were copied to an isolated
test directory on VideoLP3D without changing the installed application. Device
0/output channel 0/physical port 2 and the driver/runtime versions above were
reconfirmed; the owner's disconnected-output test setup remained the basis of
this test. No external RF controls were used.

- Reanalyzed the finite 720p24 H.264/AAC reference file: PCR-derived rate
  **3,071,588 b/s**, zero sync/transport errors, continuity discontinuities or
  PCR/PTS/DTS leaps. File playout completed normally in **12.313 s**.
- TANK sent a finite generated 720p24 H.264/AAC stream over SRT at the same
  muxrate. Sender and live ASI launcher both exited **0**. TSDuck reported
  transmission, sender disconnect, then normal card termination. The listener's
  **23.311 s** wall time includes waiting for the sender; it is not media latency.
- The **pre-card** packet tap again matched the PCR bitrate with zero reported
  sync/transport/continuity errors or timestamp leaps; 24 video frames decoded
  without errors. Output metadata was **KJ6DZB / Diablo ASI Retest**.
- File playout reopened and completed in **12.286 s** after live shutdown.
  Final checks found no TSDuck or FFmpeg process on VideoLP3D, and the shared
  channel lock was available. TANK's rover remained active throughout.

[Repeat-test logs and analysis](testing/asi-retest-2026-11-25/) are retained.
Remote working files: `~/dektec-asi/tests/asi-retest-20261125/` on VideoLP3D.
This test used generated video, **not the Pi camera**, and did not independently
receive the ASI BNC signal. Physical timing/receiver lock, camera-to-ASI GUI
integration and endurance remain open; D-02 is not closed.

## Corrected small-FIFO stall

With a 256 KiB hardware FIFO, uncapped TSDuck output batches stalled. The first
`--wait-detach` attempt and an `--instant-detach` retry required the bounded
outer timeout to force termination. Changing detach mode alone did not fix it.

The working launcher uses:

```text
--buffer-size-mb 1 --initial-input-packets 128 --max-output-packets 128
-O dektec --device 0 --channel 0 --io-standard ASI --bitrate 3071588
--fifo-size 262144 --preload-fifo --preload-fifo-delay 100
```

A 128-packet send batch is 24,064 bytes, smaller than the hardware FIFO. File
playout uses `--wait-detach`; live playout uses `--instant-detach` to discard
queued tail at shutdown. At the tested bitrate the FIFO's capacity represents
about 683 ms of TS, with 100 ms requested preload. These are **capacity settings,
not measured end-to-end latency**; software/SRT/receiver buffers add delay.
For higher configured bitrates the shared helper increases FIFO capacity to at
least 200 ms, rounded to 64 KiB. Those higher rates have not been hardware-tested.
The fixed 1 MiB software buffer is another capacity, not a guarantee it stays full.

Both launchers use one non-blocking `flock` per device/channel under the service
account's cache directory. Use the same account and lock directory for all
Diablo playout. Other programs/accounts do not participate in this lock; the
card driver also arbitrates access. Do not remove lock files during operation.

## Configure

Keep a separate test config until the production output integration is ready:

```ini
modeoutput=DEKTEC_ASI
modulation=ASI
asi_device=0
asi_channel=0
asi_bitrate=3071588
source_layout=DIRECT
modeinput=IPTSIN
iptransport=srt
udpinport=28910
call=YOURCALL
service_name=Your service name
```

Replace `YOURCALL` with the operating callsign (including its digit). The GUI's
saved `call` and `service_name` fields use the same metadata. File mismatches
remain advisory and never block playout. Live `svrename` changes the first PAT
service; this is a **single-service** contribution path. File playout enumerates
and attempts to relabel each program. Unavailable metadata/plugin preserves
input labels, with a warning.

The live launcher accepts **already-shaped MPEG-TS**; it does not transcode,
calculate a modulator rate, or automatically correct mismatched PCR/muxrates.
Validate the incoming muxrate against `asi_bitrate` first. Independent-rate
stuffing is not enabled by this launcher. Arbitrary high-rate SRT streams are
not automatically made suitable for a lower-rate ASI output.

## Generate the finite reference file

Run on VideoLP3D (or another FFmpeg host). Set the callsign/name for your test:

```bash
ffmpeg -hide_banner -nostdin \
  -f lavfi -i 'smptebars=size=1280x720:rate=24' \
  -f lavfi -i 'sine=frequency=1000:sample_rate=48000' \
  -t 12 -map 0:v:0 -map 1:a:0 \
  -c:v libx264 -threads 2 -preset veryfast -tune zerolatency \
  -pix_fmt yuv420p -b:v 1484k -maxrate 1484k -bufsize 1484k -g 48 -bf 0 \
  -c:a aac -b:a 48k -ar 48000 -ac 2 \
  -muxrate 3071588 -pcr_period 20 -pat_period 0.1 -sdt_period 0.5 \
  -mpegts_original_network_id 1 -mpegts_transport_stream_id 1 \
  -mpegts_service_id 1 -mpegts_pmt_start_pid 4096 \
  -streamid 0:256 -streamid 1:257 \
  -metadata service_provider=KJ6DZB -metadata service_name=Diablo-ASI-Test \
  -f mpegts test720.ts
tsanalyze --json test720.ts > analysis.json
ffprobe -v error -show_programs -show_format -of json test720.ts > probe.json
```

## Start and stop file playout

Use absolute paths and verify device/channel enumeration with `tsdektec -a -v`.
If connected to a modulator, confirm RF is disabled and that its required input
TS bitrate matches. ASI playout itself does not control the modulator's RF.

```bash
export PORTSDOWN_DIR=/absolute/path/to/Diablo-DATV-Studio
export PORTSDOWN_CONFIG=/absolute/path/to/asi-test-config.txt
export PORTSDOWN_BOARD=dektec_asi
export PORTSDOWN_ASI_TS_FILE=/absolute/path/to/test720.ts
# Twelve-second sample; outer deadline also bounds unexpected driver hangs:
timeout --signal=TERM --kill-after=2s 20s "$PORTSDOWN_DIR/control/dektec-asi-file.sh"
```

Foreground **Ctrl+C** requests stop. For supervised execution, terminate the
owned process/session, never `killall tsp`. File mode drains the FIFO and may
take longer than the GUI supervisor's 500 ms grace; it is not an RF E-Stop.

## Start the live SRT listener, then send from TANK

On VideoLP3D, with the config above and **no file playout active**:

```bash
export PORTSDOWN_ASI_BIND=192.168.3.232
# Default bind is 127.0.0.1; explicitly use the intended LAN address.
# Optional bounded pre-card packet tap (consumes disk; never leave unbounded):
export PORTSDOWN_ASI_AUDIT_TS=/absolute/path/to/live-tap.ts
timeout --signal=TERM --kill-after=2s 45s "$PORTSDOWN_DIR/control/dektec-asi-live.sh"
```

On TANK, adapt the reference FFmpeg command above: replace `smptebars` with
`testsrc2`, insert `-re` before the first `-f lavfi`, use `-preset ultrafast`,
and replace the file output with:

```text
-f mpegts 'srt://192.168.3.232:28910?mode=caller&latency=200000&pkt_size=1316'
```

Keep `-t 12` and `-muxrate 3071588`. The tested sender used deliberately different
input labels (N0CALL / TANK-Test-Input), then verified the configured output
labels in the pre-card tap. The transport stream is not video/audio re-encoded
on VideoLP3D. Sender disconnect ends the listener/output; restart is explicit.
TSDuck latency is specified in milliseconds; FFmpeg's URL latency is microseconds.

`PORTSDOWN_ASI_DURATION=12` optionally limits live playout from the first packet;
retain an outer timeout to bound a listener that never receives anything.
`iptransport=udp` uses `udpinport` and a 1500 ms receive timeout. For
`modeinput=SRT`, `srt_source_slot=1..5` selects the already-running encoder slot's
loopback UDP TS port (`PORTSDOWN_SRT_TS_PORT_BASE`, default 12001). These UDP/slot
routes have argument/validation tests; only direct IPTS-over-SRT was card-tested
in this session. Starting the ASI script does not start an encoder slot.

## Still open

- Independently receive/analyze the physical BNC output: actual signal, pacing,
  PCR accuracy, continuity, receiver lock and end-to-end latency.
- Connect the full selected-source GUI lifecycle to ASI (including capture,
  shaping/rate validation and previews); source-specific launch/gating tests.
  These scripts are **not automatically installed as GUI TX hooks**.
- Integrated valid-video/media-loss gating and hardware/receiver telemetry.
  TS packet arrival and a running process are not video-valid or RF-safe claims.
- Longer-duration stability, real capture inputs, alternative rates and
  independent-rate stuffing. No tests enable RF or autostart at boot.

See [D-02](KNOWN_ISSUES.md#d-02--live-asi-integration-and-physical-dta-2145-acceptance).
