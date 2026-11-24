#!/bin/sh
# Optional standby preview; tx-super stops this process group before TX/RX.
set -eu
device=${PORTSDOWN_VIDEO_DEVICE:-/dev/video0}
port=${PORTSDOWN_MJPEG_PORT:-8082}
ffmpeg=${PORTSDOWN_FFMPEG:-ffmpeg}
case "$port" in *[!0-9]*|'') exit 2;; esac
exec "$ffmpeg" -hide_banner -loglevel warning -nostdin \
  -f v4l2 -i "$device" -vf 'scale=320:240,fps=5' \
  -q:v 10 -an -f mjpeg "tcp://127.0.0.1:$port"
