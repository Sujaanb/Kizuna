# Setup and daily use

## This checkout

The local setup performed on 2026-10-26 installed Python dependencies in `.venv`, TeX
Live 2026 under `.tools/texlive`, and the accepted TranslateGemma model under
`.tools/models/translategemma`. The compiled UI is `frontend/dist`; the Swift helper is
`macos/VisionOCR/.build/release/VisionOCR`. These generated files are ignored by Git.

From a normal Mac Terminal:

```sh
cd /path/to/Kizuna
./scripts/doctor.sh
./scripts/start.command
```

The launcher binds `http://127.0.0.1:8787`, opens your browser and stays in the Terminal.
Stop it with Ctrl-C. Finder users can double-click `scripts/start.command`; if macOS
warns about downloaded source, inspect it and use Finder's normal Open workflow. Do not
disable Gatekeeper globally. The same commands work in a Codex/VS Code integrated
terminal. No cloud account, Docker, payment or API key is required for daily use.

The launcher detects standard installed tools, then this checkout's local tools, then
Codex's bundled Node/pnpm only when normal commands are missing. For direct CLI use:

```sh
.venv/bin/kizunapdf model status
.venv/bin/kizunapdf translate tests/fixtures/generated/native.pdf --output-dir ./out
```

To use the conventional `uv run` commands in a shell without uv on PATH:

```sh
KIZUNA_ROOT="$PWD"
. ./scripts/env.sh
uv run kizunapdf doctor
```

## Fresh Mac / cloned repository

Require Apple Silicon, macOS 13 or later with supported Japanese Vision, at least 16 GB
RAM recommended, several GB free disk, and Apple Command Line Tools. Inspect first:

```sh
uname -m
sw_vers
sysctl hw.memsize
xcode-select -p
which brew uv python3 node pnpm swift gh xelatex
df -h .
```

If needed, run `xcode-select --install` and finish Apple's installer. Install uv, Node LTS
and pnpm using their official installers or `brew install uv node pnpm`. These are
explicit dependency downloads. Then:

```sh
./scripts/setup_mac.sh
```

The script resolves Python 3.12 with uv, installs the lockfile (including MLX only on
arm64 macOS), installs/builds the UI, compiles Vision, and runs doctor. It never invokes
sudo or accepts licenses for you. If XeLaTeX is missing, install BasicTeX 2026 from
[MacTeX](https://www.tug.org/mactex/) and authorize its normal installer yourself. Repair
packages explicitly:

```sh
sudo /Library/TeX/texbin/tlmgr update --self
sudo /Library/TeX/texbin/tlmgr install fontspec xcolor eso-pic geometry textpos ragged2e setspace xecjk
```

Use sudo only for a system installation you own. A user/project-local TeX Live needs
no sudo; run its absolute `bin/universal-darwin/tlmgr` instead. `KIZUNAPDF_XELATEX` may
point to another existing XeLaTeX. `doctor` finds `/Library/TeX/texbin` even if your shell
PATH omits it. English uses Arial when available, otherwise Latin Modern Sans.
Characters absent from that font use Hiragino Sans (or Noto Sans CJK JP), then Apple
Symbols (or DejaVu Sans). Full-width digits and symbols retain their original Unicode
values. If no local font covers a character, compilation reports its code point and
region ID and blocks export. Synthetic Japanese fixtures require macOS Hiragino Sans.

Follow [MODEL_SETUP.md](MODEL_SETUP.md), accept Gemma terms, and run:

```sh
uv run kizunapdf model download
uv run kizunapdf model status
uv run kizunapdf doctor
./scripts/start.command
```

## Sample and translation

```sh
uv run python examples/synthetic_fixtures_generator.py
uv run kizunapdf translate tests/fixtures/generated/native.pdf --output-dir ./out
uv run kizunapdf validate ./out/native.en.pdf --manifest ./out/manifest.json
```

The generator creates original synthetic Japanese PDFs: native prose/artwork, two
columns, financial table, science, geometry variants, scans, encryption and invalid
input. It never uses your documents. Generated PDFs remain ignored by Git.

For your own PDF:

```sh
uv run kizunapdf translate '/absolute/path/japanese.pdf' --output-dir './out'
# Optional password prompt; never put a password in a shell argument:
uv run kizunapdf translate '/absolute/path/encrypted.pdf' --password --output-dir './out'
# Explicit experimental scan opt-in:
uv run kizunapdf translate '/absolute/path/scan.pdf' --experimental-scans --output-dir './out'
```

Exit codes: 0 = automated gates passed; 2 = needs review (a draft may exist); 1 = failed.
Always inspect `qa_report.json`. `validate` with just a manifest checks page geometry;
it does not reproduce the original job's content/visual checks.

## Browser workflow

Choose or drop a PDF, optionally entering its runtime password and enabling scans
**before upload**. Native text is inspected locally. Run environment checks from the
model badge. Click Translate locally. Progress shows translation, removal, compilation
and QA. Stop requests cancellation at safe boundaries. Return to recent jobs after
restart to resume saved segments. Keep one application process per data directory.

Use linked page/zoom controls and synchronized scroll. Click a page region or region
list row to inspect Japanese, English, role and extraction confidence. Edit the English,
change reading order, or mark translate/protect/ignore. Protection changes need a reason.
Save & rebuild performs no model inference. The current implementation recompiles the
document; optimization to only affected pages is deferred. Rebuild is also available in
the toolbar. Quality issues can navigate to their page/region. The UI never labels a
needs-review result as verified. Complex scans require manual correction outside this
limited cleanup path.

Download English PDF, LaTeX bundle and QA JSON once available. English is selectable in
the PDF; preserved formula text and artwork retain their source representation. The
preview region boxes are interactive; full PDF text selection can be done in a PDF reader.

## Editable bundle and offline rebuild

```sh
uv run kizunapdf rebuild './out/native.kizunapdf.zip' --output './rebuilt.pdf'
unzip './out/native.kizunapdf.zip' -d './my_document.kizunapdf'
uv run kizunapdf rebuild './my_document.kizunapdf' --output './rebuilt.pdf'
# `kizunapdf build` is an alias; scripts/rebuild.sh is also supplied.
```

Edit `tex/pages/page_0001.tex` to adjust typesetting. It contains plain escaped English
strings, explicit positions and reusable background assets. If you change translated
words, update `target` in `ir/document_ir.json` too, so content QA expects the edited
text. Rebuild compiles saved TeX as written, without translation or regeneration. Each
page can be compiled from its `tex/pages` directory with `xelatex -no-shell-escape`;
use the app rebuild command to merge and restore all original boxes/origins/rotation.
Treat editable bundles as private and compile only trusted TeX.

After dependencies/model are installed, disconnect Wi-Fi/network and repeat translation
and rebuild. Also test with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`. The service has no
document network calls; a cached model is mandatory. Repository tests cannot prove
behavior of every OS/library component; do not call a library offline test an OS-level
network capture.

## Tests, performance and publication

```sh
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run pytest
pnpm --dir frontend build
uv run python scripts/model_smoke.py
uv run python scripts/real_integration.py
./scripts/benchmark.sh
```

Default CI never downloads model weights or runs real inference. Local integration
requires XeLaTeX/Hiragino Sans. Benchmark receipts contain actual elapsed time and peak
process RSS; they are measurements of the sample, not throughput promises.

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for publication status.
This checkout's `origin` is the existing [Sujaanb/Kizuna repository](https://github.com/Sujaanb/Kizuna).
Pushing requires GitHub authentication. After installing GitHub CLI if needed, sign in
and configure Git to use it:

```sh
gh auth login
gh auth setup-git
gh auth status
git status --short
git remote -v
git push -u origin main
```

Check that `origin` points to the intended repository before pushing. Never force-push
or overwrite an existing repository. Model
weights, source documents, private prompts, runtime output and credentials are ignored.
The application license is AGPL-3.0-only; model licensing remains separate.

For storage/deletion details see [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md); for
known issues see [TROUBLESHOOTING.md](TROUBLESHOOTING.md) and [QUALITY.md](QUALITY.md).
