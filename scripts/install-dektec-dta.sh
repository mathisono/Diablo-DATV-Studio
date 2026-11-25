#!/usr/bin/env bash
# Install the legacy DekTec Dta DKMS driver for a DTA-2145 on x86-64 Linux.
# This script never starts ASI playout or controls an external modulator.
set -Eeuo pipefail

sdk_version=2026.09.0
sdk_sha256=f7bdf97421b39047efa379cfffbd208114bf0f3cb37c3565d709e46f3157fdf3
sdk_url="https://www.dektec.com/products/SDK/DTAPI/Downloads/LinuxSDK_v${sdk_version}.tar.gz"
project_dir=${DEKTEC_ASI_HOME:-"$HOME/dektec-asi"}
archive="$project_dir/sdk/LinuxSDK_v${sdk_version}.tar.gz"
sdk_dir="$project_dir/sdk/LinuxSDK"
kernel=$(uname -r)

status() {
    printf 'Host: %s; kernel: %s; architecture: %s\n' "$(hostname)" "$kernel" "$(uname -m)"
    lspci -nnk -d 1a0e:0861 || true
    dkms status 2>/dev/null | grep -F dektec_dta || true
    modinfo -F signer Dta 2>/dev/null || true
    if command -v mokutil >/dev/null 2>&1; then
        sb_state=$(mokutil --sb-state 2>/dev/null || true)
        printf '%s\n' "$sb_state"
        if [ "$sb_state" = 'SecureBoot enabled' ] &&
           [ -r /var/lib/shim-signed/mok/MOK.der ]; then
            mokutil --test-key /var/lib/shim-signed/mok/MOK.der || true
        fi
    fi
    lsmod | grep -E '^Dta([[:space:]]|Nw[[:space:]])' || true
    ls -l /dev/dta* /dev/Dta* 2>/dev/null || true
}

if [ "${1:-}" = --status ]; then
    status
    exit 0
fi
if [ "$#" -ne 0 ]; then
    echo 'Usage: install-dektec-dta.sh [--status]' >&2
    exit 2
fi
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run as a normal user with sudo access, not as root.' >&2
    exit 2
fi
if [ "$(uname -m)" != x86_64 ]; then
    echo 'This DTA-2145 installation is for an x86-64 PCIe host.' >&2
    exit 2
fi
for command_name in lspci curl tar sha256sum sudo apt-get dkms; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "Missing required command: $command_name" >&2
        exit 2
    }
done
if ! lspci -n -d 1a0e:0861 | grep -q .; then
    echo 'DTA-2145 (PCI ID 1a0e:0861) is not enumerated; refusing driver installation.' >&2
    exit 2
fi

mkdir -p "$project_dir/sdk" "$project_dir/logs"
echo "Installing DekTec Dta for $kernel; no ASI output will be started."
sudo apt-get install -y dkms build-essential libelf-dev "linux-headers-$kernel"
[ -d "/lib/modules/$kernel/build/kernel" ] || {
    echo "Matching kernel headers are missing for $kernel" >&2
    exit 2
}

if [ ! -f "$archive" ]; then
    curl --fail --location --show-error --retry 3 --output "$archive.tmp" "$sdk_url"
    mv "$archive.tmp" "$archive"
fi
printf '%s  %s\n' "$sdk_sha256" "$archive" | sha256sum --check --status || {
    echo "Official SDK archive failed the recorded SHA-256 check: $archive" >&2
    exit 2
}
if [ ! -f "$sdk_dir/Version" ] || [ "$(head -n 1 "$sdk_dir/Version")" != "$sdk_version" ]; then
    tar -xzf "$archive" -C "$project_dir/sdk"
fi

if ! dkms status | grep -Fq "dektec_dta/$sdk_version, $kernel, x86_64: installed"; then
    echo 'Building/installing the vendor Dta and DtaNw DKMS modules.'
    sudo "$sdk_dir/Drivers/Install_Dta" 2>&1 | tee "$project_dir/logs/dta-dkms-install.log"
else
    echo 'Matching DekTec Dta DKMS modules are already installed.'
fi

if ! sudo modprobe Dta; then
    echo 'Dta is installed but cannot load. Check Secure Boot/MOK enrollment.' >&2
    echo 'If Secure Boot is enabled and the signing key is not enrolled, disable Secure Boot in local UEFI setup (or enroll the MOK), reboot, then rerun --status and sudo modprobe Dta.' >&2
    status
    exit 3
fi

if ! getent group dektec >/dev/null; then
    sudo groupadd --system dektec
fi
if ! id -nG "$(id -un)" | grep -qw dektec; then
    sudo usermod -aG dektec "$(id -un)"
    echo "Group membership for $(id -un) takes effect at next login."
fi
# The vendor's 51-dta.rules uses MODE=0666. Override it for this host without
# changing the vendor rule, so only the dektec group can access the device.
printf '%s\n' 'KERNEL=="Dta[0-9]*", GROUP="dektec", MODE="0660"' |
    sudo tee /etc/udev/rules.d/99-dektec-asi.rules >/dev/null
sudo udevadm control --reload-rules
for node in /dev/Dta[0-9]*; do
    [ -e "$node" ] || continue
    sudo chgrp dektec "$node"
    sudo chmod 0660 "$node"
done

echo 'Dta loaded. Verify card binding and device access before any ASI playout.'
status
