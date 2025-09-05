#!/usr/bin/env bash
set -euo pipefail
ROOT="/docker-workspace"

. "${ROOT}/lib/log.sh"

ENV=""
RESUME=false
ONLY=""
YES=false
PAUSE=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="$2"; shift 2;;
    --resume) RESUME=true; shift;;
    --only) ONLY="$2"; shift 2;;
    --yes|-y) YES=true; shift;;
    --no-pause) PAUSE=false; shift;;
    *) shift;;
  esac
done
[[ -n "$ENV" ]] || fail "Missing --env"

ENV_DIR="/usr_home/${ENV}"
PLAN="${ENV_DIR}/plan.yaml"
[[ -r "$PLAN" ]] || fail "Plan not found: $PLAN"

RUN_ID="$(date -u +'%FT%H-%M-%SZ')-$(head -c4 /dev/urandom|od -An -tx1|tr -d ' \n')"
LOG_DIR="${ENV_DIR}/logs/${RUN_ID}"
mkdir -p "$LOG_DIR"
cp "$PLAN" "${LOG_DIR}/plan.yaml"

# --- helpers -------------------------------------------------------

run_and_tee() {
  local logfile="$1"; shift
  [[ "$1" == "--" ]] && shift
  set +e
  set -o pipefail
  "$@" 2>&1 | tee -a "$logfile"
  local rc=${PIPESTATUS[0]}
  set +o pipefail
  set -e
  return $rc
}

exec_one_task() {
  local id="$1"; local kind="$2"; local obj_json="$3"
  local rc=0
  case "$kind" in
    bash)
      local script; script=$(jq -r '.script' <<<"$obj_json")
      run_and_tee "$STEP_LOG" -- bash "$script" --env "$ENV" || rc=$? ;;
    ansible)
      local inv pbk
      inv=$(jq -r '.inventory' <<<"$obj_json")
      pbk=$(jq -r '.playbook'  <<<"$obj_json")
      run_and_tee "$STEP_LOG" -- ansible-playbook -i "$inv" "$pbk" -vv || rc=$? ;;
    terraform)
      local tfdir; tfdir=$(jq -r '.tfdir' <<<"$obj_json")
      pushd "$tfdir" >/dev/null
      if [[ ! -f .terraform/initialized ]]; then
        run_and_tee "$STEP_LOG" -- terraform init -input=false -lockfile=readonly || { rc=$?; popd >/dev/null; }
        mkdir -p .terraform && touch .terraform/initialized
      fi
      [[ $rc -ne 0 ]] || run_and_tee "$STEP_LOG" -- terraform apply -input=false -lock=true -auto-approve || rc=$?
      popd >/dev/null ;;
    helmfile)
      local hf; hf=$(jq -r '.helmfile' <<<"$obj_json")
      run_and_tee "$STEP_LOG" -- helmfile -f "$hf" apply --skip-deps || rc=$? ;;
    *)
      echo "Unknown kind: $kind" | tee -a "$STEP_LOG"; rc=2 ;;
  esac
  return $rc
}

load_custom_tasks_json() {
  local phase="$1"
  local file="${ENV_DIR}/custom/${phase}/tasks.yaml"
  [[ -f "$file" ]] || { jq -n '[]'; return 0; }
  yq -o=json "$file" | sed "s#/usr_home/{{env}}#/usr_home/${ENV}#g"
}

run_custom_phase() {
  local phase="$1"
  local PHASE_JSON; PHASE_JSON="$(load_custom_tasks_json "$phase")"
  local total; total=$(jq 'length' <<<"$PHASE_JSON")
  [[ "$total" -eq 0 ]] && return 0

  echo "Running custom/${phase} tasks (${total})…"
  local idx=0
  while read -r item; do
    idx=$((idx+1))
    local id kind
    id=$(jq -r '.id' <<<"$item")
    kind=$(jq -r '.kind' <<<"$item")
    STEP_LOG="${LOG_DIR}/custom_${phase}_$(printf '%02d' "$idx")_${id}.log"

    echo "[custom ${phase} ${idx}/${total}] ${id} (live)…"
    local rc=0
    exec_one_task "$id" "$kind" "$item" || rc=$?
    if [[ $rc -ne 0 ]]; then
      echo "❌ custom/${phase} failed: ${id} (rc=$rc). See $STEP_LOG"
      exit $rc
    fi
    echo "✅ custom/${phase}: ${id}"
  done < <(jq -c '.[]' <<<"$PHASE_JSON")
}

# --- load main plan ------------------------------------------------

readarray -t RAW < <(yq -r '.tasks[] | [.id,.kind,.label] | @tsv' "$PLAN")
if [[ -n "$ONLY" ]]; then
  IFS=',' read -r -a INC <<<"$ONLY"
  mapfile -t RAW < <(printf "%s\n" "${RAW[@]}" | awk -v list="$(IFS='|'; echo "${INC[*]}")" -F'\t' '$1 ~ ("^("list")$")')
fi

COUNT="${#RAW[@]}"
echo "Apply plan for env=${ENV} (${COUNT} tasks):"
i=0; for row in "${RAW[@]}"; do ((i++)); IFS=$'\t' read -r _ _ label <<<"$row"; printf "  %d) %s\n" "$i" "$label"; done
$YES || read -r -p "Proceed? [y/N]: " ans; $YES || [[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# --- run phases ----------------------------------------------------

run_custom_phase "pre"

PROGRESS="${ENV_DIR}/.progress.json"
jq -n --arg rid "$RUN_ID" '{run_id:$rid, completed:[]}' > "$PROGRESS"

i=0
for row in "${RAW[@]}"; do
  ((i++))
  IFS=$'\t' read -r id kind label <<<"$row"
  STEP_LOG="${LOG_DIR}/$(printf '%02d' "$i")_${id}.log"

  if $RESUME && jq -e --arg id "$id" '.completed | index($id) != null' "$PROGRESS" >/dev/null 2>&1; then
    printf "[%d/%d] %s SKIP (completed)\n" "$i" "$COUNT" "$id"
    continue
  fi

  printf "[%d/%d] %s (live)…\n" "$i" "$COUNT" "$label"

  if $PAUSE; then
    echo "  starting in 15s… (c=cancel, Enter=continue)"
    for t in {15..1}; do
      read -t 1 -n 1 key && { [[ "$key" == "c" ]] && echo && fail "Canceled by user"; }
      printf "."
    done
    echo
  fi

  rc=0
  obj_json="$(yq -o=json ".tasks[] | select(.id==\"$id\")" "$PLAN")"
  exec_one_task "$id" "$kind" "$obj_json" || rc=$?

  if [[ $rc -eq 0 ]]; then
    echo "✅ Finished: $id"
    tmp="$(mktemp)"; jq --arg id "$id" '.completed += [$id]' "$PROGRESS" > "$tmp" && mv "$tmp" "$PROGRESS"
  else
    echo "❌ Failed: $id (rc=$rc). See $STEP_LOG"
    exit "$rc"
  fi
done

run_custom_phase "post"
echo "✅ APPLY complete. Logs: ${LOG_DIR}"