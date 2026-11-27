#!/usr/bin/env bash
# Configure user-local HTTPS and web-admin-password peer TLS. No service or RF start.
set -Eeuo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
prefix=${DIABLO_PREFIX:-"$HOME/.local/share/diablo-datv-studio"}
password_file= host= role= peer_host= https_port= interactive=1 managed=0 password_stdin=0 peer_host_set=0
while (($#)); do
    case $1 in
        --prefix) prefix=${2:?}; shift 2;;
        --password-stdin) password_stdin=1; shift;;
        --password-file) password_file=${2:?}; shift 2;;
        --host) host=${2:?}; shift 2;;
        --https-port) https_port=${2:?}; shift 2;;
        --role) role=${2:?}; shift 2;;
        --peer-host) peer_host=${2-}; peer_host_set=1; shift 2;;
        --non-interactive) interactive=0; shift;;
        --first-start-managed) managed=1; shift;;
        --help) echo 'Usage: bash scripts/setup-access.sh [--prefix PATH] [--password-file PRIVATE_FILE] [--host LAN_IP] [--https-port 8443] [--role STANDALONE|MASTER|SLAVE] [--peer-host SLAVE_IP] [--non-interactive]'; exit;;
        *) echo 'Unknown access setup option' >&2; exit 2;;
    esac
done
[[ $(id -u) != 0 ]] || { echo 'Run as your normal user.' >&2; exit 2; }
[[ -O $prefix/diablo.env && ! -L $prefix/diablo.env ]] || { echo 'Install Diablo first.' >&2; exit 2; }
source "$prefix/diablo.env"
[[ ${PORTSDOWN_DIR:-} == "$repo" ]] || { echo 'Use the checkout saved in diablo.env' >&2; exit 2; }
if ((!managed)); then
    exec 9>"$prefix/install.lock"; flock -n 9 || { echo 'Setup already running'; exit 2; }
    exec 8>"$PORTSDOWN_RUN_DIR/launcher.lock"; flock -n 8 || { echo 'Stop Diablo before changing access'; exit 2; }
fi
umask 077
host=${host:-${PORTSDOWN_TLS_HOST:-${PORTSDOWN_SRT_ADVERTISE_HOST:-}}}
[[ -n $host ]] || host=$(hostname -I | awk '{print $1}')
https_port=${https_port:-${PORTSDOWN_HTTPS_PORT:-8443}}
if ((!peer_host_set)); then peer_host=${PORTSDOWN_PEER_REMOTE_HOST:-}; fi
if ((interactive)); then
    if [[ -z $role ]]; then read -r -p "Role STANDALONE/MASTER/SLAVE [${PORTSDOWN_PEER_ROLE:-STANDALONE}]: " role; fi
    if ((!managed)); then
        read -r -p "LAN address for browser [$host]: " answer; host=${answer:-$host}
    fi
fi
role=${role:-${PORTSDOWN_PEER_ROLE:-STANDALONE}}
role=${role^^}
case $role in STANDALONE|MASTER|SLAVE) ;; *) echo 'Invalid role' >&2; exit 2;; esac
if [[ $role == MASTER && $interactive == 1 ]]; then
    read -r -p "Slave LAN address [$peer_host]: " answer; peer_host=${answer:-$peer_host}
fi
valid_ip() {
    [[ $1 =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ && $1 != 0.0.0.0 ]] || return 1
    local part; local -a parts; IFS=. read -r -a parts <<< "$1"
    for part in "${parts[@]}"; do ((10#$part <= 255)) || return 1; done
}
valid_ip "$host" || { echo 'Enter a LAN IPv4 address' >&2; exit 2; }
[[ $role != MASTER ]] || valid_ip "$peer_host" || { echo 'MASTER needs the Slave IPv4 address' >&2; exit 2; }
[[ $https_port =~ ^[0-9]{4,5}$ ]] && ((10#$https_port >= 1024 && 10#$https_port <= 65535)) || exit 2
https_port=$((10#$https_port))
for reserved in "${PORTSDOWN_HTTP_PORT:-8080}" 18080 18181 18182 8181 {8082..8092}; do
    [[ $https_port != "$reserved" ]] || { echo 'HTTPS port conflicts with an internal/peer port' >&2; exit 2; }
done
password=
valid_password() {
    local bytes
    bytes=$(printf %s "$1" | wc -c)
    ((bytes >= 8 && bytes <= 128)) && [[ $1 != *$'\r'* && $1 != *$'\n'* ]]
}
if ((password_stdin)); then
    IFS= read -r password || [[ -n $password ]] || true
elif [[ -n $password_file ]]; then
    [[ -f $password_file && ! -L $password_file && -O $password_file && $(stat -c %a "$password_file") == 600 ]] || { echo 'Password file must be an owned mode-600 regular file' >&2; exit 2; }
    mapfile -t password_lines < "$password_file"
    [[ ${#password_lines[@]} == 1 ]] || { echo 'Password file must contain exactly one line' >&2; exit 2; }
    password=${password_lines[0]}; unset password_lines
elif ((!interactive)) && [[ -n ${PORTSDOWN_AUTH_FILE:-} ]]; then
    : # An unattended rerun keeps the existing password.
elif ((interactive)); then
    while :; do
        if [[ -n ${PORTSDOWN_AUTH_FILE:-} ]]; then
            read -r -s -p 'New web admin password (Enter keeps current): ' password; echo
            [[ -n $password ]] || break
        else
            read -r -s -p 'Web admin password (at least 8 characters): ' password; echo
            if [[ -z $password ]]; then
                echo 'A password is needed when opening Diablo from another computer. Choose Pi-only access for no password.' >&2
                continue
            fi
        fi
        if ! valid_password "$password"; then
            echo 'Password is too short, too long, or contains a line break. Please try again.' >&2
            continue
        fi
        read -r -s -p 'Repeat web admin password: ' confirm; echo
        if [[ $password != "$confirm" ]]; then
            echo 'Passwords do not match. Please try again.' >&2
            unset confirm
            continue
        fi
        unset confirm
        break
    done
else
    echo 'First setup needs --password-file (private mode 600); never put passwords in command arguments.' >&2; exit 2
fi
if [[ -n $password ]] && ! valid_password "$password"; then
    echo 'Web admin password is too short, too long, or contains a line break.' >&2
    exit 2
fi
mkdir -p "$prefix/security"
[[ -O $prefix/security && ! -L $prefix/security ]] || exit 2
chmod 700 "$prefix/security"
if [[ -n $password ]]; then
    access=$(mktemp -d "$prefix/security/access-XXXXXXXX")
    printf %s "$password" | "$repo/control/auth-store" create "$access/password.conf" || {
        echo 'Could not save the web admin password; no access settings were changed.' >&2; exit 2;
    }
    unset password
    printf 'diablo:%s\n' "$("$repo/control/auth-store" peer-key "$access/password.conf")" > "$access/peer.psk"
else
    [[ -n ${PORTSDOWN_AUTH_FILE:-} ]] || { echo 'A web admin password is required for LAN access' >&2; exit 2; }
    access=$(dirname "$PORTSDOWN_AUTH_FILE")
fi
# Keep a valid certificate on ordinary reruns so browser trust remains stable.
cert=${PORTSDOWN_TLS_CERT:-}; key=${PORTSDOWN_TLS_KEY:-}
if [[ -f $cert && ! -L $cert && -O $cert && -f $key && ! -L $key && -O $key &&
      $(stat -c %a "$cert") == 600 && $(stat -c %a "$key") == 600 ]] &&
   openssl x509 -in "$cert" -noout -checkip "$host" >/dev/null 2>&1 &&
   openssl x509 -in "$cert" -noout -checkend 86400 >/dev/null 2>&1; then
    : # Same trusted address/certificate; retain it.
else
    certdir=$(mktemp -d "$prefix/security/cert-XXXXXXXX")
    cert="$certdir/cert.pem"; key="$certdir/key.pem"
    openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 825 \
        -subj '/CN=Diablo DATV Studio' -addext "subjectAltName=IP:$host,IP:127.0.0.1,DNS:localhost" \
        -keyout "$key" -out "$cert" 2> "$certdir/generate.log"
fi
backup="$prefix/backups/access-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$backup"; cp -p "$prefix/diablo.env" "$backup/diablo.env"
{
    awk '/^# BEGIN DIABLO ACCESS$/ {skip=1;next} /^# END DIABLO ACCESS$/ {skip=0;next} !skip' "$prefix/diablo.env"
    echo '# BEGIN DIABLO ACCESS'
    printf 'export PORTSDOWN_AUTH_FILE=%q\n' "$access/password.conf"
    printf 'export PORTSDOWN_TLS_PSK=%q\n' "$access/peer.psk"
    printf 'export PORTSDOWN_TLS_CERT=%q\nexport PORTSDOWN_TLS_KEY=%q\n' "$cert" "$key"
    printf 'export PORTSDOWN_TLS_HOST=%q\nexport PORTSDOWN_HTTPS_PORT=%q\n' "$host" "$https_port"
    printf 'export PORTSDOWN_INTERNAL_HTTP_PORT=%q\nexport PORTSDOWN_TLS_BIND=%q\n' "${PORTSDOWN_INTERNAL_HTTP_PORT:-18080}" "${PORTSDOWN_TLS_BIND:-0.0.0.0}"
    printf 'export PORTSDOWN_PEER_ROLE=%q\nexport PORTSDOWN_PEER_REMOTE_HOST=%q\n' "$role" "$peer_host"
    printf 'export PORTSDOWN_PEER_TLS_PORT=%q\n' "${PORTSDOWN_PEER_TLS_PORT:-8181}"
    echo '# END DIABLO ACCESS'
} | "$repo/control/config-store" "$prefix/diablo.env"
printf 'LAN browser: https://%s:%s/\nRole: %s\n' "$host" "$https_port" "$role"
echo 'Certificate SHA-256 fingerprint (check before trusting the first browser visit):'
openssl x509 -in "$cert" -noout -fingerprint -sha256
echo 'Access saved. Anyone knowing the web admin password can sign in and control matching peers.'
echo 'Restart Diablo to apply. No router/firewall, boot service or output settings were changed.'
