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

# -------- pick ENV from usr_home via menu --------
# Gather non-hidden directories in usr_home
mapfile -t ENV_DIRS < <(
  find "${USR_HOME_DIR}" -mindepth 1 -maxdepth 1 -type d \
    ! -name '.*' \
    ! -name 'sample_aws' \
    ! -name 'sample_baremetal' \
    ! -name 'sample_basekit' \
    -printf "%f\n" | sort
)

[[ ${#ENV_DIRS[@]} -ge 1 ]] || die "No environment directories found in ${USR_HOME_DIR}"

if [[ -t 0 ]]; then
  echo "Select environment:"
  select ENV_NAME in "${ENV_DIRS[@]}"; do
    if [[ -n "${ENV_NAME:-}" ]]; then
      break
    else
      echo "Invalid selection. Try again."
    fi
  done
fi

ENV_DIR="${USR_HOME_DIR}/${ENV_NAME}"
[[ -d "${ENV_DIR}" ]] || die "Environment dir not found: ${ENV_DIR}"

# -------- runtime detection --------
if command -v podman >/dev/null 2>&1; then
  RUNTIME="podman"
  SE_OPT_DATA="rw,Z"
  SE_OPT_ENV="rw,Z"
  SE_OPT_LOGS="rw,Z"
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

if [[ -z $(${RUNTIME} images --format '{{.Repository}}:{{.Tag}}') ]]; then
  ${RUNTIME} load -i "${IMAGE_ARCHIVE}"
else
  echo "Image already loaded"
fi

IMAGE_REF="$(${RUNTIME} images --format '{{.Repository}}:{{.Tag}}' | grep -i 'onboarder' | head -1 || true)"

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
${RUNTIME} run \
  --name "${CONTAINER_NAME}" \
  -u "${HOST_UID}:${HOST_GID}" \
  -v "${DATA_DIR}:/install/data:${SE_OPT_DATA}" \
  -v "${ENV_DIR}:/install/usr_home/${ENV_NAME}:${SE_OPT_ENV}" \
  -v "${LOG_DIR}:/install/logs:${SE_OPT_LOGS}" \
  -w /install \
  "${IMAGE_REF}" \
  python3 /install/data/main.py \
    --env "${ENV_NAME}" \
    --profile "${PROFILE_YAML}"
set +x

echo "Onboarder run complete. Logs: ${LOG_DIR}"