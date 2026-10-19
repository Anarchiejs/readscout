"""Deterministic reading of logs: events grouped with their first and last occurrence, multi-line traces kept whole.

The code finds the events and their positions; interpretation (cause, relations) stays with the reader of the receipt.
A group is a message shape (numbers, hex and timestamps ignored) so that a thousand repeats become one entry, but the
distinct values (hosts, ids, ports...) of the repeats are kept, because two similar events can concern different resources.
"""
import json
import re
from dataclasses import dataclass, field

from .text import Line

ERROR_LINE = re.compile(r'(?i)\b(error|err!|exception|traceback|fatal|fail(ed|ure)?|panic|assert|denied|refused|timed? ?out|cannot|unable|undefined|not found|warn(ing)?)\b|^\s*at |^E\s')
TIMESTAMP = re.compile(r'^\s*[\[(]?(?:\d{4}-\d\d-\d\d[T ]|\d\d/\w{3}/\d{4}:)?\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?[\])]?\s*')
DATE_ONLY = re.compile(r'^\s*[\[(]?\d{4}-\d\d-\d\d[\])]?\s*')
VALUE = re.compile(r'[\w.:/@-]*\d[\w.:/@-]*')
MAX_VARIANTS = 6
# The level field, in capitals near the start of the line (after the timestamp) or as level=...: words in the message do not count.
LEVEL = re.compile(r'(?<![\w.-])(TRACE|DEBUG|FINE|INFO|NOTICE|WARN|WARNING|ERROR|ERR|FATAL|CRITICAL|CRIT|PANIC|SEVERE|ALERT|EMERG)(?![\w.-])'
                   r'|\blevel=["\']?(\w+)', re.I)
SEVERE = {'ERROR', 'ERR', 'FATAL', 'CRITICAL', 'CRIT', 'PANIC', 'SEVERE', 'ALERT', 'EMERG'}
SEVERE_WORDS = re.compile(r'(?i)\b(error|exception|traceback|fatal|panic)\b')
NOTABLE = SEVERE | {'WARN', 'WARNING'}
# A hex id (trace, commit, request) mixes digits and letters: without this every line of a traced log has its own shape.
HEX_ID = re.compile(r'\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{6,}\b')
JSON_LEVEL_KEYS = ('level', 'severity', 'lvl', 'loglevel', 'log.level', 'levelname')
# Common/combined access log: the status follows the quoted request line. It is the event level, the wording is not.
ACCESS_STATUS = re.compile(r'"(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|CONNECT|TRACE) [^"]*" ([1-5]\d\d) ')
MAX_OCCURRENCES = 12                # the start of each repeat is kept up to this many, so few repeats can each be cited


@dataclass
class Group:
    shape: str
    first: list[Line]                   # the first occurrence, whole (a trace is one unit)
    last_start: Line                    # where the last occurrence starts
    count: int = 1
    variants: list = field(default_factory=list)
    variants_omitted: bool = False
    starts: list = field(default_factory=list)      # where each occurrence starts, up to MAX_OCCURRENCES


def _strip_time(text: str) -> str:
    without_time = TIMESTAMP.sub('', text, count=1)
    return without_time if without_time != text else DATE_ONLY.sub('', text, count=1)


def shape(text: str) -> str:
    body = _strip_time(text).strip().lower()
    body = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|0x[0-9a-f]+', '#', body)
    body = re.sub(r'\d+', '#', HEX_ID.sub('#', body))
    status = access_status(text)        # a 502 and a 404 of the same route are different events
    return re.sub(r'\s+', ' ', body) + (f' status={status}' if status is not None else '')


def json_level(text: str) -> str | None:
    """The level field of a JSON log line, wherever it is in the object."""
    body = text.strip()
    if not (body.startswith('{') and body.endswith('}')):
        return None
    try:
        record = json.loads(body)
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    for key in JSON_LEVEL_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def access_status(text: str) -> int | None:
    m = ACCESS_STATUS.search(text)
    return int(m.group(1)) if m else None


def is_event(text: str) -> bool:
    """A line worth listing: error-like wording, a WARN or worse JSON level, or an access-log status of 400 or more."""
    status = access_status(text)
    if status is not None:
        return status >= 400
    level = json_level(text)
    if level is not None and level in NOTABLE:
        return True
    return bool(ERROR_LINE.search(text))


def is_error(text: str) -> bool:
    """Error level: read from the level field when the line has one, from the wording otherwise."""
    status = access_status(text)
    if status is not None:
        return status >= 500
    level = json_level(text)
    if level is not None:
        return level in SEVERE
    head = _strip_time(text)[:48]
    for m in LEVEL.finditer(head):
        if m.group(1) and not m.group(1).isupper():
            continue        # "error" written in lower case is a word of the message, not the level field
        return (m.group(1) or m.group(2)).upper() in SEVERE
    return bool(SEVERE_WORDS.search(text))


def _continues(text: str) -> bool:
    # The exception line a JVM test report prints under its [ERROR] line, before the indented frames, belongs to it.
    return bool(re.match(r'\s+\S|Caused by|E\s|\.\.\. \d+ more|[a-z][\w$]*(?:\.[\w$]+)+(?:Exception|Error|Failure)\b', text))


def units(lines: list[Line]) -> list[list[Line]]:
    """Event units: an error-like line with the lines that belong to it (indented frames, `Caused by`, pytest `E` lines,
    the exception line that closes a Python traceback). A trace is never cut at a fixed distance from the keyword."""
    out, i = [], 0
    while i < len(lines):
        if not is_event(lines[i].text) or (_continues(lines[i].text) and not re.match(r'E\s', lines[i].text)):
            i += 1
            continue
        j = i + 1
        while j < len(lines) and lines[j].no == lines[j - 1].no + 1 and _continues(lines[j].text):
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
        if len(g.starts) < MAX_OCCURRENCES:
            g.starts.append(unit[0])
        for v in values:
            if v not in g.variants:
                if len(g.variants) < MAX_VARIANTS:
                    g.variants.append(v)
                else:
                    g.variants_omitted = True
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
