"""Isolated, sequential Codex CLI token experiment. Not part of CI."""
import argparse
import hashlib
import html
import json
import os
import platform
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

from readscout import __version__, hardware, tasks
from readscout.bench import generate
from readscout.bench.runner import score
from readscout.text import Line, locate, redact

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/token-savings'
POINTER = ROOT / '.git/token-savings-work.json'
SEED = 20261016
PILOT = ['hackathon:env_controllers', 'boilerplate:env_schema']
PROMPT = ('Answer a question about the code in the current directory. Do not modify any file. Question: {question}\n'
          'Scope: only these files or folders, relative to the current directory: {paths}.\n'
          'Answer only with JSON matching the schema: `findings` is a list of objects with `path` '
          '(relative to the current directory), `line`, `quote` (the verbatim code line, 10 to 120 characters) '
          'and `answer` (at most 30 words).')
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['findings'], 'properties': {
    'findings': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'required': ['path', 'line', 'quote', 'answer'], 'properties': {
            'path': {'type': 'string'}, 'line': {'type': 'integer'},
            'quote': {'type': 'string', 'minLength': 10, 'maxLength': 120},
            'answer': {'type': 'string'}}}}}}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def scrub(text):
    # Scrub literal and JSON-escaped Windows paths; never load credential contents here.
    for base in (str(Path.home()), str(ROOT)):
        for form in (base, base.replace('\\', '/'), base.replace('\\', '\\\\')):
            text = text.replace(form, '<HOME>' if base == str(Path.home()) else '<REPO>')
    text = re.sub(r'(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s"<>]+', '<HOME>', text)
    text = re.sub(r'(?i)("(?:access_token|refresh_token|id_token|api_key)"\s*:\s*")[^"]+', r'\1[REDACTED]', text)
    return redact(text).replace(chr(0x2014), '-')


def parse_events(raw):
    events, invalid = [], []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            invalid.append(line)
    completed = [e for e in events if e.get('type') == 'turn.completed']
    usages = [e.get('usage', {}) for e in completed]
    # Only completed items: started/updated events must not double count calls.
    items = [e['item'] for e in events if e.get('type') == 'item.completed' and 'item' in e]
    shell = [i for i in items if i.get('type') == 'command_execution']
    mcp = [i for i in items if i.get('type') == 'mcp_tool_call']
    calls = {}
    for i in mcp:
        key = i.get('server', '?') + '.' + i.get('tool', '?')
        calls[key] = calls.get(key, 0) + 1
    return {'usage': {k: sum(u.get(k, 0) for u in usages) for k in {k for u in usages for k in u}},
            'turn_usages': usages, 'turns': len(completed), 'shell_calls': len(shell),
            'mcp_calls': calls, 'shell_chars': sum(len(i.get('aggregated_output', '')) for i in shell),
            'mcp_chars': sum(len(json.dumps(i.get('result', {}), ensure_ascii=False)) for i in mcp),
            'invalid_events': invalid, 'errors': [e for e in events if e.get('type') in ('error', 'turn.failed')]}


def normalize_path(path, root):
    text = path.replace('\\', '/')
    prefix = root.as_posix().rstrip('/') + '/'
    if text.lower().startswith(prefix.lower()):
        text = text[len(prefix):]
    if re.match(r'^[A-Za-z]:', text) or text.startswith('/') or '..' in text.split('/'):
        raise ValueError('Path outside task root')
    return text.removeprefix('./')


def grade_answer(task, answer):
    verified, wrong, details, used = [], 0, [], set()
    scope = {normalize_path(p, task.root) for p in tasks.expand(task.paths, [task.root])}
    for f in answer.get('findings', []):
        try:
            path = normalize_path(f['path'], task.root)
            if path not in scope:
                raise ValueError('Out of scope')
            lines = [Line(path, n, s) for n, s in enumerate(
                (task.root / path).read_text(encoding='utf-8').splitlines(), 1)]
            hit = locate(f['quote'], lines, int(f['line']), used)
            if hit is None:
                raise ValueError('Quote not found')
            used.add(hit)
            verified.append((*hit, f['answer'], f['quote']))
            details.append({'claimed': f['line'], 'actual': hit[1], 'path': path})
        except (KeyError, ValueError, OSError, TypeError) as exc:
            wrong += 1
            details.append({'error': str(exc), 'finding': f})
    result = score(task, verified)
    # Preserve the benchmark score and explicitly penalize unverifiable findings as wrong.
    result['benchmark_score'] = dict(result)
    if wrong:
        result['precision'] = round(result['precision'] * len(verified) / (len(verified) + wrong), 3)
        p, r = result['precision'], result['recall']
        result['f1'] = round(2 * p * r / (p + r), 3) if p + r else 0.0
    return {**result, 'unverifiable': wrong, 'verified': len(verified), 'locations': details}


def size(task):
    return sum((task.root / p).stat().st_size for p in tasks.expand(task.paths, [task.root]))


def select(all_tasks):
    by_id = {t.id: t for t in all_tasks}
    logs = sorted((t for t in all_tasks if t.family == 'log'), key=lambda t: (size(t), t.id))
    locates, seen = [], set()
    for t in sorted((t for t in all_tasks if t.family == 'locate'), key=lambda t: (size(t), t.id)):
        if tuple(t.paths) not in seen:
            locates.append(t.id)
            seen.add(tuple(t.paths))
    groups = {'W': ['hackathon:env_controllers', 'boilerplate:routes_all', 'fastapi:endpoints_all',
                    'nextjs:supabase_access', logs[-1].id, logs[-2].id],
              'N': ['hackathon:post_without_auth', 'boilerplate:routes_without_auth', 'fastapi:public_endpoints'],
              'M': ['hackathon:routes_auth', 'hackathon:routes_limited'],
              'L': ['boilerplate:env_schema', logs[0].id, *locates[:2]]}
    selected = [{'id': key, 'group': g, 'bytes': size(by_id[key]), 'paths': by_id[key].paths}
                for g, ids in groups.items() for key in ids]
    random.Random(SEED).shuffle(selected)
    for i, row in enumerate(selected):
        row['order'] = ['A', 'B'] if i % 2 == 0 else ['B', 'A']
    return selected


def command(args, env=None, timeout=120):
    return subprocess.run(args, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def environment(work, config, metrics):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('CODEX_', 'READSCOUT_')):
            del env[key]
    home = work / config
    env.update(HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(home / '.codex'),
               APPDATA=str(home / 'AppData/Roaming'), READSCOUT_HOME=str(metrics))
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env['PATH']
    # Doctor checks every CLI on PATH. Hide unrelated Claude in these Codex-only homes.
    while claude := shutil.which('claude', path=env['PATH']):
        env['PATH'] = os.pathsep.join(p for p in env['PATH'].split(os.pathsep)
                                     if Path(p).resolve() != Path(claude).parent.resolve())
    return env


def state():
    return Path(json.loads(POINTER.read_text())['work'])


ISOLATED_FLAGS = ['--no-daemon', '--disable', 'apps', '--disable', 'plugins', '--disable', 'remote_plugin',
                  '-c', 'windows.sandbox="unelevated"']


def isolate_skills(work):
    """Windows Codex uses the OS profile for global skills even with fake HOME."""
    env = environment(work, 'A', work / 'diagnostic')
    probe = command(['codex', *ISOLATED_FLAGS, 'debug', 'prompt-input'], env)
    if probe.returncode:
        raise RuntimeError('Cannot inspect prompt isolation')
    entries = json.loads(probe.stdout)
    text = '\n'.join(c.get('text', '') for x in entries for c in x.get('content', []))
    roots = dict(re.findall(r'- `(r\d+)` = `([^`]+)`', text))
    current = tomllib.loads((work / 'A/.codex/config.toml').read_text(encoding='utf-8'))
    disabled = [s['path'] for s in current.get('skills', {}).get('config', []) if not s.get('enabled', True)]
    for alias, tail in re.findall(r'\(file: (r\d+)/([^\)]+)\)', text):
        path = (Path(roots[alias]) / tail).as_posix()
        if not Path(path).is_relative_to(work):
            if path not in disabled:
                disabled.append(path)
    for config in ('A', 'B'):
        cfg = work / config / '.codex/config.toml'
        text = cfg.read_text(encoding='utf-8').split('[[skills.config]]')[0]
        for path in disabled:
            text += '\n[[skills.config]]\npath = ' + json.dumps(path) + '\nenabled = false\n'
        cfg.write_text(text, encoding='utf-8')
    target = work / 'B/.codex/skills/readscout/SKILL.md'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(work / 'B/.agents/skills/readscout/SKILL.md', target)
    audit = {}
    for config in ('A', 'B'):
        env = environment(work, config, work / 'diagnostic')
        probe = command(['codex', *ISOLATED_FLAGS, 'debug', 'prompt-input'], env)
        if probe.returncode:
            raise RuntimeError('Cannot validate isolated prompt')
        present = '- readscout:' in probe.stdout
        global_skills = (Path.home() / '.agents/skills').as_posix() in probe.stdout.replace('\\\\', '/')
        if present != (config == 'B') or global_skills:
            raise RuntimeError('Global skill leakage or missing B skill')
        audit[config] = {'readscout_skill': present, 'real_global_skill_root': global_skills,
                         'prompt_sha256': hashlib.sha256(probe.stdout.encode()).hexdigest()}
    return audit


def sandbox_probe(work):
    """Grant sandbox-readable ACLs only to public corpus and skill copies, never auth."""
    if sys.platform != 'win32':
        return {'status': 'not measured', 'reason': 'Windows-only preflight'}
    allowed = [work / 'corpus-state', work / 'B/.codex/skills', work / 'schema.json']
    for path in allowed:
        if path.exists():
            grant = '*S-1-1-0:(RX)' if path.is_file() else '*S-1-1-0:(OI)(CI)(RX)'
            p = command(['icacls', str(path), '/grant', grant, '/T', '/Q'])
            if p.returncode:
                raise RuntimeError('Failed temporary public corpus read ACL setup')
    env = environment(work, 'A', work / 'diagnostic')
    # A separate non-sensitive probe directory avoids granting access to fake homes.
    probe_dir = work / 'sandbox-probe'
    probe_dir.mkdir(exist_ok=True)
    (probe_dir / 'read.txt').write_text('READ_OK', encoding='ascii')
    command(['icacls', str(probe_dir), '/grant', '*S-1-1-0:(OI)(CI)(RX)', '/T', '/Q'])
    base = ['codex', *ISOLATED_FLAGS, 'sandbox', '-P', ':read-only', '-C', str(probe_dir), '--', 'cmd.exe', '/d', '/c']
    read = command([*base, 'type read.txt'], env)
    write = command([*base, 'echo forbidden > write.txt'], env)
    if read.returncode or read.stdout.strip() != 'READ_OK' or not write.returncode or (probe_dir / 'write.txt').exists():
        raise RuntimeError('Read-only sandbox preflight failed')
    return {'read_exit': read.returncode, 'read_output': read.stdout.strip(),
            'write_exit': write.returncode, 'write_created': False}


def prepare():
    if POINTER.exists():
        raise SystemExit('Existing workspace: do not overwrite it')
    work = Path(tempfile.mkdtemp(prefix='readscout-token-savings-'))
    write_json(POINTER, {'work': str(work)})
    user_config = tomllib.loads((Path.home() / '.codex/config.toml').read_text(encoding='utf-8'))
    model, effort = user_config['model'], user_config['model_reasoning_effort']
    os.environ['READSCOUT_HOME'] = str(work / 'corpus-state')
    selected = select(generate.build())
    meta = {'date': '2026-10-16', 'seed': SEED, 'model': model, 'effort': effort,
            'readscout': __version__, 'codex': command(['codex', '--version']).stdout.strip(),
            'ollama': command(['ollama', '--version']).stdout.strip(),
            'models': command(['ollama', 'list']).stdout,
            'hardware': hardware.as_dict(hardware.detect()), 'platform': platform.platform(),
            'cpu': platform.processor(), 'source_commit': command(['git', 'rev-parse', 'HEAD']).stdout.strip(),
            'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((ROOT / 'src/readscout').rglob('*')) if p.is_file() and '__pycache__' not in str(p)},
            'tasks': selected, 'attempts': [], 'controls': [], 'deviations': []}
    if __version__ != '0.1.6':
        raise SystemExit('Requires v0.1.6')
    for config in ('A', 'B'):
        home = work / config
        (home / '.codex').mkdir(parents=True)
        auth = Path.home() / '.codex/auth.json'
        if auth.exists():
            shutil.copyfile(auth, home / '.codex/auth.json')
        (home / '.codex/config.toml').write_text(
            f'model = {json.dumps(model)}\nmodel_reasoning_effort = {json.dumps(effort)}\n'
            'approval_policy = "never"\nsandbox_mode = "read-only"\n', encoding='utf-8')
    env = environment(work, 'B', work / 'doctor')
    installed = command([sys.executable, '-m', 'readscout.cli', 'install-agent', 'codex'], env)
    meta['install'] = scrub(installed.stdout + installed.stderr)
    meta['isolation_audit'] = isolate_skills(work)
    doctor = command([sys.executable, '-m', 'readscout.cli', 'doctor'], env)
    meta['doctor'] = scrub(doctor.stdout + doctor.stderr)
    meta['doctor_ok'] = doctor.returncode == 0 and 'All good.' in doctor.stdout
    write_json(work / 'meta.json', meta)
    write_json(work / 'schema.json', SCHEMA)
    meta['sandbox_probe'] = sandbox_probe(work)
    write_json(work / 'meta.json', meta)
    write_json(OUT / 'results.json', meta)
    protocol(meta)
    print(json.dumps({'tasks': selected, 'doctor': meta['doctor'], 'install': meta['install']}, indent=2))


def protocol(meta):
    text = '''# Pre-registered token savings protocol

This file is frozen before measured sessions. Amendments may only be appended.

## Setup and selection

Environment, exact source hashes, pinned corpus, versions, model, effort, seed and
selected tasks are recorded below and in results.json. The repository venv is used
at exactly v0.1.6; src/readscout stays frozen throughout the campaign.
Each cell runs once, strictly sequentially. One retry is allowed only for a crash
or timeout, retaining the original attempt. A session timeout is 1200 seconds.
The pilot executes the two specified task pairs in their randomized relative order;
remaining pairs retain their randomized order. Pair first configuration alternates
by the original randomized index. Pilot data counts unless the harness changes.
Controls run after the pilot and are excluded from task aggregates.

## Isolation and execution

Two temporary HOME/USERPROFILE/CODEX_HOME/APPDATA directories contain only minimal
configuration and copied authentication. B is installed using install-agent codex.
A has no skill or MCP. B gets a fresh READSCOUT_HOME per session, explicitly in
the MCP env table. No real user configuration is written, no existing process is
killed. Codex exec uses --json, --ephemeral, --skip-git-repo-check, --sandbox read-only,
-c approval_policy="never", -m, -c model_reasoning_effort, -C, --output-schema, -o.
No model warmup. Stop is called after B only when no pre-existing Ollama model
would be affected; otherwise only models used by this session may be unloaded.
The MCP remains the installed three-tool surface; local_edit is outside scope.
Final answers and JSONL events are scrubbed before storage. Temporary homes are
deleted after the experiment. No credentials are printed or committed.

## Prompt and schema

The identical prompt template for A and B is:

```text
''' + PROMPT + '''
```

The controls use exactly `Reply with the word OK.` without a findings schema.
The task schema is stored in the harness. No tool-use hints are added.

## Metrics and grading

Store every turn.completed usage field verbatim and sum fields across turns.
Primary total = reported input_tokens + output_tokens. Secondary total = input
minus cached input plus output. Sensitivity assumes cached input costs 10% of
uncached input: input - 0.9 * cached + output. This is not an actual price.
Cached-input inclusion and reasoning-output inclusion will be checked against
available local session telemetry; if not empirically identifiable they remain
unverified, with no invented reasoning counts or double counting.
Savings = (A - B) / A, using sums for group/overall and paired savings for median,
min and max. Count completed shell/MCP items once, measure returned characters,
wall time, exit/timeout, read calls, model/loading telemetry and session metrics.
Grade final JSON without using the configuration label. Normalize source paths,
enforce scope, recompute quote locations with locate and call the existing score.
Keep its raw scores; count unlocatable/out-of-scope findings as wrong by multiplying
precision by verified/(verified + unverifiable) and recomputing F1. Report both.
An empty or invalid final answer has zero F1. Same grading for both configurations.
No empirical break-even threshold is inferred unless the observed pairs support it.

## Hypotheses and falsification

- H1: W total tokens fall clearly, defined before running as at least 10%.
  Refuted when W savings are below 10%; inconclusive if W pairs are incomplete.
- H2: L B total is at least A total. Refuted by positive aggregate L savings.
- H3: mean task F1 B is no more than 0.05 below A. Refuted by a larger loss.
- H4: sum dashboard tokens_avoided_est exceeds A-B measured tokens. Refuted
  when estimate is no greater than actual saving. Negative savings are reported.
- H5: at least one B task does not call local_ask/local_digest. Refuted if every
  completed B task calls one. Incomplete campaign verdicts remain inconclusive.

## Limitations

One run per cell, no significance claim; one agent, one machine; project-authored
public corpus, caching, run order, cold model loading and nondeterminism. A pilot
without real successful MCP execution does not authorize the remaining campaign.
Missing metrics are not measured, never zero-filled as measurements.

## Frozen environment and tasks

```json
''' + json.dumps({k: v for k, v in meta.items() if k not in ('attempts', 'controls')}, indent=2) + '\n```\n'
    (OUT / 'PROTOCOL.md').write_text(text, encoding='utf-8')


def run_one(work, meta, task, config, attempt=1):
    key = task.id if task else 'control'
    slug = key.replace(':', '_') + f'-{config}-{attempt}'
    metrics = work / 'metrics' / slug
    env = environment(work, config, metrics)
    if config == 'B':
        cfg = work / 'B/.codex/config.toml'
        text = cfg.read_text(encoding='utf-8').split('[mcp_servers.readscout.env]')[0]
        text += '\n[mcp_servers.readscout.env]\nREADSCOUT_HOME = ' + json.dumps(metrics.as_posix()) + '\n'
        cfg.write_text(text, encoding='utf-8')
    final = work / f'{slug}.json'
    args = ['codex', '--no-daemon', 'exec', *ISOLATED_FLAGS[1:], '--json', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
            '-c', 'approval_policy="never"', '-m', meta['model'], '-c',
            'model_reasoning_effort=' + json.dumps(meta['effort']), '-C', str(task.root if task else work),
            '-o', str(final)]
    if task:
        args += ['--output-schema', str(work / 'schema.json')]
    prompt = PROMPT.format(question=task.question, paths=', '.join(task.paths)) if task else 'Reply with the word OK.'
    args += [prompt]
    started = time.time()
    timed_out = False
    # Persist output immediately in the private temporary workspace so an interrupted
    # coordinating session cannot lose the evidence or accidentally rerun a cell.
    journal = work / f'{slug}.started.json'
    write_json(journal, {'task': key, 'config': config, 'attempt': attempt, 'started': started})
    raw = work / f'{slug}.events.jsonl'
    err = work / f'{slug}.stderr.txt'
    with raw.open('wb') as stdout_file, err.open('wb') as stderr_file:
        proc = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=stdout_file, stderr=stderr_file,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            exit_code = proc.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.terminate()  # Only this harness-owned process.
            proc.wait(timeout=30)
            exit_code = None
    stdout = raw.read_text(encoding='utf-8', errors='replace')
    stderr = err.read_text(encoding='utf-8', errors='replace')
    row = {'task': key, 'config': config, 'attempt': attempt, 'wall_seconds': round(time.time() - started, 3),
           'exit_code': exit_code, 'timeout': timed_out, **parse_events(stdout)}
    raw_answer = final.read_text(encoding='utf-8') if final.exists() else ''
    try:
        answer = json.loads(raw_answer) if task else raw_answer
    except ValueError:
        answer = {}
    row['answer'] = answer
    row['grade'] = grade_answer(task, answer) if task else None
    row['metrics'] = [json.loads(line) for line in (metrics / 'metrics.jsonl').read_text(encoding='utf-8').splitlines()] if (metrics / 'metrics.jsonl').exists() else []
    row['stderr'] = stderr
    run_dir = OUT / 'runs'
    run_dir.mkdir(exist_ok=True)
    (run_dir / f'{slug}.jsonl').write_text(scrub(stdout), encoding='utf-8')
    (run_dir / f'{slug}.answer.json').write_text(scrub(raw_answer), encoding='utf-8')
    if config == 'B':
        # Stop only if models were not resident before this session.
        from readscout import backend
        existing = meta.get('preexisting_models', [])
        if not existing:
            row['stop'] = command([sys.executable, '-m', 'readscout.cli', 'stop'], env).stdout
        else:
            for name in {r.get('model') for r in row['metrics']} - set(existing) - {None}:
                backend.unload(name, 'http://127.0.0.1:11434')
            row['stop'] = 'Preserved pre-existing models; unloaded only campaign-used models.'
    return json.loads(scrub(json.dumps(row, ensure_ascii=True)))


def run(phase):
    work = state()
    meta = json.loads((work / 'meta.json').read_text())
    if not meta['doctor_ok']:
        raise SystemExit('Doctor did not pass; campaign blocked')
    for path, expected in meta['source_hashes'].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise SystemExit('Code under test changed: campaign frozen')
    if command(['git', 'status', '--porcelain', '--', 'docs/token-savings/PROTOCOL.md', 'scripts/token_savings.py']).stdout:
        raise SystemExit('Commit protocol and harness before measured runs')
    os.environ['READSCOUT_HOME'] = str(work / 'corpus-state')
    all_tasks = {t.id: t for t in generate.build()}
    from readscout import backend
    meta.setdefault('preexisting_models', list(backend.loaded_models('http://127.0.0.1:11434')))
    selected = [r for r in meta['tasks'] if (r['id'] in PILOT) == (phase == 'pilot')]
    if phase == 'controls':
        selected = [{'id': None, 'order': ['A', 'B']}]
    for selected_row in selected:
        for config in selected_row['order']:
            rows = meta['controls'] if phase == 'controls' else meta['attempts']
            key = selected_row['id'] or 'control'
            previous = [r for r in rows if r['task'] == key and r['config'] == config]
            if previous:
                continue  # Explicit resume never repeats a cell.
            slug = key.replace(':', '_') + f'-{config}-1'
            if (work / f'{slug}.started.json').exists():
                raise SystemExit('Unreconciled interrupted attempt; recover its raw files before resuming')
            row = run_one(work, meta, all_tasks.get(key), config)
            rows.append(row)
            write_json(work / 'meta.json', meta)
            write_json(OUT / 'results.json', meta)
            print(f"{key} {config}: exit={row['exit_code']} usage={row['usage']} MCP={row['mcp_calls']}", flush=True)
            if row['timeout'] or row['exit_code'] not in (0, None):
                # Record failure, stop for diagnosis; retry is explicit, never automatic quota spending.
                raise SystemExit('Run failed; retained raw attempt. Diagnose before proceeding.')
    if phase == 'pilot':
        successful = [r for r in meta['attempts'] if r['config'] == 'B' and r['metrics'] and any(
            k.endswith(('.local_ask', '.local_digest')) for k in r['mcp_calls'])]
        meta['pilot_valid'] = bool(successful) and len(meta['attempts']) == 4
        write_json(work / 'meta.json', meta)
        write_json(OUT / 'results.json', meta)
        if not meta['pilot_valid']:
            raise SystemExit('Pilot invalid: no demonstrated readscout call and session metrics')


def total(row, discount=1):
    usage = row.get('usage', {})
    if 'input_tokens' not in usage or 'output_tokens' not in usage:
        return None
    return usage['input_tokens'] + usage['output_tokens'] - (1 - discount) * usage.get('cached_input_tokens', 0)


def aggregates(meta):
    paired = []
    for task in meta['tasks']:
        rows = {c: next((r for r in reversed(meta['attempts']) if r['task'] == task['id']
                        and r['config'] == c and r['exit_code'] == 0 and total(r) is not None), None)
                for c in ('A', 'B')}
        if all(rows.values()):
            a, b = rows['A'], rows['B']
            paired.append({**task, 'A': a, 'B': b, 'saving': (total(a) - total(b)) / total(a)})
    summaries = {}
    for group in ('W', 'N', 'M', 'L', 'overall'):
        pairs = [p for p in paired if group == 'overall' or p['group'] == group]
        if not pairs:
            summaries[group] = None
            continue
        a = sum(total(p['A']) for p in pairs)
        b = sum(total(p['B']) for p in pairs)
        summaries[group] = {'pairs': len(pairs), 'A': a, 'B': b, 'saving': (a - b) / a,
                            'median': statistics.median(p['saving'] for p in pairs),
                            'min': min(p['saving'] for p in pairs), 'max': max(p['saving'] for p in pairs),
                            'f1_A': statistics.mean(p['A']['grade']['f1'] for p in pairs),
                            'f1_B': statistics.mean(p['B']['grade']['f1'] for p in pairs)}
    return paired, summaries


def report():
    meta = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))
    paired, summaries = aggregates(meta)
    meta['aggregates'] = summaries
    write_json(OUT / 'results.json', meta)
    overall = summaries['overall']
    complete = len(paired) == len(meta['tasks'])
    lines = ['# Measured Codex token savings', '', '## TL;DR', '']
    if not complete:
        lines += ['The campaign is incomplete. No overall token-saving claim is supported.',
                  f"Completed pairs: {len(paired)} of {len(meta['tasks'])}; retained attempts: {len(meta['attempts'])}."]
    if overall:
        lines += [f"Observed paired total: A {overall['A']:,} tokens; B {overall['B']:,}; saving {overall['saving']:.1%}.",
                  'By group: ' + '; '.join(f"{g} {s['saving']:.1%}" if s else f'{g}: not measured'
                                         for g, s in summaries.items() if g != 'overall') + '.',
                  f"Tasks saving/tied/costing more: {sum(p['saving'] > 0 for p in paired)}/"
                  f"{sum(p['saving'] == 0 for p in paired)}/{sum(p['saving'] < 0 for p in paired)}. "
                  f"Mean F1 A {overall['f1_A']:.3f}; B {overall['f1_B']:.3f}."]
    else:
        lines += ['Tokens A versus B, overall and per group savings, and comparative accuracy: not measured.']
    lines += ['', '## Setup', '', f"Date: {meta['date']}; seed: {meta['seed']}; Codex: {meta['codex']}; "
              f"model: {meta['model']}; reasoning effort: {meta['effort']}; readscout: {meta['readscout']}.",
              '', '```json', json.dumps({k: meta[k] for k in ('hardware', 'cpu', 'platform', 'ollama', 'models')}, indent=2),
              '```', '', '## Method', '',
              'See the frozen [protocol](token-savings/PROTOCOL.md). Identical task prompts, temporary isolated homes, '
              'read-only Codex sessions, sequential paired runs, existing benchmark scoring and source-verified quotes. '
              'All numbers on this page are generated from [results.json](token-savings/results.json).', '',
              '## Per-task results', '',
              '| Task | Group | A in/cache/out/total | B in/cache/out/total | Saving | Shell A/B | MCP A/B | Seconds A/B | F1 A/B | Read calls B |',
              '|---|---|---|---|---|---|---|---|---|---|']
    def token_cell(row):
        if not row:
            return 'not measured'
        u = row['usage']
        return '/'.join(str(u.get(k, 'not measured')) for k in ('input_tokens', 'cached_input_tokens', 'output_tokens')) + '/' + str(total(row))
    for task in meta['tasks']:
        pair = next((p for p in paired if p['id'] == task['id']), None)
        a, b = (pair['A'], pair['B']) if pair else (None, None)
        if pair:
            extra = (f"{pair['saving']:.1%} | {a['shell_calls']}/{b['shell_calls']} | "
                     f"{sum(a['mcp_calls'].values())}/{sum(b['mcp_calls'].values())} | "
                     f"{a['wall_seconds']}/{b['wall_seconds']} | {a['grade']['f1']}/{b['grade']['f1']} | "
                     f"{sum(v for k, v in b['mcp_calls'].items() if k.endswith(('.local_ask', '.local_digest')))}")
        else:
            extra = 'not measured | not measured | not measured | not measured | not measured | not measured'
        lines.append(f"| {task['id']} | {task['group']} | {token_cell(a)} | {token_cell(b)} | {extra} |")
    lines += ['', '## Aggregates', '', '| Group | Pairs | A total | B total | Saving | Median | Min | Max |',
              '|---|---|---|---|---|---|---|---|']
    for g, s in summaries.items():
        lines.append(f"| {g} | {s['pairs']} | {s['A']} | {s['B']} | {s['saving']:.1%} | {s['median']:.1%} | {s['min']:.1%} | {s['max']:.1%} |"
                     if s else f'| {g} | not measured | not measured | not measured | not measured | not measured | not measured | not measured |')
    lines += ['', 'Secondary views (cached input discount is an assumption, not a price):', '',
              '| Cache weight | A | B | Saving |', '|---|---|---|---|']
    for discount in (0, 0.1, 1):
        if paired:
            a, b = (sum(total(p[c], discount) for p in paired) for c in ('A', 'B'))
            lines.append(f'| {discount:.0%} | {a:.1f} | {b:.1f} | {(a-b)/a:.1%} |')
    lines += ['', '## Accuracy', '']
    for p in paired:
        a, b = p['A']['grade'], p['B']['grade']
        lines.append(f"- {p['id']}: F1 A/B {a['f1']}/{b['f1']}; unverifiable A/B {a['unverifiable']}/{b['unverifiable']}. "
                     'Inspect retained answers and locations for missing, incorrect or unverifiable findings.')
    if not paired:
        lines.append('Comparative accuracy: not measured. No completed pair with usage telemetry.')
    lines += ['', '## Where readscout helps, hurts, and break-even', '']
    if paired:
        lines += ['Observed winners: ' + ', '.join(p['id'] for p in paired if p['saving'] > 0) + '.',
                  'Observed costs/ties: ' + ', '.join(p['id'] for p in paired if p['saving'] <= 0) + '.']
    lines += ['A reliable size break-even is not measured: task shape and grep strategy confound size, and there is no replication.',
              '', '## Fixed-overhead controls', '', '| Config | Tokens | Seconds | Status |', '|---|---|---|---|']
    for r in meta['controls']:
        lines.append(f"| {r['config']} | {total(r)} | {r['wall_seconds']} | {r['exit_code']} |")
    if not meta['controls']:
        lines.append('Controls: not measured because the pilot did not validate the campaign.')
    lines += ['', '## Dashboard estimate versus measured savings', '']
    if paired:
        estimate = sum(max(0, round((sum(m.get('bytes_read', 0) for m in p['B']['metrics']) -
                                       sum(m.get('chars_returned', 0) for m in p['B']['metrics'])) / 3.5)) for p in paired)
        actual = overall['A'] - overall['B']
        lines += [f'Dashboard estimate sum: {estimate} tokens. Actual paired difference: {actual} tokens.',
                  f'Estimate/difference ratio: {estimate / actual:.3f}.' if actual > 0 else 'A positive savings ratio is not defined.']
    else:
        estimate, actual = None, None
        lines.append('Not measured: no comparable token totals. The dashboard formula is not an agent-session measurement.')
    lines += ['', '## Hypotheses', '']
    verdicts = {}
    if complete:
        verdicts = {'H1': summaries['W']['saving'] >= 0.1, 'H2': summaries['L']['saving'] <= 0,
                    'H3': overall['f1_B'] >= overall['f1_A'] - 0.05, 'H4': estimate > actual,
                    'H5': any(not any(k.endswith(('.local_ask', '.local_digest')) for k in p['B']['mcp_calls']) for p in paired)}
    for h in ('H1', 'H2', 'H3', 'H4', 'H5'):
        verdict = ('confirmed' if verdicts[h] else 'refuted') if h in verdicts else 'inconclusive'
        lines.append(f'- {h}: {verdict}. Evidence: the aggregate and per-task measurements above; definitions in the protocol.')
    lines += ['', '## Limitations and threats to validity', '',
              'One run per cell supports no significance claim. One model and machine, a public corpus authored by this '
              'project, prompt caching, pilot-first order, model loading and nondeterminism limit generalization. '
              'Reasoning output tokens are not measured if absent from CLI telemetry. Cache inclusion cannot be '
              'established from an absent counter. Missing sessions are not zero-token successes.', '',
              '### Deviations and observed failures', '']
    lines += meta['deviations'] or ['No deviations recorded.']
    for r in meta['attempts']:
        if r['exit_code'] != 0 or r['errors']:
            lines += [f"- {r['task']} {r['config']}, attempt {r['attempt']}: exit {r['exit_code']}, timeout {r['timeout']}, "
                      f"wall {r['wall_seconds']} seconds; errors: `{json.dumps(r['errors'])}`. "
                      f"stderr: `{r['stderr'][:2500]}`."]
    lines += ['', '## Reproduce', '',
              'Use the repository venv at the recorded source revision and the recorded Codex/Ollama versions. '
              'Run `python scripts/token_savings.py prepare`, review and commit the protocol and harness, then '
              '`pilot`, `controls`, `remaining`, `report`, and `cleanup` in that order. '
              'The run commands resume without repeating existing cells. Never reinterpret a failed pilot as a savings result. '
              'The report subcommand works offline using only results.json. All retained raw attempts are in '
              '[runs/](token-savings/runs/).']
    (ROOT / 'docs/TOKEN-SAVINGS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    chart = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="760" role="img" aria-label="Paired token totals">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="20" y="25" font-family="sans-serif" font-size="20">Codex reported total tokens: A (blue), B (orange)</text>']
    maximum = max((total(p[c]) for p in paired for c in ('A', 'B')), default=1)
    for i, task in enumerate(meta['tasks']):
        y = 65 + i * 44
        chart.append(f'<text x="10" y="{y}" font-family="sans-serif" font-size="12">{html.escape(task["id"])}</text>')
        p = next((p for p in paired if p['id'] == task['id']), None)
        if p:
            for j, c in enumerate(('A', 'B')):
                width = 600 * total(p[c]) / maximum
                chart.append(f'<rect x="340" y="{y-12+j*16}" width="{width:.2f}" height="14" fill="{["#2563eb", "#ea580c"][j]}"/>')
                chart.append(f'<text x="{345+width:.2f}" y="{y+j*16}" font-size="11">{total(p[c])}</text>')
        else:
            chart.append(f'<text x="340" y="{y}" font-family="sans-serif" font-size="12">not measured</text>')
    chart.append('</svg>')
    (OUT / 'chart.svg').write_text('\n'.join(chart) + '\n', encoding='utf-8')
    for filename, french in [('README.md', False), ('README.fr.md', True)]:
        p = ROOT / filename
        content = p.read_text(encoding='utf-8')
        start, end = '<!-- token-savings:start -->', '<!-- token-savings:end -->'
        if complete:
            paragraph = (f"Mesure Codex : A {overall['A']:,} tokens contre B {overall['B']:,}, soit {overall['saving']:.1%} "
                         'économisés. Une exécution par tâche sur une seule machine ne permet pas de généraliser.' if french else
                         f"Measured Codex totals: A {overall['A']:,} tokens versus B {overall['B']:,}, {overall['saving']:.1%} saved. "
                         'One run per task on one machine does not establish a general saving.')
        else:
            paragraph = ('La mesure des économies de tokens reste incomplète : aucune économie globale vérifiée à annoncer.' if french else
                         'The token-savings experiment is incomplete: no verified overall savings to claim.')
        block = start + '\n\n' + ('### Économies de tokens mesurées' if french else '### Measured token savings') + '\n\n' + paragraph + ' [Report](docs/TOKEN-SAVINGS.md).\n\n' + end
        if start in content:
            content = content[:content.index(start)] + block + content[content.index(end)+len(end):]
        else:
            first_blank = content.find('\n\n')
            content = content[:first_blank+2] + block + '\n\n' + content[first_blank+2:]
        p.write_text(content, encoding='utf-8')
    print(json.dumps(summaries, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'pilot', 'remaining', 'controls', 'report', 'cleanup'])
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action in ('pilot', 'remaining', 'controls'):
        if args.action != 'pilot' and not json.loads((state() / 'meta.json').read_text()).get('pilot_valid'):
            raise SystemExit('Pilot must pass before further sessions')
        run(args.action)
    elif args.action == 'cleanup':
        work = state().resolve()
        if work.parent != Path(tempfile.gettempdir()).resolve() or not work.name.startswith('readscout-token-savings-'):
            raise SystemExit('Unsafe cleanup path')
        shutil.rmtree(work)
        POINTER.unlink()
    else:
        report()


if __name__ == '__main__':
    main()
