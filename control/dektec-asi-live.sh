#!/bin/sh
# Already-shaped, single-service live MPEG-TS -> ASI; no encoding or RF control.
# Input PCR/muxrate must match asi_bitrate. This is not a valid-video RF gate.
set -eu
. "$(dirname "$0")/dektec-asi-common.sh"
[ "$(config_value source_layout)" = DIRECT ] || { echo 'Live ASI requires Direct IP/SRT input' >&2; exit 1; }
input=$(config_value modeinput)
bind=${PORTSDOWN_ASI_BIND:-127.0.0.1}
case "$bind" in ''|*[!0-9.]* ) echo 'ASI bind must be an IPv4 address' >&2; exit 1;; esac
case "$input" in
    IPTSIN)
        transport=$(config_value iptransport)
        port=$(config_value udpinport)
        ;;
    SRT)
        slot=$(config_value srt_source_slot)
        case "$slot" in [1-5]) ;; *) echo 'Invalid SRT slot' >&2; exit 1;; esac
        base=${PORTSDOWN_SRT_TS_PORT_BASE:-12001}
        case "$base" in ''|*[!0-9]*) exit 1;; esac
        [ "$base" -ge 1024 ] && [ "$base" -le 65531 ] || exit 1
        port=$((base + slot - 1)); transport=udp; bind=127.0.0.1
        ;;
    *) echo 'Select IPTS input or an already-running SRT encoder slot' >&2; exit 1;;
esac
case "$port" in ''|*[!0-9]*) echo 'Invalid input port' >&2; exit 1;; esac
[ "$port" -ge 1024 ] && [ "$port" -le 65535 ] || exit 1
case "$transport" in
    srt) set -- -I srt --listener "$bind:$port" --latency 200 --peer-idle-timeout 1500;;
    udp) set -- -I ip "$port" --local-address "$bind" --receive-timeout 1500;;
    *) echo 'IPTS transport must be srt or udp' >&2; exit 1;;
esac
. "$(dirname "$0")/../scripts/ts_service_metadata.sh"
if ts_service_metadata_load "$PORTSDOWN_CONFIG" && tsp -P svrename --help >/dev/null 2>&1; then
    set -- "$@" -P svrename --provider "$TS_SERVICE_PROVIDER" --name "$TS_SERVICE_NAME"
else
    echo 'Configured metadata unavailable; preserving input service labels' >&2
fi
if [ -n "${PORTSDOWN_ASI_DURATION:-}" ]; then
    case "$PORTSDOWN_ASI_DURATION" in *[!0-9]*) exit 1;; esac
    [ "$PORTSDOWN_ASI_DURATION" -ge 1 ] && [ "$PORTSDOWN_ASI_DURATION" -le 3600 ] || exit 1
    set -- "$@" -P until --seconds "$PORTSDOWN_ASI_DURATION"
fi
# Optional bounded-test packet tap: this is before hardware, not an ASI receiver.
if [ -n "${PORTSDOWN_ASI_AUDIT_TS:-}" ]; then
    [ "${PORTSDOWN_ASI_AUDIT_TS#/}" != "$PORTSDOWN_ASI_AUDIT_TS" ] || exit 1
    set -- "$@" -P file "$PORTSDOWN_ASI_AUDIT_TS"
fi
# No automatic retry or saved recording fallback after live input loss.
asi_detach=--instant-detach
asi_output "$@"
