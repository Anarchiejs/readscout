"""Campaign two: offline preparation, one-cell execution, and evidence-only reports."""
import argparse
import hashlib
import html
import importlib.util
import json
import os
import random
import re
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

from readscout import agents, backend, extract, logs, tasks
from readscout.bench import generate
from readscout.text import Line, locate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/token-savings/v2'
POINTER = ROOT / '.git/token-savings-v2-work.json'
BASE = ROOT / 'docs/token-savings/results.json'
spec = importlib.util.spec_from_file_location('campaign_one_harness', ROOT / 'scripts/token_savings.py')
assert spec and spec.loader
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
SEED = 2026101602
READ = re.compile(r'(?i)\b(rg|grep|sed|cat|type|Get-Content|Select-String|read_text|read_bytes)\b')
CITE = re.compile(r'^- (.+?):(\d+)(?:-(\d+))?(?=\s|$)', re.M)
QUOTE = re.compile(r'\u00ab (.*?) \u00bb')


def hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'src/readscout').rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(meta, work=None):
    old.write_json(OUT / 'results.json', meta)
    if work:
        old.write_json(work / 'meta.json', meta)


def safe_delete(work):
    work = work.resolve()
    if work.parent != Path(tempfile.gettempdir()).resolve() or not work.name.startswith('readscout-v2-'):
        raise ValueError('Unsafe cleanup path')
    shutil.rmtree(work)


def verified(task, answer):
    scope = {old.normalize_path(p, task.root) for p in tasks.expand(task.paths, [task.root])}
    out, wrong, used = [], 0, set()
    for f in answer.get('findings', []):
        try:
            p = old.normalize_path(f['path'], task.root)
            if p not in scope:
                raise ValueError('Out of scope')
            lines = [Line(p, n, s) for n, s in enumerate((task.root / p).read_text(encoding='utf-8').splitlines(), 1)]
            hit = locate(f['quote'], lines, int(f['line']), used, p)
            if not hit:
                raise ValueError('Quote not found')
            used.add(hit)
            out.append((*hit, f['answer'], f['quote']))
        except (KeyError, ValueError, OSError, TypeError):
            wrong += 1
    return out, wrong


def grade_v2(task, answer):
    """Keep v1 location rules, allow proven env occurrences across scope, check explicit semantic GT."""
    vs, wrong = verified(task, answer)

    def hit(g, v):
        if task.family == 'env_vars' and g.get('key'):
            # A claim alone is insufficient: the variable must occur in the verified source quote.
            return bool(re.search(r'\b' + re.escape(g['key']) + r'\b', v[4]))
        if not old._hit(g, v, task.family):
            return False
        text = (v[3] + ' ' + v[4]).lower()
        return all(str(g[k]).lower() in text for k in ('method', 'route', 'table', 'operation', 'description') if k in g)

    found = {i for i, g in enumerate(task.gt) if any(hit(g, v) for v in vs)}
    good = sum(any(hit(g, v) for g in task.gt) for v in vs)
    p = good / (len(vs) + wrong) if vs or wrong else 0.0
    if task.family == 'log':
        p = (len(vs) / (len(vs) + wrong)) if good else 0.0
    if task.family == 'locate' and vs and hit(task.gt[0], vs[0]):
        p = len(vs) / (len(vs) + wrong)
    r = len(found) / len(task.gt) if task.gt else 1.0
    return {'precision': round(p, 3), 'recall': round(r, 3),
            'f1': round(2 * p * r / (p + r), 3) if p + r else 0.0,
            'unverifiable': wrong, 'verified': len(vs),
            'negatives_returned': sum(any(hit(g, v) for g in task.negatives) and not any(hit(g, v) for g in task.gt) for v in vs)}


def receipt_answer(text):
    """Parse only quoted finding rows; omit unquoted not-recognized diagnostics."""
    rows = []
    for row in text.splitlines():
        m = CITE.match(row)
        if not m:
            continue
        qs = QUOTE.findall(row)
        if qs:
            rows.append({'path': m[1], 'line': int(m[2]), 'quote': qs[0], 'answer': row[m.end():row.index('\u00ab')].strip()})
            # A deterministic trace can also cite its closing exception line.
            end = re.search(r'ends (.+?):(\d+) ', row)
            if end and len(qs) > 1:
                rows.append({'path': end[1], 'line': int(end[2]), 'quote': qs[1], 'answer': 'trace closing exception'})
    return {'findings': rows}


def instrument(raw, task=None):
    """Conservative command-level phase and re-read proxies, without pretending they are request usage."""
    items = []
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get('type') == 'item.completed':
            items.append(e.get('item', {}))
    calls, receipts, rereads, cited = [], [], [], set()
    delegated = False
    for item in items:
        kind = item.get('type')
        if kind == 'mcp_tool_call' and item.get('tool') in ('local_ask', 'local_digest') and item.get('server') == 'readscout':
            result = item.get('result', {})
            text = '\n'.join(c.get('text', '') for c in result.get('content', []) if isinstance(c, dict)) if isinstance(result, dict) else str(result)
            cited.update(p.replace('\\', '/') for p, _, _ in CITE.findall(text))
            status = re.search(r'status: (complete|partial|undetermined)', text, re.I)
            rec = {'status': status[1].lower() if status else 'not measured', 'text': text,
                   'next_action': 'stopped', 'receipt_v1': old.grade_answer(task, receipt_answer(text)) if task else None,
                   'receipt_v2': grade_v2(task, receipt_answer(text)) if task else None}
            receipts.append(rec)
            phase, chars = 'readscout', len(text)
            delegated = True
        elif kind == 'command_execution':
            cmd = item.get('command', '')
            output = item.get('aggregated_output', '')
            lower = cmd.lower().replace('\\', '/')
            core = 'skill.md' in lower and 'readscout' in lower
            refs = 'references/' in lower and 'readscout' in lower
            touched = [p for p in cited if p.lower() in lower or Path(p).name.lower() in lower]
            targeted = bool(re.search(r"sed\s+-n\s+['\"]?\d+(?:,\d+)?p|Select-Object\s+-Skip\s+\d+.*?-First\s+\d+|\[\d+\.\.\d+\]", cmd, re.I))
            # Regex line-range evidence is a proxy. Ambiguous commands remain broad.
            phase = 'skill' if core or refs else 'discovery' if re.search(r'AGENTS\.md|--files|Get-ChildItem|\bls\b', cmd, re.I) else 'fallback' if delegated else 'discovery'
            if delegated and READ.search(cmd) and (touched or re.search(r'\b(rg|grep|Select-String)\b', cmd, re.I)) and not (core or refs):
                mode = 'targeted' if targeted and touched else 'broad'
                phase = 'verification' if mode == 'targeted' else 'fallback'
                rereads.append({'mode': mode, 'chars': len(output), 'files': touched, 'command': cmd,
                                'file_overlap': 'explicit' if touched else 'possible: broad search scope'})
                if receipts:
                    receipts[-1]['next_action'] = 'fallback' if mode == 'broad' else 'targeted check'
            chars = len(output)
            calls.append({'phase': phase, 'chars': chars, 'command': cmd, 'core': core, 'references': refs})
            continue
        elif kind == 'agent_message':
            phase, chars = 'final', len(item.get('text', ''))
        else:
            continue
        calls.append({'phase': phase, 'chars': chars})
    return {'calls': calls, 'receipts': receipts, 'rereads': rereads,
            'skill_core': any(c.get('core') for c in calls), 'skill_references': any(c.get('references') for c in calls),
            'readscout_calls': len(receipts), 'fallbacks': sum(r['next_action'] == 'fallback' for r in receipts),
            'request_usage': None, 'request_usage_reason': '--ephemeral creates no rollout; JSON exposes turn aggregate only',
            'context_chars': None, 'context_chars_reason': 'Tool output characters are a proxy; model-bound truncation not exposed',
            'phase_tokens': None, 'phase_tokens_reason': 'No request-level usage: tool phases cannot be assigned token costs'}


def custom_tasks(work):
    root = work / 'readscout-holdout'
    for name in ('paths.py', 'web.py'):
        dest = root / 'src/readscout' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'src/readscout' / name, dest)
    envpath, webpath = 'src/readscout/paths.py', 'src/readscout/web.py'
    envlines = (root / envpath).read_text(encoding='utf-8').splitlines()
    weblines = (root / webpath).read_text(encoding='utf-8').splitlines()

    def line(rows, needle):
        return next(i for i, row in enumerate(rows, 1) if needle in row)

    envgt = [{'path': envpath, 'line': line(envlines, needle), 'key': key} for key, needle in
             [('READSCOUT_HOME', "base = Path(os.environ['READSCOUT_HOME'])"), ('APPDATA', "os.environ.get('APPDATA'"),
              ('XDG_CONFIG_HOME', "os.environ.get('XDG_CONFIG_HOME'"), ('READSCOUT_CLI', "os.environ.get('READSCOUT_CLI'")]]
    routegt = []
    for route in ('/', '/setup', '/api/ping', '/api/state', '/api/pull', '/api/models', '/api/agent', '/api/ollama-env'):
        get = route in ('/', '/setup', '/api/ping', '/api/state')
        needle = "if path in ('/', '/setup'):" if route in ('/', '/setup') else "if " + ('path' if get else 'self.path') + f" == '{route}':"
        n = line(weblines, needle)
        routegt.append({'path': webpath, 'line': n, 'span': [n, n + 1], 'method': 'GET' if get else 'POST', 'route': route})
    data = [
        ('load_config', "cfg = json.loads(p.read_text"),
        ('save_config', 'tmp.write_text(json.dumps(cfg'),
        ('save_config', 'tmp.replace(p)'),
    ]
    datagt = [{'path': envpath, 'line': line(envlines, needle), 'description': name, 'operation': operation}
              for (name, needle), operation in zip(data, ('read', 'write', 'replace'))]
    fixture = root / 'build.log'
    fixture.write_text('2026-10-16 08:00:00 INFO build started\n'
                       '2026-10-16 08:00:01 ERROR compiler: missing header widget.h\n'
                       '2026-10-16 08:00:02 ERROR linker skipped after compiler failure\n'
                       '2026-10-16 08:00:03 INFO build stopped with exit code 1\n', encoding='utf-8')
    return [
        generate.Task('readscout:env_locations', 'env_vars', 'easy', root, [envpath], 'List the environment variables read by name in paths.py, one finding per variable.', envgt),
        generate.Task('readscout:http_routes', 'routes_list', 'medium', root, [webpath], 'List each explicit HTTP path handled by Handler, one finding per method and path. Exclude 404 fallbacks.', routegt),
        generate.Task('readscout:routes_without_token', 'routes_negation', 'medium', root, [webpath], 'Which explicit HTTP paths have handlers that do not check X-Readscout-Token? Give one finding per method and path. Check only Handler in this file.', [g for g in routegt if g['method'] == 'GET'], [g for g in routegt if g['method'] == 'POST']),
        generate.Task('readscout:config_data_access', 'data_access', 'medium', root, [envpath], 'List direct configuration file data accesses in load_config and save_config: the read, temporary write and atomic replacement. Name function and operation in each finding.', datagt),
        generate.Task('readscout:build_log', 'log', 'easy', root, ['build.log'], 'What went wrong? Give first the earliest root-cause error, then the consequences. Ignore noise.', [{'path': 'build.log', 'line': 2, 'key': 'missing header', 'span': [2, 2]}]),
    ]


def offline(all_tasks, baseline):
    rows = []
    for task in all_tasks:
        if task.family not in ('env_vars', 'routes_list', 'routes_filter', 'routes_negation', 'data_access', 'log'):
            continue
        lines = tasks.gather(task.paths, [task.root])
        nbytes = sum(len(ln.text) + 1 for ln in lines)
        kind = 'env' if task.family == 'env_vars' else 'supabase' if task.family == 'data_access' else 'endpoints' if task.id.startswith('fastapi:') else 'routes'
        if task.family == 'log':
            groups = logs.group_events(lines)
            text = tasks.digest_receipt(lines, groups, nbytes, 25)
            unknown = 0
            deterministic = len(groups) <= tasks.DETERMINISTIC_MAX_GROUPS
        else:
            kind = 'endpoints!CurrentUser' if task.id == 'fastapi:public_endpoints' else kind
            res = extract.run(kind, lines)
            text = tasks.extract_receipt(res, nbytes, 40, 'local_ask extract=' + kind)
            unknown = len(res.unrecognized)
            deterministic = True
        answer = receipt_answer(text)
        checks = []
        for f in answer['findings']:
            hit = locate(f['quote'], lines, f['line'], file=f['path'])
            exact = any(ln.path == f['path'] and ln.no == f['line'] and f['quote'] in ln.text for ln in lines)
            raw = (task.root / f['path']).read_text(encoding='utf-8').splitlines()[f['line'] - 1]
            checks.append({'path': f['path'], 'line': f['line'], 'located': bool(hit), 'verbatim_raw': f['quote'] in raw,
                           'verbatim_loaded': exact, 'added_ellipsis': '...' in f['quote'] and '...' not in raw,
                           'masked_reference': '[REDACTED]' in f['quote'] and 'process.env.' in raw})
        rows.append({'task': task.id, 'extract': kind if task.family != 'log' else 'digest', 'deterministic': deterministic,
                     'status': re.search(r'status: (\w+)', text)[1], 'not_recognized': unknown,
                     'v1': old.grade_answer(task, answer), 'v2': grade_v2(task, answer), 'citations': checks, 'receipt': text,
                     'note': 'Unfiltered structural output, no question-specific route filter or semantic model inference'})
    previous_skill = old.command(['git', 'show', baseline['source_commit'] + ':src/readscout/skill/SKILL.md']).stdout
    previous_server = old.command(['git', 'show', baseline['source_commit'] + ':src/readscout/server.py']).stdout
    # Exact current tool schemas, and old schemas reconstructed by importing frozen server.py in a temporary module.
    from readscout.server import mcp
    import asyncio
    current_tools = asyncio.run(mcp.list_tools())
    source = previous_server.replace('from . import editing, paths, tasks', 'from readscout import editing, paths, tasks').replace('from .backend import BackendError', 'from readscout.backend import BackendError').replace('from .text import AccessError', 'from readscout.text import AccessError')
    namespace = {'__name__': 'frozen_campaign_one_server'}
    exec(compile(source, '<frozen-server>', 'exec'), namespace)
    previous_tools = asyncio.run(namespace['mcp'].list_tools())

    def sizes(text):
        return {'chars': len(text), 'tokens_est': len(text) / 4, 'estimator': '4 characters/token; not tokenizer-exact'}

    return rows, {'B1': {'skill': sizes(previous_skill), 'tools': sizes(json.dumps([t.model_dump(mode='json', exclude_none=True) for t in previous_tools], ensure_ascii=False, sort_keys=True))},
                  'B2': {'skill': sizes(agents.SKILL.read_text(encoding='utf-8')), 'tools': sizes(json.dumps([t.model_dump(mode='json', exclude_none=True) for t in current_tools], ensure_ascii=False, sort_keys=True))}}


def prepare():
    if POINTER.exists() or (OUT / 'results.json').exists():
        raise SystemExit('Refuse to overwrite campaign 2')
    base = read_json(BASE)
    current = old.command(['codex', '--version']).stdout.strip()
    if current != base['codex']:
        raise SystemExit('CLI version differs: ask user before remeasuring A and B1')
    work = Path(tempfile.mkdtemp(prefix='readscout-v2-campaign-'))
    old.write_json(POINTER, {'work': str(work)})
    os.environ['READSCOUT_HOME'] = str(work / 'corpus-state')
    built = generate.build()
    custom = custom_tasks(work)
    by_id = {t.id: t for t in built + custom}
    tuning = [dict(t, set='tuning', family=by_id[t['id']].family) for t in base['tasks']]
    holdids = ['boilerplate:routes_manage', 'hackathon:locate:user.js:851', 'logs:ingest-4000.log'] + [t.id for t in custom]
    holdout = [{'id': key, 'set': 'holdout', 'group': 'holdout', 'family': by_id[key].family,
                'paths': by_id[key].paths, 'bytes': old.size(by_id[key])} for key in holdids]
    random.Random(SEED).shuffle(tuning)
    random.Random(SEED + 1).shuffle(holdout)
    for i, t in enumerate(holdout):
        t['order'] = ['A', 'B2'] if i % 2 == 0 else ['B2', 'A']
    for t in tuning:
        t['order'] = ['B2']
    controls = [{'task': 'control', 'config': 'A'}, {'task': 'control', 'config': 'B2'},
                {'task': min((t for t in built if t.family == 'locate'), key=old.size).id, 'config': 'B2', 'extra_control': True}]
    cells = [{'task': key, 'config': c, 'phase': 'pilot'} for key in old.PILOT for c in ('A', 'B2')]
    cells += [dict(c, phase='controls') for c in controls]
    cells += [{'task': t['id'], 'config': 'B2', 'phase': 'tuning'} for t in tuning if t['id'] not in old.PILOT]
    cells += [{'task': t['id'], 'config': c, 'phase': 'holdout'} for t in holdout for c in t['order']]
    structural, overhead = offline(built, base)
    for c in ('A', 'B'):
        home = work / c / '.codex'
        home.mkdir(parents=True)
        auth = Path.home() / '.codex/auth.json'
        if not auth.is_file():
            raise SystemExit('Authentication unavailable; no online session started')
        shutil.copyfile(auth, home / 'auth.json')
        (home / 'config.toml').write_text(f'model = {json.dumps(base["model"])}\nmodel_reasoning_effort = {json.dumps(base["effort"])}\napproval_policy = "never"\nsandbox_mode = "read-only"\n', encoding='utf-8')
    dest = work / 'B/.agents/skills/readscout/SKILL.md'
    agents._copy_skill(dest)
    cfg = work / 'B/.codex/config.toml'
    with cfg.open('a', encoding='utf-8') as f:
        f.write('\n[mcp_servers.readscout]\ncommand = ' + json.dumps(Path(sys.executable).as_posix()) + '\nargs = ["-m", "readscout.server"]\n')
    audit = old.isolate_skills(work)
    old.write_json(work / 'schema.json', old.SCHEMA)
    sandbox = old.sandbox_probe(work)
    old.command(['icacls', str(work / 'readscout-holdout'), '/grant', '*S-1-1-0:(OI)(CI)(RX)', '/T', '/Q'])
    meta = {'campaign': 2, 'date': '2026-10-16', 'seed': SEED, 'model': base['model'], 'effort': base['effort'], 'codex': current,
            'source_commit': old.command(['git', 'rev-parse', 'HEAD']).stdout.strip(), 'source_hashes': hashes(),
            'baseline_sha256': hashlib.sha256(BASE.read_bytes()).hexdigest(), 'baseline_source_commit': base['source_commit'],
            'tasks': tuning + holdout, 'cells': cells, 'attempts': [], 'controls': [],
            'structural_coverage': structural, 'fixed_overhead': overhead, 'isolation_audit': audit, 'sandbox_probe': sandbox,
            'preexisting_models': list(backend.loaded_models('http://127.0.0.1:11434')),
            'budget': {'max_tokens': None, 'reason': 'User authorized remaining account quota, exposed as percentages only',
                       'initial_primary_used_percent': 79, 'initial_secondary_used_percent': 28,
                       'primary_stop_used_percent': 97.9, 'secondary_stop_used_percent': 92.8,
                       'reset_policy': 'Stop at initial window reset; do not spend refreshed quota', 'stop_at_fraction': 0.9},
            'deviations': ['User authorized five new ReadScout holdout tasks because unused corpus families are insufficient.',
                           'Numeric token ceiling unavailable: user authorized remaining quota; use percentage gate and record tokens actually spent.',
                           'B1 trivial control reused from campaign 1; A and B2 controls remeasured.',
                           'Work sessions not run: CLI resume exists but --ephemeral prevents persistence needed to resume. No four-question batching substituted.'],
            'work_sessions': {'status': 'not measured', 'reason': 'Noninteractive resume requires saved sessions; frozen isolation requires --ephemeral'},
            'repetitions': {'status': 'not measured', 'reason': 'None by default; no automatic repetitions authorized'},
            'baseline_regraded': [], 'baseline_controls': base['controls'], 'baseline_attempts': base['attempts']}
    for row in base['attempts']:
        task = by_id[row['task']]
        rawpath = ROOT / 'docs/token-savings/runs' / (row['task'].replace(':', '_') + f'-{row["config"]}-{row["attempt"]}.jsonl')
        meta['baseline_regraded'].append({'task': task.id, 'config': 'B1' if row['config'] == 'B' else 'A',
                                          'v1': row['grade'], 'v2': grade_v2(task, row['answer']),
                                          'instrumentation': instrument(rawpath.read_text(encoding='utf-8'), task) if rawpath.exists() else None})
    meta['custom_ground_truth'] = [{'id': t.id, 'family': t.family, 'paths': t.paths, 'question': t.question,
                                    'gt': t.gt, 'negatives': t.negatives} for t in custom]
    for c in custom:
        for p in c.paths:
            meta.setdefault('holdout_hashes', {})[p] = hashlib.sha256((c.root / p).read_bytes()).hexdigest()
    save(meta, work)
    write_protocol(meta)
    print(json.dumps({'prepared': True, 'structural_tasks': len(structural), 'cells': len(cells), 'isolation': audit,
                      'citation_failures': sum(not c['located'] or not c['verbatim_raw'] or c['added_ellipsis'] or c['masked_reference'] for r in structural for c in r['citations'])}, indent=2))


def write_protocol(meta):
    text = '''# Campaign 2 frozen protocol

Freeze before any measured session. Append deviations only. Source under test is
committed separately and checked by hashes before every cell. Campaign 1 remains
unchanged except the expressly requested Campaign 2 report pointer.

## Question, conditions, and isolation

B2 versus reused B1 is primary; B2 versus reused A is secondary. Model, effort,
CLI, exact source commit and file hashes are below. Fresh pilot A cells are
diagnostics, excluded from tuning comparisons. B2 pilot cells count if harness
does not change. One run per cell, sequential; no warmup, 1200-second timeout.
No extra retries or repetitions automatically. Preserve failed attempts. Stop
on isolation failure, absent pilot MCP execution, more than three failed cells,
or B2 cumulative token total at least 10% above B1 after six tuning tasks.
The numeric definition of clearly worse is pre-registered here as 10%.

Use only temporary HOME/USERPROFILE/CODEX_HOME/APPDATA/READSCOUT_HOME, copied
authentication never logged, isolated complete skill directory, no account apps
or plugins, and read-only sandbox. Existing models/processes remain untouched;
skip online execution if a model is already resident because shared GPU handoff
could unload it. The B2 server uses this venv explicitly. Stop only campaign-owned
models. Delete fake homes at completion. CLI flags checked against local help:
--json --ephemeral --skip-git-repo-check --sandbox read-only -c approval_policy="never"
-m MODEL -c model_reasoning_effort=EFFORT -C ROOT --output-schema SCHEMA -o FINAL.
Controls use no output schema. --no-daemon and isolation overrides follow the
campaign 1 verified option positions. Do not mutate user config or Ollama settings.

## Tasks and budget

Tuning IDs and groups copied from campaign 1 without recomputation. They were
visible during improvement development. Holdout is reported separately: three
unused corpus tasks plus five newly authored ReadScout tasks, as authorized by
the user. This is task-level holdout, not a claim of independently held-out source
repositories. Synthetic build log is fixed before any run. Exact questions,
ground truth, seed, randomized order, cell list, budget and stop rules are below.
User authorized remaining quota. Account tool exposes percentages, not a token
allowance: max_tokens is not measured, never inferred from percentages. Observe
account limits before each cell and stop at the recorded 90% thresholds or reset.
Use a fresh external quota checkpoint per invocation; never loop online cells.
Unreported failed usage blocks continuation until reconciled.

## Prompt and schema

Identical to campaign 1, with no delegation hints:

```text
''' + old.PROMPT + '''
```

```json
''' + json.dumps(old.SCHEMA, indent=2) + '''
```

## Metrics, attribution, and scoring

All usage fields verbatim. Primary = input + output; secondary = input - cached
input + output; sensitivity discounts cached input to 10% (assumption, not price).
Both sum-weighted savings and mean task percentages, per task/family/group/set.
Win above 5% saving, tie within inclusive +/-5%, loss below -5%. Savings require
mean F1 loss <=0.05, no extra unverifiable findings, incomplete results visible.
Only completed pairs enter paired comparisons; report missing/failed cells.

Scorer v1: unchanged campaign 1 benchmark plus its source verification penalty.
Scorer v2: same scope and locate check. An env variable can be cited anywhere in
scope if its exact identifier is in the verified source quote. A claim unsupported
by its quote does not count. All explicit method, route, table, operation and
description ground-truth fields must appear case-insensitively in quote plus
answer. Original corpus GT only has locations/keys/spans, so semantic properties
absent from that GT are not invented; new ReadScout route/data tasks carry them.
Compute recall over targets, precision over findings including unverifiable ones;
preserve v1 special log/locate precision. Regrade original A/B1 separately.
No configuration label enters either scorer. Record receipt-only and final F1.

Tool phase rules (ordered): skill core or references read = skill; readscout MCP
= readscout; after delegation explicit cited-file line window = verification;
other read/search after delegation = fallback; listing/instructions and reads
before delegation = discovery; agent final = final. These are command proxies.
Count re-reads when a later read command names a receipt file, or a broad search
may cover it (mark uncertain overlap). Targeted = sed explicit numeric line range,
Select-Object -Skip plus -First, or numeric index slice, and a named cited file;
ambiguous commands are broad. Record returned chars, targeted share, broad chars
per reading MCP call. Receipt status comes from header, not inconsistent metrics.
Next action = stopped, targeted check, or fallback. Skill read detection is based
on readscout + SKILL.md or references/ in completed shell commands.
--ephemeral has no rollout; JSON turn usage is aggregate. Per-request usage,
phase token costs, true post-truncation context and separate local load/inference
time are not measured unless directly exposed. Never allocate aggregate tokens
to commands. Preserve local telemetry verbatim and flag unavailable fields.

## Hypotheses and falsifiers

- H1: W B2/A saving >=10%; refuted below 10%.
- H2: L B2 >= A; refuted by positive aggregate savings.
- H3: mean B2 F1 >= A F1 -0.05; refuted below, for both scorers.
- H4: tokens_avoided_est > measured A-B2; refuted otherwise.
- H5: at least one B2 task does not call readscout; refuted if all call it.
- H6: B2 control tokens < B1 control; refuted if >=.
- H7: B2 broad re-read chars per reading call < B1; refuted if >=.
- H8: logs B2 tokens < B1, small-log overhead versus A <27%; refuted otherwise.
- H9: extraction receipts complete with no broad/full-file later reads; refuted
  by any broad re-read after a complete extraction receipt.
- H10: B2 mean F1 >= B1 -0.05 in tuning and holdout with both scorers; refuted
  below. Holdout/B1 is inconclusive because B1 was not measured there.
- H11: holdout B2/A saving >= half tuning B2/A saving; refuted below.
- H12: tuning sum-weighted B2/A saving >=30%; refuted below.

Missing required evidence = inconclusive. No significance claim from one cell.
No ablation: contributions of the six changes cannot be independently estimated.
Changes include source quotes/file schema, shorter skill and references, bounded
status receipts, deterministic logs, syntax extraction, and unified findings cap.
Original and new conditions differ in schema/skill/digest/tool descriptions.

## Frozen metadata

```json
'''
    frozen = {k: v for k, v in meta.items() if k not in ('structural_coverage', 'baseline_attempts', 'baseline_regraded', 'baseline_controls', 'attempts', 'controls')}
    (OUT / 'PROTOCOL.md').write_text(text + json.dumps(frozen, indent=2) + '\n```\n', encoding='utf-8')


def quota_stop(budget, primary_used, secondary_used, resets_at, now):
    if now >= resets_at:
        return 'Initial quota window reset; refreshed allowance not authorized'
    if primary_used >= budget['primary_stop_used_percent'] or secondary_used >= budget['secondary_stop_used_percent']:
        return '90% of initially remaining account quota reached'
    return None


def next_cell(quota_used, secondary_used, resets_at):
    work = Path(read_json(POINTER)['work'])
    meta = read_json(OUT / 'results.json')
    if meta.get('stop_reason'):
        raise SystemExit(meta['stop_reason'])
    reason = quota_stop(meta['budget'], quota_used, secondary_used, resets_at, time.time())
    if reason:
        meta['stop_reason'] = reason
        save(meta, work)
        raise SystemExit(meta['stop_reason'])
    if hashes() != meta['source_hashes'] or hashlib.sha256(BASE.read_bytes()).hexdigest() != meta['baseline_sha256']:
        raise SystemExit('Frozen source or baseline changed')
    if old.command(['git', 'status', '--porcelain', '--', 'scripts/token_savings.py', 'scripts/token_savings_v2.py', 'tests/test_token_savings.py', 'docs/token-savings/v2/PROTOCOL.md']).stdout:
        raise SystemExit('Commit protocol, harness and tests before measured runs')
    if meta['preexisting_models'] or backend.loaded_models('http://127.0.0.1:11434'):
        raise SystemExit('Existing model residency: do not interfere with user processes')
    if sys.platform == 'win32':
        running = old.command(['powershell', '-NoProfile', '-Command', "@(Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue).Count"])
        if running.returncode or running.stdout.strip() != '0':
            raise SystemExit('Existing llama-server or unavailable process check; do not interfere')
    done = {(r['task'], r['config'], r['phase']) for r in meta['attempts']}
    cell = next((c for c in meta['cells'] if (c['task'], c['config'], c['phase']) not in done), None)
    if not cell:
        meta['complete'] = True
        save(meta, work)
        print('All scheduled cells complete')
        return
    os.environ['READSCOUT_HOME'] = str(work / 'corpus-state')
    all_tasks = {t.id: t for t in generate.build() + custom_tasks(work)}
    task = all_tasks.get(cell['task'])
    config = 'B' if cell['config'] == 'B2' else 'A'
    slug = cell['task'].replace(':', '_') + f'-{config}-1'
    if (work / f'{slug}.started.json').exists():
        raise SystemExit('Unreconciled journal; do not repeat a cell')
    old.OUT = OUT
    row = old.run_one(work, meta, task, config)
    row.update(config=cell['config'], phase=cell['phase'], quota_used_before=quota_used,
               secondary_quota_used_before=secondary_used, quota_resets_at=resets_at)
    raw = (work / f'{slug}.events.jsonl').read_text(encoding='utf-8')
    row['instrumentation'] = json.loads(old.scrub(json.dumps(instrument(raw, task))))
    row['grade_v2'] = grade_v2(task, row['answer']) if task else None
    meta['attempts'].append(row)
    if cell['phase'] == 'controls':
        meta['controls'].append(row)
    if not row.get('usage') or row['exit_code'] != 0:
        meta['stop_reason'] = 'Session failed or usage missing; evidence retained, no automatic retry'
    pilot = [r for r in meta['attempts'] if r['phase'] == 'pilot']
    if len(pilot) == 4:
        meta['pilot_valid'] = all(r['exit_code'] == 0 for r in pilot) and any(r['config'] == 'B2' and r['metrics'] and old.read_calls(r) for r in pilot)
        if not meta['pilot_valid']:
            meta['stop_reason'] = 'Pilot did not execute readscout in B2; mandatory stop, no synthetic replacement'
    tuning = [r for r in meta['attempts'] if r['config'] == 'B2' and r['phase'] in ('pilot', 'tuning')]
    if len(tuning) == 6:
        prior = {r['task']: r for r in meta['baseline_attempts'] if r['config'] == 'B'}
        b1 = sum(old.total(prior[r['task']]) for r in tuning)
        b2 = sum(old.total(r) or 0 for r in tuning)
        if b2 >= 1.1 * b1:
            meta['stop_reason'] = 'B2 cumulative tokens >=10% above B1 after six tuning tasks'
    save(meta, work)
    print(json.dumps({k: row[k] for k in ('task', 'config', 'phase', 'usage', 'mcp_calls', 'exit_code')}, indent=2))
    if meta.get('stop_reason'):
        print('STOP:', meta['stop_reason'])


def comparisons(meta, set_name, against):
    selected = [t for t in meta['tasks'] if t['set'] == set_name]
    result = []
    for t in selected:
        b2 = next((r for r in meta['attempts'] if r['task'] == t['id'] and r['config'] == 'B2' and r['phase'] in ('pilot', 'tuning', 'holdout') and r['exit_code'] == 0), None)
        if set_name == 'tuning':
            a = next((r for r in meta['baseline_attempts'] if r['task'] == t['id'] and r['config'] == ('B' if against == 'B1' else 'A')), None)
        else:
            a = next((r for r in meta['attempts'] if r['task'] == t['id'] and r['config'] == against and r['phase'] == 'holdout' and r['exit_code'] == 0), None)
        if a and b2 and old.total(a) and old.total(b2):
            result.append({'task': t['id'], 'group': t['group'], 'family': t['family'], 'base': a, 'B2': b2,
                           'saving': (old.total(a) - old.total(b2)) / old.total(a)})
    return result


def aggregate(pairs):
    if not pairs:
        return None
    a = sum(old.total(p['base']) for p in pairs)
    b = sum(old.total(p['B2']) for p in pairs)
    return {'pairs': len(pairs), 'base': a, 'B2': b, 'saving': (a - b) / a,
            'mean_task_saving': statistics.mean(p['saving'] for p in pairs),
            'wins': sum(p['saving'] > .05 for p in pairs), 'ties': sum(abs(p['saving']) <= .05 for p in pairs),
            'losses': sum(p['saving'] < -.05 for p in pairs),
            'F1_base_v1': statistics.mean(p['base']['grade']['f1'] for p in pairs),
            'F1_B2_v1': statistics.mean(p['B2']['grade']['f1'] for p in pairs),
            'unverifiable_base': sum(p['base']['grade']['unverifiable'] for p in pairs),
            'unverifiable_B2': sum(p['B2']['grade']['unverifiable'] for p in pairs),
            'cache_sensitivity': {str(d): {'base': sum(old.total(p['base'], d) for p in pairs), 'B2': sum(old.total(p['B2'], d) for p in pairs)} for d in (0, .1, 1)}}


def report():
    meta = read_json(OUT / 'results.json')
    paired = {s + '/' + c: comparisons(meta, s, c) for s in ('tuning', 'holdout') for c in ('A', 'B1')}
    derived = {k: aggregate(v) for k, v in paired.items()}
    meta['derived'] = derived
    meta['spent_total_tokens'] = sum(old.total(r) or 0 for r in meta['attempts'])
    meta['usage_missing_attempts'] = sum(old.total(r) is None for r in meta['attempts'])
    meta['raw_bytes'] = sum(p.stat().st_size for p in (OUT / 'runs').glob('*')) if (OUT / 'runs').exists() else 0
    save(meta)
    lines = ['# Campaign 2: measured token savings', '', '## TL;DR', '',
             'Campaign status: ' + ('complete' if meta.get('complete') else 'incomplete') + '.',
             meta.get('stop_reason', 'Preparation complete; measured sessions pending.'),
             f"New sessions: {len(meta['attempts'])}; reported total tokens spent: {meta['spent_total_tokens']:,}.",
             'Missing measurements are not zero-token successes. No full-campaign saving is claimed.', '',
             '## Setup', '', f"Frozen source `{meta['source_commit']}`; CLI `{meta['codex']}`; model `{meta['model']}`; effort `{meta['effort']}`.",
             'A and B1 reused from campaign 1 for tuning, with identical CLI, pinned model and effort. Fresh pilot A is separate.', '',
             '## Method', '', '[Frozen protocol](token-savings/v2/PROTOCOL.md). [Machine-readable evidence](token-savings/v2/results.json).', '',
             '## Changes and expectations', '', '| Change | Expected effect |', '|---|---|',
             '| Source quotes, file field, code-reference redaction | Avoid quote repairs |',
             '| Short skill and references | Reduce fixed overhead |',
             '| Status receipts and narrow verification rules | Reduce broad re-reads |',
             '| Deterministic simple logs | Avoid local inference and broad reads |',
             '| Syntax extraction | Improve structural coverage |',
             '| Shared findings cap | Make truncation visible |', '']
    for s in ('tuning', 'holdout'):
        lines += ['## ' + s.title() + ' set', '', '| Task | A total | B1 total | B2 total | F1 v1/v2 B2 |', '|---|---|---|---|---|']
        for t in (t for t in meta['tasks'] if t['set'] == s):
            vals = []
            for c in ('A', 'B1', 'B2'):
                if s == 'tuning' and c != 'B2':
                    row = next((r for r in meta['baseline_attempts'] if r['task'] == t['id'] and r['config'] == ('B' if c == 'B1' else c)), None)
                else:
                    row = next((r for r in meta['attempts'] if r['task'] == t['id'] and r['config'] == c and r['phase'] in ('pilot', 'tuning', 'holdout')), None)
                vals.append(str(old.total(row)) if row and old.total(row) is not None else 'not measured')
            b2 = next((r for r in meta['attempts'] if r['task'] == t['id'] and r['config'] == 'B2' and r['phase'] in ('pilot', 'tuning', 'holdout')), None)
            f1 = f"{b2['grade']['f1']}/{b2['grade_v2']['f1']}" if b2 and b2.get('grade') else 'not measured'
            lines.append(f"| {t['id']} | " + ' | '.join(vals) + f' | {f1} |')
    lines += ['', '## Both averages and per-family/group breakdown', '', 'Only completed matched pairs enter these descriptive aggregates. Partial subsets cannot establish the full-set hypotheses.', '']
    for k, pairs in paired.items():
        lines += [f'### {k}', '', '```json', json.dumps(aggregate(pairs), indent=2), '```', '']
        for field in ('group', 'family'):
            for value in sorted({p[field] for p in pairs}):
                lines += [f'{field}: {value}', '', '```json', json.dumps(aggregate([p for p in pairs if p[field] == value]), indent=2), '```', '']
    instruments = [r['instrumentation'] for r in meta['attempts']]
    lines += ['## Cost by phase', '', 'Phase token usage: not measured. Ephemeral CLI exposes turn aggregates, not request-level attribution. Tool returned characters are proxies:', '', '```json',
              json.dumps({p: sum(c['chars'] for i in instruments for c in i['calls'] if c['phase'] == p) for p in ('discovery', 'skill', 'readscout', 'verification', 'fallback', 'final')}, indent=2), '```', '',
              '## Re-read rate', '', 'Command/file overlap is a conservative proxy; ambiguous broad search scope is labelled separately.', '']
    for label, inst in [('B1', [r['instrumentation'] for r in meta['baseline_regraded'] if r['config'] == 'B1' and r['instrumentation']]),
                        ('B2', [r['instrumentation'] for r in meta['attempts'] if r['config'] == 'B2'])]:
        n = sum(i['readscout_calls'] for i in inst)
        rr = [r for i in inst for r in i['rereads']]
        broad = sum(r['chars'] for r in rr if r['mode'] == 'broad')
        lines.append(f"- {label}: {n} reading calls; {len(rr)} re-reads; {broad} broad returned chars; broad chars/call: {broad / n if n else 'not measured'}; targeted reads: {sum(r['mode'] == 'targeted' for r in rr)}.")
    lines += ['', '## Skill loading and fixed overhead', '', '```json', json.dumps(meta['fixed_overhead'], indent=2), '```', '',
              'Exact serialized schema/core characters; estimated tokens use 4 chars/token. Skill presence does not imply the core was read.',
              f"Measured core reads: {sum(i['skill_core'] for i in instruments)}; references reads: {sum(i['skill_references'] for i in instruments)}.",
              '', 'Controls:', '', '```json', json.dumps([{'config': r['config'], 'task': r['task'], 'total': old.total(r)} for r in meta['controls']], indent=2), '```', '',
              '## Logs and extraction: structural coverage', '', 'Offline only, no agent or model. Unfiltered route extraction is scored against each question and can include unwanted routes. Structural completeness does not guarantee semantic relevance.', '',
              '| Task | Path | Status | Unrecognized | Precision v1/v2 | Recall v1/v2 | F1 v1/v2 |', '|---|---|---|---|---|---|---|']
    for r in meta['structural_coverage']:
        lines.append(f"| {r['task']} | {r['extract']} | {r['status']} | {r['not_recognized']} | {r['v1']['precision']}/{r['v2']['precision']} | {r['v1']['recall']}/{r['v2']['recall']} | {r['v1']['f1']}/{r['v2']['f1']} |")
    checks = [c for r in meta['structural_coverage'] for c in r['citations']]
    lines += ['', f"Citation checks: {len(checks)}; failures: {sum(not c['located'] or not c['verbatim_raw'] or c['added_ellipsis'] or c['masked_reference'] for c in checks)}.", '',
              '## Accuracy: scorer v1 and v2', '', 'Campaign 1 recomputed without editing its files:', '', '| Task | Config | F1 v1 | F1 v2 |', '|---|---|---|---|']
    for r in meta['baseline_regraded']:
        lines.append(f"| {r['task']} | {r['config']} | {r['v1']['f1']} | {r['v2']['f1']} |")
    lines += ['', 'Receipt-only grades and final v1/v2 grades are retained per session in results.json.', '', '## Real work sessions', '', meta['work_sessions']['reason'], '',
              '## Estimate accuracy', '', 'tokens_avoided_est is a local text-size proxy. No full-campaign calibration without complete paired data.', '', '## Hypotheses', '']
    for n in range(1, 13):
        lines.append(f'- H{n}: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.')
    lines += ['', '## Which improvement contributed what', '', 'No ablation was run: individual contributions cannot be separated. Offline overhead and structural accuracy are directly measurable; agent token benefits need completed paired sessions.', '',
              '## Bugs and oddities observed before runs', '',
              '- Extraction telemetry computes status from unrecognized constructs only; hidden results can make the receipt partial while metrics say complete.',
              '- Model receipt telemetry omits hidden findings and digest missing-role checks used by the receipt.',
              '- The env extractor reads named accesses, not Joi schema declarations: a complete empty receipt can miss variables a question asks the configuration to validate.',
              '- Deterministic logs group errors and show head/tail; their complete status does not prove the first event is the semantic root cause.', '',
              '## Limitations', '', 'One run per cell, one agent model, one machine, project-authored corpus, tuning tasks seen during development, caching, run order, cold load time, nondeterminism, no variance estimate. Holdout is task-level and partly authored on this project. No per-request token use, post-truncation model input, phase token costs, separate load/inference timings, or maximum token allowance available. New tool schema/skill/digest behavior makes conditions different; no ablation.', '',
              '## Reproduction', '', '`python scripts/token_savings.py v2 prepare`, commit protocol/harness/tests, then invoke `v2 next --quota-used PERCENT` once per fresh account checkpoint. `v2 report` is offline; `v2 cleanup` removes fake homes. Never repeat an existing cell. Preserve raw evidence and stop state.', '',
              '## Deviations', ''] + ['- ' + d for d in meta['deviations']]
    (ROOT / 'docs/TOKEN-SAVINGS-V2.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    rows = meta['tasks']
    chart = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="'+str(80 + 55 * len(rows))+'" role="img" aria-label="Campaign 2 token totals">', '<rect width="100%" height="100%" fill="white"/>', '<text x="20" y="25" font-family="sans-serif">Reported tokens: A blue, B1 orange, B2 green; missing cells not measured</text>']
    maximum = max((old.total(r) or 1 for r in meta['baseline_attempts'] + meta['attempts']), default=1)
    for i, t in enumerate(rows):
        y = 60 + 55 * i
        chart.append(f'<text x="10" y="{y}" font-size="11" font-family="sans-serif">{html.escape(t["id"])}</text>')
        for j, c in enumerate(('A', 'B1', 'B2')):
            pool = meta['baseline_attempts'] if t['set'] == 'tuning' and c != 'B2' else meta['attempts']
            rc = 'B' if c == 'B1' else c
            row = next((r for r in pool if r['task'] == t['id'] and r['config'] == rc and r.get('phase') != 'controls'), None)
            if row and old.total(row) is not None:
                value = old.total(row)
                w = 600 * value / maximum
                chart += [f'<rect x="350" y="{y - 10 + 14*j}" width="{w:.2f}" height="12" fill="{("#2563eb", "#ea580c", "#16a34a")[j]}"/>', f'<text x="{355+w:.2f}" y="{y+14*j}" font-size="10">{value}</text>']
            else:
                chart.append(f'<text x="350" y="{y+14*j}" font-size="10">{c}: not measured</text>')
    (OUT / 'chart.svg').write_text('\n'.join(chart + ['</svg>']) + '\n', encoding='utf-8')
    print(json.dumps({'spent_tokens': meta['spent_total_tokens'], 'paired': derived, 'stop': meta.get('stop_reason')}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'next', 'report', 'cleanup'))
    parser.add_argument('--quota-used', type=float)
    parser.add_argument('--quota-secondary-used', type=float)
    parser.add_argument('--quota-resets-at', type=int)
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        prepare()
    elif args.action == 'next':
        if args.quota_used is None or args.quota_secondary_used is None or args.quota_resets_at is None:
            raise SystemExit('A fresh account quota checkpoint is required')
        next_cell(args.quota_used, args.quota_secondary_used, args.quota_resets_at)
    elif args.action == 'report':
        report()
    else:
        work = Path(read_json(POINTER)['work'])
        meta = read_json(OUT / 'results.json')
        # Never stop shared or pre-existing processes as part of filesystem cleanup.
        safe_delete(work)
        POINTER.unlink()
        meta['cleanup'] = {'fake_homes_deleted': True}
        save(meta)


if __name__ == '__main__':
    main()
