"""The command line, with Ollama, the hardware probe and the agents stubbed out."""
import pytest

from readscout import agents, backend, cli, editing, hardware, llamacpp, paths, tasks
from readscout.hardware import Hardware

REC = {'fast': {'model': 'small', 'download_gb': 3, 'why': 'fits', 'ctx': 32768},
       'quality': {'model': 'big', 'download_gb': 9, 'why': 'better', 'ctx': 32768}}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(hardware, 'ensure_config', lambda: None)
    monkeypatch.setattr(hardware, 'detect', lambda: Hardware(gpu='Test GPU', vram_gb=8.0, ram_gb=32.0, os='test', source='stub'))
    monkeypatch.setattr(hardware, 'recommend', lambda v, r: REC)
    monkeypatch.setattr(backend, 'health', lambda url, timeout=3: '0.40')
    monkeypatch.setattr(backend, 'ensure_ollama', lambda url, wait=60: None)
    monkeypatch.setattr(backend, 'ollama_binary', lambda: 'ollama')
    monkeypatch.setattr(backend, 'installed_models', lambda url: {'gemma4:e4b', 'gemma4:26b'})
    monkeypatch.setattr(agents, 'status', lambda: {'claude_cli': True, 'claude_wired': True, 'codex_config': False})


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(['--version'])
    assert e.value.code == 0 and 'readscout' in capsys.readouterr().out


def test_doctor_all_good(capsys):
    paths.save_config(paths.load_config())
    assert cli.main(['doctor']) == 0
    out = capsys.readouterr().out
    assert 'All good.' in out and 'any folder the agent names' in out and 'gate commands: on' in out
    assert 'readscout gate off' in out                 # the gate risk is said while gate commands are allowed
    assert cli.main(['gate', 'off']) == 0 and cli.main(['doctor']) == 0
    assert 'readscout gate off' not in capsys.readouterr().out


def test_doctor_with_llamacpp(monkeypatch, tmp_path, capsys):
    f = tmp_path / 'small.gguf'
    f.write_bytes(b'GGUF')
    monkeypatch.setattr(llamacpp, 'binary', lambda cfg: None)
    assert cli.main(['engine', 'llamacpp', '--fast', str(f), '--quality', str(f)]) == 0
    capsys.readouterr()
    assert cli.main(['doctor']) == 1
    out = capsys.readouterr().out
    assert 'FAIL llama-server found' in out and f'OK   fast model file {f}' in out and 'Ollama' not in out


def test_doctor_with_mixed_engines_checks_each_model_on_its_engine(monkeypatch, tmp_path, capsys):
    f = tmp_path / 'big.gguf'
    f.write_bytes(b'GGUF')
    monkeypatch.setattr(llamacpp, 'binary', lambda cfg: 'llama-server')
    monkeypatch.setattr(backend, 'installed_models', lambda url: {'gemma4:e4b'})      # the 26B only exists as a .gguf
    assert cli.main(['engine', 'llamacpp', '--quality', str(f)]) == 0
    capsys.readouterr()
    assert cli.main(['doctor']) == 0
    out = capsys.readouterr().out
    assert f'OK   quality model file {f}' in out and 'OK   fast model gemma4:e4b installed' in out
    assert 'quality model gemma4:26b' not in out


def test_doctor_reports_missing_model_and_agent(monkeypatch, capsys):
    monkeypatch.setattr(backend, 'installed_models', lambda url: {'gemma4:e4b'})
    monkeypatch.setattr(agents, 'status', lambda: {'claude_cli': False, 'codex_config': False})
    assert cli.main(['doctor']) == 1
    out = capsys.readouterr().out
    assert 'FAIL quality model gemma4:26b installed' in out and 'no coding agent found' in out and 'Fix the FAIL' in out


def test_doctor_when_ollama_does_not_start(monkeypatch, capsys):
    monkeypatch.setattr(backend, 'health', lambda url, timeout=3: None)

    def fail(url, wait=60):
        raise backend.BackendError('no')
    monkeypatch.setattr(backend, 'ensure_ollama', fail)
    assert cli.main(['doctor']) == 1
    assert 'Ollama running (not running)' in capsys.readouterr().out


def test_hardware(capsys):
    assert cli.main(['hardware']) == 0
    out = capsys.readouterr().out
    assert 'Test GPU' in out and 'small' in out and 'big' in out


def test_pull_recommended_models_updates_the_config(monkeypatch, capsys):
    pulled = []

    def pull(name, url, progress):
        progress('success', 10, 10)
        pulled.append(name)
    monkeypatch.setattr(backend, 'pull', pull)
    assert cli.main(['pull']) == 0
    assert pulled == ['big', 'small']
    assert paths.load_config()['models']['fast']['name'] == 'small'
    assert '100.0%' in capsys.readouterr().out


def test_pull_named_model_keeps_the_config(monkeypatch):
    pulled = []
    monkeypatch.setattr(backend, 'pull', lambda name, url, progress: pulled.append(name))
    before = paths.load_config()['models']
    assert cli.main(['pull', 'other:1b']) == 0
    assert pulled == ['other:1b'] and paths.load_config()['models'] == before


def test_agent_commands(monkeypatch, capsys):
    monkeypatch.setitem(agents.INSTALL, 'codex', lambda: 'installed codex')
    monkeypatch.setitem(agents.UNINSTALL, 'claude', lambda: 'removed claude')
    cli.main(['install-agent', 'codex'])
    cli.main(['uninstall-agent', 'claude'])
    out = capsys.readouterr().out
    assert 'installed codex' in out and 'removed claude' in out


def test_task_commands_call_the_tools(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(tasks, 'ask', lambda *a: calls.append(('ask', a)) or 'ASK')
    monkeypatch.setattr(tasks, 'digest', lambda *a: calls.append(('digest', a)) or 'DIGEST')
    monkeypatch.setattr(editing, 'edit', lambda *a: calls.append(('edit', a)) or 'EDIT')
    cli.main(['ask', 'src', 'lib', '-q', 'where?', '--summary', '--quality'])
    cli.main(['digest', 'build.log', '-f', 'tests'])
    cli.main(['edit', 'a.py', '-i', 'add types', '--gate', 'python -m pytest -q', '--gate', 'ruff check'])
    assert calls[0] == ('ask', (['src', 'lib'], 'where?', 'summary', True))
    assert calls[1] == ('digest', ('build.log', 'tests'))
    assert calls[2] == ('edit', (['a.py'], 'add types', [['python', '-m', 'pytest', '-q'], ['ruff', 'check']]))
    assert capsys.readouterr().out.split() == ['ASK', 'DIGEST', 'EDIT']


def test_stats(capsys):
    assert cli.main(['stats', '--days', '7']) == 0
    assert '0 call(s) in 7 days' in capsys.readouterr().out


def test_stop(monkeypatch, capsys):
    loaded = ['small']
    monkeypatch.setattr(backend, 'unload_all', lambda url: list(loaded))
    monkeypatch.setattr(backend, 'loaded_models', lambda url: [])
    assert cli.main(['stop']) == 0
    assert 'Unloaded: small' in capsys.readouterr().out
    monkeypatch.setattr(backend, 'loaded_models', lambda url: ['small'])
    assert cli.main(['stop']) == 1
    assert 'STILL LOADED' in capsys.readouterr().out
    monkeypatch.setattr(backend, 'health', lambda url, timeout=3: None)
    assert cli.main(['stop']) == 0
    assert 'not running' in capsys.readouterr().out


def test_warm(monkeypatch, capsys):
    monkeypatch.setattr(tasks, 'ensure_ollama', lambda url: None)
    monkeypatch.setattr(tasks, 'installed_models', lambda url: {'gemma4:e4b'})
    monkeypatch.setattr(backend, 'chat', lambda *a, **k: None)
    assert cli.main(['warm']) == 0
    assert 'gemma4:e4b loaded' in capsys.readouterr().out


def test_setup_and_dashboard_open_the_page(monkeypatch):
    opened = []
    monkeypatch.setattr(cli, 'open_page', lambda path: opened.append(path))
    cli.main(['setup'])
    cli.main(['dashboard'])
    assert opened == ['/setup', '/']


def test_folders_add_list_remove(tmp_path, capsys):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    assert cli.main(['folders']) == 0
    assert 'No folder list' in capsys.readouterr().out
    assert cli.main(['folders', 'add', str(a), str(b), str(a)]) == 0
    assert paths.allowed_folders(paths.load_config()) == [a.resolve(), b.resolve()]
    assert cli.main(['folders', 'remove', str(a)]) == 0
    assert paths.allowed_folders(paths.load_config()) == [b.resolve()]
    assert str(b.resolve()) in capsys.readouterr().out
    assert cli.main(['folders', 'add', str(tmp_path / 'missing')]) == 1
    assert cli.main(['folders', 'add']) == 2


def test_gate_on_off():
    cli.main(['gate', 'off'])
    assert not paths.gate_allowed(paths.load_config())
    cli.main(['gate', 'on'])
    assert paths.gate_allowed(paths.load_config())
