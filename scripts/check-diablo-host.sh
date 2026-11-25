#!/usr/bin/env bash
# Read-only dependency/capture readiness check; never opens a device or starts TX.
set -Eeuo pipefail
failed=0
missing() { echo "MISSING: $*"; failed=1; }
[[ $(uname -s) == Linux ]] || { echo 'Linux is required.' >&2; exit 2; }
. /etc/os-release
printf 'Platform: %s; kernel architecture: %s; userspace: %s-bit\n' "${PRETTY_NAME:-Linux}" "$(uname -m)" "$(getconf LONG_BIT)"
if [[ -r /proc/device-tree/model ]]; then
    printf 'Board: '; tr -d '\0' < /proc/device-tree/model; printf '\n'
fi
if [[ $(getconf LONG_BIT) != 64 ]]; then
    echo 'NOTE: 32-bit userspace remains experimental; a 64-bit kernel alone does not make this a 64-bit install.'
fi
for tool in git cmake make cc pkg-config ffmpeg ffprobe flock; do
    command -v "$tool" >/dev/null || missing "$tool"
done
if command -v pkg-config >/dev/null; then
    pkg-config --exists json-c || missing 'json-c development headers (libjson-c-dev)'
fi
ffmpeg=${PORTSDOWN_FFMPEG:-/usr/bin/ffmpeg}
if command -v "$ffmpeg" >/dev/null; then
    # Capture complete output: grep -q in a pipe can trigger SIGPIPE under pipefail.
    protocols=$("$ffmpeg" -hide_banner -protocols 2>/dev/null)
    encoders=$("$ffmpeg" -hide_banner -encoders 2>/dev/null)
    filters=$("$ffmpeg" -hide_banner -filters 2>/dev/null)
    formats=$("$ffmpeg" -hide_banner -formats 2>/dev/null)
    for item in srt tcp udp; do grep -qw "$item" <<< "$protocols" || missing "FFmpeg protocol $item"; done
    for item in libx264 aac mjpeg; do grep -qw "$item" <<< "$encoders" || missing "FFmpeg encoder $item"; done
    for item in scale fps overlay xstack; do grep -qw "$item" <<< "$filters" || missing "FFmpeg filter $item"; done
    for item in mpegts v4l2 alsa; do grep -qw "$item" <<< "$formats" || missing "FFmpeg format $item"; done
fi
camera=$(command -v rpicam-vid || command -v libcamera-vid || true)
[[ -z $camera ]] && echo 'OPTIONAL: Pi Camera needs rpicam-vid (or libcamera-vid) and supported camera hardware.' || echo "Pi camera tool: $camera"
shopt -s nullglob
for device in /dev/video* /dev/snd/pcm* /dev/dri/renderD*; do
    if [[ ! -r $device || ! -w $device ]]; then
        printf 'DEVICE ACCESS: %s needs read/write access (group %s); see FIRST_START.md.\n' "$device" "$(stat -c %G "$device")"
    fi
done
echo 'Device presence/access is not proof of capture or hardware encoding. No devices opened.'
if ((failed)); then echo 'Dependency check failed; install required packages before building.'; exit 2; fi
echo 'Core dependency check passed. Hardware-specific backends remain separate.'
