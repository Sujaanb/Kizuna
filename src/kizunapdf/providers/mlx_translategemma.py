from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from kizunapdf.config import MODEL_ID, TERMS_URL, Settings

_LOCK = threading.Lock()
_INSTANCE = None


def messages(text: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "source_lang_code": "ja", "target_lang_code": "en", "text": text}
            ],
        }
    ]


def model_status(settings: Settings) -> dict:
    p = settings.model_dir
    files = ["config.json", "tokenizer_config.json", "tokenizer.json", "download.json"]
    ready = all((p / f).is_file() for f in files) and bool(list(p.glob("*.safetensors")))
    receipt = json.loads((p / "download.json").read_text()) if ready else {}
    return {
        "ready": ready,
        "model_id": MODEL_ID,
        "path": str(p),
        "terms_url": TERMS_URL,
        "revision": receipt.get("revision"),
        "download_bytes": 2_180_000_000,
    }


def download_model(settings: Settings, accepted_terms: bool) -> dict:
    if not accepted_terms:
        raise ValueError(f"Review and accept Gemma Terms first: {TERMS_URL}")
    import shutil

    from huggingface_hub import HfApi, snapshot_download

    settings.model_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(settings.model_dir).free < 4_000_000_000:
        raise ValueError("Model setup requires at least 4 GB free disk space")
    info = HfApi().model_info(MODEL_ID)
    snapshot_download(
        MODEL_ID,
        revision=info.sha,
        local_dir=settings.model_dir,
        allow_patterns=["*.json", "*.safetensors", "*.model", "*.jinja", "LICENSE*", "README*"],
    )
    (settings.model_dir / "download.json").write_text(
        json.dumps(
            {
                "model_id": MODEL_ID,
                "revision": info.sha,
                "terms": TERMS_URL,
                "accepted_terms": True,
                "timestamp": time.time(),
            },
            indent=2,
        )
    )
    return model_status(settings)


class MLXTranslator:
    model_id = MODEL_ID

    def __init__(self, settings: Settings):
        self.settings = settings
        status = model_status(settings)
        if not status["ready"]:
            raise RuntimeError(
                "Model is not cached. Run kizunapdf model download after accepting Gemma Terms."
            )
        self.revision = status["revision"]
        self.model = self.tokenizer = None

    def _load(self):
        if self.model is None:
            from mlx_lm import load

            # A filesystem Path avoids implicit Hub resolution. This path is checked before load.
            self.model, self.tokenizer = load(Path(self.settings.model_dir))
            # The community snapshot declares only <eos>; real TranslateGemma
            # generations terminate with the template's <end_of_turn> token.
            # Resolve its ID through the downloaded tokenizer, never a magic number.
            self.tokenizer.add_eos_token("<end_of_turn>")
            if not self.tokenizer.chat_template:
                raise RuntimeError("Downloaded tokenizer has no structured chat template")
            prompt = self.tokenizer.apply_chat_template(
                messages("こんにちは。"), tokenize=False, add_generation_prompt=True
            )
            self.template_sha256 = hashlib.sha256(self.tokenizer.chat_template.encode()).hexdigest()
            if "こんにちは。" not in prompt:
                raise RuntimeError("Tokenizer failed structured TranslateGemma template validation")

    def _chunks(self, text: str) -> list[str]:
        def count(t):
            return len(
                self.tokenizer.apply_chat_template(
                    messages(t), tokenize=True, add_generation_prompt=True
                )
            )

        if count(text) <= self.settings.max_input_tokens:
            return [text]
        import re

        sentences = re.split(r"(?<=[。！？\n])", text)
        result, current = [], ""
        for sentence in sentences:
            if count(sentence) > self.settings.max_input_tokens:
                raise ValueError(
                    "A single sentence exceeds the safe token budget; split the region manually"
                )
            if count(current + sentence) > self.settings.max_input_tokens:
                result.append(current)
                current = sentence
            else:
                current += sentence
        if current:
            result.append(current)
        return result

    def translate(self, text: str, cancel=None) -> str:
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        with _LOCK:
            self._load()
            translated = []
            for chunk in self._chunks(text):
                prompt = self.tokenizer.apply_chat_template(
                    messages(chunk), tokenize=False, add_generation_prompt=True
                )
                started = time.monotonic()
                output, last = [], None
                for response in stream_generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=self.settings.max_output_tokens,
                    sampler=make_sampler(temp=0),
                ):
                    if cancel and cancel():
                        raise InterruptedError("Translation cancelled")
                    if time.monotonic() - started > self.settings.inference_timeout:
                        raise TimeoutError("Model inference exceeded timeout")
                    output.append(response.text)
                    last = response
                if last is None or last.finish_reason == "length":
                    raise ValueError(
                        "Model output hit its token limit; no truncated translation accepted"
                    )
                target = "".join(output).strip()
                if not target:
                    raise ValueError("Model returned an empty translation")
                translated.append(target)
            return " ".join(translated)


def get_translator(settings: Settings) -> MLXTranslator:
    global _INSTANCE
    if _INSTANCE is None or _INSTANCE.settings.model_dir != settings.model_dir:
        _INSTANCE = MLXTranslator(settings)
    return _INSTANCE
