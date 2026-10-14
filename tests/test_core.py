import sys

import pytest

from readscout import tasks
from readscout.backend import BackendError, Model, Reply
from readscout.text import AccessError, Line, chunk, locate, redact, resolve


def L(*texts, path='a.py'):
    return [Line(path, i, t) for i, t in enumerate(texts, 1)]


def test_locate_single_line_ignores_whitespace_and_number_prefix():
    lines = L('def f():', '    return   compute(x,  y)', 'pass')
    assert locate('return compute(x, y)', lines) == ('a.py', 2, 2)
    assert locate('2| return compute(x, y)', lines) == ('a.py', 2, 2)


def test_locate_multiline_and_missing():
    lines = L('app.get("/a",', '  auth,', '  handler)')
    assert locate('app.get("/a", auth, handler)', lines) == ('a.py', 1, 3)
    assert locate('app.post("/b")', lines) is None
    assert locate('x', lines) is None  # too short to prove anything


def test_locate_does_not_cross_files():
    lines = L('alpha beta') + L('gamma delta', path='b.py')
    assert locate('beta gamma', lines) is None


def test_chunk_respects_budget_and_keeps_all_lines():
    lines = L(*[f'line {i} ' + 'x' * 50 for i in range(100)])
    parts = chunk(lines, 1000)
    assert len(parts) > 1 and sum(len(p) for p in parts) == 100
    assert all(sum(len(l.text) + 6 for l in p) <= 1100 for p in parts)


def test_redact_secrets():
    text = redact('key = "sk-abcdefghijklmnopqrstuvwxyz"\npassword: hunter2hunter2hunter2\nname = "ok"')
    assert 'sk-abc' not in text and 'hunter2' not in text and 'ok' in text


def test_resolve_confined_to_roots(tmp_path):
    root = tmp_path / 'proj'
    (root / '.git').mkdir(parents=True)
    (root / 'src.py').write_text('x = 1\n')
    (root / '.env').write_text('SECRET=1\n')
    (root / '.git' / 'config').write_text('[core]\n')
    (tmp_path / 'outside.py').write_text('y = 2\n')
    assert resolve('src.py', [root])[1] == 'src.py'
    for bad in ['.env', '.git/config', str(tmp_path / 'outside.py'), '../outside.py']:
        with pytest.raises(AccessError):
            resolve(bad, [root])


def test_prefilter_keeps_errors_head_tail_and_dedupes():
    lines = L(*([f'INFO ok {i}' for i in range(500)] + ['ERROR boom at db'] + [f'INFO ok {i}' for i in range(500)]))
    kept = tasks.prefilter(lines, keep_head=5, keep_tail=5)
    assert any('ERROR boom' in l.text for l in kept)
    assert len(kept) < 30


def fake_chat(replies):
    calls = []

    def chat(model, system, user, schema, max_tokens=2048, timeout=600, temperature=0.0):
        calls.append(user)
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return Reply(r, 10, 5, 0.1)
    return chat, calls


def test_run_ask_drops_unquotable_findings(monkeypatch):
    chat, _ = fake_chat([{'findings': [{'quote': 'return 42', 'answer': 'returns 42'},
                                       {'quote': 'return 43', 'answer': 'invented'}]}])
    monkeypatch.setattr(tasks, 'chat', chat)
    out = tasks.run_ask(L('def f():', '    return 42'), 'what does f return?', Model('m'))
    assert [(v[1], v[3]) for v in out.verified] == [(2, 'returns 42')]
    assert out.dropped == 1


def test_run_ask_survives_backend_error(monkeypatch):
    chat, _ = fake_chat([BackendError('down')])
    monkeypatch.setattr(tasks, 'chat', chat)
    out = tasks.run_ask(L('a = 1'), 'q', Model('m'))
    assert out.verified == [] and out.errors


def test_apply_exact_and_tolerant_and_ambiguous():
    assert tasks._apply('a\nb\nc\n', 'b\n', 'B\n') == 'a\nB\nc\n'
    assert tasks._apply('def f():\n    y = 2   \n    z\n', 'y = 2\nz', 'y = 3\nz') == 'def f():\n    y = 3\n    z\n'
    assert tasks._apply('b\nb\n', 'b', 'B') is None


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'm.py').write_bytes(b'def f():\r\n    return 1\r\n')
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {'quality': {'name': 'm'}, 'fast': {'name': 'm'}}}, [root]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    monkeypatch.setattr(tasks, 'ensure_ollama', lambda m: None)
    monkeypatch.setattr(tasks, 'installed_models', lambda url: {'m', 'small', 'big'})
    return root


def test_edit_applies_keeps_crlf_and_runs_gate(project, monkeypatch):
    chat, _ = fake_chat([{'edits': [{'path': 'm.py', 'search': '    return 1', 'replace': '    return 2'}], 'summary': 's'}])
    monkeypatch.setattr(tasks, 'chat', chat)
    gate = [[sys.executable, '-c', 'import sys; sys.path.insert(0, "."); import m; assert m.f() == 2']]
    out = tasks.edit(['m.py'], 'return 2', gate)
    assert out.startswith('APPLIED') and 'gate passed' in out
    assert (project / 'm.py').read_bytes() == b'def f():\r\n    return 2\r\n'


def test_edit_restores_files_when_gate_keeps_failing(project, monkeypatch):
    bad = {'edits': [{'path': 'm.py', 'search': '    return 1', 'replace': '    return 3'}], 'summary': 's'}
    chat, calls = fake_chat([bad, dict(bad)])
    monkeypatch.setattr(tasks, 'chat', chat)
    gate = [[sys.executable, '-c', 'import sys; sys.path.insert(0, "."); import m; assert m.f() == 2']]
    out = tasks.edit(['m.py'], 'return 2', gate)
    assert out.startswith('ESCALATE') and len(calls) == 2
    assert 'BROKE THE CHECKS' in calls[1]
    assert (project / 'm.py').read_bytes() == b'def f():\r\n    return 1\r\n'


def test_edit_refuses_paths_outside_request(project, monkeypatch):
    evil = {'edits': [{'path': '../x.py', 'search': '', 'replace': 'boom'}], 'summary': 's'}
    chat, _ = fake_chat([evil, dict(evil)])
    monkeypatch.setattr(tasks, 'chat', chat)
    assert tasks.edit(['m.py'], 'x', None).startswith('ESCALATE')
    assert not (project.parent / 'x.py').exists()


def test_model_refuses_remote_endpoint():
    with pytest.raises(BackendError):
        Model('m', url='http://example.com:11434')


def test_pick_tier_routes_negations_to_quality():
    assert tasks.pick_tier('Which routes are registered WITHOUT authMiddleware?', None) == 'quality'
    assert tasks.pick_tier("Quelles routes n'ont pas de limite ?", None) == 'quality'
    assert tasks.pick_tier('List every route', None) == 'fast'
    assert tasks.pick_tier('What does the node module do?', None) == 'fast'
    assert tasks.pick_tier('List every route', True) == 'quality'
    assert tasks.pick_tier('Which routes lack auth?', False) == 'fast'


def test_ask_escalates_to_quality_when_fast_finds_nothing(project, monkeypatch):
    (project / 'a.py').write_text('def f():\n    return 42\n')
    used = []

    def chat(model, system, user, schema, max_tokens=2048, timeout=600, temperature=0.0):
        used.append(model.name)
        found = [{'quote': 'return 42', 'answer': 'returns 42'}] if model.name == 'big' else []
        return Reply({'findings': found}, 1, 1, 0.1)
    monkeypatch.setattr(tasks, 'chat', chat)
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {'fast': {'name': 'small'}, 'quality': {'name': 'big'}}}, [project]))
    monkeypatch.setattr(tasks, 'ensure_ollama', lambda m: None)
    monkeypatch.setattr(tasks, 'installed_models', lambda url: {'m', 'small', 'big'})
    out = tasks.ask(['a.py'], 'what does f return?')
    assert used == ['small', 'big'] and 'retried with quality model' in out and 'a.py:2' in out


def test_cli_register_refuses_broad_folders_and_saves(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from readscout import cli, paths
    monkeypatch.setenv('READSCOUT_HOME', str(tmp_path / 'home'))
    with pytest.raises(SystemExit):
        cli.register('home', str(Path.home()))
    with pytest.raises(SystemExit):
        cli.register('bad id!', str(tmp_path))
    proj = tmp_path / 'proj'
    proj.mkdir()
    cli.register('proj', str(proj))
    assert 'proj' in json.loads(paths.config_file().read_text())['projects']
    cli.unregister('proj')
    assert json.loads(paths.config_file().read_text())['projects'] == {}


def test_model_prose_never_contains_em_dash():
    assert tasks.no_em_dash('auth \u2014 checked') == 'auth : checked'
    assert tasks.no_em_dash('a\u2014b') == 'a-b'


def test_missing_quality_model_falls_back_to_fast(monkeypatch):
    monkeypatch.setattr(tasks, 'ensure_ollama', lambda url: None)
    monkeypatch.setattr(tasks, 'installed_models', lambda url: {'small'})
    cfg = {'models': {'fast': {'name': 'small'}, 'quality': {'name': 'big'}}}
    m = tasks.model_for(cfg, 'quality')
    assert m.name == 'small' and 'readscout pull big' in m.note
    assert tasks.model_for(cfg, 'fast').note == ''


def test_identical_quotes_land_on_distinct_lines():
    lines = L('@router.get(', '    dependencies=[Depends(admin)],', ')', 'x = 1', '@router.post(', '    dependencies=[Depends(admin)],', ')')
    used = set()
    first = locate('dependencies=[Depends(admin)]', lines, 0, used)
    used.add(first)
    second = locate('dependencies=[Depends(admin)]', lines, 0, used)
    assert (first[1], second[1]) == (2, 6)
    assert locate('dependencies=[Depends(admin)]', lines, hint=6)[1] == 6     # the hint picks among verified places
    assert locate('dependencies=[Depends(other)]', lines, hint=6) is None     # but never verifies a quote by itself


def test_glued_multiline_quote_is_found():
    lines = L("const { error } = await supabase", "    .from('products')", "    .upsert([productData]);")
    assert locate(".from('products').upsert([productData]);", lines) == ('a.py', 2, 3)
