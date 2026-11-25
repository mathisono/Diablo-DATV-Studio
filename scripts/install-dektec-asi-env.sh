#!/usr/bin/env bash
# Reproducible x86-64 DTA-2145 driver, TSDuck and FFmpeg environment.
# Never starts ASI output, enables RF, or installs a boot-time playout service.
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_dir=${DEKTEC_ASI_HOME:-"$HOME/dektec-asi"}
tsduck_version=3.45-4798.ubuntu24
tsduck_archive="$project_dir/sdk/tsduck_${tsduck_version}_amd64.deb"
tsduck_url="https://github.com/tsduck/tsduck/releases/download/v3.45-4798/tsduck_${tsduck_version}_amd64.deb"
tsduck_sha256=0023689f76e75b64e45253771208bcf8ca95b91fbfd0900da097c729f3c39fde

if [ "$(id -u)" -eq 0 ]; then
    echo 'Run as a normal user with sudo access, not as root.' >&2
    exit 2
fi
if [ "$(uname -m)" != x86_64 ]; then
    echo 'This installer targets the x86-64 DTA-2145 test host.' >&2
    exit 2
fi
for tool in curl sha256sum dpkg-query sudo apt-get; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Missing required command: $tool" >&2
        exit 2
    fi
done

mkdir -p "$project_dir/sdk" "$project_dir/logs" "$project_dir/tests"
bash "$script_dir/install-dektec-dta.sh"
sudo apt-get install -y ffmpeg git

if [ ! -f "$tsduck_archive" ]; then
    curl --fail --location --show-error --retry 3 \
        --output "$tsduck_archive.tmp" "$tsduck_url"
    mv "$tsduck_archive.tmp" "$tsduck_archive"
fi
printf '%s  %s\n' "$tsduck_sha256" "$tsduck_archive" |
    sha256sum --check --status || {
        echo "TSDuck package failed the recorded SHA-256 check: $tsduck_archive" >&2
        exit 2
    }
installed_version=$(dpkg-query -W -f='${Version}' tsduck 2>/dev/null || true)
if [ "$installed_version" != "$tsduck_version" ]; then
    sudo apt-get install -y "$tsduck_archive"
else
    echo "TSDuck $tsduck_version is already installed."
fi

version_info=$(tsversion --version=all 2>&1)
printf '%s\n' "$version_info" | tee "$project_dir/logs/tsduck-version.log"
if ! grep -Fq 'Dektec: DTAPI:' <<< "$version_info"; then
    echo 'TSDuck was installed without DekTec support.' >&2
    exit 3
fi
if id -nG | grep -qw dektec; then
    tsdektec -a -v 2>&1 | tee "$project_dir/logs/dektec-devices.log"
else
    echo 'Log out and back in to activate dektec group before non-root card enumeration.'
fi

# Grant access to the Intel render node, if one is present. A fresh login is
# needed before the new supplementary groups are effective in this process.
if [ -e /dev/dri/renderD128 ]; then
    gpu_groups=()
    for group in render video; do
        if getent group "$group" >/dev/null && ! id -nG "$(id -un)" | grep -qw "$group"; then
            gpu_groups+=("$group")
        fi
    done
    if [ "${#gpu_groups[@]}" -gt 0 ]; then
        gpu_group_list=$(IFS=,; echo "${gpu_groups[*]}")
        sudo usermod -aG "$gpu_group_list" "$(id -un)"
        echo "Added $(id -un) to $gpu_group_list; log in again before GPU testing."
    fi
fi

# QSV is optional. Jasper Lake's driver exposes CQP but rejects the usual
# bitrate/ICQ controls; probe a real finite CQP encode, not just the encoder
# listing. CQP does not bound instantaneous bitrate, so keep libx264 for
# fixed-rate transport streams unless the chosen content/QP is validated.
if command -v ffmpeg >/dev/null 2>&1 && [ -r /dev/dri/renderD128 ]; then
    if ffmpeg -hide_banner -loglevel warning \
        -f lavfi -i 'testsrc2=size=1280x720:rate=24' -t 2 \
        -vf format=nv12 -c:v h264_qsv -low_power 1 \
        -qscale:v 30 -b:v 0 \
        -y "$project_dir/tests/qsv-h264-test.mp4" \
        >"$project_dir/logs/qsv-h264-test.log" 2>&1; then
        echo 'Finite QSV H.264 CQP encode passed; fixed-rate TS output is not implied.'
    else
        echo 'QSV encode did not pass; see logs/qsv-h264-test.log. Using libx264 fallback.'
        rm -f "$project_dir/tests/qsv-h264-test.mp4"
    fi
elif [ -e /dev/dri/renderD128 ]; then
    echo 'Render device exists but is not readable in this login; log in again and rerun.'
fi
ffmpeg -hide_banner -loglevel error \
    -f lavfi -i 'testsrc2=size=640x480:rate=24' -t 1 \
    -c:v libx264 -preset veryfast -pix_fmt yuv420p \
    -y "$project_dir/tests/libx264-fallback-test.mp4"
echo 'Finite software H.264 encode passed. ASI output was not started.'
