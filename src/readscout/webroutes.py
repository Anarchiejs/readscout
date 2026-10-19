"""Deterministic extraction of HTTP routes declared by annotation or registration outside Python and Express:
Spring (Java, Kotlin), NestJS (TypeScript) and Go routers (gin, echo, chi, gorilla).

Same contract as extract.py: a route is found by syntax, its line and citation are read from the file, and a construct
that is seen but not understood is listed instead of guessed. Prefixes are resolved when they are declared in the files
read (class or controller prefix, a router group passed to a registration function); a prefix set elsewhere is stated.
"""
import re

from .extract import Fact, Result, Source, _code_lines, _literal, call_end, split_args

SCOPE = {
    'spring': 'Spring handler methods annotated @GetMapping/@PostMapping/@PutMapping/@DeleteMapping/@PatchMapping/@RequestMapping(method=...), '
              'with the class-level @RequestMapping prefix and the security annotations (@PreAuthorize, @Secured, @RolesAllowed) of the method and class',
    'nest': 'NestJS handlers decorated @Get/@Post/@Put/@Delete/@Patch/@Options/@Head/@All(path), with the @Controller(prefix) of their class '
            'and their @UseGuards (method and class)',
    'go': 'Go router registrations x.GET/POST/PUT/DELETE/PATCH/OPTIONS/HEAD/Any(path, handlers) (gin, echo), x.Get/Post/...(path, handler) (chi) '
          'and x.HandleFunc(path, handler).Methods(...) (gorilla), with the prefixes of x.Group(prefix) / x.Route / PathPrefix resolved through '
          'variables and through router groups passed to registration functions in these files; middlewares added with x.Use(...) are not '
          'attributed to the routes',
}

# ---------------------------------------------------------------- annotations (Java, Kotlin, TypeScript)

_ANNOT = re.compile(r'@([A-Za-z_][\w.]*)')
_TYPE_DECL = re.compile(r'(?:(?:public|protected|private|internal|open|abstract|final|static|sealed|data|export|default|declare)\s+)*'
                        r'(?:class|interface|record|enum|object)\b')
_SPRING = {'GetMapping': 'GET', 'PostMapping': 'POST', 'PutMapping': 'PUT', 'DeleteMapping': 'DELETE', 'PatchMapping': 'PATCH', 'RequestMapping': None}
_SPRING_SECURITY = ('PreAuthorize', 'PostAuthorize', 'Secured', 'RolesAllowed', 'PermitAll', 'DenyAll')
_NEST = {'Get': 'GET', 'Post': 'POST', 'Put': 'PUT', 'Delete': 'DELETE', 'Patch': 'PATCH', 'Options': 'OPTIONS', 'Head': 'HEAD', 'All': 'ALL'}


def _annotations(text: str, pos: int):
    """Annotations that follow each other from pos: (name, args or None, start, end). Stops at the first other code."""
    while True:
        m = re.compile(r'\s*@([A-Za-z_][\w.]*)').match(text, pos)
        if not m:
            return
        end = m.end()
        args = None
        p = re.compile(r'\s*\(').match(text, end)
        if p:
            close = call_end(text, p.end() - 1)
            if close < 0:
                return
            args = text[p.end():close]
            end = close + 1
        yield m.group(1).split('.')[-1], args, m.start() + len(m.group(0)) - len(m.group(0).lstrip()), end
        pos = end


def _paths(args: str | None, keys=('value', 'path')) -> list[str] | None:
    """Literal paths of an annotation: positional, value=/path=, or an array of them. [''] without any; None when computed."""
    if args is None or not args.strip():
        return ['']
    parts = split_args(args)
    found: list[str] = []
    for part in parts:
        name, eq, value = part.partition('=')
        if eq and not re.fullmatch(r'\s*\w+\s*', name):
            name, value = '', part
        if eq and name.strip() not in keys:
            continue
        value = (value if eq else part).strip()
        if value.startswith(('{', '[')) and value.endswith(('}', ']')):
            items = split_args(value[1:-1])
            lits = [_literal(i) for i in items]
            if any(x is None for x in lits):
                return None
            found += [x for x in lits if x is not None]
        elif value.startswith('{') and not eq:          # NestJS @Controller({ path: 'x', ... })
            m = re.search(r'\bpath\s*:\s*([\'"`][^\'"`]*[\'"`])', value)
            if not m:
                return ['']
            found.append(_literal(m.group(1)) or '')
        else:
            lit = _literal(value)
            if lit is None:
                return None
            found.append(lit)
    return found or ['']


def _join(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if not path:
        return prefix
    return prefix.rstrip('/') + '/' + path.lstrip('/')


def _decl_after(text: str, pos: int) -> tuple[str, str, int]:
    """What the annotations at pos annotate: ('type', name, offset) or ('method', name, offset of the name)."""
    rest_at = len(text) - len(text[pos:].lstrip()) if pos < len(text) else pos
    t = _TYPE_DECL.match(text, rest_at)
    if t:
        name = re.compile(r'\s*([A-Za-z_]\w*)').match(text, t.end())
        return 'type', name.group(1) if name else '', rest_at
    head = re.compile(r'[^;{}=]*?\b([A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*\(').match(text, rest_at)
    if head:
        return 'method', head.group(1), head.start(1)
    return 'other', '', rest_at


def _annotation_blocks(text: str):
    """Each run of consecutive annotations with the declaration it annotates: (annots, kind, name, name_offset, first_offset)."""
    pos = 0
    while True:
        m = _ANNOT.search(text, pos)
        if not m:
            return
        annots = list(_annotations(text, m.start()))
        if not annots:
            pos = m.end()
            continue
        end = annots[-1][3]
        kind, name, at = _decl_after(text, end)
        yield annots, kind, name, at, annots[0][2]
        pos = max(end, m.end())


def extract_annotated(src: Source, res: Result, names: list[str], framework: str) -> None:
    text = _code_lines(src)
    table = _SPRING if framework == 'spring' else _NEST
    prefix, prefix_line = '', 0
    class_marks: list[str] = []
    for annots, kind, name, at, first in _annotation_blocks(text):
        if kind == 'type':
            prefix, prefix_line, class_marks = '', 0, []
            for a, args, start, _ in annots:
                if (framework == 'spring' and a == 'RequestMapping') or (framework == 'nest' and a == 'Controller'):
                    found = _paths(args)
                    if found is None:
                        res.unrecognized.append((src.path, src.line_of(start), f'@{a}() with a computed prefix: the paths of {name} are shown without it'))
                    elif len(found) > 1:
                        res.unrecognized.append((src.path, src.line_of(start), f'@{a}() with several prefixes: the paths of {name} are shown without them'))
                    else:
                        prefix, prefix_line = found[0], src.line_of(start)
                if a in _SPRING_SECURITY or a == 'UseGuards':
                    class_marks.append(src.row(src.line_of(start)))
            continue
        routes = [(a, args, start) for a, args, start, _ in annots if a in table]
        if not routes or kind != 'method':
            if routes:
                res.unrecognized.append((src.path, src.line_of(routes[0][2]), f'@{routes[0][0]} not followed by a method'))
            continue
        marks = [src.row(src.line_of(start)) for a, _, start, _ in annots if a in _SPRING_SECURITY or a == 'UseGuards']
        handler_line = src.line_of(at)
        signature = ' '.join(src.row(handler_line).split())[:300]
        for a, args, start in routes:
            ln = src.line_of(start)
            method = table[a]
            if method is None:          # @RequestMapping on a method: its method= attribute, any method without one
                verbs = re.findall(r'RequestMethod\.([A-Z]+)', args or '')
                method = ','.join(verbs) if verbs else 'ANY'
            found = _paths(args)
            if found is None:
                res.unrecognized.append((src.path, ln, f'@{a}() with a computed path'))
                continue
            blob = ' '.join(src.rows[ln - 1:handler_line] + marks + class_marks)
            res.inspected += len(found)
            if any(re.search(r'\b' + re.escape(n) + r'\b', blob) for n in names):
                continue
            detail = signature
            if marks or class_marks:
                detail += f' | security: {"; ".join(marks + [m + " (class)" for m in class_marks])}'
            if prefix:
                detail += f' | declared path "{found[0]}" under prefix "{prefix}" (line {prefix_line})' if len(found) == 1 else ''
            for p in found:
                full = _join(prefix, p)
                if framework == 'nest':         # Nest joins controller and handler paths with one slash, from the root
                    full = '/' + full.strip('/')
                res.facts.append(Fact(f'{method} {full} {name}', src.path, ln, handler_line, detail, src.row(ln)))
            if names:
                _, blocks = res.excerpts.setdefault(src.path, (src.rows, []))
                if prefix_line and (prefix_line, prefix_line, True) not in blocks:
                    blocks.insert(0, (prefix_line, prefix_line, True))
                blocks.append((src.line_of(first), handler_line, False))


# ---------------------------------------------------------------- Go routers

_GO_VERBS = {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD', 'Any',
             'Get', 'Post', 'Put', 'Delete', 'Patch', 'Options', 'Head', 'Connect', 'Trace'}
_GO_CALL = re.compile(r'(?<![\w.])([A-Za-z_]\w*)\s*\.\s*(' + '|'.join(sorted(_GO_VERBS, key=len, reverse=True)) + r'|HandleFunc|Handle)\s*\(')
_GO_NOT_ROUTERS = {'http', 'client', 'c', 'ctx', 'req', 'resp', 'res', 'r2', 'os', 'url', 'q', 'values', 'header', 'headers', 'cache', 'm', 'sync'}
_GO_FUNC = re.compile(r'^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)', re.M)
_GO_GROUP = re.compile(r'(?<![\w.])([A-Za-z_]\w*)\s*\.\s*(?:Group|Route|PathPrefix)\s*\(\s*"([^"]*)"')


def _go_functions(src: Source, text: str):
    """(name, parameter names, body start, body end) of each top-level function."""
    for m in _GO_FUNC.finditer(text):
        brace = text.find('{', m.end())
        if brace < 0:
            continue
        end = call_end(text, brace)
        params = [p.strip().split()[0] for p in m.group(2).split(',') if p.strip()]
        yield m.group(1), params, brace, end if end > 0 else len(text)


def extract_go(sources: list[Source], res: Result, names: list[str]) -> None:
    files = [(src, _code_lines(src)) for src in sources]
    funcs: dict[str, list] = {}                 # function name -> [(src, text, params, start, end)]
    for src, text in files:
        for name, params, a, b in _go_functions(src, text):
            funcs.setdefault(name, []).append((src, text, params, a, b))
    param_prefix: dict[tuple[str, str], str] = {}       # (function, parameter) -> prefix given by its callers in these files

    def locals_of(fname, text, a, b) -> dict[str, str]:
        """Variables of a function bound to a router group: their full prefix."""
        env = {p: param_prefix.get((fname, p), '') for _, _, params, _, _ in funcs.get(fname, [])[:1] for p in params}
        for m in re.finditer(r'(?<![\w.])([A-Za-z_]\w*)\s*:?=\s*', text[a:b]):
            g = _GO_GROUP.match(text, a + m.end())
            if g:
                env[m.group(1)] = _join(env.get(g.group(1), ''), g.group(2))
        return env

    for _ in range(4):                          # prefixes flow from main to registration functions, possibly through several calls
        changed = False
        for fname, defs in funcs.items():
            for src, text, params, a, b in defs:
                env = locals_of(fname, text, a, b)
                for m in re.finditer(r'(?<![\w])(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)\s*\(', text[a:b]):
                    callee = m.group(1)
                    if callee not in funcs:
                        continue
                    close = call_end(text, a + m.end() - 1)
                    if close < 0:
                        continue
                    args = split_args(text[a + m.end():close])
                    callee_params = funcs[callee][0][2]
                    for param, arg in zip(callee_params, args):
                        g = _GO_GROUP.match(arg.strip())
                        value = _join(env.get(g.group(1), ''), g.group(2)) if g else env.get(arg.strip())
                        if value is not None and value != '' and param_prefix.get((callee, param)) != value:
                            param_prefix[(callee, param)] = value
                            changed = True
        if not changed:
            break
    callers_seen = {f for f, _ in param_prefix}
    unresolved = set()
    for fname, defs in funcs.items():
        for src, text, params, a, b in defs:
            env = locals_of(fname, text, a, b)
            for m in _GO_CALL.finditer(text, a, b):
                recv, verb = m.group(1), m.group(2)
                if recv in _GO_NOT_ROUTERS:
                    continue
                close = call_end(text, m.end() - 1)
                if close < 0:
                    continue
                args = split_args(text[m.end():close])
                if len(args) < 2:
                    continue
                path = _literal(args[0])
                ln = src.line_of(m.start())
                if path is None:
                    res.unrecognized.append((src.path, ln, f'{recv}.{verb}() with a computed path'))
                    continue
                if path and not path.startswith('/'):
                    continue
                method = verb.upper()
                if verb in ('HandleFunc', 'Handle'):
                    chained = re.compile(r'\s*\.\s*Methods\s*\(([^)]*)\)').match(text, close + 1)
                    method = ','.join(re.findall(r'"(\w+)"', chained.group(1))) if chained else 'ANY'
                handler = 'inline func' if args[-1].lstrip().startswith('func') else ' '.join(args[-1].split())[:80]
                res.inspected += 1
                blob = ' '.join(src.rows[ln - 1:src.line_of(close)])
                if any(re.search(r'\b' + re.escape(n) + r'\b', blob) for n in names):
                    continue
                prefix = env.get(recv, '')
                if not prefix and recv in params and fname not in callers_seen:
                    unresolved.add(f'{fname}({recv})')
                mids = [' '.join(x.split())[:60] for x in args[1:-1]]
                detail = f'middlewares: {", ".join(mids) if mids else "none"} | handler: {handler}'
                if prefix:
                    detail += f' | declared path "{path}" under group prefix "{prefix}"'
                full = _join(prefix, path) or '""'           # a group's own root: written "" in the source
                res.facts.append(Fact(f'{method} {full} {handler}', src.path, ln, src.line_of(close), detail, src.row(ln)))
                if names:
                    _, blocks = res.excerpts.setdefault(src.path, (src.rows, []))
                    blocks.append((ln, src.line_of(close), False))
    if unresolved:
        res.coverage.append(f'Paths are as declared: the router group passed to {", ".join(sorted(unresolved))} is created by a caller outside '
                            'these files, so its prefix is not applied. Every registration is listed; read the caller only if full paths matter.')


# ---------------------------------------------------------------- entry point

def framework_of(src: Source) -> str | None:
    if re.search(r'\.(java|kt|kts)$', src.path):
        return 'spring' if re.search(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\b', src.text) else None
    if re.search(r'\.(ts|mts|cts)$', src.path):
        return 'nest' if re.search(r'@nestjs/|@Controller\s*\(', src.text) else None
    if src.path.endswith('.go'):
        return 'go'
    return None


def extract(sources: list[Source], names: list[str]) -> Result:
    res = Result('routes', '')
    seen = set()
    go = []
    for src in sources:
        fw = framework_of(src)
        if fw is None:
            continue
        seen.add(fw)
        res.files += 1
        if fw == 'go':
            go.append(src)
        else:
            extract_annotated(src, res, names, fw)
    if go:
        extract_go(go, res, names)
    for src in sources:
        for m in re.finditer(r'\.\s*setGlobalPrefix\s*\(\s*([\'"`])([^\'"`]*)\1', src.text):
            res.coverage.append(f'Global prefix "{m.group(2)}" set at {src.path}:{src.line_of(m.start())}: it comes before every NestJS path above.')
    res.scope = '; '.join(SCOPE[f] for f in ('spring', 'nest', 'go') if f in seen or not seen)
    return res
