#!/bin/sh
set -eu
KIZUNA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$KIZUNA_ROOT/scripts/env.sh"
exec "$KIZUNA_ROOT/.venv/bin/kizunapdf" doctor
