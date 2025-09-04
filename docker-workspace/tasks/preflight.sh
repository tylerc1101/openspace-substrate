#!/usr/bin/env bash
set -euo pipefail
ENV=""
while [[ $# -gt 0 ]]; do case "$1" in --env) ENV="$2"; shift 2;; *) shift;; esac; done
[[ -n "$ENV" ]] || { echo "missing --env"; exit 2; }
/docker-workspace/lib/validate.sh preflight "$ENV"
