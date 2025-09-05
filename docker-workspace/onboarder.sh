#!/usr/bin/env bash
set -euo pipefail
ROOT="/docker-workspace"
ENV_DIR_BASE="/usr_home"

usage() {
  cat <<EOF
onboarder
  init            --env NAME
  secrets init    --env NAME
  secrets check   --env NAME
  plan            --env NAME
  apply           --env NAME [--yes] [--resume] [--only id1,id2] [--no-pause]
  doctor
EOF
}

require_env() {
  case "${1:-}" in
    --env)
      [[ -n "${2:-}" ]] || { echo "Empty --env value"; exit 2; }
      echo "$2"
      ;;
    --env=*)
      echo "${1#--env=}"
      ;;
    *)
      echo "Missing --env"; exit 2
      ;;
  esac
}


cmd_init() {
  local env; env="$(require_env "$@")"
  local src="${ENV_DIR_BASE}/sample_environment"
  local dst="${ENV_DIR_BASE}/${env}"
  [[ -d "$src" ]] || { echo "sample_environment missing"; exit 1; }
  [[ -e "$dst" ]] && { echo "usr_home/${env} exists"; exit 1; }
  cp -a "$src" "$dst"
  jq -n --arg env "$env" --arg ver "1.0.0" --arg now "$(date -u +'%FT%TZ')" \
     '{env_name:$env,onboarder_version:$ver,schema_version:"1",created:$now}' > "${dst}/.env_meta.json"
  echo "Created usr_home/${env}. Edit config.toml next."
}

cmd_secrets_init()  { exec "${ROOT}/lib/secrets_sops.sh" init  "$@"; }
cmd_secrets_check() { exec "${ROOT}/lib/secrets_sops.sh" check "$@"; }

cmd_plan() {
  local env; env="$(require_env "$@")"
  "${ROOT}/build_plan.sh" --env "$env"
  echo "Plan summary:"
  yq -r '.tasks[] | "- " + .label' "/usr_home/${env}/plan.yaml"
}

cmd_apply() {
  local env=""; local yes=""; local resume=""; local only=""; local nopause=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env) env="$2"; shift 2;;
      --yes|-y) yes="--yes"; shift;;
      --resume) resume="--resume"; shift;;
      --only) only="--only $2"; shift 2;;
      --no-pause) nopause="--no-pause"; shift;;
      *) shift;;
    esac
  done
  [[ -n "$env" ]] || { echo "Missing --env"; exit 2; }
  "${ROOT}/build_plan.sh" --env "$env"
  "${ROOT}/lib/secrets_sops.sh" export --env "$env"
  "${ROOT}/run_plan.sh" --env "$env" $yes $resume $only $nopause
}

cmd_doctor() {
  echo "Mounts:"; df -h /usr_home /data /docker-workspace || true
  echo; echo "Tool versions:"
  for t in bash jq yq sops age ansible-playbook terraform helmfile ctr nerdctl; do
    if command -v "$t" >/dev/null 2>&1; then
      printf "%-20s %s\n" "$t" "$("$t" --version 2>&1 | head -1)"
    else
      printf "%-20s %s\n" "$t" "NOT FOUND"
    fi
  done
}

case "${1:-}" in
  init) shift; cmd_init "$@";;
  secrets)
    shift; case "${1:-}" in
      init)  shift; cmd_secrets_init "$@";;
      check) shift; cmd_secrets_check "$@";;
      *) usage; exit 2;;
    esac;;
  plan)  shift; cmd_plan "$@";;
  apply) shift; cmd_apply "$@";;
  doctor|-h|--help|"") usage;;
  *) usage; exit 2;;
esac
