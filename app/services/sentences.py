import re

_BOUNDARY = re.compile(r"""[.!?।॥]+["'”’»)}\]]*\s+""")
_ABBREVIATION = re.compile(r"\b(?:e\.g|i\.e|etc|vs|fig|eq|no|dr|mr|mrs|ms|approx|cf)\.$", re.I)
_LIST_NUMBER = re.compile(r"\s*[0-9]+\.")
_DIGIT_STOP = re.compile(r"[0-9]\.$")


def sentence_ranges(text: str) -> list[tuple[int, int]]:
    """Return contiguous code-point ranges into unchanged reader text."""
    ranges = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        end = match.end()
        head = text[start:end].rstrip()
        if _ABBREVIATION.search(head) or _LIST_NUMBER.fullmatch(head):
            continue
        if end < len(text) and text[end] in "0123456789" and _DIGIT_STOP.search(head):
            continue
        ranges.append((start, end))
        start = end
    if start < len(text):
        ranges.append((start, len(text)))
    return ranges
