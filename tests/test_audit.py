"""Regression tests for the pre-release audit fixes."""
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from readscout import tasks, web
from readscout.backend import Model, Reply
from readscout.text import AccessError, Line, load_lines, resolve


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'm.py').write_text('def f():\n    return 1\n')
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {'quality': {'name': 'big'}, 'fast': {'name': 'small'}}}, [root]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    monkeypatch.setattr(tasks, 'ensure_ollama', lambda url: None)
    monkeypatch.setattr(tasks, 'installed_models', lambda url: {'small', 'big'})
    return root


def never_called(*a, **k):
    raise AssertionError('the model must not be called')


def test_edit_refuses_files_with_secrets(project, monkeypatch):
    (project / 'cfg.py').write_text('API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"\n')
    monkeypatch.setattr(tasks, 'chat', never_called)
    with pytest.raises(AccessError, match='secret'):
        tasks.edit(['cfg.py'], 'rename the constant')


def test_edit_refuses_oversized_and_non_utf8(project, monkeypatch):
    monkeypatch.setattr(tasks, 'chat', never_called)
    (project / 'big.py').write_text('x = 1\n' * 20_000)
    with pytest.raises(AccessError, match='too large'):
        tasks.edit(['big.py'], 'x')
    (project / 'latin.py').write_bytes('s = "caf\xe9"\n'.encode('latin-1'))
    with pytest.raises(AccessError, match='UTF-8'):
        tasks.edit(['latin.py'], 'x')


def test_edit_accepts_dot_prefixed_paths(project, monkeypatch):
    (project / '.github').mkdir()
    (project / '.github' / 'ci.yml').write_text('name: ci\n')
    reply = {'edits': [{'path': './.github/ci.yml', 'search': 'name: ci', 'replace': 'name: tests'}], 'summary': 's'}
    monkeypatch.setattr(tasks, 'chat', lambda *a, **k: Reply(reply, 1, 1, 0.1))
    assert tasks.edit(['.github/ci.yml'], 'rename the workflow').startswith('APPLIED')
    assert (project / '.github' / 'ci.yml').read_text() == 'name: tests\n'


def test_receipt_warns_when_a_list_hit_the_cap(monkeypatch):
    lines = [Line('a.py', i, f'route_{i} = 1') for i in range(1, 60)]
    findings = [{'line': i, 'quote': f'route_{i} = 1', 'answer': f'route {i}'} for i in range(1, tasks.MAX_FINDINGS + 1)]
    monkeypatch.setattr(tasks, 'chat', lambda *a, **k: Reply({'findings': findings}, 1, 1, 0.1))
    out = tasks.run_ask(lines, 'list every route', Model('m'))
    assert out.capped == 1
    assert 'may be incomplete' in tasks.receipt(out, Model('m'), 100, 40, 'local_ask')


def test_no_pointless_retry_when_quality_falls_back_to_fast(project, monkeypatch):
    monkeypatch.setattr(tasks, 'installed_models', lambda url: {'small'})   # quality model missing
    calls = []
    monkeypatch.setattr(tasks, 'chat', lambda model, *a, **k: calls.append(model.name) or Reply({'findings': []}, 1, 1, 0.1))
    tasks.ask(['m.py'], 'what does f return?')
    assert calls == ['small']


def test_sensitive_names_refused_and_long_lines_capped(tmp_path):
    for name in ['.npmrc', 'id_rsa', 'credentials.json']:
        (tmp_path / name).write_text('x')
        with pytest.raises(AccessError):
            resolve(name, [tmp_path])
    (tmp_path / 'min.js').write_text('a' * 50_000 + '\nb\n')
    lines = load_lines('min.js', [tmp_path])
    assert len(lines[0].text) < 4100 and lines[0].text.endswith('[line truncated]') and lines[1].text == 'b'


def test_web_rejects_malformed_bodies():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        for body in [b'not json', b'[1, 2]']:
            req = urllib.request.Request(f'http://127.0.0.1:{port}/api/models', body, {'X-Readscout-Token': web.TOKEN})
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req, timeout=5)
            assert e.value.code == 400
    finally:
        srv.shutdown()


def test_missing_fast_model_gives_an_actionable_message(project, monkeypatch):
    monkeypatch.setattr(tasks, 'installed_models', lambda url: set())
    monkeypatch.setenv('READSCOUT_CLI', 'uvx --from X readscout')
    from readscout.backend import BackendError
    with pytest.raises(BackendError, match='uvx --from X readscout pull'):
        tasks.ask(['m.py'], 'what does f return?')
