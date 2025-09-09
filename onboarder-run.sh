#!/usr/bin/env bash
set -euo pipefail

# ===== CONFIG =====
IMAGE_NAME="localhost/openspace/onboarder"
IMAGE_TAG="1.0"
IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"
IMAGE_ARCHIVE="onboarder-${IMAGE_TAG}.oci.tar"
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

# ===== LOAD IMAGE IF MISSING =====
# Check if image exists
if ! "$RUNTIME" image inspect "$IMAGE" >/dev/null 2>&1; then
  # If not, try to load it from the local archive
  if [ -f "${ROOT_DIR}/${IMAGE_ARCHIVE}" ]; then
    echo "INFO: Image ${IMAGE} not found. Loading from ${IMAGE_ARCHIVE}..."
    "$RUNTIME" load -i "${ROOT_DIR}/${IMAGE_ARCHIVE}"
  else
    echo "ERROR: Image ${IMAGE} not found and ${IMAGE_ARCHIVE} does not exist." >&2
    echo "Please pull the image from the registry or provide the local archive." >&2
    exit 1
  fi
fi

# ===== MOUNT FLAGS =====
V_OPTS=()
case "$RUNTIME" in
  podman)
    V_OPTS+=("-v" "${HOST_DOCKER_WORKSPACE}:${CONT_DOCKER_WORKSPACE}:ro,z")
    V_OPTS+=("-v" "${HOST_DATA}:${CONT_DATA}:z")
    V_OPTS+=("-v" "${HOST_USR_HOME}:${CONT_USR_HOME}:z")
    ;;
  docker)
    V_OPTS+=("-v" "${HOST_DOCKER_WORKSPACE}:${CONT_DOCKER_WORKSPACE}:ro,Z")
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

# Run as current user to avoid permissions issues with mounted volumes
USER_FLAG=(--user "$(id -u):$(id -g)")
if [[ "$RUNTIME" == "podman" ]]; then
  # For podman, also use keep-id to map the user namespace
  USER_FLAG+=(--userns=keep-id)
fi

# ===== RUN =====
exec "$RUNTIME" run --rm \
  "${TTY_FLAG[@]}" \
  --name "${CONTAINER_NAME}" \
  --shm-size "${SHM_SIZE}" \
  --security-opt no-new-privileges \
  --workdir "${CONT_DOCKER_WORKSPACE}" \
  "${USER_FLAG[@]}" \
  "${V_OPTS[@]}" \
  "${IMAGE}" \
  /docker-workspace/onboarder.py "$@"