#!/bin/sh
set -eu
KIZUNA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$KIZUNA_ROOT/scripts/env.sh"
cd "$KIZUNA_ROOT"
.venv/bin/python examples/synthetic_fixtures_generator.py
exec /usr/bin/time -l .venv/bin/kizunapdf translate tests/fixtures/generated/native.pdf --output-dir output/benchmark
