#!/bin/sh
# systemd fallback when tx-super itself is killed before its signal cleanup.
set -eu
hook=${PORTSDOWN_SAFE_OFF_EXEC:-}
case "$hook" in /*) exec "$hook" ;; *) exit 1 ;; esac
