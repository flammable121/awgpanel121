#!/usr/bin/env bash
set -euo pipefail

# WARP+Xray+iptables install/apply script
# This script is executed by the panel when WARP_APPLY_MODE includes "script".
# It receives these environment variables:
#   WARP_GEOIP_URL, WARP_GEOSITE_URL, WARP_RULES, WARP_RULES_FILE
#   XRAY_CONFIG_PATH, XRAY_DAT_DIR, WARP_SOCKS_HOST, WARP_SOCKS_PORT
#   WARP_TPROXY_PORT, WARP_FWMARK, AWG_INTERFACE
#   WARP_MODE, WARP_WG_SECRET_KEY, WARP_WG_ADDRESS, WARP_WG_RESERVED, WARP_WG_MTU
#   WARP_WG_PUBLIC_KEY, WARP_WG_ENDPOINT, WARP_WG_KEEPALIVE, WARP_WG_WORKERS, WARP_WG_DOMAIN_STRATEGY
#
# Replace this file with your full installation / setup logic.
# You can also use it to (re)start Xray, apply iptables, etc.

printf '%s\n' "[warp-apply] placeholder script executed" >&2
exit 0
