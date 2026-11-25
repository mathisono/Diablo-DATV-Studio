#!/usr/bin/env bash
# Build only. Never opens DATV-Express USB or enables transmission.
set -Eeuo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
deps=${DIABLO_DEPS_DIR:-"$HOME/.cache/diablo-datv-studio"}
pin=eff68b37047196e5bc732b08fa7f73c2bf94107e
jobs=${DIABLO_BUILD_JOBS:-2}
[[ $jobs =~ ^[1-9][0-9]?$ ]] || { echo 'Build jobs must be 1-99.' >&2; exit 2; }
pkg-config --exists libusb-1.0 fftw3 || { echo 'Install build-essential pkg-config libusb-1.0-0-dev libfftw3-dev first.' >&2; exit 2; }
mkdir -p "$deps"
exec 9>"$deps/express-build.lock"
flock -n 9 || { echo 'Express S2 build already running.' >&2; exit 2; }
lib="$deps/libdvbmod-$pin"
if [[ ! -d $lib/.git ]]; then
    git init "$lib"
    git -C "$lib" fetch --depth 1 https://github.com/F5OEO/libdvbmod.git "$pin"
    git -C "$lib" checkout --detach FETCH_HEAD
fi
[[ $(git -C "$lib" rev-parse HEAD) == "$pin" ]] || { echo 'Unexpected libdvbmod revision.' >&2; exit 2; }
[[ -z $(git -C "$lib" diff HEAD --) ]] || { echo 'Modified libdvbmod sources; refusing to overwrite.' >&2; exit 2; }
make -C "$lib/libdvbmod" -j "$jobs"
make -C "$repo/src/express_s2" -j "$jobs" LIBDVBMOD_DIR="$lib/libdvbmod"
echo "Built $repo/src/express_s2/express_s2 (offline/experimental; no USB/RF test)."
