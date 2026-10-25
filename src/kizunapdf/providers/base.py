from typing import Protocol


class Translator(Protocol):
    model_id: str
    revision: str

    def translate(self, text: str, cancel=None) -> str: ...
