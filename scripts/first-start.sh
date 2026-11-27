#!/usr/bin/env bash
# Guided/bootstrap first start; no hardware TX, firewall changes or boot service.
set -Eeuo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
prefix=${DIABLO_PREFIX:-"$HOME/.local/share/diablo-datv-studio"}
source_selected=0
interactive=1 configure_only=0 packages=1 start=0 verify=1 ssh_enable=0 pi_packages=0
call= service= source= slot= device= input_format= advertise= groups= http_port= audio_device= picam_index= ipts_port= ipts_scope=
password_file= local_only=0
enable_srt=keep
usage() {
cat <<'HELP'
Usage: bash scripts/first-start.sh [options]
Default: install, prompt for initial settings, verify GUI, offer foreground start.
  --prefix PATH               Existing/new absolute user-local prefix
  --non-interactive           No prompts; supply identity or retain saved identity
  --configure-only            Use an already installed native runtime
  --skip-system-packages      Pass through to installer
  --callsign CALL --service-name TEXT
  --source SRT|HDMI|CAMH264|IPTSIN|IPCAM1|IPCAM2
  --srt-slot 1..5             Selected SRT input (default 1)
  --enable-srt | --disable-srt  Enable/disable selected listener on future launches
  --http-port PORT            Loopback GUI port (default 8080)
  --advertise-ip IPv4         LAN IP displayed in SRT caller links
  --video-device /dev/videoN --input-format auto|mjpeg|yuyv422
  --audio-device ALSA        e.g. hw:1,0 (use none to disable)
  --picam-index 0..3 --ipts-port PORT --ipts-scope LOCAL|LAN
  --device-groups video,audio,render  Explicit selected group grants; sudo required
  --enable-ssh                Install openssh-server and enable/start ssh; no auth edits
  --pi-camera-packages        Install distro rpicam package on a detected Raspberry Pi
  --start                    Continue into foreground GUI after setup
  --password-file PATH        Mode-600 file for unattended web admin password setup
  --local-only                Pi-only browser on loopback; no LAN access or web password
  --no-verify                Skip bounded GUI startup/API/shutdown check
No RF/ASI/TS start, firewall edits, reboot, lingering or boot autostart.
HELP
}
while (($#)); do
    case $1 in
        --prefix) prefix=${2:?}; shift 2;;
        --non-interactive) interactive=0; shift;;
        --configure-only) configure_only=1; shift;;
        --skip-system-packages) packages=0; shift;;
        --callsign) call=${2:?}; shift 2;;
        --service-name) service=${2:?}; shift 2;;
        --source) source=${2:?}; source_selected=1; shift 2;;
        --srt-slot) slot=${2:?}; shift 2;;
        --video-device) device=${2:?}; shift 2;;
        --audio-device) audio_device=${2:?}; shift 2;;
        --picam-index) picam_index=${2:?}; shift 2;;
        --ipts-port) ipts_port=${2:?}; shift 2;;
        --ipts-scope) ipts_scope=${2:?}; shift 2;;
        --input-format) input_format=${2:?}; shift 2;;
        --http-port) http_port=${2:?}; shift 2;;
        --advertise-ip) advertise=${2:?}; shift 2;;
        --device-groups) groups=${2:?}; shift 2;;
        --enable-srt) enable_srt=yes; shift;;
        --disable-srt) enable_srt=no; shift;;
        --enable-ssh) ssh_enable=1; shift;;
        --pi-camera-packages) pi_packages=1; shift;;
        --start) start=1; shift;;
        --password-file) password_file=${2:?}; shift 2;;
        --local-only) local_only=1; shift;;
        --no-verify) verify=0; shift;;
        --help|-h) usage; exit 0;;
        *) usage >&2; exit 2;;
    esac
done
fail() { echo "$*" >&2; exit 2; }
[[ $(id -u) != 0 ]] || fail 'Run as your normal user, not root.'
[[ $prefix == /* && $prefix != / && $prefix != *$'\n'* ]] || fail 'Prefix must be absolute.'
(( !interactive )) || [[ -t 0 ]] || fail 'Use --non-interactive when stdin is not a terminal.'
umask 077
if (( !configure_only )); then
    args=(--prefix "$prefix")
    ((packages)) || args+=(--skip-system-packages)
    bash "$repo/scripts/install-diablo.sh" "${args[@]}"
fi
[[ -f $prefix/diablo.env && -O $prefix/diablo.env ]] || fail 'Install first: missing owned diablo.env.'
source "$prefix/diablo.env"
: "${PORTSDOWN_RUN_DIR:?}" "${PORTSDOWN_CONFIG:?}" "${DIABLO_RUNTIME:?}"
[[ ${PORTSDOWN_DIR:-} == "$repo" ]] || fail 'Run first-start from the checkout saved in diablo.env.'
[[ ${PORTSDOWN_BOARD:-none} == none && -z ${PORTSDOWN_TX_EXEC:-} && -z ${PORTSDOWN_RX_EXEC:-} && ${PORTSDOWN_PEER_ROLE:-STANDALONE} == STANDALONE ]] || fail 'First-start is for standalone, unarmed installations. Existing hardware/peer configuration left unchanged.'
mkdir -p "$PORTSDOWN_RUN_DIR"
[[ ! -L $PORTSDOWN_RUN_DIR && -O $PORTSDOWN_RUN_DIR ]] || fail 'Invalid runtime directory.'
exec 9>"$prefix/install.lock"
flock -n 9 || fail 'Another installer/setup is running.'
exec 8>"$PORTSDOWN_RUN_DIR/launcher.lock"
flock -n 8 || fail 'Stop the running Diablo launcher before setup.'
get_setting() { awk -v key="$1" 'index($0,key"=")==1 {value=substr($0,length(key)+2)} END {print value}' "$PORTSDOWN_CONFIG"; }
prompt() {
    local name=$1 label=$2 value
    read -r -p "$label [${!name}]: " value
    [[ -z $value ]] || printf -v "$name" '%s' "$value"
}
call=${call:-$(get_setting call)}
service=${service:-$(get_setting service_name)}
source=${source:-$(get_setting modeinput)}
source=${source:-SRT}
slot=${slot:-$(get_setting srt_source_slot)}; slot=${slot:-1}
device=${device:-$(get_setting expresshdmidevice)}; device=${device:-/dev/video0}
advertise=${advertise:-${PORTSDOWN_SRT_ADVERTISE_HOST:-}}
input_format=${input_format:-${PORTSDOWN_HDMI_INPUT_FORMAT:-}}
http_port=${http_port:-${PORTSDOWN_HTTP_PORT:-8080}}
audio_device=${audio_device:-$(get_setting expressaudiodevice)}
picam_index=${picam_index:-$(get_setting picam_index)}; picam_index=${picam_index:-0}
ipts_port=${ipts_port:-$(get_setting ipts_input_port)}; ipts_port=${ipts_port:-10000}
ipts_scope=${ipts_scope:-$(get_setting ipts_bind_scope)}; ipts_scope=${ipts_scope:-LOCAL}
if [[ -z $advertise ]]; then
    for candidate in $(hostname -I); do
        if [[ $candidate =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ && $candidate != 127.* ]]; then advertise=$candidate; break; fi
    done
fi
if ((interactive)); then
    while :; do
        prompt call 'Your amateur-radio callsign'
        call=${call^^}
        if [[ $call =~ ^[A-Z0-9/]{3,20}$ && $call =~ [0-9] && $call != N0CALL ]]; then break; fi
        echo 'Enter your own callsign; N0CALL is not accepted.' >&2
        call=
    done
    if [[ $source == SRT ]]; then
        echo 'First video input: SRT test picture. Choose a camera or other input in the web page later.'
        if [[ $enable_srt == keep && -z ${PORTSDOWN_START_SRT_SLOT:-} ]]; then enable_srt=yes; fi
    elif [[ $source == HDMI ]]; then
        command -v v4l2-ctl >/dev/null && v4l2-ctl --list-devices || true
        prompt device 'USB HDMI capture node'
        prompt input_format 'Input format: auto/mjpeg/yuyv422 (blank = keep/default)'
        command -v arecord >/dev/null && arecord -l || true
        prompt audio_device 'ALSA audio device, e.g. hw:1,0 (none = disabled)'
    elif [[ $source == CAMH264 ]]; then
        prompt picam_index 'Pi Camera index 0-3'
    elif [[ $source == IPTSIN ]]; then
        prompt ipts_port 'IPTS UDP listening port'
        prompt ipts_scope 'IPTS UDP bind: LOCAL or LAN'
    fi
    if ((!local_only)) && [[ -z ${PORTSDOWN_AUTH_FILE:-} ]]; then
        while :; do
            read -r -p 'Open Diablo from another computer on your network? yes/no [yes]: ' answer
            case ${answer,,} in
                ''|yes|y) break;;
                no|n) local_only=1; break;;
                *) echo 'Answer yes or no.' >&2;;
            esac
        done
    fi
fi
call=${call^^}
[[ -n $call && $call != N0CALL ]] || fail 'Enter your own callsign; N0CALL is not accepted.'
service=${service:-$call}
if ((local_only)) && [[ -n ${PORTSDOWN_AUTH_FILE:-} ]]; then
    fail 'This installation already has protected LAN access; --local-only cannot disable it.'
fi
case $source in SRT|HDMI|CAMH264|IPTSIN|IPCAM1|IPCAM2) ;; *) fail 'Unsupported initial source; configure advanced sources in the GUI.';; esac
[[ $slot =~ ^[1-5]$ ]] || fail 'SRT slot must be 1-5.'
case $enable_srt in yes|no|keep) ;; *) fail 'Listener choice must be yes, no or keep.';; esac
[[ $enable_srt != yes || $source == SRT ]] || fail '--enable-srt requires source SRT.'
[[ -z $input_format || $input_format == auto || $input_format == mjpeg || $input_format == yuyv422 ]] || fail 'Input format must be mjpeg or yuyv422.'
[[ $http_port =~ ^[0-9]{4,5}$ ]] && ((10#$http_port >= 1024 && 10#$http_port <= 65535)) || fail 'HTTP port must be 1024-65535.'
http_port=$((10#$http_port))
if [[ -n $advertise ]]; then
    [[ $advertise =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ && $advertise != 127.* && $advertise != 0.0.0.0 ]] || fail 'Use a non-loopback LAN IPv4 address.'
    IFS=. read -r -a octets <<< "$advertise"
    for octet in "${octets[@]}"; do ((10#$octet <= 255)) || fail 'Invalid IPv4 octet.'; done
fi
IFS=, read -r -a group_list <<< "$groups"
for group in "${group_list[@]}"; do
    case $group in video|audio|render) getent group "$group" >/dev/null || fail "Group not present: $group";; *) fail "Unsupported device group: $group";; esac
done
export LD_LIBRARY_PATH="$DIABLO_RUNTIME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export DIABLO_SETUP_call="$call" DIABLO_SETUP_service_name="$service" DIABLO_SETUP_modeinput="$source"
[[ $audio_device != none ]] || audio_device=
export DIABLO_SETUP_expressaudiodevice="$audio_device" DIABLO_SETUP_picam_index="$picam_index"
export DIABLO_SETUP_ipts_input_port="$ipts_port" DIABLO_SETUP_ipts_bind_scope="$ipts_scope"
export DIABLO_SETUP_RESET_LAYOUT="$source_selected"
export DIABLO_SETUP_srt_source_slot="$slot" DIABLO_SETUP_expresshdmidevice="$device"
ucode=("$DIABLO_RUNTIME/bin/ucode" -L "$DIABLO_RUNTIME/lib/ucode" -L "$repo/control/ucode")
DIABLO_SETUP_VALIDATE_ONLY=1 "${ucode[@]}" "$repo/control/ucode/first-start.uc"
# Only explicit options change host access; never relax device node permissions.
if ((ssh_enable || pi_packages)) || [[ -n $groups ]]; then
    . /etc/os-release
    case " ${ID:-} ${ID_LIKE:-} " in *debian*|*ubuntu*|*linuxmint*) ;; *) fail 'Host setup options require a Debian-family OS.';; esac
fi
if ((pi_packages)); then
    [[ -r /proc/device-tree/model ]] && grep -aq 'Raspberry Pi' /proc/device-tree/model || fail 'Pi camera package option requires a Raspberry Pi.'
    sudo apt-get update
    camera_package=
    for package in rpicam-apps-lite rpicam-apps; do
        candidate=$(apt-cache policy "$package" | awk '/Candidate:/ {print $2}')
        if [[ -n $candidate && $candidate != '(none)' ]]; then camera_package=$package; break; fi
    done
    [[ -n $camera_package ]] || fail 'No distro rpicam package available; repositories unchanged.'
    sudo apt-get install -y "$camera_package"
fi
if ((ssh_enable)); then
    sudo apt-get update
    sudo apt-get install -y openssh-server
    sudo systemctl enable --now ssh
fi
if [[ -n $groups ]]; then
    sudo usermod -aG "$groups" "$(id -un)"
    echo 'Device groups updated. Log out and back in before testing capture; this shell retains old groups.'
fi
backup="$prefix/backups/first-start-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$backup"
cp -p "$prefix/diablo.env" "$backup/diablo.env"
cp -p "$PORTSDOWN_CONFIG" "$backup/portsdown_config.txt"
"${ucode[@]}" "$repo/control/ucode/first-start.uc"
# Replace only the managed first-start block; keep other settings and credentials.
# config-store performs fsync + atomic rename, with private backup above.
{
    awk '/^# BEGIN DIABLO FIRST START$/ {skip=1; next} /^# END DIABLO FIRST START$/ {skip=0; next} !skip' "$prefix/diablo.env"
    printf '# BEGIN DIABLO FIRST START\n'
    printf 'export PORTSDOWN_HTTP_PORT=%q\n' "$http_port"
    [[ -z $advertise ]] || printf 'export PORTSDOWN_SRT_ADVERTISE_HOST=%q\n' "$advertise"
    [[ -z $input_format ]] || printf 'export PORTSDOWN_HDMI_INPUT_FORMAT=%q\n' "$input_format"
    case $enable_srt in
        yes) printf 'export PORTSDOWN_START_SRT_SLOT=%q\n' "$slot";;
        no) printf 'export PORTSDOWN_START_SRT_SLOT=0\n';;
        keep) printf 'export PORTSDOWN_START_SRT_SLOT=%q\n' "${PORTSDOWN_START_SRT_SLOT:-0}";;
    esac
    printf '# END DIABLO FIRST START\n'
} | "$repo/control/config-store" "$prefix/diablo.env"
if ((!local_only)); then
    access_args=(--prefix "$prefix" --first-start-managed --role STANDALONE --host "$advertise")
    ((interactive)) || access_args+=(--non-interactive)
    [[ -z $password_file ]] || access_args+=(--password-file "$password_file")
    bash "$repo/scripts/setup-access.sh" "${access_args[@]}"
fi
# Release both locks before the bounded verification or foreground launch.
flock -u 8; exec 8>&-
flock -u 9; exec 9>&-
source "$prefix/diablo.env"
port=${PORTSDOWN_INTERNAL_HTTP_PORT:-${PORTSDOWN_HTTP_PORT:-8080}}
if ((verify)); then
    command -v curl >/dev/null || fail 'Verification requires curl; install curl or use --no-verify.'
    log="$prefix/logs/first-start-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
    mkdir -p "$prefix/logs"
    child=
    cleanup() { [[ -z $child ]] || { kill -TERM "$child" 2>/dev/null || true; wait "$child" || true; }; }
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM HUP
    bash "$repo/scripts/run-diablo.sh" "$prefix/diablo.env" > "$log" 2>&1 & child=$!
    ready=0
    for ((attempt=0; attempt<50; attempt++)); do
        kill -0 "$child" 2>/dev/null || break
        if curl --noproxy '*' -fsS --max-time 1 "http://127.0.0.1:$port/api/state" > /dev/null 2>&1; then ready=1; break; fi
        sleep .1
    done
    # Verify the owned launcher is still alive, not just an unrelated HTTP server.
    sleep .2
    kill -0 "$child" 2>/dev/null || ready=0
    if ((ready)); then
        state=$(curl --noproxy '*' -fsS --max-time 2 "http://127.0.0.1:$port/api/state")
        DIABLO_SETUP_STATE="$state" "${ucode[@]}" -e '
          let data = json(getenv("DIABLO_SETUP_STATE"));
          let status = data?.supervisor?.status ?? "";
          if (!data?.supervisor?.ok || index(status, "tx=stopped") < 0 ||
              index(status, "rx=stopped") < 0 || index(status, "source_ts=stopped") < 0)
            die("GUI verification did not confirm idle TX/RX/TS\n");
          let slot = getenv("PORTSDOWN_START_SRT_SLOT") ?? "0";
          if (slot != "0" && getenv("DIABLO_SETUP_modeinput") == "SRT" &&
              slot == getenv("DIABLO_SETUP_srt_source_slot") &&
              index(status, `srt${slot}=running`) < 0)
            die("Configured SRT listener did not start\n");'
    fi
    if ((ready)) && [[ -n ${PORTSDOWN_AUTH_FILE:-} ]]; then
        # Exercise the public TLS front door, not only the internal helper API.
        code=$(curl --noproxy '*' --cacert "$PORTSDOWN_TLS_CERT" -sS --max-time 3 \
            -o /dev/null -w '%{http_code}' "https://127.0.0.1:${PORTSDOWN_HTTPS_PORT:-8443}/api/state") || ready=0
        [[ $code == 401 ]] || ready=0
    fi
    cleanup; child=
    trap - EXIT INT TERM HUP
    ((ready)) || fail "GUI startup check failed; see $log"
    echo 'GUI startup/API/shutdown check passed; no TS/ASI/RF output started.'
fi
printf 'Settings saved; private backup: %s\n' "$backup"
if [[ -n ${PORTSDOWN_AUTH_FILE:-} ]]; then
    printf 'Browser: https://%s:%s/ (use your web admin password; no SSH tunnel)\n' "$PORTSDOWN_TLS_HOST" "${PORTSDOWN_HTTPS_PORT:-8443}"
else
    printf 'Browser on this Pi only: http://127.0.0.1:%s/ (no web password)\n' "$port"
fi
if [[ $source == SRT ]]; then
    printf 'SRT caller: srt://%s:%s?mode=caller&latency=200000\n' "${advertise:-ENCODER_LAN_IP}" "$(( ${PORTSDOWN_SRT_PORT_BASE:-9101} + slot - 1 ))"
    echo 'Send MPEG-TS; UDP access must be allowed from the intended sender. The browser connection does not carry this video stream.'
fi
[[ $source != IPCAM* ]] || echo 'Save the private RTSP URL in IP CAM input encoders, then Restart; never pass camera passwords on this command line.'
if ((interactive && !start)); then
    choice=yes
    prompt choice 'Start GUI now in foreground? yes/no'
    [[ $choice != yes ]] || start=1
fi
if ((start)); then exec bash "$repo/scripts/run-diablo.sh" "$prefix/diablo.env"; fi
printf 'Start: %q\n' "$prefix/bin/diablo-studio"
