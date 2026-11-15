#!/bin/sh
set -eu

if [ -n "${SASHINY_AUTHINFO:-}" ]; then
  authinfo="${HOME:-/root}/.authinfo"
  (umask 077; printf '%s\n' "$SASHINY_AUTHINFO" > "$authinfo")
  unset SASHINY_AUTHINFO
fi

exec "$@"
