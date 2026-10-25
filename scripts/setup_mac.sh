#!/bin/sh
set -eu
KIZUNA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$KIZUNA_ROOT/scripts/env.sh"
cd "$KIZUNA_ROOT"
uname -m
sw_vers
sysctl hw.memsize || true
xcode-select -p
for KIZUNA_TOOL in brew uv python3 node pnpm swift gh xelatex; do command -v "$KIZUNA_TOOL" || true; done
df -h .
if [ "$(uname -m)" != arm64 ]; then echo 'Local MLX inference requires Apple Silicon.'; exit 1; fi
if ! command -v uv >/dev/null 2>&1; then
    echo 'Install uv first: brew install uv (or the official uv installer), then rerun.'; exit 1
fi
uv sync --frozen --extra mlx --python 3.12
if ! command -v pnpm >/dev/null 2>&1; then
    echo 'Install Node LTS and pnpm: brew install node pnpm, then rerun.'; exit 1
fi
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
mkdir -p macos/VisionOCR/.build/release .tools/swift-module-cache
swiftc -O -module-cache-path "$KIZUNA_ROOT/.tools/swift-module-cache" macos/VisionOCR/Sources/VisionOCR/main.swift -o macos/VisionOCR/.build/release/VisionOCR
if ! command -v xelatex >/dev/null 2>&1; then
    echo 'Install BasicTeX from https://www.tug.org/mactex/ (the installer requires your authorization).'
    echo 'Then: sudo /Library/TeX/texbin/tlmgr install fontspec xcolor eso-pic textpos ragged2e setspace xecjk'
fi
.venv/bin/kizunapdf doctor || true
printf '\nSetup does not download model weights. Run: uv run kizunapdf model download\n'
