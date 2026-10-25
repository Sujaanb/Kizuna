"""Strict fixture-only test double. Never selectable by the production UI or CLI."""


class FakeTranslator:
    model_id = "test-only/human-reference"
    revision = "1"

    def __init__(self, translations: dict[str, str]):
        self.translations = translations

    def translate(self, text: str, cancel=None) -> str:
        if cancel and cancel():
            raise InterruptedError("Cancelled")
        if text not in self.translations:
            raise ValueError(f"Missing human-authored fixture translation: {text!r}")
        return self.translations[text]
