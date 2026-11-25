#!/bin/sh
# Finite MPEG-TS file playout; bounded DTA-2145 driver/card test recorded in docs.
set -eu

. "$(dirname "$0")/dektec-asi-common.sh"
: "${PORTSDOWN_ASI_TS_FILE:?Set PORTSDOWN_ASI_TS_FILE to an absolute MPEG-TS file}"
[ "${PORTSDOWN_ASI_TS_FILE#/}" != "$PORTSDOWN_ASI_TS_FILE" ] && [ -r "$PORTSDOWN_ASI_TS_FILE" ] || { echo 'Invalid TS file' >&2; exit 1; }
command -v ffprobe >/dev/null 2>&1 || { echo 'ffprobe is not installed' >&2; exit 1; }
format=$(ffprobe -v error -show_entries format=format_name \
    -of default=noprint_wrappers=1:nokey=1 "$PORTSDOWN_ASI_TS_FILE") || {
    echo 'Cannot probe TS file' >&2; exit 1;
}
case ",$format," in *,mpegts,*) ;; *) echo 'Input is not MPEG-TS' >&2; exit 1;; esac
# TSDuck's svrename updates the SDT service descriptors in flight, without
# decoding or FFmpeg-remuxing the video/audio. This is best-effort metadata,
# not an acceptance gate: missing config, plugin, or program enumeration leaves
# the original TS playable. Never prevent playout for a name/provider mismatch.
set -- -I file "$PORTSDOWN_ASI_TS_FILE"
# shellcheck source=../scripts/ts_service_metadata.sh
. "$(dirname "$0")/../scripts/ts_service_metadata.sh"
if ts_service_metadata_load "$PORTSDOWN_CONFIG" &&
   tsp -P svrename --help >/dev/null 2>&1; then
    programs=$(ffprobe -v error -show_entries program=program_id \
        -of default=noprint_wrappers=1:nokey=1 "$PORTSDOWN_ASI_TS_FILE") || programs=
    if [ -n "$programs" ]; then
        for service_id in $programs; do
            case "$service_id" in *[!0-9]*|'') continue;; esac
            set -- "$@" -P svrename "$service_id" \
                --provider "$TS_SERVICE_PROVIDER" --name "$TS_SERVICE_NAME"
        done
        echo 'Applying configured TS service metadata during ASI playout' >&2
    else
        echo 'Cannot enumerate TS programs; playing original TS metadata' >&2
    fi
else
    echo 'TS service metadata unavailable; playing original TS metadata' >&2
fi
asi_detach=--wait-detach
asi_output "$@"
