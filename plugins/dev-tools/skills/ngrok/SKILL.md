---
name: ngrok
description: Expose a local port (or a specific URL on a local server) via ngrok so the user can open it from another device or share it externally. Use whenever the user wants to share something running on localhost — phrases like "expose my dev server", "make this accessible on my phone", "share this via ngrok", "tunnel port X", "ngrok this", or after generating any local artifact (HTML report, dashboard, file viewer, diff page) that they want to view from a different machine. Also trigger if the user complains they can't reach a localhost URL from another device. The skill prints a copy-pasteable bare URL (no angle brackets), tracks the ngrok PID for clean teardown, and offers to open the URL in the default browser.
---

# Expose a local port via ngrok

## When to use

The user has something running on localhost — a dev server, a `python -m http.server`, an HTML report, a file viewer — and wants to access it from a different device (phone, laptop, another person). ngrok wraps the local port in a public HTTPS URL.

## Steps

### 0. Is this session reading the CURRENT skill text?

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-freshness.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Local, no network, and **silent** unless something is wrong. Exit **3** — this session is serving
an older cached copy of THIS plugin than the one installed; a session pins its version at the first
call and never moves. Put it to the user (`AskUserQuestion`): reload (`/reload-plugins`) and re-run,
or carry on knowingly — and if you already put this question for this plugin in this session, just
note it and carry on; the check is stateless and will keep reporting. Exit **2** — could not
determine, which is not a pass. Exit **4**, or `No such file` / exit **127** — this call is wired
wrong and checked nothing; report it. Why: `docs/conventions.md` in `mzvonar/claude-skills-public`.

### 1. Verify ngrok is installed

```bash
ngrok version 2>&1 | head -1
```

If missing, tell the user to install it (`brew install ngrok` on macOS, otherwise https://ngrok.com/download), then stop. Don't try to install it for them — ngrok requires an auth token configured under the user's own account.

### 2. Verify the local port responds

A tunnel pointed at a dead port produces a confusing 502 from ngrok later — better to fail fast and tell the user.

```bash
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://localhost:<PORT><PATH-IF-ANY>
```

Any 2xx/3xx is fine. `Connection refused` (HTTP 000) → ask the user to start the local server first; don't proceed.

### 3. Check no stale tunnel is already running

```bash
pgrep -f "ngrok http" 2>/dev/null
```

ngrok's free plan allows one tunnel at a time. If a PID comes back, ask the user before killing it.

### 4. Start ngrok in the background

Log to a file rather than `/dev/null` — if the tunnel doesn't come up, the log is the only place to see why.

```bash
NGROK_LOG="${TMPDIR:-/tmp}/ngrok.log"
ngrok http <PORT> --log=stdout > "$NGROK_LOG" 2>&1 &
NGROK_PID=$!
```

### 5. Read the public URL from ngrok's local API

Don't grep the log — ngrok exposes `http://127.0.0.1:4040/api/tunnels` for tunnel introspection, and that's the canonical source.

```bash
sleep 2
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys,json; d=json.load(sys.stdin); [print(t['public_url']) for t in d['tunnels']]"
```

If this returns nothing:
- `tail "$NGROK_LOG"` — common causes: tunnel limit reached on free plan, no auth token configured, network blocked
- Report the actual error to the user; don't guess

### 6. Print the URL bare

**Output the URL with no angle brackets, no Markdown link syntax, on its own line.** Some renderers wrap URLs as `<https://...>` to autolink them, but that wrapping ends up in the user's clipboard when they copy and produces 404s when pasted into a browser. The user wants to copy-paste the URL directly.

If they asked you to share a specific path on the local server (e.g. `/diff-review.html`), append the path to the public URL when you tell them — `https://abc123.ngrok-free.app/diff-review.html`, not just the bare host.

Example output (note the formatting — bare URL, then PID):

```
URL: https://abc123.ngrok-free.app/diff-review.html
ngrok PID: 12345 — kill it with: kill 12345
```

### 7. Offer to open the URL

After printing, ask the user: *"Want me to open this in your default browser?"* If yes:

```bash
open "<full-url>"          # macOS
xdg-open "<full-url>"      # Linux
```

If they only want the URL on their phone, no need to open anything locally.

## Notes & gotchas

- **ngrok-free interstitial.** A fresh tunnel served to a browser that's never visited ngrok before may show a one-time "Visit Site" warning page. Clicking through proceeds to the real content. To bypass it programmatically (e.g. for `curl` or scripts), send the header `ngrok-skip-browser-warning: 1`.
- **Trailing junk in URLs.** If the user reports a 404 on the URL you gave them, double-check they haven't accidentally copied trailing characters (Markdown bold `**`, a closing paren, a period from the end of a sentence). The ngrok dashboard at `http://127.0.0.1:4040` shows the exact path that hit the tunnel — useful for diagnosing.
- **Don't expose sensitive ports without asking.** If the local server is an admin dashboard, real DB UI, or anything that touches production data, confirm with the user before tunneling.
- **One tunnel at a time** on the free plan. If a tunnel start fails, check for stale ngrok processes (`pgrep -f "ngrok http"`).

---
To change this skill, do not edit this copy: use `/dev-tools:update-skill`, or see `docs/updating-skills.md` in `mzvonar/claude-skills-public`.
