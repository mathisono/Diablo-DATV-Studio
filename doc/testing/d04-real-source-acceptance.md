# D-04 — real-source and endurance test instructions

**Status: planned, not passed.** This is the test procedure for [D-04](https://github.com/mathisono/Diablo-DATV-Studio/issues/4). Existing [Pi Camera](picam-srt-two-host-2026-11-25.md) and [MacroSilicon USB capture](../usb-hdmi-capture.md) results are useful baselines, but neither replaces the physical-source and endurance checks below.

## Required equipment and acceptance gates

| Gate | Required real equipment and route | Evidence needed |
| --- | --- | --- |
| **ATEM Mini Pro — required** | A physical **Blackmagic ATEM Mini Pro**, known moving HDMI program picture with an audible sync cue, and its own Ethernet **SRT caller** into a Diablo SRT input slot | Actual ATEM model/firmware, SRT settings, live preview, H.264/AAC TS, measured duration and loss/reconnect results. An OBS sender, file loop, or `atem_srt_emulator.sh` does **not** pass this gate. |
| Elgato video and audio | Physical Elgato HDMI capture device with known external HDMI picture and audio | V4L2 and ALSA identity, actual picture/audio capture, source loss/recovery and A/V sync. The previously tested MS2109 is not an Elgato substitute. |
| Pi Camera | Physical Pi Camera, released by any other owner for the test | 480p25, 720p24, 1080p15 video and the requested high-resolution-to-lower-resolution path, with valid TS where a route exists. The earlier 720p24/10.8 s result is only a bounded subset. |
| Two IP cameras | Two distinct physical RTSP cameras simultaneously | Each camera's preview, local TS, independently induced loss/reconnect, and high-resolution downsampling. |
| Five SRT encoders | Five independent **live physical-source** callers at once; the ATEM Mini Pro is one of them | Slots 1–5 live together, separate preview/TS evidence, individual reconnect without disturbing the other four, and CPU/thermal/latency measurements. Five copies of one file are not real-source acceptance. |

Use an isolated test installation/configuration, or back up the active configuration and record exactly what will be restored. Keep **RF/PTT and ASI output disabled**; this plan tests video sources and local MPEG-TS, not transmitter hardware. Do not seize a camera used by another service without arranging its safe stop and restoration. Keep camera URLs, SRT passphrases, login credentials, private scenes and full logs out of published evidence.

Before starting, record the Diablo commit, host/OS, FFmpeg version, physical device models/firmware, network topology, chosen SRT ports, and source video/audio formats. Confirm FFmpeg has SRT support and that `ffprobe` and `tsanalyze` are available on the test host. Default Diablo ports are SRT **9101–9105/UDP**, per-slot loopback TS **12001–12005/UDP**, and selected local output TS **127.0.0.1:12010/UDP**; use the actual GUI/`diablo.env` values if changed. Only one caller should use each slot.

## 1. ATEM Mini Pro: mandatory SRT test

1. Connect a real, moving HDMI source with a visible clock or clap and audible sound to the ATEM Mini Pro. Select it on the ATEM program output. Verify the ATEM's own program picture and audio meters first; device-generated bars or a silent feed do not prove external input.
2. Connect ATEM Ethernet to the test LAN. In Diablo, enable **SRT input encoder 1**, select **Direct source → SRT input → slot 1**, save, and copy the caller address shown by the GUI (normally `srt://DIABLO_LAN_IP:9101?mode=caller&latency=200000`). Configure the **ATEM itself** to call that listener over SRT. Record ATEM model, firmware, SRT profile, video standard, measured bitrate and audio format. Check the installed ATEM firmware/menu: if it cannot originate SRT, mark this gate **BLOCKED**; a USB or OBS-to-SRT bridge is a separate experiment, not a pass for native ATEM SRT.
3. Start the ATEM stream. Confirm that Diablo's `NO SRT INPUT 1` card changes to the real moving picture, the slot reports live, and the preview is current. The preview is video-only; verify actual audio in the recorded TS, not by looking at the preview.
4. Record a **60-second TS sample** using the selected **Start output TS** route, then stop that route. On the Diablo host, start the receiver command below and click **Start output TS** promptly. Replace the loopback port if customized. A timeout or empty file is a failure to investigate, not evidence of a pass.

   ```sh
   run_dir=$(mktemp -d /tmp/diablo-d04.XXXXXX)
   timeout 100s ffmpeg -hide_banner -nostdin -loglevel warning \
     -f mpegts -i 'udp://127.0.0.1:12010?fifo_size=100000&overrun_nonfatal=1' \
     -t 60 -map 0 -c copy -f mpegts "$run_dir/atem-slot1.ts"
   ffprobe -v error -show_programs -show_streams -show_format -of json \
     "$run_dir/atem-slot1.ts" > "$run_dir/atem-probe.json"
   tsanalyze --json "$run_dir/atem-slot1.ts" > "$run_dir/atem-ts.json"
   ffmpeg -v error -i "$run_dir/atem-slot1.ts" -map 0:v:0 \
     -frames:v 100 -f null -
   ffmpeg -v error -i "$run_dir/atem-slot1.ts" -map 0:a:0 \
     -t 10 -f null -
   ```

   Check the recorded duration, H.264 video, AAC audio, picture motion, decoded frames, service/PID information and TS analyzer errors. FFmpeg remuxes this sample: it verifies the resulting TS, but can conceal original UDP packet continuity defects. Use a raw packet capture as additional evidence if investigating transport continuity. Review the clip for A/V sync against the source cue and record the observed end-to-end latency; do not claim an unmeasured latency.
5. Stop **only the ATEM SRT stream**. Verify the slot returns to `NO SRT INPUT 1`, no stale frame or saved TS continues as live input, and the other sources remain unaffected. Restart the ATEM stream and record the time until fresh picture/audio return. Repeat once with a brief Ethernet interruption if safe for the test setup. No RF/PTT should start or remain keyed during any of this.
6. Run the ATEM stream continuously for the single-source endurance window below. Record any reconnects, frame/audio gaps, bitrate changes, process exits and temperature/CPU changes.

**Additional ATEM USB check:** If the ATEM Mini Pro USB-C webcam output is also being qualified, test it separately as **USB HDMI capture**. Enumerate `v4l2-ctl --list-devices`, the actual capture formats and `arecord -l`; select the discovered device (never assume `/dev/video0` or a fixed ALSA card), verify external program picture and audio, then test loss/recovery. This is useful, but **does not replace the required ATEM SRT test** or the separate Elgato test.

## 2. Other real-source checks

1. **Elgato:** connect a known moving HDMI picture and audible cue to the real Elgato capture device. Enumerate its V4L2 node, supported formats and ALSA card under the *service account*, then select **USB HDMI capture** in Diablo. Verify the preview shows the external picture, not only device-generated bars. Make a bounded video+audio capture using the enumerated modes; inspect it with `ffprobe`, decode both streams and check A/V sync. Remove and restore the HDMI input and USB device separately; record waiting/live behavior and any permission errors. The current GUI's **Start output TS** route does not directly support USB HDMI, so do not claim that integration from preview alone.
2. **Pi Camera:** with its normal owner safely stopped, test actual camera capture at **854×480/25**, **1280×720/24**, and **1920×1080/15** using `scripts/capture_ts_ffmpeg.sh --source rpicam` with `--size`, `--fps`, `--video-bitrate`, `--muxrate`, `--duration` and `--output` set for each run. Analyze and decode each finite TS; label a synthetic test tone as synthetic, not microphone audio. Test a **physical high-resolution camera feed downsampled** to both 480p25 and 720p24 (the Direct IP CAM route supports this when a high-resolution RTSP camera is available). The new GUI does not yet route Direct Pi Camera to **Start output TS**; mark that GUI integration **BLOCKED** until wired, even if the standalone helper passes. Restore the prior camera owner afterward.
3. **Two RTSP cameras:** enter each physical camera's private URL through **IP CAM input encoders → Save IP** and use **Restart** to reconnect. Check the two independent previews simultaneously. Select each Direct IP CAM source and save 60-second local TS samples at **480p25** (`16:9` format), **720p24**, and **1080p15** where supported; analyze/decode the TS and record the actual input versus output sizes. Stop one physical camera or network path, verify only its own preview/TS falls back, restore it, then repeat for the other. Redact RTSP URLs and credentials in screenshots/logs.
4. **Five SRT slots:** while the ATEM and four other independent physical-source callers are live, enable slots 1–5 and verify five distinct current previews. One possible mapping is ATEM Mini Pro, Elgato HDMI capture, Pi Camera, RTSP camera 1 and RTSP camera 2, with the latter four encoded to SRT by separate live senders; record the actual mapping used. Sample each loopback TS port **12001–12005**, record source identity/codec/audio/bitrate and confirm no slot displays an old file or another slot's feed. Interrupt and restore each caller **one at a time**; the other four must continue. Measure reconnect time per slot. If only synthetic or replayed callers are available, record a useful stress run but leave the real-source gate open.

## 3. Endurance, results and cleanup

**Proposed minimum observation windows:** 10 minutes per required source and 30 minutes with all five SRT slots running concurrently. Record actual start/end times and durations; short functional samples do not count as endurance. Once per minute, log CPU load, memory, temperature (and Pi throttling status where available), process restarts, per-slot bitrate/frame rate, preview freshness and measured latency. Retain logs/TS analyses privately; publish only sanitized summaries and approved images. The issue currently has no numeric CPU or latency limit, so report values and any drift rather than inventing a pass threshold. Any thermal throttling, crash, unplanned reconnect, stalled/stale preview, missing required audio or invalid TS is a failure to diagnose.

For every gate, record **PASS / FAIL / BLOCKED**, the physical source and route, commit, device firmware, actual duration, TS file/probe/analyzer results, decoded frame/audio result, observed loss/reconnect times, CPU/thermal/latency measurements, and a short limitation note. Mark D-04 complete only when all required physical-source and endurance gates pass; do not promote a synthetic, preview-only, or short bounded subset to full acceptance.

Finish by stopping local output TS and all test callers, confirming no RF/PTT/ASI output was enabled, restoring the saved configuration and any displaced camera service, and checking that temporary test processes are gone. Preserve evidence only in the intended private test directory and review it before publication.
