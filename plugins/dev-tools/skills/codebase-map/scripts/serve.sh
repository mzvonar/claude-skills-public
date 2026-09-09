#!/usr/bin/env bash
# Serve a built codebase-map site on the LAN. Usage: serve.sh [DIR] [PORT]
set -euo pipefail
DIR="${1:-codebase-map-site}"
PORT="${2:-8777}"
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null \
     || hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)
echo "Serving $DIR"
echo "  local : http://127.0.0.1:$PORT/"
echo "  LAN   : http://$IP:$PORT/"
echo "(Ctrl-C to stop)"
exec python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$DIR"
