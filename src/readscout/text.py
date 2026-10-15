"""File access, chunking and the deterministic check that turns model quotes into real line numbers."""
import bisect
import re
from dataclasses import dataclass
from pathlib import Path

SECRET = re.compile(r'-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----[\s\S]*?-----END[^-]*-----'
                    r'|\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}'
                    r'|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{30,})\b')
# key = value, key: value and "key": "value" (JSON), also for prefixed or suffixed names (client_secret, DB_PASSWORD, authToken).
ASSIGNED_SECRET = re.compile(r'(?i)(\b[\w.-]*(?:api[_-]?key|password|passwd|secret|token|private[_-]?key)[\w-]*["\']?\s*[:=]\s*["\']?)[^\s"\',}]{12,}')
SKIPPED_DIRS = {'.git', '.hg', '.svn', '.ssh', '.gnupg', '.aws', '.azure', '.kube', '.docker', '.claude', '.codex',
                'node_modules', '.venv', 'venv', '__pycache__'}
SKIPPED_SUFFIXES = {'.pem', '.key', '.pfx', '.p12', '.p8', '.jks', '.keystore', '.kdbx', '.gpg', '.sqlite', '.db',
                    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.pdf', '.zip', '.gz', '.7z', '.exe', '.dll', '.so',
                    '.dylib', '.woff', '.woff2', '.ttf', '.mp3', '.mp4'}
SKIPPED_NAMES = {'.npmrc', '.pypirc', '.netrc', '.git-credentials', 'id_rsa', 'id_ed25519', 'id_ecdsa', 'id_dsa',
                 'credentials', 'credentials.json', 'secrets.json', 'service-account.json'}
MAX_FILE_BYTES = 2_000_000
MAX_LINE_CHARS = 4000      # a minified one-line file must not overflow the model's context in one piece


class AccessError(ValueError):
    pass


@dataclass
class Line:
    path: str   # path as given by the caller (relative to its root when possible)
    no: int     # 1-based line number in the original file
    text: str
    cut: bool = False   # the line was longer than MAX_LINE_CHARS and its end is not shown to the model


def resolve(path: str, roots: list[Path]) -> tuple[Path, str]:
    """Return the real file path and a display path.

    The agent decides what to read: any file on this machine is allowed, relative paths start at the first root (the
    folder the agent works in). Only sensitive or binary files are refused. The display path is relative to the folder
    the file is in (a root, else the home folder) so that `.git` or `.ssh` in the path are recognised, else absolute.
    """
    p = Path(path).expanduser()
    candidates = [p] if p.is_absolute() else [r / p for r in roots]
    for c in candidates:
        real = c.resolve()
        if not real.is_file():
            continue
        base = next((r.resolve() for r in sorted(roots, key=lambda r: -len(r.resolve().parts)) if real.is_relative_to(r.resolve())), None)
        if base is None:
            home = Path.home().resolve()
            base = home if real.is_relative_to(home) else None
        rel = real.relative_to(base) if base else Path(*real.parts[1:])
        if is_sensitive(rel.parts, real.name):
            raise AccessError(f'Sensitive or binary file refused: {path}')
        in_root = any(real.is_relative_to(r.resolve()) for r in roots)
        return real, (rel.as_posix() if in_root else real.as_posix())
    raise AccessError(f'File not found: {path}')


def _mask(m: re.Match) -> str:
    # Keep the number of lines: a multi-line key must not shift the line numbers of everything below it.
    return '[REDACTED]' + '\n' * m.group(0).count('\n')


def redact(text: str) -> str:
    return ASSIGNED_SECRET.sub(r'\1[REDACTED]', SECRET.sub(_mask, text))


def is_sensitive(rel_parts, name: str) -> bool:
    """Case-insensitive: Windows and macOS file systems treat `.ENV` and `.Git` as `.env` and `.git`."""
    return (any(p.lower() in SKIPPED_DIRS or p.lower().startswith('.env') for p in rel_parts)
            or Path(name).suffix.lower() in SKIPPED_SUFFIXES or name.lower() in SKIPPED_NAMES)


def load_lines(path: str, roots: list[Path], label: str | None = None) -> list[Line]:
    real, shown = resolve(path, roots)
    shown = label or shown
    if real.stat().st_size > MAX_FILE_BYTES:
        raise AccessError(f'File larger than {MAX_FILE_BYTES // 1_000_000} MB: {path}')
    raw = real.read_bytes()
    if b'\0' in raw[:8192]:
        raise AccessError(f'Binary file refused: {path}')
    text = redact(raw.decode('utf-8', errors='replace'))
    return [Line(shown, i, t if len(t) <= MAX_LINE_CHARS else t[:MAX_LINE_CHARS] + ' [line truncated]', len(t) > MAX_LINE_CHARS)
            for i, t in enumerate(text.splitlines(), 1)]


def render(lines: list[Line]) -> str:
    """Show lines with their real numbers, with a header whenever the file changes."""
    out, current = [], None
    for ln in lines:
        if ln.path != current:
            current = ln.path
            out.append(f'===== FILE {current} =====')
        out.append(f'{ln.no}| {ln.text}')
    return '\n'.join(out)


def chunk(lines: list[Line], max_chars: int) -> list[list[Line]]:
    """Split on line boundaries so that each rendered chunk stays under max_chars."""
    chunks, cur, size, current = [], [], 0, None
    for ln in lines:
        cost = len(ln.text) + len(str(ln.no)) + 3
        if ln.path != current or not cur:       # render() adds a "===== FILE x =====" header on every file change
            cost += len(ln.path) + 16
            current = ln.path
        if cur and size + cost > max_chars:
            chunks.append(cur)
            cur, size, current = [], 0, ln.path
            cost = len(ln.text) + len(str(ln.no)) + 3 + len(ln.path) + 16
        cur.append(ln)
        size += cost
    if cur:
        chunks.append(cur)
    return chunks


_NUM_PREFIX = re.compile(r'^\s*\d+\|\s?')


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def _runs(lines: list[Line]) -> dict[tuple[str, int], list[Line]]:
    """Group lines into runs of consecutive line numbers per file: a quote may span lines only if they are adjacent
    in the file (a filtered log leaves gaps, and text from distant lines must never be glued together)."""
    runs: dict[tuple[str, int], list[Line]] = {}
    key = None
    for ln in lines:
        last = runs[key][-1] if key else None
        if not last or last.path != ln.path or ln.no != last.no + 1:
            key = (ln.path, ln.no)
            runs[key] = []
        runs[key].append(ln)
    return runs


def locate_all(quote: str, lines: list[Line]) -> list[tuple[str, int, int]]:
    """Every place a quote appears verbatim (modulo whitespace), as (path, first_line, last_line), in file order."""
    parts = [_NUM_PREFIX.sub('', part) for part in quote.strip().strip('"«»“”`').splitlines()]
    q = _norm('\n'.join(parts))
    if len(q) < 4:
        return []
    single = [(ln.path, ln.no, ln.no) for ln in lines if q in _norm(ln.text)]
    if single:
        return single
    # Quote spanning lines: search each run of adjacent lines, first joined by a single space, then (models often glue
    # chained calls: ".from('x')" + ".upsert(...)") joined directly. Only line breaks and indentation may differ.
    needles = {' ': q, '': ''.join(_norm(p) for p in parts)}
    for glue in (' ', ''):
        needle = needles[glue]
        found = []
        for group in _runs(lines).values():
            starts, pieces, pos = [], [], 0
            for ln in group:
                piece = _norm(ln.text)
                starts.append(pos)
                pieces.append(piece)
                pos += len(piece) + len(glue)
            text = glue.join(pieces)
            hit = text.find(needle)
            while hit >= 0:
                first = bisect.bisect_right(starts, hit) - 1
                last = bisect.bisect_right(starts, hit + len(needle) - 1) - 1
                if last > first:
                    found.append((group[first].path, group[first].no, group[last].no))
                hit = text.find(needle, hit + 1)
        if found:
            return found
    return []


def locate(quote: str, lines: list[Line], hint: int = 0, used: set | None = None) -> tuple[str, int, int] | None:
    """Where a quote is in the source; None if it is not there (the anti-hallucination gate).

    Line numbers always come from here. When the same text appears several times (identical lines are common:
    the same decorator, the same call), the model's line hint and the occurrences already used by earlier
    findings pick the right one; the hint alone can never make an unverified quote pass.
    """
    occurrences = locate_all(quote, lines)
    if not occurrences:
        return None
    free = [o for o in occurrences if not used or o not in used] or occurrences
    if hint:
        return min(free, key=lambda o: abs(o[1] - hint))
    return free[0]
