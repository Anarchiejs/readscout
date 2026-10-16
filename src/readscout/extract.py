"""Deterministic extraction of code facts (no model): environment variables, Express routes, Python endpoints and
Supabase accesses.

A fact is found by syntax, its line and citation are read from the file, and everything the extractor does not
understand is reported (`Result.unrecognized`) instead of being guessed: the receipt says `partial` and lists it.
"""
import ast
import bisect
import re
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
                        '(direct, bracket, destructuring and simple alias forms)')
    for src in sources:
        text = _code_lines(src)
        res.files += 1

        def add(name, offset, how):
            ln = src.line_of(offset)
            res.facts.append(Fact(name, src.path, ln, ln, how, src.row(ln)))

        for rx in _ENV_LITERAL:
            for m in rx.finditer(text):
                add(_env_name(m), m.start(), 'read')
        for m in re.finditer(r'(?:const|let|var)\s*\{([^}]*)\}\s*=\s*process\.env\b', text):
            for part in m.group(1).split(','):
                name = re.split(r'[:=]', part.strip())[0].strip()
                if re.fullmatch(r'[A-Za-z_]\w*', name):
                    add(name, m.start(), 'destructured')
        if re.search(r'from\s+os\s+import[^\n]*\b(?:environ|getenv)\b', text):
            for rx in (re.compile(r'(?<![\w.])environ\[\s*([\'"])([^\'"]+)\1\s*\]'),
                       re.compile(r'(?<![\w.])environ\.get\(\s*([\'"])([^\'"]+)\1'),
                       re.compile(r'(?<![\w.])getenv\(\s*([\'"])([^\'"]+)\1')):
                for m in rx.finditer(text):
                    add(m.group(2), m.start(), 'read')
        aliases = set(re.findall(r'(?:const|let|var)\s+(\w+)\s*=\s*process\.env\s*(?:;|\n|$)', text))
        aliases |= set(re.findall(r'^\s*(\w+)\s*=\s*os\.environ\s*$', text, re.M))
        for a in aliases:
            for m in re.finditer(r'(?<![\w.])' + re.escape(a) + r'(?:\.([A-Za-z_]\w*)|\[\s*([\'"])([^\'"]+)\2\s*\]|\.get\(\s*([\'"])([^\'"]+)\4)', text):
                name = m.group(1) or m.group(3) or m.group(5)
                if name not in ('get', 'items', 'keys', 'values', 'copy'):
                    add(name, m.start(), f'read through alias {a}')
        for rx in _ENV_DYNAMIC:
            for m in rx.finditer(text):
                res.unrecognized.append((src.path, src.line_of(m.start()), 'environment variable read with a computed name'))
    return res


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
                    add(name, path, cargs, m.start(), cend)
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
    return res


# ---------------------------------------------------------------- Python endpoints

_PY_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'options', 'head', 'trace', 'websocket', 'route', 'api_route'}


def _deps_of(call: ast.Call) -> list[str]:
    out = []
    for kw in call.keywords:
        if kw.arg == 'dependencies':
            out.append(ast.unparse(kw.value))
    return out


def extract_endpoints(sources: list[Source], lacking: str = '') -> Result:
    scope = ('Python endpoint functions decorated with @x.get/post/put/patch/delete/route/api_route/websocket(path), with their full '
             'signature, decorator dependencies and the dependencies of their router (APIRouter(dependencies=...), include_router(..., dependencies=...))')
    if lacking:
        scope += f'; only endpoints whose decorator, signature and router dependencies do not mention "{lacking}" are listed. This is a property of ' \
                 f'the endpoints analysed here, not a guarantee about the whole application'
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
    router_deps: dict[str, list[str]] = {}
    for src, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if ast.unparse(node.value.func).split('.')[-1] in ('APIRouter', 'FastAPI', 'Blueprint'):
                    router_deps.setdefault(node.targets[0].id, []).extend(_deps_of(node.value))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'include_router' and node.args:
                deps = _deps_of(node)
                if deps:
                    target = node.args[0]
                    if isinstance(target, ast.Name):
                        router_deps.setdefault(target.id, []).extend(deps)
                    else:
                        res.unrecognized.append((src.path, node.lineno, f'include_router({ast.unparse(target)}, dependencies=...) cannot be linked to its endpoints'))
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
                inherited = router_deps.get(recv, [])
                blob = ' '.join([ast.unparse(dec), signature] + inherited)
                if lacking and re.search(r'\b' + re.escape(lacking) + r'\b', blob):
                    continue
                detail = signature[:300]
                if deco_deps:
                    detail += f' | decorator dependencies: {"; ".join(deco_deps)}'
                if inherited:
                    detail += f' | router dependencies: {"; ".join(inherited)}'
                res.facts.append(Fact(f'{method} {path} {node.name}', src.path, dec.lineno, node.lineno, detail, src.row(dec.lineno)))
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
    return res


def run(kind: str, lines: list[Line]) -> Result:
    """kind: env | routes | endpoints | supabase, and 'endpoints!Name' for the endpoints that never mention Name."""
    name, _, lacking = kind.partition('!')
    sources = group_files(lines)
    if name == 'env':
        return extract_env(sources)
    if name == 'routes':
        return extract_routes(sources)
    if name == 'endpoints':
        return extract_endpoints(sources, lacking.strip())
    if name == 'supabase':
        return extract_supabase(sources)
    raise ValueError(f'Unknown extraction "{kind}": use one of {", ".join(KINDS)}')
