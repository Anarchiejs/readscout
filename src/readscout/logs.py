"""Deterministic reading of logs: events grouped with their first and last occurrence, multi-line traces kept whole.

The code finds the events and their positions; interpretation (cause, relations) stays with the reader of the receipt.
A group is a message shape (numbers, hex and timestamps ignored) so that a thousand repeats become one entry, but the
distinct values (hosts, ids, ports...) of the repeats are kept, because two similar events can concern different resources.
"""
import re
from dataclasses import dataclass, field

from .text import Line

ERROR_LINE = re.compile(r'(?i)\b(error|err!|exception|traceback|fatal|fail(ed|ure)?|panic|assert|denied|refused|timed? ?out|cannot|unable|undefined|not found|warn(ing)?)\b|^\s*at |^E\s')
TIMESTAMP = re.compile(r'^\s*[\[(]?(?:\d{4}-\d\d-\d\d[T ]|\d\d/\w{3}/\d{4}:)?\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?[\])]?\s*')
DATE_ONLY = re.compile(r'^\s*[\[(]?\d{4}-\d\d-\d\d[\])]?\s*')
VALUE = re.compile(r'[\w.:/@-]*\d[\w.:/@-]*')
MAX_UNIT_LINES = 40
MAX_VARIANTS = 6


@dataclass
class Group:
    shape: str
    first: list[Line]                   # the first occurrence, whole (a trace is one unit)
    last_start: Line                    # where the last occurrence starts
    count: int = 1
    variants: list = field(default_factory=list)


def _strip_time(text: str) -> str:
    return TIMESTAMP.sub('', DATE_ONLY.sub('', text, count=1), count=1)


def shape(text: str) -> str:
    body = _strip_time(text).strip().lower()
    body = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|0x[0-9a-f]+|\d+', '#', body)
    return re.sub(r'\s+', ' ', body)


def _continues(text: str) -> bool:
    return bool(re.match(r'\s+\S|Caused by|E\s|\.\.\. \d+ more', text))


def units(lines: list[Line]) -> list[list[Line]]:
    """Event units: an error-like line with the lines that belong to it (indented frames, `Caused by`, pytest `E` lines,
    the exception line that closes a Python traceback). A trace is never cut at a fixed distance from the keyword."""
    out, i = [], 0
    while i < len(lines):
        if not ERROR_LINE.search(lines[i].text) or (_continues(lines[i].text) and not re.match(r'E\s', lines[i].text)):
            i += 1
            continue
        j = i + 1
        while j < len(lines) and j - i < MAX_UNIT_LINES and lines[j].no == lines[j - 1].no + 1 and _continues(lines[j].text):
            j += 1
        if _strip_time(lines[i].text).lstrip().startswith('Traceback') and j < len(lines) and lines[j].no == lines[j - 1].no + 1 and not _continues(lines[j].text):
            j += 1          # the exception line that ends a Python traceback is not indented
        out.append(lines[i:j])
        i = j
    return out


def group_events(lines: list[Line]) -> list[Group]:
    groups: dict[str, Group] = {}
    for unit in units(lines):
        key = shape(unit[0].text) + ' | ' + (shape(unit[-1].text) if len(unit) > 1 else '')
        values = VALUE.findall(_strip_time(unit[0].text))
        g = groups.get(key)
        if g is None:
            groups[key] = g = Group(key, unit, unit[0])
        else:
            g.count += 1
            g.last_start = unit[0]
        for v in values:
            if v not in g.variants and len(g.variants) < MAX_VARIANTS:
                g.variants.append(v)
    return list(groups.values())


def prefilter(lines: list[Line], keep_head=20, keep_tail=60, context=2) -> list[Line]:
    """For the model: the head, the tail, and for each event group its first occurrence (whole, with context) and the
    start of its last occurrence. Repeats are dropped, but the first and the last occurrence of every group stay."""
    pos = {id(ln): i for i, ln in enumerate(lines)}
    keep = set(range(min(keep_head, len(lines)))) | set(range(max(0, len(lines) - keep_tail), len(lines)))
    for g in group_events(lines):
        a, b = pos[id(g.first[0])], pos[id(g.first[-1])]
        keep.update(range(max(0, a - context), min(len(lines), b + context + 1)))
        keep.add(pos[id(g.last_start)])
    return [lines[i] for i in sorted(keep)]
