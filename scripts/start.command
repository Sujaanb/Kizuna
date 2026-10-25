#!/bin/sh
set -eu
KIZUNA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$KIZUNA_ROOT/scripts/env.sh"
cd "$KIZUNA_ROOT"
if [ ! -x .venv/bin/kizunapdf ]; then
    echo 'Run scripts/setup_mac.sh first.'; exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
    if command -v pnpm >/dev/null 2>&1; then pnpm --dir frontend build
    else echo 'Frontend missing. Run scripts/setup_mac.sh.'; exit 1; fi
fi
# A shell trap cleans up the child backend when Finder/Terminal stops this launcher.
.venv/bin/kizunapdf serve --host 127.0.0.1 --port 8787 &
KIZUNA_SERVER_PID=$!
trap 'kill "$KIZUNA_SERVER_PID" 2>/dev/null || true' EXIT INT TERM
.venv/bin/python - <<'PY'
import time, urllib.request, webbrowser
for _ in range(40):
    try:
        urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health',timeout=1)
        webbrowser.open('http://127.0.0.1:8787')
        break
    except OSError:
        time.sleep(.25)
PY
wait "$KIZUNA_SERVER_PID"
