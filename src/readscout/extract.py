"""Deterministic extraction of code facts (no model): environment variables, Express routes, Python endpoints and
Supabase accesses.

A fact is found by syntax, its line and citation are read from the file, and everything the extractor does not
understand is reported (`Result.unrecognized`) instead of being guessed: the receipt says `partial` and lists it.
"""
import ast
import bisect
import io
import re
import tokenize
from dataclasses import dataclass, field

from .text import Line

KINDS = ('env', 'routes', 'endpoints', 'supabase')


@dataclass
class Fact:
    key: str        # what the fact is deduplicated on: variable name, "GET /path", "table.operation"
    path: str
    line: int
    end: int        # last line of the construct
    detail: str
    cite: str       # the source line at `line`, read from the file


@dataclass
class Result:
    kind: str
    scope: str                                  # the exact property that was extracted
    facts: list = field(default_factory=list)
    files: int = 0
    unrecognized: list = field(default_factory=list)    # (path, line, reason)
    inspected: int = 0          # units the extractor recognized before any filter: 0 means "nothing of this kind was seen"
    status: str = ''            # set by the receipt, recorded in the metrics: one computation, never two
    coverage: list = field(default_factory=list)     # lines stating what was resolved, so the reader need not check it
    # path -> (source rows, [(first, last, is_header)]): the lines a check of the listed items reads, shown by the receipt
    excerpts: dict = field(default_factory=dict)

    def groups(self) -> list[list[Fact]]:
        by_key: dict[str, list[Fact]] = {}
        for f in self.facts:
            by_key.setdefault(f.key, []).append(f)
        return list(by_key.values())


class Source:
    """One file: its text (line n is text.split('\\n')[n - 1]) and offset to line conversion."""

    def __init__(self, path: str, lines: list[Line]):
        self.path = path
        self.rows = [ln.text for ln in lines]
        self.text = '\n'.join(self.rows)
        self.starts = [0]
        for m in re.finditer('\n', self.text):
            self.starts.append(m.end())

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)

    def row(self, no: int) -> str:
        return self.rows[no - 1].strip() if 0 < no <= len(self.rows) else ''


def group_files(lines: list[Line]) -> list[Source]:
    by_path: dict[str, list[Line]] = {}
    for ln in lines:
        by_path.setdefault(ln.path, []).append(ln)
    return [Source(p, ls) for p, ls in by_path.items()]


# ---------------------------------------------------------------- scanning helpers

def _skip_string(text: str, i: int) -> int:
    """text[i] is a quote: index just after the closing quote (or end of text)."""
    q = text[i]
    i += 1
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == q:
            return i + 1
        if q != '`' and text[i] == '\n':
            return i
        i += 1
    return i


def call_end(text: str, open_idx: int) -> int:
    """Index of the parenthesis closing the one at open_idx, or -1."""
    depth, i = 0, open_idx
    while i < len(text):
        c = text[i]
        if c in '\'"`':
            i = _skip_string(text, i)
            continue
        if c == '/' and text[i:i + 2] == '//':
            i = text.find('\n', i)
            if i < 0:
                return -1
            continue
        if c == '/' and text[i:i + 2] == '/*':
            i = text.find('*/', i)
            if i < 0:
                return -1
            i += 2
            continue
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def split_args(inner: str) -> list[str]:
    args, depth, cur, i = [], 0, [], 0
    while i < len(inner):
        c = inner[i]
        if c in '\'"`':
            j = _skip_string(inner, i)
            cur.append(inner[i:j])
            i = j
            continue
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        if c == ',' and depth == 0:
            args.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    if ''.join(cur).strip():
        args.append(''.join(cur).strip())
    return args


def _literal(arg: str) -> str | None:
    m = re.fullmatch(r'(["\'`])(.*)\1', arg.strip(), re.S)
    return m.group(2) if m and '${' not in m.group(2) else None


def _code_lines(src: Source) -> str:
    """The text with comment-only lines blanked. Same length as src.text, so offsets still map to the right line."""
    return '\n'.join(' ' * len(r) if re.match(r'\s*(//|#|\*|/\*)', r) else r for r in src.rows)


_ENV_HINT = re.compile(r'environ|getenv|\benv\b')     # an opaque string that may hide an environment read


def _env_scan(src: Source) -> tuple[str, list[bool], set[int], list[int]]:
    """Keep literal arguments, but distinguish expression positions from strings and comments.

    This is lexical filtering, not a JavaScript parser. In a template literal the text parts are strings and every
    ${...} is code, scanned like the rest (nested strings, templates and braces included).
    Python uses its standard tokenizer so triple-quoted strings and escaped quotes keep correct offsets; from Python 3.12
    the expressions of a formatted string are tokens of their own, before that the string is opaque and reported only
    when it mentions the environment.
    """
    text, chars = src.text, list(src.text)
    code = [True] * len(text)
    starts: set[int] = set()
    uncertain: list[int] = []

    def hide(a, b, comment=False):
        code[a:b] = [False] * (b - a)
        if comment:
            chars[a:b] = ['\n' if c == '\n' else ' ' for c in text[a:b]]
        else:
            starts.add(a)

    if src.path.endswith('.py'):
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                a = src.starts[min(token.start[0] - 1, len(src.starts) - 1)] + token.start[1]
                b = src.starts[min(token.end[0] - 1, len(src.starts) - 1)] + token.end[1]
                b = min(b, len(text))
                kind = tokenize.tok_name[token.type]
                if kind in ('FSTRING_START', 'FSTRING_MIDDLE', 'FSTRING_END'):     # Python 3.12+: the text parts only
                    hide(a, b)
                elif token.type in (tokenize.STRING, tokenize.COMMENT):
                    hide(a, b, token.type == tokenize.COMMENT)
                    if token.type == tokenize.STRING and re.match(r'(?i)[rub]*f', token.string) and _ENV_HINT.search(token.string):
                        uncertain.append(a)
                elif token.type == tokenize.ERRORTOKEN and token.string.strip():
                    uncertain.append(a)
        except (tokenize.TokenError, IndentationError):
            uncertain.append(0)
        return ''.join(chars), code, starts, uncertain

    def template(i: int) -> int:
        """text[i] is a backtick: hide the text parts, scan each ${...} as code. Index just after the closing backtick."""
        j, part = i + 1, i
        while j < len(text):
            if text[j] == '\\':
                j += 2
            elif text[j] == '`':
                hide(part, j + 1)
                return j + 1
            elif text.startswith('${', j):
                hide(part, j + 2)
                j = scan(j + 2, interpolation=True)
                part = j - 1        # the closing brace belongs to the next text part
            else:
                j += 1
        hide(part, len(text))
        return len(text)

    def scan(i: int, interpolation: bool = False) -> int:
        """Hide strings, comments and regex literals from text[i]. In an interpolation, stop after its closing brace."""
        depth = 0
        while i < len(text):
            c = text[i]
            if text.startswith('//', i) or text.startswith('/*', i):
                end = text.find('\n', i) if text.startswith('//', i) else text.find('*/', i + 2)
                end = len(text) if end < 0 else end + (2 if text.startswith('/*', i) else 0)
                hide(i, end, True)
                i = end
            elif c in '\'"':
                end = _skip_string(text, i)
                hide(i, end)
                i = end
            elif c == '`':
                i = template(i)
            elif c == '/' and (not text[max(0, i - 128):i].strip() or re.search(r'(?:[=(:,\[!&|?{};]|\breturn|\bthrow)\s*$', text[max(0, i - 128):i])):
                # A regex literal is data too. Escapes and character classes may contain slashes.
                end, bracket = i + 1, False
                while end < len(text) and text[end] != '\n':
                    if text[end] == '\\':
                        end += 2
                        continue
                    if text[end] == '/' and not bracket:
                        end += 1
                        while end < len(text) and text[end].isalpha():
                            end += 1
                        break
                    if text[end] in '[]':
                        bracket = text[end] == '['
                    end += 1
                hide(i, min(end, len(text)))
                i = end
            elif interpolation and c in '{}':
                if c == '}' and depth == 0:
                    return i + 1
                depth += 1 if c == '{' else -1
                i += 1
            else:
                i += 1
        return i

    scan(0)
    return ''.join(chars), code, starts, uncertain


# ---------------------------------------------------------------- environment variables

_ENV_LITERAL = [
    re.compile(r'process\.env\.([A-Za-z_]\w*)'),
    re.compile(r'process\.env\[\s*([\'"`])([^\'"`]+)\1\s*\]'),
    re.compile(r'import\.meta\.env\.([A-Za-z_]\w*)'),
    re.compile(r'Deno\.env\.get\(\s*([\'"])([^\'"]+)\1'),
    re.compile(r'os\.environ\[\s*([\'"])([^\'"]+)\1\s*\]'),
    re.compile(r'os\.environ\.(?:get|pop|setdefault)\(\s*([\'"])([^\'"]+)\1'),
    re.compile(r'os\.getenv\(\s*([\'"])([^\'"]+)\1'),
]
_ENV_DYNAMIC = [re.compile(r'process\.env\[\s*(?![\'"`\s])'), re.compile(r'os\.environ\[\s*(?![\'"\s])'),
                re.compile(r'os\.environ\.(?:get|pop|setdefault)\(\s*(?![\'"\s])'), re.compile(r'os\.getenv\(\s*(?![\'"\s])'),
                re.compile(r'Deno\.env\.get\(\s*(?![\'"\s])')]


def _env_name(m: re.Match) -> str:
    return m.group(m.lastindex if m.lastindex and m.lastindex > 1 else 1)


def extract_env(sources: list[Source]) -> Result:
    res = Result('env', 'environment variables read by name through process.env, import.meta.env, Deno.env, os.environ and os.getenv '
                        '(direct, bracket, destructuring and simple alias forms), and UPPER_CASE keys declared in Joi.object / z.object '
                        'schemas or in pydantic BaseSettings classes (a variable validated but never read by name is listed too)')
    for src in sources:
        text, code, string_starts, uncertain = _env_scan(src)
        res.files += 1
        res.unrecognized.extend((src.path, src.line_of(i), 'formatted/template string or invalid tokens not inspected') for i in uncertain)

        def add(name, offset, how):
            ln = src.line_of(offset)
            res.facts.append(Fact(name, src.path, ln, ln, how, src.row(ln)))

        for rx in _ENV_LITERAL:
            for m in rx.finditer(text):
                if code[m.start()]:
                    add(_env_name(m), m.start(), 'read')
        for m in re.finditer(r'(?:const|let|var)\s*\{([^}]*)\}\s*=\s*process\.env\b', text):
            if not code[m.start()]:
                continue
            for part in m.group(1).split(','):
                name = re.split(r'[:=]', part.strip())[0].strip()
                if re.fullmatch(r'[A-Za-z_]\w*', name):
                    add(name, m.start(), 'destructured')
        if any(code[m.start()] for m in re.finditer(r'from\s+os\s+import[^\n]*\b(?:environ|getenv)\b', text)):
            for rx in (re.compile(r'(?<![\w.])environ\[\s*([\'"])([^\'"]+)\1\s*\]'),
                       re.compile(r'(?<![\w.])environ\.get\(\s*([\'"])([^\'"]+)\1'),
                       re.compile(r'(?<![\w.])getenv\(\s*([\'"])([^\'"]+)\1')):
                for m in rx.finditer(text):
                    if code[m.start()]:
                        add(m.group(2), m.start(), 'read')
        aliases = {m.group(1) for m in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*process\.env\s*(?:;|\n|$)', text) if code[m.start()]}
        aliases |= {m.group(1) for m in re.finditer(r'^\s*(\w+)\s*=\s*os\.environ\s*$', text, re.M) if code[m.start()]}
        for a in aliases:
            for m in re.finditer(r'(?<![\w.])' + re.escape(a) + r'(?:\.([A-Za-z_]\w*)|\[\s*([\'"])([^\'"]+)\2\s*\]|\.get\(\s*([\'"])([^\'"]+)\4)', text):
                name = m.group(1) or m.group(3) or m.group(5)
                if code[m.start()] and name not in ('get', 'items', 'keys', 'values', 'copy'):
                    add(name, m.start(), f'read through alias {a}')
        for rx in _ENV_DYNAMIC:
            for m in rx.finditer(text):
                if code[m.start()]:
                    res.unrecognized.append((src.path, src.line_of(m.start()), 'environment variable read with a computed name'))
        for offset, name in _schema_keys(text, code, string_starts):
            add(name, offset, 'declared in a validation schema')
        if src.path.endswith('.py'):
            for ln, name in _settings_fields(src):
                res.facts.append(Fact(name, src.path, ln, ln, 'pydantic settings field', src.row(ln)))
    res.inspected = len(res.facts)
    return res


_SCHEMA_CALL = re.compile(r'(?<![\w$.])(?:Joi|z)\s*\.\s*object\s*\(')
_SCHEMA_KEY = re.compile(r'''['"]?([A-Z][A-Z0-9_]+)['"]?\s*:\s*(?:Joi|z)\s*\.''')


def _depth(text: str, a: int, b: int) -> int:
    """Nesting of ([{ at text[b], counted from text[a] and ignoring strings."""
    depth, i = 0, a
    while i < b:
        c = text[i]
        if c in '\'"`':
            i = _skip_string(text, i)
            continue
        depth += (c in '([{') - (c in ')]}')
        i += 1
    return depth


def _schema_keys(text: str, code: list[bool] | None = None, string_starts: set[int] | None = None):
    """(offset, NAME) of the top-level UPPER_CASE keys of Joi.object({...}), Joi.object().keys({...}) and z.object({...})."""
    inside = -1          # a schema nested in another one describes a sub-object, not environment variables
    for m in _SCHEMA_CALL.finditer(text):
        if m.start() < inside or (code is not None and not code[m.start()]):
            continue
        end = call_end(text, m.end() - 1)
        if end < 0:
            continue
        spans = [(m.end(), end)]
        spans += [(text.find("(", st) + 1, cend) for name, _, st, cend in _chain_calls(text, end + 1) if name in ("keys", "append")]
        inside = max(b for _, b in spans)
        for a, b in spans:
            brace = text.find("{", a, b)
            if brace < 0:
                continue
            for k in _SCHEMA_KEY.finditer(text, brace, b):
                if (code is None or code[k.start()] or k.start() in (string_starts or set())) and _depth(text, brace, k.start()) == 1:
                    yield k.start(), k.group(1)


def _settings_fields(src: Source):
    try:
        tree = ast.parse(src.text)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(ast.unparse(b).endswith('BaseSettings') for b in node.bases):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and not item.target.id.startswith('_'):
                    yield item.lineno, item.target.id.upper()


# ---------------------------------------------------------------- Express routes

_METHODS = ('get', 'post', 'put', 'patch', 'delete', 'options', 'head', 'all')
_NOT_ROUTERS = {'axios', 'http', 'https', 'request', 'superagent', 'client', 'fetch', 'got', 'supertest', 'ky', 'cy', 'page', 'map', 'headers',
                'params', 'searchparams', 'formdata', 'cache', 'storage', 'store', 'localstorage', 'sessionstorage', 'cookies', 'req', 'res'}
_ROUTE_CALL = re.compile(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*\.\s*(' + '|'.join(_METHODS) + r')\s*\(')
_ROUTE_CHAIN = re.compile(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*\.\s*route\s*\(')


def _chain_calls(text: str, pos: int):
    """Calls `.name(args)` that follow each other from pos (whitespace and line breaks allowed): (name, args, end)."""
    while True:
        m = re.compile(r'\s*\.\s*([A-Za-z_$][\w$]*)\s*\(').match(text, pos)
        if not m:
            return
        end = call_end(text, m.end() - 1)
        if end < 0:
            return
        yield m.group(1), split_args(text[m.end():end]), m.start(), end
        pos = end + 1


def extract_routes(sources: list[Source]) -> Result:
    res = Result('routes', 'Express style route declarations app.METHOD(path, ...handlers) and router.route(path).METHOD(...), with their '
                           'middlewares (every handler before the last); paths are as written in each file, prefixes added by app.use(...) are not resolved')
    for src in sources:
        if not re.search(r'\.(js|jsx|ts|tsx|mjs|cjs)$', src.path):
            continue
        res.files += 1
        text = _code_lines(src)
        seen = set()

        def add(method, path, handlers, offset, end):
            ln, last = src.line_of(offset), src.line_of(end)
            mids, handler = handlers[:-1], handlers[-1] if handlers else ''
            detail = f'middlewares: {", ".join(mids) if mids else "none"} | handler: {" ".join(handler.split())[:80] or "none"}'
            res.facts.append(Fact(f'{method.upper()} {path}', src.path, ln, last, detail, src.row(ln)))

        for m in _ROUTE_CHAIN.finditer(text):
            end = call_end(text, m.end() - 1)
            args = split_args(text[m.end():end]) if end > 0 else []
            path = _literal(args[0]) if args else None
            if path is None:
                res.unrecognized.append((src.path, src.line_of(m.start()), 'route() with a computed path'))
                continue
            seen.add(m.start())
            for name, cargs, start, cend in _chain_calls(text, end + 1):
                if name in _METHODS:
                    add(name, path, cargs, text.index('.', start), cend)      # the line of this method, not of route(...)
        for m in _ROUTE_CALL.finditer(text):
            recv = m.group(1)
            if recv.lower() in _NOT_ROUTERS or m.start() in seen:
                continue
            end = call_end(text, m.end() - 1)
            if end < 0:
                continue
            args = split_args(text[m.end():end])
            if len(args) < 2 or args[-1].lstrip().startswith('{'):
                continue            # axios.get(url), map.get(key), client.get(url, {options}): not a route
            path = _literal(args[0])
            if path is None:
                if re.search(r'(?i)(app|router|route|server|api)$', recv):
                    res.unrecognized.append((src.path, src.line_of(m.start()), f'{recv}.{m.group(2)}() with a computed path'))
                continue
            if not path.startswith(('/', '*')):
                continue
            add(m.group(2), path, args[1:], m.start(), end)
    res.inspected = len(res.facts)
    return res


# ---------------------------------------------------------------- Python endpoints

_PY_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'options', 'head', 'trace', 'websocket', 'route', 'api_route'}


def _deps_of(call: ast.Call) -> list[str]:
    out = []
    for kw in call.keywords:
        if kw.arg == 'dependencies':
            out.append(ast.unparse(kw.value))
    return out


def _header_blocks(tree: ast.Module) -> list[tuple[int, int, bool]]:
    """Imports, router declarations and include_router calls of a module: where its protections come from."""
    blocks = []
    for node in tree.body:
        router = (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                  and ast.unparse(node.value.func).split('.')[-1] in ('APIRouter', 'FastAPI', 'Blueprint'))
        include = (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                   and node.value.func.attr == 'include_router')
        if isinstance(node, (ast.Import, ast.ImportFrom)) or router or include:
            blocks.append((node.lineno, node.end_lineno or node.lineno, True))
    return blocks


def _prefix_of(call: ast.Call) -> str | None:
    """The literal prefix= of a router or an inclusion; '' without one, None when it is computed."""
    for kw in call.keywords:
        if kw.arg == 'prefix':
            return kw.value.value if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str) else None
    return ''


def extract_endpoints(sources: list[Source], lacking: str = '') -> Result:
    names = [n.strip() for n in re.split(r'[,|]', lacking) if n.strip()]
    scope = ('Python endpoint functions decorated with @x.get/post/put/patch/delete/route/api_route/websocket(path), with their full '
             'signature, decorator dependencies and the dependencies of their router (APIRouter(dependencies=...), include_router(..., dependencies=...)); '
             'paths include the prefixes of APIRouter(prefix=...) and include_router(..., prefix=...) declared in the same file, '
             'a prefix added in another file is not resolved')
    if names:
        scope += (f'; only endpoints whose decorator, signature and router dependencies mention none of {", ".join(names)} are listed. This is a '
                  f'textual property of the endpoints analysed here: it is not the same as "public" or "not logged in" (authentication can come from '
                  f'middleware, another module or the application) and it is not a guarantee about the whole application. Pass every name that counts '
                  f'as protection, for example endpoints!CurrentUser,get_current_active_superuser')
    res = Result('endpoints', scope)
    trees = []
    for src in sources:
        if not src.path.endswith('.py'):
            continue
        res.files += 1
        try:
            trees.append((src, ast.parse(src.text)))
        except SyntaxError as e:
            res.unrecognized.append((src.path, e.lineno or 1, 'file does not parse'))
    router_deps: dict[tuple[str, str], list[str]] = {}
    own_prefix: dict[tuple[str, str], str] = {}
    included_in: dict[tuple[str, str], tuple[str, str]] = {}     # child router -> (parent, prefix of the inclusion)
    prefix_elsewhere: list[str] = []
    for src, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if ast.unparse(node.value.func).split('.')[-1] in ('APIRouter', 'FastAPI', 'Blueprint'):
                    router_deps.setdefault((src.path, node.targets[0].id), []).extend(_deps_of(node.value))
                    prefix = _prefix_of(node.value)
                    if prefix is None:
                        res.unrecognized.append((src.path, node.lineno, f'{node.targets[0].id} has a computed prefix: its endpoints are shown without it'))
                    else:
                        own_prefix[(src.path, node.targets[0].id)] = prefix
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'include_router' and node.args:
                deps, prefix, target = _deps_of(node), _prefix_of(node), node.args[0]
                if not deps and prefix == '':
                    continue
                child = target.id if isinstance(target, ast.Name) else ''
                local = bool(child) and any(
                    isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == child for t in n.targets) for n in tree.body)
                if not local and not deps:
                    # Only a prefix, applied to a router of another module: every endpoint is still listed, only its full path is not.
                    # Stated, not counted as unrecognized: a partial status would send the reader to re-read files it does not need.
                    prefix_elsewhere.append(f'{src.path}:{node.lineno} include_router({ast.unparse(target)}, prefix='
                                            f'{ast.unparse(next(k.value for k in node.keywords if k.arg == "prefix"))})')
                    continue
                if not local:
                    what = ', '.join(w for w, used in (('dependencies=...', deps), ('prefix=...', prefix != '')) if used)
                    if child:
                        reason = f'include_router({child}, {what}) is not defined in this file'
                    else:
                        reason = f'include_router({ast.unparse(target)}, {what}) cannot be linked to its endpoints'
                    if prefix != '':
                        reason += ': the full paths of its endpoints are not resolved here'
                    res.unrecognized.append((src.path, node.lineno, reason))
                    continue
                router_deps.setdefault((src.path, child), []).extend(deps)
                if prefix is None:
                    res.unrecognized.append((src.path, node.lineno, f'include_router({child}, prefix=...) with a computed prefix: '
                                                                    f'its endpoints are shown without it'))
                elif prefix and isinstance(node.func.value, ast.Name):
                    included_in[(src.path, child)] = (node.func.value.id, prefix)

    def full_prefix(path: str, name: str, seen=()) -> str:
        """FastAPI joins prefixes as written: parent router prefix + inclusion prefix + router prefix."""
        if name in seen:
            return own_prefix.get((path, name), '')
        parent = included_in.get((path, name))
        outer = full_prefix(path, parent[0], seen + (name,)) + parent[1] if parent else ''
        return outer + own_prefix.get((path, name), '')

    applied: dict[str, set[str]] = {}       # file with listed endpoints -> the router prefixes applied to them
    declared: list[tuple[Fact, str, str]] = []
    for src, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in _PY_METHODS):
                    continue
                recv = ast.unparse(dec.func.value)
                path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str) else None
                if path is None:
                    if dec.args or any(k.arg == 'path' for k in dec.keywords):
                        res.unrecognized.append((src.path, dec.lineno, f'@{recv}.{dec.func.attr}() with a computed path'))
                    continue
                method = dec.func.attr.upper()
                if dec.func.attr == 'route':
                    for kw in dec.keywords:
                        if kw.arg == 'methods':
                            method = ','.join(re.findall(r'[A-Za-z]+', ast.unparse(kw.value))).upper()
                    method = method if method != 'ROUTE' else 'GET'
                signature = f'{"async " if isinstance(node, ast.AsyncFunctionDef) else ""}def {node.name}({ast.unparse(node.args)})'
                deco_deps = _deps_of(dec)
                inherited = router_deps.get((src.path, recv), [])
                blob = ' '.join([ast.unparse(dec), signature] + inherited)
                res.inspected += 1
                if any(re.search(r'\b' + re.escape(n) + r'\b', blob) for n in names):
                    continue
                detail = signature[:300]
                prefix = full_prefix(src.path, recv)
                if deco_deps:
                    detail += f' | decorator dependencies: {"; ".join(deco_deps)}'
                if inherited:
                    detail += f' | router dependencies: {"; ".join(inherited)}'
                res.facts.append(Fact(f'{method} {prefix}{path} {node.name}', src.path, dec.lineno, node.lineno, detail, src.row(dec.lineno)))
                applied.setdefault(src.path, set()).update({prefix} if prefix else set())
                declared.append((res.facts[-1], path, prefix))
                if names:       # a filtered list answers a protection question: keep what checking it reads
                    _, blocks = res.excerpts.setdefault(src.path, (src.rows, _header_blocks(tree)))
                    blocks.append((min(d.lineno for d in node.decorator_list), node.end_lineno or node.lineno, False))
    for fact, path, prefix in declared:
        if prefix and len(applied[fact.path]) > 1:     # one prefix per file is stated once, in the coverage line below
            fact.detail += f' | declared path "{path}" under router prefix "{prefix}"'
    # Questions often ask for full paths: say which prefixes were applied, so the reader need not open each router.
    unresolved = sum('prefix' in why for _, _, why in res.unrecognized)
    unresolved_note = f' {unresolved} prefix{"es" if unresolved > 1 else ""} not resolved (see Not recognized).' if unresolved else ''
    with_prefix = [p + ' ' + ', '.join(f'"{x}"' for x in sorted(v)) for p, v in applied.items() if v]
    without = [p for p, v in applied.items() if not v]
    if with_prefix:
        res.coverage.append(f'Router prefixes applied: {"; ".join(with_prefix)}' + (f'; none in {", ".join(without)}' if without else '')
                            + '.' + unresolved_note)
    elif unresolved:
        res.coverage.append('Router prefixes:' + unresolved_note)
    elif applied and not prefix_elsewhere:
        res.coverage.append('No router prefix is declared in these files.')
    if prefix_elsewhere:
        res.coverage.append(f'Prefixes added to routers of other modules, not applied to the paths above: {"; ".join(prefix_elsewhere[:8])}'
                            f'{"; ..." if len(prefix_elsewhere) > 8 else ""}. Every endpoint is listed; join them yourself if full paths matter.')
    return res


# ---------------------------------------------------------------- Supabase

SUPABASE_OPS = ('select', 'insert', 'update', 'delete', 'upsert')
_FROM = re.compile(r'\.\s*from\s*\(')
_NOT_SUPABASE = {'Array', 'Buffer', 'Observable', 'Object', 'Uint8Array', 'Int8Array', 'Float32Array', 'Float64Array', 'Set', 'Map'}


def extract_supabase(sources: list[Source]) -> Result:
    res = Result('supabase', 'Supabase accesses: .from("table") followed (across line breaks) by select, insert, update, delete or upsert, '
                             'and .rpc("function") calls')
    for src in sources:
        if not re.search(r'\.(js|jsx|ts|tsx|mjs|cjs|vue|svelte)$', src.path):
            continue
        res.files += 1
        text = _code_lines(src)
        mentions = bool(re.search(r'supabase|createClient', text, re.I))
        for m in _FROM.finditer(text):
            before = re.search(r'([A-Za-z_$][\w$]*)\s*$', text[:m.start()])
            if before and before.group(1) in _NOT_SUPABASE:
                continue
            end = call_end(text, m.end() - 1)
            if end < 0:
                continue
            args = split_args(text[m.end():end])
            table = _literal(args[0]) if len(args) == 1 else None
            ops = [(name, cend) for name, cargs, start, cend in _chain_calls(text, end + 1) if name in SUPABASE_OPS]
            if table is None:
                if mentions and (not before or before.group(1) not in _NOT_SUPABASE):
                    res.unrecognized.append((src.path, src.line_of(m.start()), '.from() with a computed table name'))
                continue
            if not ops:
                continue
            ln = src.line_of(m.start())
            for name, cend in ops:
                res.facts.append(Fact(f'{table}.{name}', src.path, ln, src.line_of(cend), f'table {table}, operation {name}', src.row(ln)))
        for m in re.finditer(r'\.\s*rpc\s*\(\s*([\'"])([\w.-]+)\1', text):
            if mentions:
                ln = src.line_of(m.start())
                res.facts.append(Fact(f'rpc.{m.group(2)}', src.path, ln, ln, f'rpc {m.group(2)}', src.row(ln)))
    res.inspected = len(res.facts)
    return res


def extract_http(sources: list[Source], kind: str, lacking: str = '') -> Result:
    """routes and endpoints are one question to the reader: every framework whose files are present is read, whichever was asked."""
    from . import webroutes
    names = [n.strip() for n in re.split(r'[,|]', lacking) if n.strip()]
    nest = {s.path for s in sources if webroutes.framework_of(s) == 'nest'}
    express = extract_routes([s for s in sources if s.path not in nest])
    if names:
        express.facts = [f for f in express.facts if not any(re.search(r'\b' + re.escape(n) + r'\b', f.detail + ' ' + f.cite) for n in names)]
    parts = [extract_endpoints(sources, lacking), express, webroutes.extract(sources, names)]
    present = [p for p in parts if p.files] or parts
    res = Result(kind, '. Also: '.join(p.scope for p in present if p.scope))
    for p in present:
        res.facts += p.facts
        res.files += p.files
        res.unrecognized += p.unrecognized
        res.inspected += p.inspected
        res.coverage += p.coverage
        res.excerpts.update(p.excerpts)
    return res


def run(kind: str, lines: list[Line]) -> Result:
    """kind: env | routes | endpoints | supabase, and 'endpoints!A,B' for the endpoints that mention neither A nor B."""
    name, _, lacking = kind.partition('!')
    sources = group_files(lines)
    if name == 'env':
        return extract_env(sources)
    if name in ('routes', 'endpoints'):
        return extract_http(sources, name, lacking)
    if name == 'supabase':
        return extract_supabase(sources)
    raise ValueError(f'Unknown extraction "{kind}": use one of {", ".join(KINDS)}')
