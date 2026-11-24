#!/bin/sh
# Source from a shell TS producer; never evaluate config values as shell code.
ts_service_metadata_load() {
  cfg=$1
  [ -r "$cfg" ] || { echo 'TS metadata config unreadable' >&2; return 2; }
  TS_SERVICE_PROVIDER=$(awk -F= '$1 == "call" { print substr($0, index($0, "=") + 1); exit }' "$cfg")
  TS_SERVICE_NAME=$(awk -F= '$1 == "service_name" { print substr($0, index($0, "=") + 1); exit }' "$cfg")
  printf '%s\n' "$TS_SERVICE_PROVIDER" | LC_ALL=C grep -Eq '^[A-Z0-9/]{3,20}$' &&
    printf '%s\n' "$TS_SERVICE_PROVIDER" | grep -q '[0-9]' || {
      echo 'Configure a CALLSIGN (3-20 uppercase letters, digits or /)' >&2; return 2;
    }
  [ -n "$(printf '%s' "$TS_SERVICE_NAME" | tr -d '[:space:]')" ] &&
    [ "$(printf '%s' "$TS_SERVICE_NAME" | LC_ALL=C wc -c)" -le 64 ] &&
    ! printf '%s' "$TS_SERVICE_NAME" | LC_ALL=C grep -q '[[:cntrl:]]' || {
      echo 'Configure a printable service_name (1-64 UTF-8 bytes)' >&2; return 2;
    }
  export TS_SERVICE_PROVIDER TS_SERVICE_NAME
}
