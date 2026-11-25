#!/usr/bin/env bash
# User-local headless install. No RF/ASI, driver changes, or service autostart.
set -Eeuo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
prefix=${DIABLO_PREFIX:-"$HOME/.local/share/diablo-datv-studio"}
jobs=${DIABLO_BUILD_JOBS:-2}
packages=1
usage() {
    echo 'Usage: bash scripts/install-diablo.sh [--prefix ABSOLUTE_PATH] [--jobs N] [--skip-system-packages]'
}
while (($#)); do
    case $1 in
        --prefix) prefix=${2:?Missing prefix}; shift 2;;
        --jobs) jobs=${2:?Missing jobs}; shift 2;;
        --skip-system-packages) packages=0; shift;;
        --help|-h) usage; exit 0;;
        *) usage >&2; exit 2;;
    esac
done
[[ $(id -u) != 0 ]] || { echo 'Run as your normal user; sudo is used only for packages.' >&2; exit 2; }
[[ $prefix == /* && $prefix != / && $prefix != *$'\n'* ]] || { echo 'Prefix must be an absolute directory.' >&2; exit 2; }
[[ $jobs =~ ^[1-9][0-9]?$ ]] || { echo 'Jobs must be 1-99.' >&2; exit 2; }
if ((packages)); then
    . /etc/os-release
    case " ${ID:-} ${ID_LIKE:-} " in
        *debian*|*ubuntu*|*linuxmint*) ;;
        *) echo 'Install build dependencies manually, then use --skip-system-packages.' >&2; exit 2;;
    esac
    sudo apt-get update
    sudo apt-get install -y build-essential cmake pkg-config libjson-c-dev git ca-certificates ffmpeg
fi
for tool in git cmake make cc pkg-config ffmpeg flock; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }
done
pkg-config --exists json-c || { echo 'Missing libjson-c-dev / json-c.pc.' >&2; exit 2; }
ffmpeg -hide_banner -protocols 2>/dev/null | grep -qw srt || { echo 'FFmpeg must include SRT.' >&2; exit 2; }
mkdir -p "$prefix" "$prefix/src" "$prefix/build" "$prefix/bin" "$prefix/logs" "$prefix/state"
chmod 700 "$prefix/state"
exec 9>"$prefix/install.lock"
flock -n 9 || { echo 'Another Diablo installer is running.' >&2; exit 2; }
exec > >(tee "$prefix/logs/install.log") 2>&1

fetch_pin() {
    local name=$1 url=$2 revision=$3 checkout="$prefix/src/$1"
    if [[ ! -d $checkout/.git ]]; then
        git init "$checkout"
        git -C "$checkout" remote add origin "$url"
    fi
    [[ -z $(git -C "$checkout" status --porcelain) ]] || { echo "Modified dependency: $checkout" >&2; exit 2; }
    if ! git -C "$checkout" cat-file -e "$revision^{commit}" 2>/dev/null; then
        git -C "$checkout" fetch --depth 1 "$url" "$revision"
    fi
    git -C "$checkout" checkout --detach "$revision"
}
fetch_pin libubox https://git.openwrt.org/project/libubox.git a396f38a8568a1d670c240465cd8d24fdfdf6463
fetch_pin ucode https://github.com/jow-/ucode.git a2c42eac6369a0bba0315007c7dc7b7130275340
cmake -S "$prefix/src/libubox" -B "$prefix/build/libubox" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix/runtime" \
    -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_LUA=OFF -DBUILD_EXAMPLES=OFF
cmake --build "$prefix/build/libubox" --parallel "$jobs"
cmake --install "$prefix/build/libubox"
cmake -S "$prefix/src/ucode" -B "$prefix/build/ucode" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix/runtime" \
    -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_PREFIX_PATH="$prefix/runtime" \
    -DCMAKE_INSTALL_RPATH="$prefix/runtime/lib" -DULOOP_SUPPORT=ON -DSOCKET_SUPPORT=ON
cmake --build "$prefix/build/ucode" --parallel "$jobs"
cmake --install "$prefix/build/ucode"
make -C "$repo/control" -j "$jobs"
LD_LIBRARY_PATH="$prefix/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$prefix/runtime/bin/ucode" -L "$prefix/runtime/lib/ucode" \
    -e 'import * as fs from "fs"; import * as socket from "socket"; import * as uloop from "uloop"; print("Runtime modules OK\n");'

if [[ ! -e $prefix/state/portsdown_config.txt ]]; then
    install -m 600 "$repo/control/diablo-config.example" "$prefix/state/portsdown_config.txt"
fi
# Preserve operator configuration and private camera credentials on reruns.
if [[ ! -e $prefix/diablo.env ]]; then
    (
        umask 077
        {
            printf 'export PORTSDOWN_DIR=%q\n' "$repo"
            printf 'export DIABLO_RUNTIME=%q\n' "$prefix/runtime"
            printf 'export PORTSDOWN_CONFIG=%q\n' "$prefix/state/portsdown_config.txt"
            printf 'export PORTSDOWN_PRESETS_PATH=%q\n' "$prefix/state/presets.json"
            printf 'export PORTSDOWN_IPCAM_CONFIG=%q\n' "$prefix/state/ip-cameras.conf"
            printf 'export PORTSDOWN_RUN_DIR=%q\n' "${XDG_RUNTIME_DIR:-/tmp}/diablo-$(id -u)"
            cat <<'ENV'
export PORTSDOWN_BOARD=none
export PORTSDOWN_TX_EXEC=
export PORTSDOWN_RX_EXEC=
export PORTSDOWN_SAFE_OFF_EXEC=
export PORTSDOWN_HTTP_PORT=8080
export PORTSDOWN_MJPEG_PORT=8082
export PORTSDOWN_SRT_PORT_BASE=9101
export PORTSDOWN_SRT_TS_PORT_BASE=12001
export PORTSDOWN_SRT_MJPEG_PORT_BASE=8083
export PORTSDOWN_SOURCE_MJPEG_PORT_BASE=8088
export PORTSDOWN_PEER_ROLE=STANDALONE
export PORTSDOWN_SRT_EXEC="$PORTSDOWN_DIR/control/srt-slot.sh"
export PORTSDOWN_SOURCE_PREVIEW_EXEC="$PORTSDOWN_DIR/control/source-preview.sh"
export PORTSDOWN_SOURCE_TS_EXEC="$PORTSDOWN_DIR/control/source-ts.sh"
# Optional: export PORTSDOWN_SRT_ADVERTISE_HOST=192.0.2.10
# Optional: export PORTSDOWN_SOURCE_TS_URL='udp://127.0.0.1:12010?pkt_size=1316'
ENV
        } > "$prefix/diablo.env"
    )
else
    echo "Preserved $prefix/diablo.env (check PORTSDOWN_DIR if the checkout moved)."
fi
{
    printf '#!/usr/bin/env bash\nexec %q %q\n' "$repo/scripts/run-diablo.sh" "$prefix/diablo.env"
} > "$prefix/bin/diablo-studio"
chmod 755 "$prefix/bin/diablo-studio"
printf '\nInstalled. Start manually: %q\n' "$prefix/bin/diablo-studio"
echo 'Open http://127.0.0.1:8080/ or use an SSH tunnel. Stop with Ctrl+C.'
echo 'Enter your CALLSIGN and service name in the GUI before generating TS.'
echo 'No service enabled, driver installed, ASI playout started, or RF keyed.'
