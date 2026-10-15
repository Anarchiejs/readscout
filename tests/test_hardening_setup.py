"""Regression tests for the second audit: local-only models, config writes, Codex TOML, web actions."""
import io
import json
import threading
import tomllib
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from readscout import agents, backend, paths, web
from readscout.backend import BackendError, Model


def test_cloud_model_names_are_refused():
    for name in ['gpt-oss:120b-cloud', 'qwen3-coder:480b-cloud', 'x:cloud']:
        with pytest.raises(BackendError, match='Cloud model'):
            Model(name)
    assert Model('gemma4:e4b').name == 'gemma4:e4b'


def test_models_served_remotely_are_refused_even_with_a_normal_name(monkeypatch):
    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    tags = {'models': [{'name': 'sneaky:latest', 'model': 'sneaky:latest', 'remote_host': 'https://ollama.com:443'},
                       {'name': 'gemma4:e4b', 'model': 'gemma4:e4b'}]}
    monkeypatch.setattr(backend, '_request', lambda url, body=None, timeout=600: Resp(json.dumps(tags).encode()))
    monkeypatch.setattr(backend, 'CHECKED', set())
    backend.check_local(Model('gemma4:e4b'))
    with pytest.raises(BackendError, match='remote'):
        backend.check_local(Model('sneaky:latest'))


def test_ollama_is_started_with_cloud_features_off():
    assert backend.OLLAMA_ENV['OLLAMA_NO_CLOUD'] == '1'


def test_unload_reports_failures(monkeypatch):
    def failing(url, body=None, timeout=600):
        raise BackendError('down')
    monkeypatch.setattr(backend, '_request', failing)
    assert backend.unload('m') is False


def test_config_updates_do_not_lose_each_other(tmp_path):
    def add(i):
        paths.update_config(lambda cfg: cfg['projects'].__setitem__(f'p{i}', f'C:/p{i}'))
    threads = [threading.Thread(target=add, args=(i,)) for i in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert set(paths.load_config()['projects']) == {f'p{i}' for i in range(12)}
    assert not (paths.home() / 'config.lock').exists()


@pytest.fixture
def codex(tmp_path, monkeypatch):
    cfg = tmp_path / '.codex' / 'config.toml'
    cfg.parent.mkdir()
    monkeypatch.setattr(agents, 'CODEX_CONFIG', cfg)
    monkeypatch.setattr(agents, 'CODEX_SKILL', tmp_path / 'skills' / 'readscout' / 'SKILL.md')
    return cfg


def test_codex_install_handles_subtables_and_crlf(codex):
    codex.write_bytes(b'model = "x"\r\n\r\n[mcp_servers.readscout]\r\ncommand = "old"\r\n\r\n[mcp_servers.readscout.env]\r\nA = "1"\r\n\r\n[other]\r\nk = 1\r\n')
    agents.install_codex()
    data = tomllib.loads(codex.read_bytes().decode())
    assert data['mcp_servers']['readscout']['command'] != 'old' and 'env' not in data['mcp_servers']['readscout']
    assert data['other'] == {'k': 1} and data['model'] == 'x'
    assert b'\r\n' in codex.read_bytes() and codex.with_name('config.toml.readscout-bak').exists()
    agents.uninstall_codex()
    assert tomllib.loads(codex.read_text()) == {'model': 'x', 'other': {'k': 1}}


def test_codex_install_never_breaks_a_valid_file(codex):
    original = 'model = "x"\n\n[mcp_servers]\nreadscout = { command = "mine" }\n'
    codex.write_text(original)
    assert 'safely' in agents.install_codex()
    assert codex.read_text() == original


def test_codex_install_refuses_an_invalid_file(codex):
    codex.write_text('this is = = not toml')
    assert 'not valid TOML' in agents.install_codex()
    assert codex.read_text() == 'this is = = not toml'


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def _post(port, path, body):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json', 'X-Readscout-Token': web.TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_web_rejects_unknown_actions_and_cloud_models(server, monkeypatch):
    called = []
    monkeypatch.setitem(agents.UNINSTALL, 'claude', lambda: called.append('uninstall') or 'x')
    assert _post(server, '/api/agent', {'agent': 'claude', 'action': 'whatever'}) == 400
    assert _post(server, '/api/agent', {'agent': 'nope', 'action': 'install'}) == 400
    assert called == []
    assert _post(server, '/api/project', {'action': 'whatever', 'id': 'x'}) == 400
    assert _post(server, '/api/models', {'fast': 'gpt-oss:120b-cloud'}) == 400
    assert _post(server, '/api/models', {'fast': 'bad name; rm'}) == 400
    assert _post(server, '/api/models', {'fast': 'gemma4:e2b'}) == 200


def test_web_state_errors_become_json(server, monkeypatch):
    monkeypatch.setattr(web, 'state', lambda *a: (_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f'http://127.0.0.1:{server}/api/state', timeout=10)
    assert e.value.code == 503 and 'disk' in e.value.read().decode()


def test_small_machines_are_not_rounded_up():
    hw = web.hardware.Hardware(0.0, 8.0, 'no GPU detected', 'none', 'linux')
    web._CACHE['hardware'] = (10**12, hw)
    try:
        st = web.state()
    finally:
        web._CACHE.pop('hardware', None)
    assert st['chosen'] == {'vram_gb': 0.0, 'ram_gb': 8.0}
    assert st['recommended']['fast']['model'] == 'gemma4:e2b'


def test_register_refuses_private_home_folders(tmp_path, monkeypatch):
    from readscout import cli
    home = tmp_path / 'home'
    for sub in ['AppData/Local', 'Documents', '.ssh', 'work/app']:
        (home / sub).mkdir(parents=True)
    monkeypatch.setattr(cli.Path, 'home', classmethod(lambda c: home))
    for bad in ['AppData/Local', 'Documents', '.ssh', '']:
        with pytest.raises(SystemExit):
            cli.register('x', str(home / bad))
    assert 'Registered' in cli.register('app', str(home / 'work' / 'app'))


def test_local_edit_is_not_advertised_as_harmless():
    from readscout import server
    tool = server.mcp._tool_manager.get_tool('local_edit')
    assert tool.annotations.destructiveHint is True and 'rights' in tool.description
