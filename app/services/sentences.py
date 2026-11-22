import re

READER_SEGMENTER_VERSION = "pathya-sentences/3"
SENTENCE_BLOCK_TYPES = frozenset({"heading", "paragraph", "list_item"})

_ABBREVIATIONS = frozenset(
    "e.g. i.e. etc. vs. cf. fig. figs. eq. eqs. no. nos. dr. mr. mrs. ms. "
    "approx. p. pp. vol. ch. sec.".split()
)
_BOUNDARY = re.compile(r"""[.!?।॥]+["'”’»«)}\]]*(?=\s|$)""")
_LIST_MARKER = re.compile(r"\(?(?:\d{1,3}|[ivxlcdm]{1,6}|[a-z])[.)]", re.IGNORECASE)


def _ends_with_abbreviation(text: str, terminator: int) -> bool:
    if text[terminator] != ".":
        return False
    start = terminator
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    return text[start : terminator + 1].lower().lstrip("(\"'«»") in _ABBREVIATIONS


def sentence_ranges(text: str) -> list[tuple[int, int]]:
    """Return contiguous code-point ranges into unchanged reader text."""
    ranges: list[tuple[int, int]] = []
    start = 0
    length = len(text)
    for match in _BOUNDARY.finditer(text):
        end = match.end()
        after_punctuation = end
        while end < length and text[end].isspace():
            end += 1
        if end == length or "a" <= text[end] <= "z":
            continue
        if _ends_with_abbreviation(text, match.start()) or _LIST_MARKER.fullmatch(
            text[start:after_punctuation].strip()
        ):
            continue
        ranges.append((start, end))
        start = end
    if start < length:
        ranges.append((start, length))
    return ranges
