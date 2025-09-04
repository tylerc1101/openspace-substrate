#!/usr/bin/env bash
set -euo pipefail

require_env() { [[ "${1:-}" == "--env" ]] || { echo "Missing --env"; exit 2; }; [[ -n "${2:-}" ]] || { echo "Empty env"; exit 2; }; echo "$2"; }

case "${1:-}" in
  init)
    shift; ENV="$(require_env "$@")"; ENV_DIR="/usr_home/${ENV}"
    TMP="/dev/shm/age-key.txt"
    install -d -m 0700 "${ENV_DIR}/keys"
    age-keygen -o "$TMP" >/dev/null
    PUB="$(grep -m1 'public key:' "$TMP" | awk '{print $4}')"
    cat > "${ENV_DIR}/.sops.yaml" <<EOF
creation_rules:
  - path_regex: secrets\\.sops\\.ya?ml$
    encrypted_regex: '^(linux\\.|rke2\\.|harbor\\.|rancher\\.)'
    age: ["$PUB"]
    unencrypted_regex: '^(meta\\.|notes\\.|_example\\.)'
EOF
    chmod 0600 "${ENV_DIR}/.sops.yaml"
    echo "Protecting private key with your passphrase…"
    age -p -o "${ENV_DIR}/keys/age-key.txt.enc" "$TMP"
    shred -u "$TMP"
    PLA="/dev/shm/secrets.plain.yaml"
    cat > "$PLA" <<'YAML'
linux:
  ssh_user: "kratos"
  become_password: ""
rke2:
  token: ""
harbor:
  admin_password: ""
rancher:
  bootstrap_password: ""
YAML
    ${EDITOR:-vi} "$PLA"
    export SOPS_AGE_RECIPIENTS="$PUB"
    cp "$PLA" "${ENV_DIR}/secrets.sops.yaml"
    sops -e -i "${ENV_DIR}/secrets.sops.yaml"
    shred -u "$PLA"
    echo "Secrets initialized in usr_home/${ENV}"
    ;;
  check)
    shift; ENV="$(require_env "$@")"; ENV_DIR="/usr_home/${ENV}"
    KEY="/dev/shm/age-key.txt"
    age -d -o "$KEY" "${ENV_DIR}/keys/age-key.txt.enc"
    export SOPS_AGE_KEY_FILE="$KEY"
    sops -d "${ENV_DIR}/secrets.sops.yaml" >/dev/null && echo "Secrets OK" || { shred -u "$KEY"; exit 1; }
    shred -u "$KEY"
    ;;
  export)
    shift; ENV="$(require_env "$@")"; ENV_DIR="/usr_home/${ENV}"
    KEY="/dev/shm/age-key.txt"
    age -d -o "$KEY" "${ENV_DIR}/keys/age-key.txt.enc"
    export SOPS_AGE_KEY_FILE="$KEY"
    set -a
    eval "$(sops -d --output-type dotenv "${ENV_DIR}/secrets.sops.yaml")"
    set +a
    shred -u "$KEY"
    ;;
  *) echo "Usage: $0 {init|check|export} --env NAME"; exit 2;;
esac
