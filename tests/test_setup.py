"""Hardware recommendations, agent wiring and the local web server's protections."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from readscout import agents, hardware, paths, web


@pytest.mark.parametrize('vram,ram,fast,quality', [
    (6, 16, 'gemma4:e4b', 'gemma4:e4b'),     # too little memory for a second model
    (8, 31.1, 'gemma4:e4b', 'gemma4:26b'),   # the measured machine (Windows reports 31.1 GB for 32 GB)
    (12, 16, 'gemma4:e4b', 'gemma4:12b'),
    (16, 32, 'gemma4:e4b', 'gemma4:26b'),
    (24, 64, 'gemma4:e4b', 'gemma4:26b'),
    (0, 16, 'gemma4:e2b', 'gemma4:e2b'),
])
def test_recommendations_follow_memory(vram, ram, fast, quality):
    rec = hardware.recommend(vram, ram)
    assert rec['fast']['model'] == fast and rec['quality']['model'] == quality
    assert all(r['why'] for r in rec.values())


def test_catalog_models_are_all_described():
    cat = hardware.catalog()
    for tier in cat['tiers'].values():
        for rule in tier:
            assert rule['model'] in cat['models']


def test_detect_returns_sane_numbers():
    hw = hardware.detect()
    assert hw.ram_gb > 0 and hw.vram_gb >= 0 and hw.os in ('windows', 'macos', 'linux')


def test_config_lives_in_user_home(tmp_path):
    cfg = paths.load_config()
    cfg['notes'] = {'x': 1}
    paths.save_config(cfg)
    assert paths.config_file().parent == tmp_path / 'readscout-home'
    assert paths.load_config()['notes'] == {'x': 1}


def test_codex_install_is_idempotent_and_reversible(tmp_path, monkeypatch):
    cfg = tmp_path / '.codex' / 'config.toml'
    cfg.parent.mkdir()
    cfg.write_text('model = "x"\n\n[mcp_servers.other]\ncommand = "a"\n')
    monkeypatch.setattr(agents, 'CODEX_CONFIG', cfg)
    monkeypatch.setattr(agents, 'CODEX_SKILL', tmp_path / 'skills' / 'readscout' / 'SKILL.md')
    agents.install_codex()
    agents.install_codex()
    text = cfg.read_text()
    assert text.count('[mcp_servers.readscout]') == 1 and '[mcp_servers.other]' in text
    agents.uninstall_codex()
    text = cfg.read_text()
    assert '[mcp_servers.readscout]' not in text and '[mcp_servers.other]' in text and 'model = "x"' in text


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def _req(port, path, body=None, headers=None):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', None if body is None else json.dumps(body).encode(),
                                 {'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_web_page_carries_token_and_post_requires_it(server):
    status, html = _req(server, '/setup')
    assert status == 200 and web.TOKEN in html and '__TOKEN__' not in html
    assert _req(server, '/api/models', {'fast': 'gemma4:e2b'})[0] == 403
    assert _req(server, '/api/models', {'fast': 'gemma4:e2b'}, {'X-Readscout-Token': 'wrong'})[0] == 403
    assert _req(server, '/api/models', {'fast': 'gemma4:e2b'}, {'X-Readscout-Token': web.TOKEN})[0] == 200
    assert paths.load_config()['models']['fast']['name'] == 'gemma4:e2b'


def test_web_refuses_foreign_origin_and_host(server):
    hdr = {'X-Readscout-Token': web.TOKEN, 'Origin': 'https://evil.example'}
    assert _req(server, '/api/models', {'fast': 'x'}, hdr)[0] == 403
    assert _req(server, '/setup', headers={'Host': 'evil.example'})[0] == 403


def test_web_only_pulls_catalog_models(server):
    status, _ = _req(server, '/api/pull', {'model': 'someone/malicious'}, {'X-Readscout-Token': web.TOKEN})
    assert status == 400


def test_first_run_config_follows_the_hardware(monkeypatch):
    monkeypatch.setattr(hardware, 'detect', lambda: hardware.Hardware(8.0, 15.0, 'gpu', 'test', 'linux'))
    assert not paths.config_file().exists()
    hardware.ensure_config()
    models = paths.load_config()['models']
    assert models['fast']['name'] == 'gemma4:e4b' and models['quality']['name'] == 'gemma4:e4b'
    hardware.ensure_config()   # never overwrites an existing config
    assert paths.load_config()['models'] == models
