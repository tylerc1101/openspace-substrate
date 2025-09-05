#!/usr/bin/env bash
set -euo pipefail

# ===== CONFIG =====
IMAGE="${ONBOARDER_IMAGE:-localhost/openspace/onboarder:1.0}"     # local image tag by default
CONTAINER_NAME="${CONTAINER_NAME:-onboarder}"
SHM_SIZE="${ONBOARDER_SHM_SIZE:-1g}"
DEV="${DEV:-0}"   # DEV=1 to live-mount host docker-workspace

# Repo root (where these dirs live on host)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_DOCKER_WORKSPACE="${ROOT_DIR}/docker-workspace"
HOST_DATA="${ROOT_DIR}/data"
HOST_USR_HOME="${ROOT_DIR}/usr_home"

# Mount points inside container
CONT_DOCKER_WORKSPACE="/docker-workspace"
CONT_DATA="/data"
CONT_USR_HOME="/usr_home"

# Ensure host dirs exist (avoids Podman/Docker creating them as root)
mkdir -p "${HOST_DATA}" "${HOST_USR_HOME}"
# docker-workspace may be optional if DEV=0; create if you plan to use DEV=1
[[ "${DEV}" = "1" ]] && mkdir -p "${HOST_DOCKER_WORKSPACE}"

# ===== DETECT RUNTIME =====
if command -v podman >/dev/null 2>&1; then
  RUNTIME="podman"
elif command -v docker >/dev/null 2>&1; then
  RUNTIME="docker"
else
  echo "ERROR: Podman or Docker required on host." >&2
  exit 1
fi

# ===== MOUNTS =====
V_OPTS=()

# Always mount env/data
case "$RUNTIME" in
  podman)
    V_OPTS+=("-v" "${HOST_USR_HOME}:${CONT_USR_HOME}:Z")
    V_OPTS+=("-v" "${HOST_DATA}:${CONT_DATA}:Z")
    ;;
  docker)
    V_OPTS+=("-v" "${HOST_USR_HOME}:${CONT_USR_HOME}:Z")
    V_OPTS+=("-v" "${HOST_DATA}:${CONT_DATA}:Z")
    ;;
esac

# Only mount docker-workspace in DEV mode (avoid exec/SELinux/noexec issues)
if [[ "${DEV}" = "1" ]]; then
  case "$RUNTIME" in
    podman) V_OPTS+=("-v" "${HOST_DOCKER_WORKSPACE}:${CONT_DOCKER_WORKSPACE}:Z");;
    docker) V_OPTS+=("-v" "${HOST_DOCKER_WORKSPACE}:${CONT_DOCKER_WORKSPACE}:Z");;
  esac
fi

# ===== USAGE =====
usage() {
  cat <<EOF
Usage: $0 <command> [args...]

Commands (run inside container):
  init             --env NAME
  secrets init     --env NAME
  secrets check    --env NAME
  plan             --env NAME
  apply            --env NAME [--yes] [--resume] [--only id1,id2] [--no-pause]

Env vars:
  ONBOARDER_IMAGE        Container image to run (default: ${IMAGE})
  CONTAINER_NAME         Container name          (default: ${CONTAINER_NAME})
  ONBOARDER_SHM_SIZE     /dev/shm size           (default: ${SHM_SIZE})
  DEV=1                  Also mount host docker-workspace (dev mode)
EOF
}

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage; exit 0
fi

# Allocate TTY if attached
TTY_FLAG=()
if [ -t 0 ]; then TTY_FLAG=(-it); else TTY_FLAG=(-i); fi

# Podman rootless: preserve UID/GID inside the container
USER_FLAG=()
EXTRA_ARGS=()
if [[ "$RUNTIME" == "podman" ]]; then
  USER_FLAG=(--userns=keep-id --user "$(id -u):$(id -g)")
  EXTRA_ARGS+=(--pull=never)
fi

# For prod mode (no DEV), set workdir to in-image /docker-workspace;
# for dev mode, the same path is mounted from host.
WORKDIR_FLAG=(--workdir "${CONT_DOCKER_WORKSPACE}")

exec "$RUNTIME" run --rm \
  "${TTY_FLAG[@]}" \
  "${EXTRA_ARGS[@]}" \
  --name "${CONTAINER_NAME}" \
  --shm-size "${SHM_SIZE}" \
  "${WORKDIR_FLAG[@]}" \
  "${USER_FLAG[@]}" \
  "${V_OPTS[@]}" \
  "${IMAGE}" \
  /docker-workspace/onboarder.sh "$@"

