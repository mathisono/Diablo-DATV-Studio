#!/bin/bash
# Direct SRT slot relay or four-tile low-rate multiview MPEG-TS output.
# This is a monitor/TS source, never an RF/PTT launcher or saved recording.
set -euo pipefail
dir=${PORTSDOWN_DIR:-$(cd "$(dirname "$0")/.." && pwd)}
config=${PORTSDOWN_CONFIG:-$dir/scripts/portsdown_config.txt}
ffmpeg=${PORTSDOWN_FFMPEG:-ffmpeg}
http_port=${PORTSDOWN_HTTP_PORT:-8080}
output=${PORTSDOWN_SOURCE_TS_URL:-udp://127.0.0.1:12010?pkt_size=1316}
duration=${PORTSDOWN_SOURCE_TS_DURATION:-}
if [[ -n $duration && ! $duration =~ ^[1-9][0-9]{0,3}$ ]]; then
  echo 'Multiview duration must be 1-9999 seconds' >&2; exit 2
fi
[[ -r $config ]] || { echo 'Configuration unavailable' >&2; exit 2; }
cfg() { awk -F= -v key="$1" '$1 == key { print substr($0, index($0, "=") + 1); exit }' "$config"; }
layout=$(cfg source_layout)
[[ $layout == MULTIVIEW || ( $layout == DIRECT && $(cfg modeinput) == SRT ) ]] || {
  echo 'Select Multiview or Direct SRT and save configuration first' >&2; exit 2;
}
[[ $http_port =~ ^[0-9]+$ ]] && (( http_port >= 1024 && http_port <= 65535 )) || exit 2
provider=$(cfg call)
name=$(cfg service_name)
[[ $provider =~ ^[A-Z0-9/]{3,20}$ && $provider =~ [0-9] && -n $name ]] || {
  echo 'Save CALLSIGN and service name before generating TS' >&2; exit 2;
}
limit=()
if [[ -n $duration ]]; then limit=(-t "$duration"); fi
if [[ $layout == DIRECT ]]; then
  slot=$(cfg srt_source_slot)
  slot=${slot:-1}
  [[ $slot =~ ^[1-5]$ ]] || { echo 'Invalid SRT slot' >&2; exit 2; }
  ts_base=${PORTSDOWN_SRT_TS_PORT_BASE:-12001}
  [[ $ts_base =~ ^[0-9]+$ ]] && (( ts_base >= 1024 && ts_base <= 65531 )) || exit 2
  input_port=$((ts_base + slot - 1))
  echo "Selected direct SRT encoder $slot: TS UDP 127.0.0.1:$input_port → $output" >&2
  if [[ -n $duration ]]; then
    exec "$ffmpeg" -hide_banner -nostdin -loglevel warning \
      -fflags +nobuffer -analyzeduration 200000 -probesize 32768 -rw_timeout 5000000 \
      -f mpegts -i "udp://127.0.0.1:$input_port?fifo_size=100000&overrun_nonfatal=1" \
      -map 0:v:0 -map '0:a:0?' -c copy \
      -metadata "service_provider=$provider" -metadata "service_name=$name" \
      "${limit[@]}" -f mpegts "$output"
  fi
  # Remain armed across caller disconnects; FFmpeg emits no TS without a
  # readable live input. Supervisor TERM ends the whole process group.
  while :; do
    "$ffmpeg" -hide_banner -nostdin -loglevel warning \
      -fflags +nobuffer -analyzeduration 200000 -probesize 32768 -rw_timeout 5000000 \
      -f mpegts -i "udp://127.0.0.1:$input_port?fifo_size=100000&overrun_nonfatal=1" \
      -map 0:v:0 -map '0:a:0?' -c copy \
      -metadata "service_provider=$provider" -metadata "service_name=$name" \
      -f mpegts "$output" || true
    sleep 1
  done
fi
case $(cfg format) in
  1080p) tile_width=960; tile_height=540;;
  720p) tile_width=640; tile_height=360;;
  16:9) tile_width=426; tile_height=240;;
  *) tile_width=320; tile_height=240;;
esac
args=(-hide_banner -nostdin -loglevel warning)
for tile in 1 2 3 4; do
  choice=$(cfg "multiview_$tile")
  case "$choice" in
    HDMI) url=/api/video/source/hdmi;;
    CAMH264) url=/api/video/source/camera;;
    IPTSIN) url=/api/video/source/ipts;;
    SRT[1-5]) url=/api/video/srt/${choice#SRT};;
    CARDH264) url=;;
    *) echo "Invalid multiview tile $tile: $choice" >&2; exit 2;;
  esac
  if [[ -n $url ]]; then
    args+=(-rw_timeout 5000000 -r 5 -f mpjpeg -i "http://127.0.0.1:$http_port$url")
  else
    args+=(-loop 1 -framerate 5 -i "$dir/www/test-card.jpg")
  fi
done
filter=''
for i in 0 1 2 3; do
  filter+="[$i:v]fps=5,scale=$tile_width:$tile_height:force_original_aspect_ratio=decrease,pad=$tile_width:$tile_height:(ow-iw)/2:(oh-ih)/2,setsar=1[v$i];"
done
filter+='[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0:fill=black[out]'
exec "$ffmpeg" "${args[@]}" -filter_complex "$filter" -map '[out]' "${limit[@]}" \
  -an -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p \
  -r 5 -g 10 -b:v 900k -maxrate 950k -bufsize 950k \
  -metadata "service_provider=$provider" -metadata "service_name=$name" \
  -f mpegts -muxrate 1100000 "$output"
