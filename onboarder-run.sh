#!/usr/bin/env bash
set -euo pipefail

# ===== CONFIG =====
IMAGE="${ONBOARDER_IMAGE:-ghcr.io/yourorg/onboarder:1.0.0}"  # pinned onboarder image
CONTAINER_NAME="onboarder"
SHM_SIZE="${ONBOARDER_SHM_SIZE:-1g}"

# Repo root (where these dirs live on host)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_DOCKER_WORKSPACE="${ROOT_DIR}/docker-workspace"
HOST_DATA="${ROOT_DIR}/data"
HOST_USR_HOME="${ROOT_DIR}/usr_home"

# Mount points inside container
CONT_DOCKER_WORKSPACE="/docker-workspace"
CONT_DATA="/data"
CONT_USR_HOME="/usr_home"

# ===== DETECT RUNTIME =====
if command -v podman >/dev/null 2>&1; then
  RUNTIME="podman"
elif command -v docker >/dev/null 2>&1; then
  RUNTIME="docker"
else
  echo "ERROR: Podman or Docker required on host." >&2
  exit 1
fi

# ===== MOUNT FLAGS =====
V_OPTS=()
case "$RUNTIME" in
  podman)
    V_OPTS+=("-v" "${HOST_DOCKER_WORKSPACE}:${CONT_DOCKER_WORKSPACE}:z")
    V_OPTS+=("-v" "${HOST_DATA}:${CONT_DATA}:z")
    V_OPTS+=("-v" "${HOST_USR_HOME}:${CONT_USR_HOME}:z")
    ;;
  docker)
    V_OPTS+=("-v" "${HOST_DOCKER_WORKSPACE}:${CONT_DOCKER_WORKSPACE}:Z")
    V_OPTS+=("-v" "${HOST_DATA}:${CONT_DATA}:Z")
    V_OPTS+=("-v" "${HOST_USR_HOME}:${CONT_USR_HOME}:Z")
    ;;
esac

# ===== USAGE =====
usage() {
  cat <<EOF
Usage: $0 <command> [args...]

Commands (run inside container):
  init             --env NAME
  secrets init     --env NAME
  secrets check    --env NAME
  plan             --env NAME
  apply            --env NAME
EOF
}

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage; exit 0
fi

# Allocate TTY if possible
TTY_FLAG=()
if [ -t 0 ]; then TTY_FLAG=(-it); else TTY_FLAG=(-i); fi

USER_FLAG=()
if [[ "$RUNTIME" == "podman" ]]; then
  USER_FLAG=(--userns=keep-id --user "$(id -u):$(id -g)")
fi

# ===== RUN =====
exec "$RUNTIME" run --rm \
  "${TTY_FLAG[@]}" \
  --name "${CONTAINER_NAME}" \
  --shm-size "${SHM_SIZE}" \
  --workdir "${CONT_DOCKER_WORKSPACE}" \
  "${USER_FLAG[@]}" \
  "${V_OPTS[@]}" \
  "${IMAGE}" \
  /docker-workspace/onboarder.sh "$@"
