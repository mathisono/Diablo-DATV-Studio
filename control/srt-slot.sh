#!/bin/sh
# One supervised SRT listener. No RF/PTT connection and no saved recordings.
set -eu
slot=${1:-}
case "$slot" in 1|2|3|4|5) ;; *) exit 2;; esac

base=${PORTSDOWN_SRT_PORT_BASE:-9101}
preview_base=${PORTSDOWN_SRT_MJPEG_PORT_BASE:-8083}
ts_base=${PORTSDOWN_SRT_TS_PORT_BASE:-12001}
case "$base:$preview_base:$ts_base" in *[!0-9:]*|:*|*::*) exit 2;; esac
srt_port=$((base + slot - 1))
preview_port=$((preview_base + slot - 1))
ts_port=$((ts_base + slot - 1))
for port in "$srt_port" "$preview_port" "$ts_port"; do
  [ "$port" -ge 1024 ] && [ "$port" -le 65535 ] || exit 2
done

ffmpeg=${PORTSDOWN_FFMPEG:-/usr/bin/ffmpeg}
[ -n "${PORTSDOWN_CONFIG:-}" ] || PORTSDOWN_CONFIG=${PORTSDOWN_DIR:-/home/pi/rpidatv}/scripts/portsdown_config.txt
# shellcheck source=../scripts/ts_service_metadata.sh
. "$(dirname "$0")/../scripts/ts_service_metadata.sh"
ts_service_metadata_load "$PORTSDOWN_CONFIG"
[ -x "$ffmpeg" ] || { echo "FFmpeg unavailable: $ffmpeg" >&2; exit 1; }
if ! "$ffmpeg" -hide_banner -protocols 2>/dev/null | grep -qx '  srt'; then
  echo "FFmpeg has no SRT protocol support" >&2
  exit 1
fi
echo "SRT slot $slot: listening on UDP $srt_port; live TS on loopback UDP $ts_port; preview on loopback TCP $preview_port"
while :; do
  # A disconnected or unreadable SRT source ends this invocation. The shell
  # restarts the listener; neither TS nor preview receives a saved frame.
  "$ffmpeg" -hide_banner -nostdin -loglevel warning -rw_timeout 3000000 \
    -i "srt://0.0.0.0:$srt_port?mode=listener&latency=200000" \
    -map 0:v:0 -map 0:a:0? \
    -c:v libx264 -threads:v 1 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
    -b:v 800k -maxrate 900k -bufsize 1200k -g 50 -c:a aac -b:a 64k -ar 48000 \
    -metadata "service_provider=$TS_SERVICE_PROVIDER" -metadata "service_name=$TS_SERVICE_NAME" \
    -f mpegts "udp://127.0.0.1:$ts_port?pkt_size=1316" \
    -map 0:v:0 -vf 'fps=5,scale=w=320:h=240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2' \
    -an -c:v mjpeg -threads:v 1 -q:v 10 \
    -f mjpeg "tcp://127.0.0.1:$preview_port"
  echo "SRT slot $slot: input lost; waiting for next caller"
  sleep 1
done
