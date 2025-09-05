#!/usr/bin/env bash
set -euo pipefail

ROOT="/docker-workspace"
[[ "${1:-}" == "--env" && -n "${2:-}" ]] || { echo "usage: $0 --env <name>"; exit 2; }
ENV="$2"
ENV_DIR="/usr_home/${ENV}"
CFG="${ENV_DIR}/config.toml"
[[ -r "$CFG" ]] || { echo "Missing ${CFG}"; exit 1; }

CTX="/dev/shm/context.json"
/docker-workspace/tools/tomlq "$CFG" > "$CTX"

PROFILE="$(jq -r '.profile // empty' "$CTX")"
INFRA="$(jq -r '.infrastructure // empty' "$CTX")"
[[ -n "$PROFILE" && -n "$INFRA" ]] || { echo "config.toml must set: profile, infrastructure"; exit 1; }

PROFDIR="${ROOT}/profiles/${PROFILE}"
[[ -d "$PROFDIR" ]] || { echo "Unknown profile: ${PROFILE}"; exit 1; }

ALLOWED=$(yq -o=json '.allowed_infra // []' "${PROFDIR}/profile.yaml")
jq -e --arg i "$INFRA" 'index($i) != null' <<<"$ALLOWED" >/dev/null || {
  echo "Profile '${PROFILE}' not validated for '${INFRA}'. Allowed: $(jq -r '.[]' <<<"$ALLOWED" | paste -sd, -)"; exit 1;
}

DEF_ADDONS=$(yq -o=json '.defaults.addons // {}' "${PROFDIR}/profile.yaml")
USR_ADDONS=$(jq '.addons // {}' "$CTX")
MERGED_ADDONS=$(jq -n --argjson a "$DEF_ADDONS" --argjson b "$USR_ADDONS" '$a * $b')

COMMON="${PROFDIR}/tasks/common.yaml"
INF_SPEC="${PROFDIR}/tasks/${INFRA}.yaml"
BASE_JSON="/dev/shm/base.json"
PATCH_JSON="/dev/shm/patch.json"
MERGED_JSON="/dev/shm/merged.json"

yq -o=json "$COMMON" | sed "s#/usr_home/{{env}}#/usr_home/${ENV}#g" > "$BASE_JSON"
if [[ -f "$INF_SPEC" ]]; then
  yq -o=json "$INF_SPEC" | sed "s#/usr_home/{{env}}#/usr_home/${ENV}#g" > "$PATCH_JSON"
else
  echo "[]" > "$PATCH_JSON"
fi

# --- merge algorithm ------------------------------------------------

cp "$BASE_JSON" "$MERGED_JSON"

# removals
jq -c '.[] | select(has("remove")) | .remove' "$PATCH_JSON" | while read -r rm; do
  id=$(echo "$rm" | tr -d '"')
  jq --arg id "$id" 'map(select(.id != $id))' "$MERGED_JSON" > "${MERGED_JSON}.tmp" && mv "${MERGED_JSON}.tmp" "$MERGED_JSON"
done

# replacements
jq -c '.[] | select(.replace == true)' "$PATCH_JSON" | while read -r item; do
  id=$(jq -r '.id' <<<"$item")
  jq --arg id "$id" 'map(select(.id != $id))' "$MERGED_JSON" > "${MERGED_JSON}.tmp" && mv "${MERGED_JSON}.tmp" "$MERGED_JSON"
  jq --argjson item "$item" '. + [$item | del(.replace,.after,.before,.remove)]' "$MERGED_JSON" > "${MERGED_JSON}.tmp" && mv "${MERGED_JSON}.tmp" "$MERGED_JSON"
done

# insert before/after
jq -c '.[] | select(has("after") or has("before"))' "$PATCH_JSON" | while read -r item; do
  after=$(jq -r 'if has("after") then .after else "" end' <<<"$item")
  before=$(jq -r 'if has("before") then .before else "" end' <<<"$item")
  clean=$(jq 'del(.replace,.after,.before,.remove)' <<<"$item")

  if [[ -n "$after" && "$after" != "null" ]]; then
    jq --arg tgt "$after" --argjson ins "$clean" '
      (map(.id) | index($tgt)) as $idx
      | if $idx == null then . + [$ins]
        else (.[0:$idx+1] + [$ins] + .[$idx+1:])
        end
    ' "$MERGED_JSON" > "${MERGED_JSON}.tmp" && mv "${MERGED_JSON}.tmp" "$MERGED_JSON"
  elif [[ -n "$before" && "$before" != "null" ]]; then
    jq --arg tgt "$before" --argjson ins "$clean" '
      (map(.id) | index($tgt)) as $idx
      | if $idx == null then . + [$ins]
        else (.[0:$idx] + [$ins] + .[$idx:])
        end
    ' "$MERGED_JSON" > "${MERGED_JSON}.tmp" && mv "${MERGED_JSON}.tmp" "$MERGED_JSON"
  fi
done

# append remaining
jq -c '.[] | select((has("after")|not) and (has("before")|not) and (has("replace")|not) and (has("remove")|not))' "$PATCH_JSON" \
| while read -r item; do
    jq --argjson item "$item" '. + [$item]' "$MERGED_JSON" > "${MERGED_JSON}.tmp" && mv "${MERGED_JSON}.tmp" "$MERGED_JSON"
  done

# optional pruning for addons
if [[ "$(jq -r '.argocd // false' <<<"$MERGED_ADDONS")" != "true" ]]; then
  jq 'map(select(.id | test("argocd") | not))' "$MERGED_JSON" > "${MERGED_JSON}.tmp" && mv "${MERGED_JSON}.tmp" "$MERGED_JSON"
fi
if [[ "$(jq -r '.gitea // false' <<<"$MERGED_ADDONS")" != "true" ]]; then
  jq 'map(select(.id | test("gitea") | not))' "$MERGED_JSON" > "${MERGED_JSON}.tmp" && mv "${MERGED_JSON}.tmp" "$MERGED_JSON"
fi

# --- emit final plan ------------------------------------------------

jq -n --arg env "$ENV" --arg rid "$(date -u +'%FT%H-%M-%SZ')" \
      --arg prof "$PROFILE" --arg infra "$INFRA" \
      --slurpfile tasks "$MERGED_JSON" \
      '{run_id:$rid, env:$env, profile:{id:$prof, infrastructure:$infra}, tasks:$tasks[0]}' \
| yq -P > "${ENV_DIR}/plan.yaml"

echo "Wrote ${ENV_DIR}/plan.yaml (profile=${PROFILE}, infra=${INFRA})"

rm -f "$CTX" "$BASE_JSON" "$PATCH_JSON" "$MERGED_JSON"