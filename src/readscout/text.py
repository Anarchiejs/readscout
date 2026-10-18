"""File access, chunking and the deterministic check that turns model quotes into real line numbers."""
import bisect
import re
from dataclasses import dataclass
from pathlib import Path

# Provider tokens with a recognisable shape: private key blocks, OpenAI/Anthropic, GitHub, GitLab, AWS, Slack, Google,
# Stripe, npm, PyPI, Hugging Face, SendGrid, JWTs and Slack webhooks.
SECRET = re.compile(r'-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----[\s\S]*?-----END[^-]*-----'
                    r'|\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}'
                    r'|(?:AKIA|ASIA)[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{30,}|ya29\.[A-Za-z0-9_-]{20,}'
                    r'|[rsp]k_(?:live|test)_[A-Za-z0-9]{16,}|whsec_[A-Za-z0-9]{20,}|npm_[A-Za-z0-9]{36}|pypi-[A-Za-z0-9_-]{50,}'
                    r'|hf_[A-Za-z0-9]{30,}|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}'
                    r'|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b'
                    r'|https://hooks\.slack\.com/services/[A-Za-z0-9/]+')
# key = value, key: value and "key": "value" (JSON), also for prefixed or suffixed names (client_secret, DB_PASSWORD,
# authToken, AccountKey). Values of 12 characters or more: shorter ones are code identifiers far more often.
ASSIGNED_SECRET = re.compile(r'(?i)(\b[\w.-]*(?:api[_-]?key|access[_-]?key|account[_-]?key|signing[_-]?key|encryption[_-]?key'
                             r'|password|passwd|passphrase|secret|token|private[_-]?key|credentials?|conn(?:ection)?[_-]?string)'
                             r'[\w-]*["\']?[ \t]*[:=][ \t]*["\']?)'
                             # An unquoted value that reads a secret from its source (process.env.X, os.environ[...]) is code, not the
                             # secret: masking it hides which variable the code uses. A call expression (Joi.string().required(), get_password(...)) is code too.
                             # Quoted values are always masked.
                             r'(?:(?<=["\'])|(?!(?:process\.env\.|import\.meta\.env\.|os\.environ|os\.getenv|getenv\(|env\.|env\(|Deno\.env'
                             r'|System\.getenv|ENV\[|\$\{|\{\{|config\.|settings\.|self\.|this\.|[A-Za-z_$][\w$.]*\('
                             # a dotted path (form_data.password) or a snake_case name (password_reset_token): letters and underscores only.
                             # A real secret has digits or no structure; masking these also swallowed the closing parenthesis and broke the code.
                             r'|[A-Za-z_]+(?:\.[A-Za-z_]+)+(?![\w$.-])|[a-z]+(?:_[a-z]+)+(?![\w$.-]))))'
                             r'[^\s"\',}]{12,}?(?=[)\];]*(?:[\s"\',}]|$))')     # never across a line break; closing brackets stay outside the mask
# The password part of user:password@host in URLs (database DSNs, git remotes), and HTTP authorization headers
# (a credential has digits; "Basic configuration" in prose does not).
URL_PASSWORD = re.compile(r'(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]{3,}(@)', re.I)
AUTH_HEADER = re.compile(r'(\b(?:Bearer|Basic|bearer)[ \t]+)(?=[A-Za-z._~+/-]*\d)[A-Za-z0-9._~+/-]{16,}=*')
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


class InputLimitError(AccessError):
    """An input budget was exceeded; never silently skip it during directory traversal."""


@dataclass
class Line:
    path: str   # path as given by the caller (relative to its root when possible)
    no: int     # 1-based line number in the original file
    text: str
    cut: bool = False   # the line was longer than MAX_LINE_CHARS and its end is not shown to the model
    source_bytes: int = 0  # actual input bytes, stored once on the first line of each loaded file


def input_bytes(lines: list[Line]) -> int:
    measured = sum(ln.source_bytes for ln in lines)
    return measured if measured else sum(len(ln.text.encode('utf-8')) + 1 for ln in lines)


def outside(real: Path, allowed: list[Path] | None) -> bool:
    """True when an allow-list is set (`readscout folders add`) and the resolved path is in none of its folders."""
    return bool(allowed) and not any(real.is_relative_to(a) for a in allowed or [])


def resolve(path: str, roots: list[Path], allowed: list[Path] | None = None) -> tuple[Path, str]:
    """Return the real file path and a display path.

    By default the agent decides what to read: any file on this machine is allowed, relative paths start at the first
    root (the folder the agent works in). With an allow-list, files outside its folders are refused. Sensitive or binary
    files are always refused. The display path is relative to the folder the file is in (a root, else the home folder)
    so that `.git` or `.ssh` in the path are recognised, else absolute.
    """
    p = Path(path).expanduser()
    candidates = [p] if p.is_absolute() else [r / p for r in roots]
    for c in candidates:
        real = c.resolve()
        if not real.is_file():
            continue
        if outside(real, allowed):
            raise AccessError(f'Outside the allowed folders: {path} (the user restricted readscout with `readscout folders`)')
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
    """Mask common secrets before any text reaches a model. Pattern based: it lowers the risk, it cannot remove it."""
    text = SECRET.sub(_mask, text)
    text = URL_PASSWORD.sub(r'\1[REDACTED]\2', text)
    text = AUTH_HEADER.sub(r'\1[REDACTED]', text)
    return ASSIGNED_SECRET.sub(r'\1[REDACTED]', text)


def is_sensitive(rel_parts, name: str) -> bool:
    """Case-insensitive: Windows and macOS file systems treat `.ENV` and `.Git` as `.env` and `.git`."""
    return (any(p.lower() in SKIPPED_DIRS or p.lower().startswith('.env') for p in rel_parts)
            or Path(name).suffix.lower() in SKIPPED_SUFFIXES or name.lower() in SKIPPED_NAMES)


def load_lines(path: str, roots: list[Path], label: str | None = None, allowed: list[Path] | None = None,
               *, max_bytes: int | None = None) -> list[Line]:
    real, shown = resolve(path, roots, allowed)
    shown = label or shown
    if real.stat().st_size > MAX_FILE_BYTES:
        raise AccessError(f'File larger than {MAX_FILE_BYTES // 1_000_000} MB: {path}')
    limit = min(MAX_FILE_BYTES, max_bytes) if max_bytes is not None else MAX_FILE_BYTES
    if real.stat().st_size > limit:
        raise InputLimitError('Input byte budget exceeded; narrow the paths')
    with real.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise InputLimitError('Input byte budget exceeded while reading; narrow the paths')
    if b'\0' in raw[:8192]:
        raise AccessError(f'Binary file refused: {path}')
    text = redact(raw.decode('utf-8', errors='replace'))
    return [Line(shown, i, t if len(t) <= MAX_LINE_CHARS else t[:MAX_LINE_CHARS] + ' [line truncated]', len(t) > MAX_LINE_CHARS,
                 len(raw) if i == 1 else 0)
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
    chunks: list[list[Line]] = []
    cur: list[Line] = []
    size, current = 0, None
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
# Below this length a quote is accepted only when it is a whole line: `None` or `return` appear everywhere, so a
# fragment that short would "verify" almost any claim.
MIN_QUOTE_CHARS = 10


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


def _quote_parts(quote: str) -> list[str]:
    return [_NUM_PREFIX.sub('', part) for part in quote.strip().strip('"«»“”`').splitlines()]


def exact_text(quote: str, lines: list[Line], where: tuple[str, int, int]) -> tuple[str, str]:
    """The text of the source at a located place, and how the model's quote matched it: 'exact' (a verbatim substring
    of one line) or 'normalized' (only whitespace or line breaks differed). The returned text always comes from the
    file, never from the model, so the receipt shows exactly what was verified."""
    path, first, last = where
    span = [ln for ln in lines if ln.path == path and first <= ln.no <= last]
    parts = _quote_parts(quote)
    if len(span) == 1:
        raw = span[0].text
        # The model may wrap a quote in quotation marks; try the quote as given first, since they can be real code.
        for verbatim in (quote.strip(), '\n'.join(parts).strip()):
            if verbatim and verbatim in raw:
                return verbatim, 'exact'
        words = _norm('\n'.join(parts)).split(' ')
        hit = re.search(r'\s+'.join(re.escape(w) for w in words), raw) if words != [''] else None
        return (hit.group(0), 'normalized') if hit else (raw.strip(), 'normalized')
    return ' '.join(ln.text.strip() for ln in span), 'normalized'


def locate_all(quote: str, lines: list[Line]) -> list[tuple[str, int, int]]:
    """Every place a quote appears verbatim (modulo whitespace), as (path, first_line, last_line), in file order."""
    parts = _quote_parts(quote)
    q = _norm('\n'.join(parts))
    if len(q) < 4:
        return []
    if len(q) < MIN_QUOTE_CHARS:
        return [(ln.path, ln.no, ln.no) for ln in lines if q == _norm(ln.text)]
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


def _same_file(given: str, path: str) -> bool:
    given = given.strip().replace('\\', '/')
    return bool(given) and (given == path or path.endswith('/' + given) or given.endswith('/' + path))


def locate(quote: str, lines: list[Line], hint: int = 0, used: set | None = None, file: str = '') -> tuple[str, int, int] | None:
    """Where a quote is in the source; None if it is not there (the anti-hallucination gate).

    Line numbers always come from here. When the same text appears several times (identical lines are common:
    the same decorator, the same call), the model's line hint and the occurrences already used by earlier
    findings pick the right one; the hint alone can never make an unverified quote pass.
    """
    occurrences = locate_all(quote, lines)
    if not occurrences:
        return None
    # The file the model named picks among identical quotes; an unknown or wrong name never rejects a verified quote.
    named = [o for o in occurrences if _same_file(file, o[0])]
    occurrences = named or occurrences
    free = [o for o in occurrences if not used or o not in used] or occurrences
    if hint:
        return min(free, key=lambda o: abs(o[1] - hint))
    return free[0]
