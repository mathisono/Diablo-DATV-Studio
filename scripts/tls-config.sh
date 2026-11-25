#!/usr/bin/env bash
# Emit stunnel config; caller has loaded an operator-owned environment.
set -euo pipefail
for name in PORTSDOWN_TLS_CERT PORTSDOWN_TLS_KEY PORTSDOWN_TLS_PSK; do
    value=${!name:?}
    [[ $value == /* && $value != *$'\n'* && -f $value && ! -L $value && -O $value ]] || exit 2
    [[ $(stat -c %a "$value") == 600 ]] || { echo 'TLS files must be private mode 600' >&2; exit 2; }
done
bind=${PORTSDOWN_TLS_BIND:-0.0.0.0}
[[ $bind =~ ^[0-9.]+$ ]] || exit 2
for value in "${PORTSDOWN_HTTPS_PORT:-8443}" "${PORTSDOWN_HTTP_PORT:-8080}" "${PORTSDOWN_PEER_TLS_PORT:-8181}"; do
    [[ $value =~ ^[0-9]{4,5}$ ]] && ((10#$value>=1024 && 10#$value<=65535)) || exit 2
done
cat <<CONFIG
foreground = yes
syslog = no
pid =
debug = warning
socket = l:TCP_NODELAY=1
socket = r:TCP_NODELAY=1
[diablo-web]
accept = $bind:${PORTSDOWN_HTTPS_PORT:-8443}
connect = 127.0.0.1:${PORTSDOWN_HTTP_PORT:-8080}
cert = $PORTSDOWN_TLS_CERT
key = $PORTSDOWN_TLS_KEY
sslVersionMin = TLSv1.2
TIMEOUTclose = 0
CONFIG
if [[ ${PORTSDOWN_PEER_ROLE:-STANDALONE} == SLAVE ]]; then
    cat <<CONFIG
[diablo-peer]
accept = $bind:${PORTSDOWN_PEER_TLS_PORT:-8181}
connect = 127.0.0.1:18181
PSKsecrets = $PORTSDOWN_TLS_PSK
ciphers = PSK-AES256-GCM-SHA384
sslVersionMin = TLSv1.2
sslVersionMax = TLSv1.2
TIMEOUTclose = 0
CONFIG
elif [[ ${PORTSDOWN_PEER_ROLE:-STANDALONE} == MASTER ]]; then
    [[ ${PORTSDOWN_PEER_REMOTE_HOST:-} =~ ^[0-9.]+$ ]] || exit 2
    cat <<CONFIG
[diablo-peer]
client = yes
accept = 127.0.0.1:18182
connect = $PORTSDOWN_PEER_REMOTE_HOST:${PORTSDOWN_PEER_TLS_PORT:-8181}
PSKsecrets = $PORTSDOWN_TLS_PSK
PSKidentity = diablo
ciphers = PSK-AES256-GCM-SHA384
sslVersionMin = TLSv1.2
sslVersionMax = TLSv1.2
TIMEOUTclose = 0
CONFIG
fi
