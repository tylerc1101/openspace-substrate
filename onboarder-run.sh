#!/usr/bin/env bash
set -euo pipefail

# -------- paths --------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${ROOT_DIR}/data"
USR_HOME_DIR="${ROOT_DIR}/usr_home"

# -------- constants --------
KNOWN_PROFILES=("basekit" "baremetal" "aws")

die() { echo "ERROR: $*" >&2; exit 1; }
usage() {
  cat <<EOF
Usage: ./onboarder-run.sh --env=<env_name>

Behavior:
  - Auto-detect runtime
  - Auto-detect profile from usr_home/<env>/group_vars/<profile>.yml
  - Read 'onboarder' image tar from that group_vars
  - Load image from data/images/onboarder/<tar>, run container 'onboarder', remove after
  - Logs directory: usr_home/<env>/logs

Runs:
  python3 /install/data/main.py --env <env> --profile <profile>
EOF
}

# -------- args --------
ENV_NAME=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      shift
      [[ $# -gt 0 ]] || die "--env requires an argument"
      ENV_NAME="$1"
      ;;
    --env=*)
      ENV_NAME="${1#*=}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown arg: $1"
      ;;
  esac
  shift
done

ENV_DIR="${USR_HOME_DIR}/${ENV_NAME}"
[[ -d "${ENV_DIR}" ]] || die "Environment dir not found: ${ENV_DIR}"

# -------- runtime detection --------
if command -v podman >/dev/null 2>&1; then
  RUNTIME="podman"
elif command -v docker >/dev/null 2>&1; then
  RUNTIME="docker"
else
  die "Neither podman nor docker found in PATH"
fi
echo "Using runtime: ${RUNTIME}"

# -------- profile detection (group_vars/<profile>.yml) --------
GROUPVARS_DIR="${ENV_DIR}/group_vars"
[[ -d "${GROUPVARS_DIR}" ]] || die "group_vars directory not found: ${GROUPVARS_DIR}"

# gather *.yml files (ignore hidden/backup)
mapfile -t GROUPVARS_FILES < <(find "${GROUPVARS_DIR}" -maxdepth 1 -type f -name "*.yml" -printf "%f\n" | sort)
[[ ${#GROUPVARS_FILES[@]} -ge 1 ]] || die "No YAML files found in ${GROUPVARS_DIR} to determine profile kind"

choose_profile_kind() {
  local candidates=("$@")
  local filtered=()
  # prefer known kinds if multiple
  for f in "${candidates[@]}"; do
    local name="${f%.yml}"
    for k in "${KNOWN_PROFILES[@]}"; do
      if [[ "${name}" == "${k}" ]]; then
        filtered+=("${name}")
      fi
    done
  done
  if [[ ${#filtered[@]} -eq 1 ]]; then
    echo "${filtered[0]}"
    return 0
  fi
  return 1
}

if ! PROFILE_YAML="$(choose_profile_kind "${GROUPVARS_FILES[@]}")"; then
  die "Ambiguous profile kind in ${GROUPVARS_DIR}. Found: ${GROUPVARS_FILES[*]}."
fi

PROFILE="${GROUPVARS_DIR}/${PROFILE_YAML}.yml"
[[ -f "${PROFILE}" ]] || die "Expected group vars file not found: ${PROFILE}"
echo "Detected profile kind: ${PROFILE_YAML}"

# -------- resolve onboarder image tar --------
# Expect in ${PROFILE}: onboarder: "onboarder-<something>.tar[.gz]"
ONBOARDER_TAR="$(grep -E '^[[:space:]]*onboarder:' "${PROFILE}" | head -1 | awk -F':' '{print $2}' | tr -d " \"'")"
[[ -n "${ONBOARDER_TAR}" ]] || die "'onboarder' not set in ${PROFILE}"

IMAGE_ARCHIVE="${DATA_DIR}/images/onboarder/${ONBOARDER_TAR}"
[[ -f "${IMAGE_ARCHIVE}" ]] || die "Onboarder image archive not found: ${IMAGE_ARCHIVE}"

# -------- load image --------
echo "Loading image: ${IMAGE_ARCHIVE}"
LOAD_OUT="$(${RUNTIME} load -i "${IMAGE_ARCHIVE}" 2>&1 || true)"
echo "${LOAD_OUT}"

IMAGE_REF=""
# docker: "Loaded image: repo:tag"
# podman: "Loaded image(s): repo:tag"
if [[ "${LOAD_OUT}" =~ Loaded[[:space:]]image(s)?:[[:space:]]([[:graph:]]+) ]]; then
  IMAGE_REF="${BASHREMATCH[2]}"
fi
# fallback: try to pick something onboarder-ish or the latest image
if [[ -z "${IMAGE_REF}" ]]; then
  CAND="$(${RUNTIME} images --format '{{.Repository}}:{{.Tag}}' | grep -i '^onboarder' | head -1 || true)"
  if [[ -n "${CAND}" ]]; then
    IMAGE_REF="${CAND}"
  else
    IMAGE_REF="$(${RUNTIME} images --format '{{.Repository}}:{{.Tag}}' | head -1 || true)"
  fi
fi
[[ -n "${IMAGE_REF}" ]] || die "Could not determine image reference after load"

echo "Using image: ${IMAGE_REF}"

# -------- container name --------
CONTAINER_NAME="onboarder"
if ${RUNTIME} ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "Removing existing container ${CONTAINER_NAME} ..."
  ${RUNTIME} rm -f "${CONTAINER_NAME}" >/dev/null
fi

# -------- logs under env --------
LOG_DIR="${ENV_DIR}/logs"
mkdir -p "${LOG_DIR}"

# -------- run container --------
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

set -x
${RUNTIME} run --rm \
  --name "${CONTAINER_NAME}" \
  -u "${HOST_UID}:${HOST_GID}" \
  -v "${DATA_DIR}:/install/data:rw" \
  -v "${ENV_DIR}:/install/usr_home/${ENV_NAME}:rw" \
  -v "${LOG_DIR}:/install/logs:rw" \
  -w /install \
  "${IMAGE_REF}" \
  python3 /install/data/main.py \
    --env "${ENV_NAME}" \
    --profile "${PROFILE_KIND}"
set +x

echo "Onboarder run complete. Logs: ${LOG_DIR}"
