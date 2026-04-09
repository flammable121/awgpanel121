#!/usr/bin/env bash
set -e

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_PATH="$ROOT_DIR/.env"
SECRETS_DIR="$ROOT_DIR/.secrets"
SECRETS_PATH="$SECRETS_DIR/panel.json"
CADDY_ENV_PATH="$SECRETS_DIR/caddy.env"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root (example: sudo bash deploy/install.sh)"
  exit 1
fi

install_docker() {
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "Docker auto-install is only supported on Debian/Ubuntu (apt)."
    return 1
  fi

  . /etc/os-release
  if [ "$ID" != "ubuntu" ] && [ "$ID" != "debian" ]; then
    echo "Docker auto-install is only supported on Debian/Ubuntu."
    return 1
  fi

  echo "Installing Docker for $ID ($VERSION_CODENAME)..."
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker || service docker start || true
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed."
  read -r -p "Install Docker automatically? [Y/n]: " INSTALL_DOCKER
  INSTALL_DOCKER=${INSTALL_DOCKER:-Y}
  case "$INSTALL_DOCKER" in
    n|N|no|NO) echo "Docker is required. Aborting."; exit 1;;
    *) install_docker || { echo "Failed to install Docker automatically."; exit 1; } ;;
  esac
fi

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "Docker Compose is not available. Install docker compose v2 or docker-compose and retry."
  exit 1
fi

read -r -p "AWG container name [amnezia-awg2]: " AWG_CONTAINER
AWG_CONTAINER=${AWG_CONTAINER:-amnezia-awg2}
read -r -p "AmneziaWG config path [/opt/amnezia/awg/awg0.conf]: " AWG_CONFIG_PATH
AWG_CONFIG_PATH=${AWG_CONFIG_PATH:-/opt/amnezia/awg/awg0.conf}
read -r -p "AmneziaWG interface [awg0]: " AWG_INTERFACE
AWG_INTERFACE=${AWG_INTERFACE:-awg0}

check_awg() {
  if docker ps -a --format '{{.Names}}' | grep -qx "$AWG_CONTAINER"; then
    if docker exec "$AWG_CONTAINER" sh -c "test -f '$AWG_CONFIG_PATH'" >/dev/null 2>&1; then
      return 0
    fi
    echo "AWG container found, but config path not accessible: $AWG_CONFIG_PATH"
    return 1
  fi
  return 1
}

echo ""
echo "Step 1: Ensure AmneziaWG 2.0 is installed..."
if ! check_awg; then
  echo "AmneziaWG 2.0 was not detected or not ready."
  echo "Please install it using the official desktop app (AmneziaVPN), then press Enter."
  read -r -p "Press Enter to continue after installation..." _
  if ! check_awg; then
    echo "AmneziaWG was not found. Please verify the container name and config path."
    exit 1
  fi
fi

echo "AmneziaWG detected. Continuing."

read -r -p "Domain name (leave empty for IP/HTTP): " PANEL_DOMAIN_INPUT
if [ -z "$PANEL_DOMAIN_INPUT" ]; then
  PANEL_DOMAIN=":80"
  echo "Panel will be available via IP over HTTP (port 80)."
else
  PANEL_DOMAIN="$PANEL_DOMAIN_INPUT"
  echo "Panel domain: $PANEL_DOMAIN"
fi

if command -v python3 >/dev/null 2>&1; then
  PANEL_TOKEN=$(python3 - <<'PY'
import secrets, string
alphabet = string.ascii_letters + string.digits
print(''.join(secrets.choice(alphabet) for _ in range(14)))
PY
)
elif command -v openssl >/dev/null 2>&1; then
  PANEL_TOKEN=$(openssl rand -hex 7)
else
  PANEL_TOKEN=$(date +%s)
fi
PANEL_BASE_PATH="/$PANEL_TOKEN"

echo "Secret panel path: $PANEL_BASE_PATH"

AWG_PORT=""
AWG_PORT=$(docker exec "$AWG_CONTAINER" sh -c "grep -E '^ListenPort' -m1 '$AWG_CONFIG_PATH' | awk -F= '{print \$2}' | tr -d ' '" 2>/dev/null || true)
if [ -n "$AWG_PORT" ]; then
  echo "Detected AmneziaWG ListenPort: $AWG_PORT/udp"
fi

PUBLIC_IP=""
if [ "$PANEL_DOMAIN" = ":80" ] && command -v curl >/dev/null 2>&1; then
  PUBLIC_IP=$(curl -fsS --max-time 5 https://api.ipify.org || true)
fi

DEFAULT_PUBLIC_ENDPOINT=""
if [ -n "$AWG_PORT" ]; then
  if [ "$PANEL_DOMAIN" = ":80" ]; then
    if [ -n "$PUBLIC_IP" ]; then
      DEFAULT_PUBLIC_ENDPOINT="${PUBLIC_IP}:${AWG_PORT}"
    fi
  else
    DEFAULT_PUBLIC_ENDPOINT="${PANEL_DOMAIN}:${AWG_PORT}"
  fi
fi
read -r -p "Public endpoint for client configs (host:port) [${DEFAULT_PUBLIC_ENDPOINT}]: " PUBLIC_ENDPOINT
PUBLIC_ENDPOINT=${PUBLIC_ENDPOINT:-$DEFAULT_PUBLIC_ENDPOINT}

DEFAULT_CLIENT_ALLOWED_IPS="0.0.0.0/0, ::/0"
DEFAULT_CLIENT_DNS="1.1.1.1, 8.8.8.8"

read -r -p "Admin username [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}

while true; do
  read -r -s -p "Admin password: " ADMIN_PASS
  echo
  read -r -s -p "Confirm password: " ADMIN_PASS_CONFIRM
  echo
  if [ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]; then
    echo "Passwords do not match. Try again."
    continue
  fi
  if [ ${#ADMIN_PASS} -lt 8 ]; then
    echo "Password is too short (min 8 characters)."
    continue
  fi
  break
done

if command -v openssl >/dev/null 2>&1; then
  SECRET_KEY=$(openssl rand -hex 32)
elif command -v python3 >/dev/null 2>&1; then
  SECRET_KEY=$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)
else
  SECRET_KEY="change-me"
fi

if command -v openssl >/dev/null 2>&1; then
  API_TOKEN=$(openssl rand -hex 24)
elif command -v python3 >/dev/null 2>&1; then
  API_TOKEN=$(python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
)
else
  API_TOKEN="$(date +%s)"
fi

if [ -f "$ENV_PATH" ] || [ -f "$SECRETS_PATH" ]; then
  read -r -p "Existing configuration found. Overwrite? [y/N]: " OVERWRITE
  OVERWRITE=${OVERWRITE:-N}
  case "$OVERWRITE" in
    y|Y|yes|YES) ;;
    *) echo "Aborted. Remove existing files to reinstall."; exit 0;;
  esac
fi

mkdir -p "$SECRETS_DIR"
cat > "$SECRETS_PATH" <<ENV
{
  "SECRET_KEY": "$SECRET_KEY",
  "ADMIN_USER": "$ADMIN_USER",
  "ADMIN_PASS": "$ADMIN_PASS",
  "API_TOKEN": "$API_TOKEN",
  "PANEL_BASE_PATH": "$PANEL_BASE_PATH",
  "AWG_CONTAINER": "$AWG_CONTAINER",
  "AWG_CONFIG_PATH": "$AWG_CONFIG_PATH",
  "AWG_INTERFACE": "$AWG_INTERFACE",
  "PUBLIC_ENDPOINT": "$PUBLIC_ENDPOINT",
  "DEFAULT_CLIENT_ALLOWED_IPS": "$DEFAULT_CLIENT_ALLOWED_IPS",
  "DEFAULT_CLIENT_DNS": "$DEFAULT_CLIENT_DNS"
}
ENV
chmod 600 "$SECRETS_PATH" || true

echo ".secrets/panel.json created."

cat > "$CADDY_ENV_PATH" <<ENV
PANEL_DOMAIN=$PANEL_DOMAIN
PANEL_BASE_PATH=$PANEL_BASE_PATH
ENV
chmod 600 "$CADDY_ENV_PATH" || true

echo ".secrets/caddy.env created."

cat > "$ENV_PATH" <<ENV
# Generated by install.sh. Sensitive settings are stored in .secrets.
ENV

echo ".env created at: $ENV_PATH"

install -m 0755 "$SCRIPT_DIR/awgpanel-cli.sh" /usr/local/bin/awgpanel || true
echo "CLI installed: awgpanel"

if command -v ufw >/dev/null 2>&1; then
  read -r -p "Open ports 80 and 443 in UFW? [Y/n]: " OPEN_UFW
  OPEN_UFW=${OPEN_UFW:-Y}
  case "$OPEN_UFW" in
    n|N|no|NO) ;;
    *)
      ufw allow 80/tcp || true
      ufw allow 443/tcp || true
      if [ -n "$AWG_PORT" ]; then
        read -r -p "Open AmneziaWG port $AWG_PORT/udp in UFW? [Y/n]: " OPEN_AWG
        OPEN_AWG=${OPEN_AWG:-Y}
        case "$OPEN_AWG" in
          n|N|no|NO) ;;
          *) ufw allow "${AWG_PORT}/udp" || true ;;
        esac
      fi
      echo "UFW rules applied. If UFW is disabled, enable it manually."
      ;;
  esac
fi

echo ""
echo "Starting containers..."
cd "$ROOT_DIR"
$DC up -d --build

if [ "$PANEL_DOMAIN" != ":80" ] && [ -n "$PANEL_DOMAIN" ]; then
  echo ""
  echo "Requesting SSL certificate for $PANEL_DOMAIN..."
  bash "$SCRIPT_DIR/get-ssl.sh" || echo "Failed to obtain SSL certificate. Check DNS and ports 80/443."
fi

PANEL_URL=""
if [ "$PANEL_DOMAIN" = ":80" ]; then
  if [ -z "$PUBLIC_IP" ] && command -v curl >/dev/null 2>&1; then
    PUBLIC_IP=$(curl -fsS --max-time 5 https://api.ipify.org || true)
  fi
  if [ -n "$PUBLIC_IP" ]; then
    PANEL_URL="http://$PUBLIC_IP$PANEL_BASE_PATH/"
  else
    PANEL_URL="http://<SERVER_IP>$PANEL_BASE_PATH/"
  fi
else
  PANEL_URL="https://$PANEL_DOMAIN$PANEL_BASE_PATH/"
fi

echo ""
echo "Done."
echo "Panel URL: $PANEL_URL"
echo "API token: $API_TOKEN"
echo "Keep this token secret. It is required for API access."
