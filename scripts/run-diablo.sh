#!/usr/bin/env bash
# Foreground pair: either process exiting shuts down the other and its children.
set -Eeuo pipefail
envfile=${1:-${DIABLO_ENV:-"$HOME/.local/share/diablo-datv-studio/diablo.env"}}
[[ -r $envfile ]] || { echo "Run scripts/install-diablo.sh first; missing $envfile" >&2; exit 2; }
# This is the operator-owned, trusted shell environment created by the installer.
source "$envfile"
: "${PORTSDOWN_DIR:?}" "${DIABLO_RUNTIME:?}" "${PORTSDOWN_RUN_DIR:?}"
export LD_LIBRARY_PATH="$DIABLO_RUNTIME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PORTSDOWN_TX_SOCKET="$PORTSDOWN_RUN_DIR/tx.sock"
umask 077
mkdir -p "$PORTSDOWN_RUN_DIR"
[[ -d $PORTSDOWN_RUN_DIR && ! -L $PORTSDOWN_RUN_DIR && -O $PORTSDOWN_RUN_DIR ]] || {
    echo 'Runtime directory is not an owned, real directory.' >&2; exit 2;
}
exec 9>"$PORTSDOWN_RUN_DIR/launcher.lock"
flock -n 9 || { echo 'Diablo DATV Studio is already running.' >&2; exit 2; }
super_pid= daemon_pid= tls_pid=
stop_children() {
    for child in "$tls_pid" "$daemon_pid" "$super_pid"; do
        [[ -z $child ]] || kill -TERM "$child" 2>/dev/null || true
    done
    for child in "$tls_pid" "$daemon_pid" "$super_pid"; do
        [[ -z $child ]] || wait "$child" 2>/dev/null || true
    done
    super_pid= daemon_pid= tls_pid=
}
cleanup() { trap - EXIT INT TERM HUP; stop_children; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
# Only the managed launcher supports coordinated web configuration restarts.
export PORTSDOWN_ACCESS_ENV=$(realpath "$envfile")
export PORTSDOWN_ACCESS_RESTART="$PORTSDOWN_RUN_DIR/access.restart"
while :; do
source "$envfile"
rm -f -- "$PORTSDOWN_ACCESS_RESTART"
if [[ -n ${PORTSDOWN_AUTH_FILE:-} ]]; then
    stunnel=${PORTSDOWN_STUNNEL:-$(command -v stunnel4 || command -v stunnel || true)}
    [[ -x $stunnel ]] || { echo 'Install stunnel4 for protected LAN access.' >&2; exit 2; }
    export PORTSDOWN_PEER_TOKEN=$("$PORTSDOWN_DIR/control/auth-store" peer-key "$PORTSDOWN_AUTH_FILE")
    [[ $PORTSDOWN_PEER_TOKEN =~ ^[0-9a-f]{64}$ ]] || exit 2
    # Plain control stays on loopback; TLS authenticates before reaching SLAVE.
    export PORTSDOWN_PEER_BIND=127.0.0.1
    if [[ ${PORTSDOWN_PEER_ROLE:-STANDALONE} == MASTER ]]; then
        export PORTSDOWN_PEER_HOST=127.0.0.1 PORTSDOWN_PEER_PORT=18182
    else
        export PORTSDOWN_PEER_PORT=18181
    fi
    bash "$PORTSDOWN_DIR/scripts/tls-config.sh" > "$PORTSDOWN_RUN_DIR/stunnel.conf"
fi
"$PORTSDOWN_DIR/control/tx-super" 9>&- & super_pid=$!
for ((attempt=0; attempt<100; attempt++)); do
    kill -0 "$super_pid" 2>/dev/null || { wait "$super_pid"; exit 1; }
    [[ ! -S $PORTSDOWN_TX_SOCKET ]] || break
    sleep .05
done
[[ -S $PORTSDOWN_TX_SOCKET ]] || { echo 'Supervisor did not create its socket.' >&2; exit 1; }
"$DIABLO_RUNTIME/bin/ucode" -L "$DIABLO_RUNTIME/lib/ucode" \
    -L "$PORTSDOWN_DIR/control/ucode" "$PORTSDOWN_DIR/control/ucode/daemon.uc" 9>&- & daemon_pid=$!
if [[ -n ${PORTSDOWN_AUTH_FILE:-} ]]; then
    "$stunnel" "$PORTSDOWN_RUN_DIR/stunnel.conf" 9>&- & tls_pid=$!
    echo "Diablo DATV Studio: https://${PORTSDOWN_TLS_HOST}:${PORTSDOWN_HTTPS_PORT:-8443}/ (shared password; Ctrl+C to stop)"
    rc=0; wait -n "$super_pid" "$daemon_pid" "$tls_pid" || rc=$?
else
    echo "Diablo DATV Studio: http://127.0.0.1:${PORTSDOWN_HTTP_PORT:-8080}/ (local-only; run setup-access.sh for LAN login)"
    rc=0; wait -n "$super_pid" "$daemon_pid" || rc=$?
fi
if [[ $rc == 75 && -f $PORTSDOWN_ACCESS_RESTART && ! -L $PORTSDOWN_ACCESS_RESTART &&
      -O $PORTSDOWN_ACCESS_RESTART && $(cat "$PORTSDOWN_ACCESS_RESTART") == restart ]]; then
    stop_children
    echo 'Applying web access settings; all old processes stopped. TX will not resume.'
    continue
fi
exit "$rc"
done
