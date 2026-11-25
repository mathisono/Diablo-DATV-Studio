#!/usr/bin/env bash
# Local, finite first-video check. Requires Diablo SRT input 1 already listening.
# No capture device, config changes, output TS launch, ASI or RF control.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
    echo 'Usage: bash scripts/test-srt-input.sh [seconds]'
    echo 'Send moving 480p25 test video and a tone to local SRT input 1 for 30 seconds.'
    echo 'Run on the Diablo computer, with input 1 enabled and no other caller.'
    echo 'Optional PORTSDOWN_TEST_SRT_PORT overrides the default UDP port 9101.'
    exit 0
fi
seconds=${1:-30}
port=${PORTSDOWN_TEST_SRT_PORT:-9101}
[[ $# -le 1 && $seconds =~ ^[0-9]{1,3}$ ]] && ((10#$seconds >= 1 && 10#$seconds <= 300)) || {
    echo 'Duration must be 1–300 seconds.' >&2; exit 2;
}
[[ $port =~ ^[0-9]{4,5}$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || {
    echo 'SRT port must be 1024–65535.' >&2; exit 2;
}
command -v ffmpeg >/dev/null || { echo 'FFmpeg is missing; complete first-start setup first.' >&2; exit 1; }
echo "Sending a test picture to this computer's SRT input (port $port) for $seconds seconds."
echo 'Watch the Diablo preview. It should return to NO SRT INPUT 1 after this finishes.'
if ! timeout --signal=TERM --kill-after=2s "$((10#$seconds + 10))s" \
    ffmpeg -hide_banner -nostdin -loglevel warning \
    -re -f lavfi -i 'testsrc2=size=640x480:rate=25' \
    -f lavfi -i 'sine=frequency=1000:sample_rate=48000' \
    -t "$((10#$seconds))" -map 0:v:0 -map 1:a:0 \
    -c:v libx264 -threads 2 -preset ultrafast -tune zerolatency \
    -pix_fmt yuv420p -b:v 600k -maxrate 600k -bufsize 600k -g 25 -bf 0 \
    -c:a aac -b:a 48k -ar 48000 -ac 2 -f mpegts \
    "srt://127.0.0.1:$((10#$port))?mode=caller&latency=200000&pkt_size=1316"; then
    echo 'Test sender stopped with an error. Is Diablo running and SRT input 1 enabled?' >&2
    echo 'Also check that no OBS/camera sender is already using that input.' >&2
    exit 1
fi
echo 'Test sender finished. Check that the preview returns to its waiting card.'
echo 'This tests local SRT video only, not LAN delivery, ASI or RF.'
