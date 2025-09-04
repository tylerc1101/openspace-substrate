#!/usr/bin/env bash
set -euo pipefail
log()  { printf "[%s] %s\n" "$(date -u +'%FT%TZ')" "$*" >&2; }
fail() { log "ERROR: $*"; exit 1; }
