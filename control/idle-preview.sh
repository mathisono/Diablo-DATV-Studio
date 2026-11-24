#!/bin/sh
# Optional standby preview; tx-super stops this process group before TX/RX.
# HDMI follows the saved V4L2 device, never a saved video recording.
set -eu
device=${PORTSDOWN_VIDEO_DEVICE:-/dev/video0}
port=${PORTSDOWN_MJPEG_PORT:-8082}
ffmpeg=${PORTSDOWN_FFMPEG:-ffmpeg}
case "$port" in *[!0-9]*|'') exit 2;; esac
[ "$port" -ge 1024 ] && [ "$port" -le 65535 ] || exit 2
config=${PORTSDOWN_CONFIG:-}
if [ -z "$config" ] && [ -n "${PORTSDOWN_DIR:-}" ]; then
  config=$PORTSDOWN_DIR/scripts/portsdown_config.txt
fi
if [ -n "${PORTSDOWN_CONFIG:-}" ] && [ ! -r "$config" ]; then
  echo 'HDMI preview configuration is unreadable' >&2; exit 2
fi
if [ -n "$config" ] && [ -r "$config" ]; then
  mode=$(awk -F= '$1 == "modeinput" { print substr($0, index($0, "=") + 1); exit }' "$config")
  if [ "$mode" = HDMI ]; then
    device=$(awk -F= '$1 == "expresshdmidevice" { print substr($0, index($0, "=") + 1); exit }' "$config")
    printf '%s\n' "$device" | grep -Eq '^/dev/video[0-9]+$' || {
      echo 'HDMI preview requires a configured /dev/videoN device' >&2; exit 2;
    }
  fi
fi
command -v "$ffmpeg" >/dev/null 2>&1 || { echo 'FFmpeg unavailable' >&2; exit 1; }
set -- -hide_banner -loglevel warning -nostdin -f v4l2
if [ "${mode:-}" = HDMI ]; then
  case "${PORTSDOWN_HDMI_INPUT_FORMAT:-auto}" in
    auto) ;;
    mjpeg|yuyv422) set -- "$@" -input_format "$PORTSDOWN_HDMI_INPUT_FORMAT" ;;
    *) echo 'Unsupported HDMI input format' >&2; exit 2;;
  esac
fi
exec "$ffmpeg" "$@" -i "$device" \
  -vf 'fps=5,scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2' \
  -q:v 10 -an -f mjpeg "tcp://127.0.0.1:$port"
