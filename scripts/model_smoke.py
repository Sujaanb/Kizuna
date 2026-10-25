"""Explicit local real-model smoke test; never downloaded or run in CI."""

import json
import time
from pathlib import Path

from kizunapdf.config import Settings
from kizunapdf.providers.mlx_translategemma import get_translator

provider = get_translator(Settings())
results = []
for source in [
    "こんにちは。よろしくお願いします。",
    "数式と図を保持します。",
    "売上はKZPHAZ円です。",
    "これはEnglishと日本語の文書です。",
]:
    start = time.monotonic()
    target = provider.translate(source)
    row = {"source": source, "target": target, "seconds": round(time.monotonic() - start, 3)}
    print(json.dumps(row, ensure_ascii=False), flush=True)
    results.append(row)
Path(".runtime").mkdir(exist_ok=True)
Path(".runtime/model_smoke.json").write_text(
    json.dumps(
        {
            "model": provider.model_id,
            "revision": provider.revision,
            "template_sha256": provider.template_sha256,
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    )
)
