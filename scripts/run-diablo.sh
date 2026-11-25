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
super_pid= daemon_pid=
cleanup() {
    trap - EXIT INT TERM HUP
    for child in "$daemon_pid" "$super_pid"; do
        [[ -z $child ]] || kill -TERM "$child" 2>/dev/null || true
    done
    for child in "$daemon_pid" "$super_pid"; do
        [[ -z $child ]] || wait "$child" 2>/dev/null || true
    done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
"$PORTSDOWN_DIR/control/tx-super" 9>&- & super_pid=$!
for ((attempt=0; attempt<100; attempt++)); do
    kill -0 "$super_pid" 2>/dev/null || { wait "$super_pid"; exit 1; }
    [[ ! -S $PORTSDOWN_TX_SOCKET ]] || break
    sleep .05
done
[[ -S $PORTSDOWN_TX_SOCKET ]] || { echo 'Supervisor did not create its socket.' >&2; exit 1; }
"$DIABLO_RUNTIME/bin/ucode" -L "$DIABLO_RUNTIME/lib/ucode" \
    -L "$PORTSDOWN_DIR/control/ucode" "$PORTSDOWN_DIR/control/ucode/daemon.uc" 9>&- & daemon_pid=$!
echo "Diablo DATV Studio: http://127.0.0.1:${PORTSDOWN_HTTP_PORT:-8080}/ (Ctrl+C to stop)"
wait -n "$super_pid" "$daemon_pid"
