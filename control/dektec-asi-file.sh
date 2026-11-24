#!/bin/sh
# Finite MPEG-TS file playout through a DekTec ASI output. Hardware-unverified.
set -eu

: "${PORTSDOWN_CONFIG:?Set PORTSDOWN_CONFIG to an absolute config path}"
: "${PORTSDOWN_ASI_TS_FILE:?Set PORTSDOWN_ASI_TS_FILE to an absolute MPEG-TS file}"
[ "${PORTSDOWN_BOARD:-}" = dektec_asi ] || { echo 'DekTec ASI board not selected' >&2; exit 1; }
[ "${PORTSDOWN_CONFIG#/}" != "$PORTSDOWN_CONFIG" ] && [ -r "$PORTSDOWN_CONFIG" ] || { echo 'Invalid config path' >&2; exit 1; }
[ "${PORTSDOWN_ASI_TS_FILE#/}" != "$PORTSDOWN_ASI_TS_FILE" ] && [ -r "$PORTSDOWN_ASI_TS_FILE" ] || { echo 'Invalid TS file' >&2; exit 1; }

config_value() {
    awk -F= -v key="$1" '$1 == key { print substr($0, index($0, "=") + 1); exit }' "$PORTSDOWN_CONFIG"
}
[ "$(config_value modeoutput)" = DEKTEC_ASI ] && [ "$(config_value modulation)" = ASI ] || {
    echo 'Config does not select DekTec ASI' >&2; exit 1;
}
device=$(config_value asi_device)
channel=$(config_value asi_channel)
bitrate=$(config_value asi_bitrate)
case "$device:$channel:$bitrate" in *[!0-9:]*|'') echo 'Invalid ASI numeric setting' >&2; exit 1;; esac
[ -n "$device" ] && [ -n "$channel" ] && [ -n "$bitrate" ] || exit 1
[ "$device" -le 15 ] && [ "$channel" -le 15 ] &&
[ "$bitrate" -ge 100000 ] && [ "$bitrate" -le 214000000 ] || {
    echo 'ASI setting outside supported range' >&2; exit 1;
}
command -v tsp >/dev/null 2>&1 || { echo 'TSDuck tsp is not installed' >&2; exit 1; }
command -v ffprobe >/dev/null 2>&1 || { echo 'ffprobe is not installed' >&2; exit 1; }
format=$(ffprobe -v error -show_entries format=format_name \
    -of default=noprint_wrappers=1:nokey=1 "$PORTSDOWN_ASI_TS_FILE") || {
    echo 'Cannot probe TS file' >&2; exit 1;
}
case ",$format," in *,mpegts,*) ;; *) echo 'Input is not MPEG-TS' >&2; exit 1;; esac
# Exact device/channel and plugin options must be confirmed against the target
# host's tsdektec and tsp -O dektec --help before hardware use.
exec tsp -I file "$PORTSDOWN_ASI_TS_FILE" -O dektec \
    --device "$device" --channel "$channel" --io-standard ASI --bitrate "$bitrate"
