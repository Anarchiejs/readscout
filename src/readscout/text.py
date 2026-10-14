"""File access, chunking and the deterministic check that turns model quotes into real line numbers."""
import bisect
import re
from dataclasses import dataclass
from pathlib import Path

SECRET = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END[^-]*-----'
                    r'|\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b')
ASSIGNED_SECRET = re.compile(r'(?i)((?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*["\']?)[^\s"\']{12,}')
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


def resolve(path: str, roots: list[Path]) -> tuple[Path, str]:
    """Return the real file path and a display path, refusing anything outside the allowed roots."""
    p = Path(path)
    candidates = [p] if p.is_absolute() else [r / p for r in roots]
    for c in candidates:
        real = c.resolve()
        for root in roots:
            root = root.resolve()
            if real.is_relative_to(root) and real.is_file():
                rel = real.relative_to(root)
                if any(part in SKIPPED_DIRS or part.startswith('.env') for part in rel.parts) \
                        or real.suffix.lower() in SKIPPED_SUFFIXES or real.name.lower() in SKIPPED_NAMES:
                    raise AccessError(f'Sensitive or binary file refused: {path}')
                return real, rel.as_posix()
    raise AccessError(f'File not found inside a registered project: {path}')


def redact(text: str) -> str:
    return ASSIGNED_SECRET.sub(r'\1[REDACTED]', SECRET.sub('[REDACTED]', text))


def load_lines(path: str, roots: list[Path]) -> list[Line]:
    real, shown = resolve(path, roots)
    if real.stat().st_size > MAX_FILE_BYTES:
        raise AccessError(f'File larger than {MAX_FILE_BYTES // 1_000_000} MB: {path}')
    raw = real.read_bytes()
    if b'\0' in raw[:8192]:
        raise AccessError(f'Binary file refused: {path}')
    text = redact(raw.decode('utf-8', errors='replace'))
    return [Line(shown, i, t if len(t) <= MAX_LINE_CHARS else t[:MAX_LINE_CHARS] + ' [line truncated]')
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
    chunks, cur, size = [], [], 0
    for ln in lines:
        cost = len(ln.text) + len(str(ln.no)) + 3
        if cur and size + cost > max_chars:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(ln)
        size += cost
    if cur:
        chunks.append(cur)
    return chunks


_NUM_PREFIX = re.compile(r'^\s*\d+\|\s?')


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def _squash(s: str) -> str:
    return re.sub(r'\s+', '', s)


def locate_all(quote: str, lines: list[Line]) -> list[tuple[str, int, int]]:
    """Every place a quote appears verbatim (modulo whitespace), as (path, first_line, last_line), in file order."""
    q = _norm('\n'.join(_NUM_PREFIX.sub('', part) for part in quote.strip().strip('"«»“”`').splitlines()))
    if len(q) < 4:
        return []
    single = [(ln.path, ln.no, ln.no) for ln in lines if q in _norm(ln.text)]
    if single:
        return single
    # Multi-line quote: search each file's joined text, first with single spaces between lines, then with no
    # whitespace at all (models often glue chained calls: ".from('x').upsert(...)").
    by_file: dict[str, list[Line]] = {}
    for ln in lines:
        by_file.setdefault(ln.path, []).append(ln)
    for squash in (False, True):
        needle = _squash(q) if squash else q
        found = []
        for path, group in by_file.items():
            starts, parts, pos = [], [], 0
            for ln in group:
                piece = _squash(ln.text) if squash else _norm(ln.text)
                starts.append(pos)
                parts.append(piece)
                pos += len(piece) + (0 if squash else 1)
            text = ('' if squash else ' ').join(parts)
            hit = text.find(needle)
            while hit >= 0:
                first = bisect.bisect_right(starts, hit) - 1
                last = bisect.bisect_right(starts, hit + len(needle) - 1) - 1
                found.append((path, group[first].no, group[last].no))
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
