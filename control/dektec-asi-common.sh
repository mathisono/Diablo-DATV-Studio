#!/bin/sh
# Shared validation and per-account, per-channel ownership for ASI launchers.
: "${PORTSDOWN_CONFIG:?Set PORTSDOWN_CONFIG to an absolute config path}"
[ "${PORTSDOWN_BOARD:-}" = dektec_asi ] || { echo 'DekTec ASI board not selected' >&2; exit 1; }
[ "${PORTSDOWN_CONFIG#/}" != "$PORTSDOWN_CONFIG" ] && [ -r "$PORTSDOWN_CONFIG" ] || { echo 'Invalid config path' >&2; exit 1; }

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

command -v flock >/dev/null 2>&1 || { echo 'flock is not installed' >&2; exit 1; }
asi_lock_dir=${PORTSDOWN_ASI_LOCK_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/diablo-datv-studio/locks}
umask 077
mkdir -p "$asi_lock_dir"
exec 9>"$asi_lock_dir/dektec-$device-$channel.lock"
flock -n 9 || { echo 'ASI output channel already owned by another Diablo process' >&2; exit 1; }

# At least 200 ms of TS capacity (rounded to 64 KiB), minimum 256 KiB.
# This leaves room for the 100 ms preload even at higher configured ASI rates.
asi_fifo=$(( (bitrate / 40 + 65535) / 65536 * 65536 ))
[ "$asi_fifo" -ge 262144 ] || asi_fifo=262144

asi_output() {
    # A TSDuck send batch must fit the reduced hardware FIFO. Without the
    # 128-packet cap, DTA-2145 playout stalled in the 2026-11-25 hardware test.
    # Live input uses instant detach to discard queued tail on disconnect;
    # finite file input drains normally. Supervisor/timeout bounds shutdown.
    exec tsp -v --bitrate "$bitrate" --buffer-size-mb 1 \
        --initial-input-packets 128 --max-output-packets 128 "$@" \
        -O dektec --device "$device" --channel "$channel" --io-standard ASI \
        --bitrate "$bitrate" --fifo-size "$asi_fifo" --preload-fifo \
        --preload-fifo-delay 100 "$asi_detach"
}
