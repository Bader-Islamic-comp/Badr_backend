#!/usr/bin/env bash
# Starts the reviewer demo API in Docker and prints what to enter in the app.
#   bash deploy/start-demo.sh          # phone on the same Wi-Fi (LAN address)
#   bash deploy/start-demo.sh --local  # this computer / Android emulator only
#   bash deploy/start-demo.sh --new-token
# Stop with: docker compose down
set -euo pipefail
cd "$(dirname "$0")/.."

local_only=false
for arg in "$@"; do
  case "$arg" in
    --local) local_only=true ;;
    --new-token) rm -f deploy/demo.env ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -s deploy/demo.env ]; then
  token="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n')"
  umask 077
  printf 'COMPANION_DEMO_TOKEN=%s\n' "$token" > deploy/demo.env
fi
token="$(sed -n 's/^COMPANION_DEMO_TOKEN=//p' deploy/demo.env)"

if $local_only; then
  bind=127.0.0.1
elif [ -n "${DEMO_BIND:-}" ]; then
  bind="$DEMO_BIND"
else
  # The address this computer uses to reach the network: a private LAN address.
  # Linux (iproute2, then hostname -I), then macOS Wi-Fi/Ethernet.
  bind="$( { ip -4 route get 1.1.1.1 2>/dev/null || true; } | sed -n 's/.* src \([0-9.]*\).*/\1/p')"
  [ -n "$bind" ] || bind="$( { hostname -I 2>/dev/null || true; } | awk '{print $1}')"
  [ -n "$bind" ] || bind="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  case "$bind" in
    10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) ;;
    *) echo "No private Wi-Fi/LAN address found (got '${bind:-none}'). Use --local, or set DEMO_BIND yourself." >&2; exit 1 ;;
  esac
fi
port="${DEMO_PORT:-8000}"

DEMO_BIND="$bind" DEMO_PORT="$port" docker compose up -d --build

printf 'Waiting for the API'
for _ in $(seq 1 30); do
  if curl -fsS "http://$bind:$port/health/live" >/dev/null 2>&1; then ok=1; break; fi
  printf '.'; sleep 1
done
echo
[ "${ok:-}" = 1 ] || { echo "The API did not become healthy. See: docker compose logs api" >&2; exit 1; }

app_url="http://$bind:$port"
$local_only && app_url="http://10.0.2.2:$port (Android emulator) or http://127.0.0.1:$port (adb reverse)"
cat <<MSG

Badr demo API is running (synthetic data, adult-operated development demo).

In the app: Parent area -> Development service -> enter
  Server address: $app_url
  Operator token: $token

Keep the token private: no screenshots, chats or repositories.
Stop: docker compose down    New token: bash deploy/start-demo.sh --new-token
MSG
