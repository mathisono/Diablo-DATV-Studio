# Real Pi camera → SRT → VideoLP3D

**Passed, 2026-11-25.** Application revision `668f1fbc94679f581ce1d561b743b087fdb58a04`,
with the development harness added alongside this report. No production source
changes were needed for this bounded test. [Machine-readable evidence](picam-srt-two-host-2026-11-25.json).

## Equipment and signal path

- **TANK:** Raspberry Pi 4, AArch64 Debian 13/Trixie, actual IMX708 CSI camera.
- **VideoLP3D:** LattePanda 3 Delta, x86-64 Linux Mint 22.3.
- Existing `scripts/capture_ts_ffmpeg.sh --source rpicam` captures raw camera
  video with `rpicam-vid`, software-encodes H.264 **1280×720 at 24 fps**, adds
  **synthetic AAC 1 kHz audio**, and sends MPEG-TS over SRT. This does not test a
  microphone. Video target 800 kb/s, audio 48 kb/s, muxrate 1.2 Mb/s.
- One capture feeds both the TS and a **320×240 / 5 fps MJPEG preview**. The
  test does not open the camera a second time for preview.
- Callsign `N0CALL` and service name `Real Pi camera test - NO RF` are isolated
  test settings, not changes to either installed station configuration.

## Results

| Check | Result |
| --- | --- |
| Standalone: TANK camera → VideoLP3D SRT encoder 1 | Live source and 320×240 preview detected |
| Standalone received TS | 10.771 s; H.264 720p24 / AAC; 24 video frames decoded without errors |
| Sender stopped | Live flag cleared; preview exactly matched the checked-in `NO SRT INPUT 1` JPEG |
| Sender restarted | SRT encoder recovered and returned to live |
| Peer: TANK MASTER camera → VideoLP3D SLAVE | MASTER kept Pi Camera; SLAVE synchronized to IPTS over SRT / no-reencode mode |
| Peer received TS | 14.938 s; H.264 720p24 / AAC stream copy; 24 video frames decoded without errors |
| Both live previews during remote mock TX | Passed; actual browser captures below |
| Local SLAVE E-Stop | MASTER reported STOPPED and cleared its TX request |
| MASTER heartbeat freeze | SLAVE mock TX stopped in 1.298 s |
| MASTER disconnect | SLAVE mock TX stopped in 0.029 s |
| Resume/reconnect | No automatic TX restart |
| Cleanup | All owned test processes exited on both hosts; SSH tunnels closed |

Times are observed software timings, not guaranteed deadlines or physical RF
measurements. The peer receiver stream-copies video/audio into a test TS and
decodes a separate MJPEG preview. The standalone SRT encoder uses its normal
transcoding path.

## Screenshots

Five actual Chromium captures appear in the [gallery](../SCREENSHOTS.md#real-pi-camera-to-srt-and-peer-control)
and selected views in the [README](../../README.md#real-camera-and-two-host-test).
Private camera scenes are covered by a clearly labeled privacy mask in the
published images. UI state is not simulated; the harness checks that a preview
image loaded before masking it. The loss screenshot shows the actual waiting
card without masking. No camera recordings, peer token or credentials are published.

## What this does not clear

- **Media and control remain separate test lifecycles.** The harness starts the
  capture/SRT receiver explicitly. GUI Arm/Start TX controls a mock `sleep`
  process, not the camera sender, modulator or ASI card. A mock TX may therefore
  run independently of media validity. This does not prove valid-video-before-key
  or media-loss-triggered RF shutdown.
- This does not add Pi Camera to the new GUI's local **Start output TS** routes.
  Automatic source/preview/output handoff remains integration work.
- No RF, PTT, ASI, downstream receiver, PCR/continuity, microphone/audio sync,
  480p/1080p real-camera, thermal or endurance acceptance was performed here.
- D-04's real-camera bounded test and D-06's real-camera peer subset are now
  recorded; the broader issues remain open.

## Reproduce

Development host requires Python 3 with `requests` and `websockets`, Chromium,
SSH and SCP. Python is a test dependency, **not a deployed application server**.
Both remote checkouts need native `make -C control` builds, pinned ucode runtimes,
FFmpeg with SRT/libx264/MJPEG/AAC, and SSH access. TANK additionally needs a working
`rpicam-vid`. Use isolated checkouts, not an active installed service checkout.

Free the Pi camera first. If another service owns it, arrange that service's
safe stop and restoration separately; this harness never stops other services.
For this run the owner confirmed track/claw actuator power OFF and authorized
temporarily stopping TANK's rover. No motion commands were sent. After cleanup,
the rover was restored **active**, its boot enablement remained **enabled**, HTTP
returned 200 and two authenticated camera snapshot requests returned fresh JPEGs.
No reboot or motion test was performed.

```sh
python3 scripts/dev/test-picam-srt-two-host.py \
  --master-ssh tank-rover --slave-ssh lattepanda-asi \
  --master-repo /home/leo/diablo-picam-srt-20261125/repo \
  --slave-repo /home/mat/dektec-asi/picam-srt-20261125/repo \
  --master-runtime /home/leo/diablo-install-review-20261125/install/runtime \
  --slave-runtime /home/mat/dektec-asi/diablo-studio/runtime \
  --slave-address 192.168.3.232 \
  --output /tmp/diablo-picam-evidence
```

Paths/SSH aliases are this test's examples; replace them with your isolated
checkouts and runtimes. Both checkouts must contain the matching
`scripts/dev/test-peer-two-host.py`, which supplies the shared worker/browser
helpers. Ports must be free: remote HTTP 28180, peer control 28181, MJPEG
28200/28210–28214/28220–28224, standalone SRT 28300, local TS UDP 28400, peer SRT
28900; local SSH-tunnel ports 29180/29182. Media senders have a finite 60-second
limit. Results, privacy-masked screenshots and private diagnostic logs go to the
specified output directory; publish only reviewed/sanitized evidence.

An initial harness attempt used the wrong case in `/api/video/source/IPTSIN`.
The valid endpoint is `/api/video/source/ipts`; the state key remains `IPTSIN`.
The harness now rejects HTTP failures/EOF instead of looping. That failed test
worker was stopped and its children cleaned up before the successful run.
