import re
from collections import Counter

JAPANESE = re.compile(
    r"[\u3041-\u3096\u309d-\u309f\u30a1-\u30fa\u30fd-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9d]"
)
LITERALS = re.compile(
    r"https?://[^\s\u3000-\u9fff]+|10\.\d{4,9}/[-._;()/A-Za-z0-9]+|"
    r"\[[0-9, –-]+\]|[¥￥$€£]?[−-]?\d[\d,]*(?:\.\d+)?(?:[/:-]\d+)*(?:[%％]|\s?(?:kg|mm|cm|km|mL|mg|Hz|°C))?"
)
TOKEN = re.compile(r"KZPH[A-Z]+Z")


def japanese(text: str) -> bool:
    return bool(JAPANESE.search(text))


def token_name(index: int) -> str:
    s = ""
    while True:
        s = chr(65 + index % 26) + s
        index = index // 26 - 1
        if index < 0:
            return "KZPH" + s + "Z"


def protect(text: str, glossary: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    if TOKEN.search(text):
        raise ValueError("Source contains reserved protection marker")
    mapping = {}
    terms = glossary or {}
    pattern = (
        re.compile(
            "|".join(re.escape(s) for s in sorted(terms, key=len, reverse=True))
            + "|"
            + LITERALS.pattern
        )
        if terms
        else LITERALS
    )

    def replace(match):
        marker = token_name(len(mapping))
        mapping[marker] = terms.get(match[0], match[0])
        return marker

    return pattern.sub(replace, text), mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    if Counter(TOKEN.findall(text)) != Counter(mapping.keys()):
        raise ValueError("Protected placeholders missing, duplicated, or changed; edit translation")
    return TOKEN.sub(lambda m: mapping[m[0]], text)


def literal_errors(source: str, target: str) -> list[str]:
    before, after = Counter(LITERALS.findall(source)), Counter(LITERALS.findall(target))
    return [
        f"Protected literal count differs: {s}"
        for s in before.keys() | after.keys()
        if before[s] != after[s]
    ]


def restore_verified_literals(source: str, target: str) -> str:
    """Accept only equal literal multisets; normalize thousands separators for comparison.

    Restore the source spelling after equivalence is established. This intentionally
    refuses currency conversion, date reordering, and missing/extra numeric literals.
    """
    import unicodedata
    from collections import defaultdict, deque

    def canonical(s):
        s = unicodedata.normalize("NFKC", s).replace("−", "-")
        if re.fullmatch(r"[¥$€£]?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?", s):
            s = s.replace(",", "")
        return s

    original = LITERALS.findall(source)
    generated = LITERALS.findall(target)
    if Counter(map(canonical, original)) != Counter(map(canonical, generated)):
        raise ValueError("Fallback translation changed, omitted, or invented a protected literal")
    spellings = defaultdict(deque)
    for value in original:
        spellings[canonical(value)].append(value)
    return LITERALS.sub(lambda m: spellings[canonical(m[0])].popleft(), target)
