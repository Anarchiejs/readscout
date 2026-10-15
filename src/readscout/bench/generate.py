"""Benchmark tasks with ground truth computed from the pinned code (never written by hand).

Each ground-truth item points at the line a correct finding must quote (or a span of lines). Negatives are items that
look similar but must NOT be returned; returning one lowers precision.
"""
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import corpus, logs


@dataclass
class Task:
    id: str
    family: str
    difficulty: str            # easy, medium, hard: what the task asks of the model, not its score
    root: Path
    paths: list[str]
    question: str
    gt: list[dict]
    negatives: list[dict] = field(default_factory=list)


def _lines(p: Path) -> list[str]:
    return p.read_text(encoding='utf-8', errors='replace').splitlines()


# ---------------------------------------------------------------- hackathon-starter (Express, one-line routes)

HS_ROUTE = re.compile(r"^app\.(get|post|put|patch|delete)\('([^']+)'(.*)$")


def hackathon(root: Path) -> list[Task]:
    rows = [(i, m[1].upper(), m[2], m[3]) for i, l in enumerate(_lines(root / 'app.js'), 1) if (m := HS_ROUTE.match(l))]

    def item(i, _path):
        return {'line': i, 'path': 'app.js'}
    tasks = []
    for name, test, label, diff in [
        ('auth', lambda r: 'passportConfig.isAuthenticated' in r, 'require a logged-in user (passportConfig.isAuthenticated)', 'medium'),
        ('authorized', lambda r: 'passportConfig.isAuthorized' in r, 'require a linked third-party account (passportConfig.isAuthorized)', 'medium'),
        ('limited', lambda r: re.search(r'\b\w+Limiter\b', r) is not None, 'are rate limited (a *Limiter middleware)', 'medium'),
    ]:
        pos = [item(i, p) for i, m, p, rest in rows if test(rest)]
        neg = [item(i, p) for i, m, p, rest in rows if not test(rest)]
        tasks.append(Task(f'hackathon:routes_{name}', 'routes_filter', diff, root, ['app.js'],
                          f'Which routes in app.js {label}? One finding per route with its method and path. Do not list other routes.',
                          pos, neg))
    pos = [item(i, p) for i, m, p, rest in rows if m == 'POST' and 'isAuthenticated' not in rest]
    neg = [item(i, p) for i, m, p, rest in rows if not (m == 'POST' and 'isAuthenticated' not in rest)]
    tasks.append(Task('hackathon:post_without_auth', 'routes_negation', 'hard', root, ['app.js'],
                      'Which POST routes in app.js are registered WITHOUT passportConfig.isAuthenticated? One finding per route.',
                      pos, neg))

    env: dict[str, dict] = {}
    for f in sorted((root / 'controllers').glob('*.js')):
        for i, l in enumerate(_lines(f), 1):
            for name in re.findall(r'process\.env\.([A-Z][A-Z0-9_]+)', l):
                env.setdefault(name, {'line': i, 'key': name, 'path': f.relative_to(root).as_posix()})
    tasks.append(Task('hackathon:env_controllers', 'env_vars', 'medium', root, ['controllers'],
                      'Which environment variables (process.env.X) does this code read? One finding per variable name.',
                      list(env.values())))

    rnd = random.Random(11)
    for fname in ['api.js', 'user.js', 'ai.js', 'ai-agent.js']:
        f = root / 'controllers' / fname
        ls = _lines(f)
        blocks = []
        for i, l in enumerate(ls):
            if l.strip() == '/**':
                end = next((j for j in range(i + 1, min(i + 15, len(ls))) if ls[j].strip() == '*/'), None)
                if end is None or end + 1 >= len(ls) or 'exports.' not in ls[end + 1] and 'const ' not in ls[end + 1]:
                    continue
                desc = ' '.join(x.strip().lstrip('*').strip() for x in ls[i + 1:end]
                                if not re.match(r'^\s*\*\s*(GET|POST|PUT|PATCH|DELETE)\s', x) and not x.strip().startswith('* @'))
                if len(desc) >= 25:
                    blocks.append((i + 1, end + 2, desc))
        counts: dict[str, int] = {}
        for b in blocks:
            counts[b[2]] = counts.get(b[2], 0) + 1
        unique = [b for b in blocks if counts[b[2]] == 1]
        for start, code, desc in rnd.sample(unique, min(2, len(unique))):
            tasks.append(Task(f'hackathon:locate:{fname}:{code}', 'locate', 'medium', root, [f'controllers/{fname}'],
                              f'Where is the code that does the following? "{desc}" Give the location of that code in one finding.',
                              [{'line': code, 'path': f'controllers/{fname}', 'span': [start, code + 8]}]))
    return tasks


# ---------------------------------------------------------------- express-boilerplate (chained multi-line routes)

def boilerplate(root: Path) -> list[Task]:
    routes = []   # (file, line, method, path, auth)
    for fname in ['src/routes/v1/user.route.js', 'src/routes/v1/auth.route.js']:
        current = None
        for i, l in enumerate(_lines(root / fname), 1):
            if m := re.search(r"\.route\('([^']+)'\)", l):
                current = m[1]
            elif m := re.match(r"\s*\.(get|post|put|patch|delete)\((.*)", l):
                auth = re.search(r"auth\(('([^']*)')?\)", m[2])
                routes.append((fname, i, m[1].upper(), current, auth[2] if auth and auth[2] else ('any' if auth else None)))
            elif m := re.match(r"router\.(get|post|put|patch|delete)\('([^']+)',(.*)", l):
                auth = re.search(r"auth\(('([^']*)')?\)", m[3])
                routes.append((fname, i, m[1].upper(), m[2], auth[2] if auth and auth[2] else ('any' if auth else None)))
    files = ['src/routes/v1/user.route.js', 'src/routes/v1/auth.route.js']
    it = lambda r: {'line': r[1], 'path': r[0]}
    tasks = [Task('boilerplate:routes_all', 'routes_list', 'hard', root, files,
                  'List every HTTP route defined in these files: one finding per route with its method and full path '
                  '(routes declared with router.route(path) apply the path to the chained .get/.post/... lines).',
                  [it(r) for r in routes])]
    manage = [r for r in routes if r[4] == 'manageUsers']
    tasks.append(Task('boilerplate:routes_manage', 'routes_filter', 'hard', root, files,
                      "Which routes require the 'manageUsers' permission (auth('manageUsers'))? One finding per route with method and path.",
                      [it(r) for r in manage], [it(r) for r in routes if r not in manage]))
    open_ = [r for r in routes if r[4] is None]
    tasks.append(Task('boilerplate:routes_without_auth', 'routes_negation', 'hard', root, files,
                      'Which routes are registered WITHOUT the auth(...) middleware? One finding per route with method and path.',
                      [it(r) for r in open_], [it(r) for r in routes if r not in open_]))
    keys = [{'line': i, 'key': m[1], 'path': 'src/config/config.js'}
            for i, l in enumerate(_lines(root / 'src/config/config.js'), 1) if (m := re.match(r'\s+([A-Z][A-Z0-9_]+): Joi', l))]
    tasks.append(Task('boilerplate:env_schema', 'env_vars', 'easy', root, ['src/config/config.js'],
                      'Which environment variables does this configuration validate? One finding per variable name.', keys))
    return tasks


# ---------------------------------------------------------------- fastapi-template (Python, implicit auth)

def fastapi(root: Path) -> list[Task]:
    base = 'backend/app/api/routes'
    eps = []   # (file, decorator_line, def_line, path, kind)
    for f in sorted((root / base).glob('*.py')):
        ls = _lines(f)
        rel = f.relative_to(root).as_posix()
        for i, l in enumerate(ls):
            if not re.match(r'@router\.(get|post|put|patch|delete)\(', l):
                continue
            j = next(k for k in range(i, len(ls)) if ls[k].startswith('def ') or ls[k].startswith('async def '))
            k = next(n for n in range(j, len(ls)) if re.search(r'\)\s*(->.*)?:\s*$', ls[n]))
            deco, sig = '\n'.join(ls[i:j]), '\n'.join(ls[j:k + 1])
            path = re.search(r'"([^"]*)"', deco)
            kind = 'superuser' if 'get_current_active_superuser' in deco + sig else 'user' if 'CurrentUser' in sig else 'public'
            eps.append((rel, i + 1, j + 1, path[1] if path else '', kind))
    it = lambda e: {'line': e[1], 'path': e[0], 'span': [e[1], e[2]]}
    files = [base]
    su = [e for e in eps if e[4] == 'superuser']
    pub = [e for e in eps if e[4] == 'public']
    return [
        Task('fastapi:endpoints_all', 'routes_list', 'medium', root, files,
             'List every API endpoint declared in this folder: one finding per endpoint with its HTTP method and path.',
             [it(e) for e in eps]),
        Task('fastapi:superuser_only', 'routes_filter', 'hard', root, files,
             'Which endpoints require a superuser (get_current_active_superuser)? One finding per endpoint.',
             [it(e) for e in su], [it(e) for e in eps if e not in su]),
        Task('fastapi:public_endpoints', 'routes_negation', 'hard', root, files,
             'Which endpoints can be called WITHOUT being logged in (no CurrentUser parameter and no superuser dependency)? '
             'One finding per endpoint.', [it(e) for e in pub], [it(e) for e in eps if e not in pub]),
    ]


# ---------------------------------------------------------------- nextjs-subscriptions (Supabase, split lines)

def nextjs(root: Path) -> list[Task]:
    gt = []
    for f in sorted((root / 'utils/supabase').glob('*.ts')):
        for i, l in enumerate(_lines(f), 1):
            if re.search(r"\.from\('([a-z_]+)'\)", l):
                gt.append({'line': i, 'path': f.relative_to(root).as_posix(), 'span': [i - 1, i + 1]})
    return [Task('nextjs:supabase_access', 'data_access', 'medium', root, ['utils/supabase'],
                 'Which Supabase tables does this code access (supabase.from("...")), and with which operation '
                 '(select, insert, upsert, update, delete)? One finding per access.', gt)]


GENERATORS = {'hackathon-starter': hackathon, 'express-boilerplate': boilerplate, 'fastapi-template': fastapi,
              'nextjs-subscriptions': nextjs}


def build(verify=True) -> list[Task]:
    tasks = []
    for repo in corpus.REPOS:
        tasks += GENERATORS[repo.name](corpus.fetch(repo, verify=verify))
    tasks += logs.tasks(corpus.cache_dir() / 'logs')
    return tasks
