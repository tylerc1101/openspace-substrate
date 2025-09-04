#!/usr/bin/env bash
set -euo pipefail
require_tools() {
  local missing=0
  for t in jq yq sops age ansible-playbook terraform helmfile; do
    command -v "$t" >/dev/null 2>&1 || { echo "Missing tool: $t"; missing=1; }
  done
  [[ $missing -eq 0 ]] || exit 1
}
check_files() {
  local envdir="$1"
  [[ -r "${envdir}/config.toml" ]] || { echo "config.toml missing"; return 1; }
  [[ -r "${envdir}/secrets.sops.yaml" ]] || { echo "secrets.sops.yaml missing"; return 1; }
  [[ -r "${envdir}/keys/age-key.txt.enc" ]] || { echo "age-key.txt.enc missing"; return 1; }
}
preflight() {
  local env="$1"
  local envdir="/usr_home/${env}"
  require_tools
  check_files "$envdir"
  /docker-workspace/lib/secrets_sops.sh check --env "$env" >/dev/null
  echo "Preflight basic checks passed."
}
[[ "${BASH_SOURCE[0]}" == "$0" ]] && preflight "$@"
