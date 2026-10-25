# Model setup

The only default model is `mlx-community/translategemma-4b-it-4bit` (~2.18 GB weights).
Review [Gemma Terms](https://ai.google.dev/gemma/terms) and the
[official model card](https://huggingface.co/google/translategemma-4b-it).
Then run `uv run kizunapdf model download` and confirm acceptance. For an already
reviewed automated setup use `--accept-gemma-terms`. The local UI exposes the same
explicit acceptance/download action. Setup scripts never fetch weights automatically.

The community repository was publicly downloadable during this installation. If Hugging
Face returns a gated-access error, open the official model page, accept its access terms
with your own account, run `uv run hf auth login`, then retry. Do not share credentials
or bypass access gates. Acceptance of terms remains required even for publicly available
community weights.

Default model directory: `.tools/models/translategemma` under this checkout. Override
with `KIZUNAPDF_MODEL_DIR`. A `download.json` receipt records exact Hub commit and terms
acceptance. `kizunapdf model status` reports readiness without downloading. An incomplete
folder is not ready; loading corrupt weights fails the job. The project-local model
cache is not part of Git, Python distributions, or document bundles.

`uv run python scripts/model_smoke.py` runs actual local inference and writes synthetic
results under `.runtime`. `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` can be set for explicit
offline enforcement at the model-library level. Real generation requires Metal access;
a restricted tool sandbox can deny the GPU even when Terminal works. Run the same
command in a normal local Terminal in that case. Never substitute fake translations as
proof of model readiness.

One provider is loaded lazily and reused by the service. Default concurrency is one.
Do not run several model processes on a 16 GB Mac. Close other memory-heavy apps if
necessary. Cold loading and long documents can take longer; the current measured sample
is not a general speed or quality benchmark.
