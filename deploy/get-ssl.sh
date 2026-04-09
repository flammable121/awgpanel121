#!/usr/bin/env bash
set -e

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_PATH="$ROOT_DIR/.env"
SECRETS_ENV_PATH="$ROOT_DIR/.secrets/caddy.env"

if [ -f "$SECRETS_ENV_PATH" ]; then
  PANEL_DOMAIN=$(grep -E '^PANEL_DOMAIN=' "$SECRETS_ENV_PATH" | tail -n1 | cut -d= -f2-)
elif [ -f "$ENV_PATH" ]; then
  PANEL_DOMAIN=$(grep -E '^PANEL_DOMAIN=' "$ENV_PATH" | tail -n1 | cut -d= -f2-)
else
  echo "Config not found. Run deploy/install.sh first."
  exit 1
fi
PANEL_DOMAIN=${PANEL_DOMAIN:-":80"}

if [ "$PANEL_DOMAIN" = ":80" ] || [ -z "$PANEL_DOMAIN" ]; then
  echo "No domain set (PANEL_DOMAIN). SSL is not needed for IP access."
  exit 0
fi

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "Docker Compose is not available."
  exit 1
fi

echo "Starting Caddy to obtain SSL for $PANEL_DOMAIN..."
cd "$ROOT_DIR"
$DC up -d caddy

echo "Waiting for certificate (up to 2 minutes)..."
END=$((SECONDS + 120))
while [ $SECONDS -lt $END ]; do
  if $DC logs --tail=50 caddy 2>/dev/null | grep -qi "certificate obtained"; then
    echo "Certificate obtained successfully."
    exit 0
  fi
  sleep 5
done

echo "Failed to obtain certificate."
echo "Check DNS and ensure ports 80/443 are reachable, then retry."
exit 1
