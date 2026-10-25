# Contributing

KizunaPDF is AGPL-3.0-only. Contributions must be compatible with that license.
Never add customer PDFs, translation caches, model weights, tokens or real personal data.

Use Python 3.12 and Node 24. Run `uv sync --extra mlx` on Apple Silicon, or `uv sync`
for tests without MLX. Run `uv run ruff check src tests examples scripts`,
`uv run ruff format --check src tests examples scripts`, and `uv run pytest`.
Build the UI with `pnpm --dir frontend install --frozen-lockfile` and
`pnpm --dir frontend build`.

Tests marked integration require XeLaTeX and a Japanese system font. Real MLX tests are
explicit scripts, never part of default CI. Include a synthetic regression fixture for
geometry, source-removal, protection or security changes. Review both rendered pages and
QA JSON; a zero exit code alone is insufficient for a layout change.

File an issue with app/tool versions, sanitized reproduction steps, and a synthetic
example. Do not attach confidential documents or raw private job logs.
