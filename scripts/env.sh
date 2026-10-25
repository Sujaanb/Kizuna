#!/bin/sh
# Source from another project script after setting KIZUNA_ROOT.
export PATH="$KIZUNA_ROOT/.venv/bin:$KIZUNA_ROOT/.tools/bootstrap/bin:$KIZUNA_ROOT/.tools/texlive/bin/universal-darwin:/Library/TeX/texbin:$PATH"
# Optional Codex-bundled runtimes, only used if a normal install is absent.
KIZUNA_RUNTIME="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if ! command -v node >/dev/null 2>&1 && [ -x "$KIZUNA_RUNTIME/node/bin/node" ]; then
    export PATH="$KIZUNA_RUNTIME/node/bin:$KIZUNA_RUNTIME/bin/fallback:$PATH"
fi
export UV_CACHE_DIR="$KIZUNA_ROOT/.tools/uv-cache"
export HF_HOME="$KIZUNA_ROOT/.tools/hf"
