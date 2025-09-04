#!/usr/bin/env bash
set -euo pipefail
toml_to_context() {
  local file="$1"
  /docker-workspace/tools/tomlq "$file" \
    | jq '{
        profile: (.profile // ""),
        infrastructure: (.infrastructure // ""),
        dns: {servers: (.dns.servers // []), domain_name: (.dns.domain_name // null)},
        ntp: {servers: (.ntp.servers // [])},
        addons: (.addons // {}),
        mcms: (.mcms // {}),
        osms: (.osms // {}),
        osdc: (.osdc // {})
      }'
}
