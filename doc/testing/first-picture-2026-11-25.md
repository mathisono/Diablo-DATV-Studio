# Beginner first-picture check — 2026-11-25

The simplified FIRST_START guide adds `bash scripts/test-srt-input.sh` as a
no-camera, no-OBS test. It sends moving 640×480 / 25 fps H.264 video and an AAC
test tone over SRT to input 1 on the same computer, for 30 seconds. This avoids
requiring a novice to configure another program before seeing the first picture.

**Passed on TANK, Pi 4 / AArch64 Trixie:**

- Used an isolated temporary configuration and the existing pinned native runtime;
  application revision `668f1fb`, with the new sender helper staged from this change.
- Ran first-start configuration and its real GUI/API check with SRT input 1
  enabled on launch. The receiver was the real `control/srt-slot.sh`, not a mock.
- Launched the GUI, ran the documented sender with no arguments, observed SRT
  input 1 `live=true`, then the sender's normal exit 0 after 30 seconds.
- Observed `live=false` after input ended and confirmed TX remained stopped.
- Stopped the isolated launcher and removed its temporary configuration. No
  camera capture, ASI/RF output, service changes or rover interruption.
- Sender syntax/help/invalid-duration checks passed; rewritten documentation's
  relative links and heading anchors resolved.

This is a bounded software-path check on an existing Linux installation, not
a new OS-image install, remote-LAN test, audio playback test or first-time human
usability study. Previously recorded native installer and wizard checks remain
in [installer review](install-review-2026-11-25.md) and
[first-start tests](first-start-2026-11-25.md). Physical-output limits remain in
[KNOWN_ISSUES](../KNOWN_ISSUES.md).
