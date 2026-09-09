#!/bin/bash
# generate-diff.sh - Generate a rich HTML diff and serve it locally
# Usage: generate-diff.sh [--markdown] [git diff args...]
# Default: shows all changes (staged + unstaged + untracked) vs HEAD

PORT="${DIFF_REVIEW_PORT:-9876}"
TMP_DIR="${TMPDIR:-/tmp}"
DIFF_FILE="${TMP_DIR%/}/diff-review.html"
SERVER_PID_FILE="${TMP_DIR%/}/diff-review-server.pid"

# ── Parse --markdown flag ────────────────────────────────────────────────────
FORCE_MARKDOWN=false
FILTERED_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--markdown" ]; then
        FORCE_MARKDOWN=true
    else
        FILTERED_ARGS+=("$arg")
    fi
done
set -- "${FILTERED_ARGS[@]}"

# ── Kill any previously running diff review server ──────────────────────────
if [ -f "$SERVER_PID_FILE" ]; then
    OLD_PID=$(cat "$SERVER_PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        echo "(Stopped previous diff server, PID $OLD_PID)"
    fi
    rm -f "$SERVER_PID_FILE"
fi
# Also kill anything still holding the port (covers stale/orphaned servers)
STALE_PID=$(lsof -ti :"$PORT" 2>/dev/null)
if [ -n "$STALE_PID" ]; then
    kill $STALE_PID 2>/dev/null || true
    sleep 0.3
fi

# ── Build git diff command ───────────────────────────────────────────────────
if [ -z "$*" ]; then
    GIT_DIFF_CMD="git diff HEAD"
    DIFF_LABEL="all uncommitted changes vs HEAD"
    INCLUDE_UNTRACKED=true
else
    GIT_DIFF_CMD="git diff $*"
    DIFF_LABEL="git diff $*"
    INCLUDE_UNTRACKED=false
fi

# ── Check for changes ────────────────────────────────────────────────────────
DIFF_OUTPUT=$(eval "$GIT_DIFF_CMD" 2>&1)

if ! echo "$DIFF_OUTPUT" | grep -q "^diff"; then
    # Try staged-only as fallback
    STAGED=$(git diff --staged 2>/dev/null)
    if echo "$STAGED" | grep -q "^diff"; then
        GIT_DIFF_CMD="git diff --staged"
        DIFF_LABEL="staged changes only"
        DIFF_OUTPUT="$STAGED"
        echo "(No unstaged changes — showing staged changes only)"
    fi
fi

# ── Append untracked files (default mode only) ───────────────────────────────
if [ "$INCLUDE_UNTRACKED" = true ]; then
    UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null)
    if [ -n "$UNTRACKED" ]; then
        while IFS= read -r file; do
            [ -f "$file" ] || continue
            UNTRACKED_DIFF=$(git diff --no-index /dev/null "$file" 2>/dev/null || true)
            DIFF_OUTPUT="${DIFF_OUTPUT}"$'\n'"${UNTRACKED_DIFF}"
        done <<< "$UNTRACKED"
    fi
fi

if ! echo "$DIFF_OUTPUT" | grep -q "^diff"; then
    echo "Working tree is clean. Nothing to diff."
    exit 0
fi

# Show stat summary regardless of mode
echo ""
echo "=== $(eval "git diff --stat $*" 2>/dev/null || echo "$DIFF_LABEL") ==="

# ── Attempt HTML mode ────────────────────────────────────────────────────────
HTML_MODE=false

# Augment PATH with common node binary locations (nvm, fnm, homebrew, volta)
# so diff2html is found even in non-interactive (no .zshrc/.bashrc) shells.
for _NODE_BIN in \
    "$NVM_BIN" \
    "$HOME/.nvm/versions/node/$(ls "$HOME/.nvm/versions/node" 2>/dev/null | sort -V | tail -1)/bin" \
    "$HOME/.fnm/bin" \
    "$HOME/.volta/bin" \
    "/opt/homebrew/bin" \
    "/usr/local/bin"; do
    [ -d "$_NODE_BIN" ] && PATH="$_NODE_BIN:$PATH"
done

if [ "$FORCE_MARKDOWN" = true ]; then
    HTML_MODE=false
elif command -v diff2html &>/dev/null; then
    DIFF2HTML_CMD="diff2html"
    HTML_MODE=true
elif command -v npx &>/dev/null; then
    # Use npx to run diff2html-cli on demand (downloads once, cached afterward)
    DIFF2HTML_CMD="npx -y diff2html-cli"
    HTML_MODE=true
fi

if [ "$HTML_MODE" = true ]; then
    echo "$DIFF_OUTPUT" | $DIFF2HTML_CMD \
        -i stdin \
        -s side \
        -d word \
        --hc true \
        --cs dark \
        --su open \
        -F "$DIFF_FILE" 2>/dev/null

    if [ ! -f "$DIFF_FILE" ]; then
        echo "WARNING: diff2html failed to generate HTML — falling back to markdown."
        HTML_MODE=false
    fi
fi

if [ "$HTML_MODE" = true ]; then
    # ── Start HTTP server ────────────────────────────────────────────────────
    SERVE_DIR=$(dirname "$DIFF_FILE")
    FILENAME=$(basename "$DIFF_FILE")

    python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$SERVE_DIR" &>/dev/null &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$SERVER_PID_FILE"

    # Give the server a moment to bind
    sleep 0.3

    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "WARNING: HTTP server failed to start — falling back to markdown."
        HTML_MODE=false
    fi
fi

if [ "$HTML_MODE" = true ]; then
    # ── Collect IP addresses ─────────────────────────────────────────────────
    # macOS: try Wi-Fi (en0), then Ethernet (en1), then any non-loopback
    LOCAL_IP=$(
        ipconfig getifaddr en0 2>/dev/null ||
        ipconfig getifaddr en1 2>/dev/null ||
        ifconfig 2>/dev/null | grep "inet " | grep -v "127\.0\.0\.1" | awk '{print $2}' | head -1 ||
        hostname -I 2>/dev/null | awk '{print $1}'
    )

    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "")

    # ── Print access URLs ────────────────────────────────────────────────────
    echo ""
    echo "┌─ Diff Review Ready ──────────────────────────────────────────────┐"
    echo "│"
    if [ -n "$LOCAL_IP" ]; then
        echo "│  Same network:  http://$LOCAL_IP:$PORT/$FILENAME"
    fi
    if [ -n "$TAILSCALE_IP" ]; then
        echo "│  Tailscale:     http://$TAILSCALE_IP:$PORT/$FILENAME"
    fi
    echo "│  Local file:    file://$DIFF_FILE"
    echo "│"
    echo "│  Server PID $SERVER_PID — stop with: kill $SERVER_PID"
    echo "└──────────────────────────────────────────────────────────────────┘"
    echo ""
else
    # ── Markdown fallback ────────────────────────────────────────────────────
    echo ""
    if [ "$FORCE_MARKDOWN" = true ]; then
        echo "(Markdown mode — skipping HTML viewer)"
    else
        echo "(diff2html-cli not found — outputting raw diff for markdown rendering)"
        echo "Install with: npm install -g diff2html-cli"
    fi
    echo ""
    echo "MARKDOWN_FALLBACK_START"
    echo "$DIFF_OUTPUT"
    echo "MARKDOWN_FALLBACK_END"
fi
