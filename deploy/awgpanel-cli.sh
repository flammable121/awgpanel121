#!/usr/bin/env bash
set -e

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SECRETS_PATH="$ROOT_DIR/.secrets/panel.json"
CADDY_ENV_PATH="$ROOT_DIR/.secrets/caddy.env"

if [ ! -f "$SECRETS_PATH" ]; then
  echo "Secrets file not found: $SECRETS_PATH"
  exit 1
fi

read_json() {
  python3 - "$SECRETS_PATH" "$1" <<'PY'
import json, sys
path = sys.argv[1]
key = sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh) or {}
print(data.get(key, ""))
PY
}

write_json() {
  python3 - "$SECRETS_PATH" "$1" <<'PY'
import json, sys, os
path = sys.argv[1]
payload = sys.argv[2] or "{}"
data = {}
if os.path.exists(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh) or {}
data.update(json.loads(payload))
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
PY
}

PANEL_BASE_PATH="$(read_json PANEL_BASE_PATH)"
ADMIN_USER="$(read_json ADMIN_USER)"

PANEL_DOMAIN=""
if [ -f "$CADDY_ENV_PATH" ]; then
  PANEL_DOMAIN=$(grep -E "^PANEL_DOMAIN=" "$CADDY_ENV_PATH" | head -n1 | cut -d= -f2-)
fi

PUBLIC_IP=""
if [ "$PANEL_DOMAIN" = ":80" ] || [ -z "$PANEL_DOMAIN" ]; then
  if command -v curl >/dev/null 2>&1; then
    PUBLIC_IP=$(curl -fsS --max-time 5 https://api.ipify.org || true)
  fi
  if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  fi
fi

if [ -n "$PANEL_DOMAIN" ] && [ "$PANEL_DOMAIN" != ":80" ]; then
  PANEL_URL="https://$PANEL_DOMAIN${PANEL_BASE_PATH}/"
else
  PANEL_URL="http://${PUBLIC_IP:-<SERVER_IP>}${PANEL_BASE_PATH}/"
fi

echo ""
echo "Panel URL: $PANEL_URL"
echo ""

read -r -p "Change admin login/password? [y/N]: " CHANGE
CHANGE=${CHANGE:-N}
case "$CHANGE" in
  y|Y|yes|YES)
    read -r -p "Admin username [${ADMIN_USER:-admin}]: " NEW_USER
    NEW_USER=${NEW_USER:-${ADMIN_USER:-admin}}
    while true; do
      read -r -s -p "Admin password: " NEW_PASS
      echo
      read -r -s -p "Confirm password: " NEW_PASS_CONFIRM
      echo
      if [ "$NEW_PASS" != "$NEW_PASS_CONFIRM" ]; then
        echo "Passwords do not match. Try again."
        continue
      fi
      if [ ${#NEW_PASS} -lt 8 ]; then
        echo "Password is too short (min 8 characters)."
        continue
      fi
      break
    done
    payload=$(python3 - <<PY
import json
print(json.dumps({"ADMIN_USER": "$NEW_USER", "ADMIN_PASS": "$NEW_PASS"}))
PY
)
    write_json "$payload" >/dev/null
    echo "Admin credentials updated."
    if docker compose version >/dev/null 2>&1; then
      (cd "$ROOT_DIR" && docker compose restart panel) || true
    elif command -v docker-compose >/dev/null 2>&1; then
      (cd "$ROOT_DIR" && docker-compose restart panel) || true
    fi
    ;;
  *)
    ;;
esac
