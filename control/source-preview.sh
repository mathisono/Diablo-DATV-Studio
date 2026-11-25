#!/bin/bash
# Independent low-rate preview producer. Never supplies RF or uses recordings.
set -euo pipefail
role=${1:-}
ffmpeg=${PORTSDOWN_FFMPEG:-ffmpeg}
config=${PORTSDOWN_CONFIG:-${PORTSDOWN_DIR:-}/scripts/portsdown_config.txt}
base=${PORTSDOWN_SOURCE_MJPEG_PORT_BASE:-$(( ${PORTSDOWN_MJPEG_PORT:-8082} + 6 ))}
case "$base" in ''|*[!0-9]*) exit 2;; esac
(( base >= 1024 && base <= 65533 )) || exit 2
[[ -r "$config" ]] || { echo 'Source preview config unavailable' >&2; exit 2; }
cfg() { awk -F= -v key="$1" '$1 == key { print substr($0, index($0, "=") + 1); exit }' "$config"; }
case "$role" in
  HDMI)
    port=$base
    device=$(cfg expresshdmidevice)
    [[ $device =~ ^/dev/video[0-9]+$ ]] || { echo 'HDMI V4L2 device not configured' >&2; exit 2; }
    args=(-f v4l2)
    case "${PORTSDOWN_HDMI_INPUT_FORMAT:-auto}" in
      auto) ;;
      mjpeg|yuyv422) args+=(-input_format "$PORTSDOWN_HDMI_INPUT_FORMAT");;
      *) exit 2;;
    esac
    args+=(-i "$device")
    ;;
  PICAM)
    port=$((base + 1))
    camera=$(command -v rpicam-vid || command -v libcamera-vid || true)
    [[ -n $camera ]] || { echo 'rpicam-vid is unavailable' >&2; exit 2; }
    camera_index=$(cfg picam_index)
    camera_index=${camera_index:-0}
    [[ $camera_index =~ ^[0-3]$ ]] || exit 2
    ;;
  IPTS)
    port=$((base + 2))
    input_port=$(cfg ipts_input_port)
    input_port=${input_port:-${PORTSDOWN_IPTS_INPUT_PORT:-10000}}
    [[ $input_port =~ ^[0-9]+$ ]] && (( input_port >= 1024 && input_port <= 65535 )) || exit 2
    bind_scope=$(cfg ipts_bind_scope)
    case "${bind_scope:-LOCAL}" in LOCAL) bind_ip=127.0.0.1;; LAN) bind_ip=0.0.0.0;; *) exit 2;; esac
    args=(-fflags +nobuffer -analyzeduration 200000 -probesize 32768
          -rw_timeout 5000000 -f mpegts
          -i "udp://$bind_ip:$input_port?fifo_size=100000&overrun_nonfatal=1")
    ;;
  *) echo 'Expected HDMI, PICAM, or IPTS' >&2; exit 2;;
esac
command -v "$ffmpeg" >/dev/null 2>&1 || exit 2
common=(-hide_banner -nostdin -loglevel warning)
output=(-vf 'fps=5,scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2' -q:v 10 -an -f mjpeg "tcp://127.0.0.1:$port")
if [[ $role == PICAM ]]; then
  "$camera" -n -t 0 --camera "$camera_index" --codec mjpeg --width 640 --height 480 -o - |
    "$ffmpeg" "${common[@]}" -f mjpeg -i pipe:0 "${output[@]}"
else
  exec "$ffmpeg" "${common[@]}" "${args[@]}" "${output[@]}"
fi
