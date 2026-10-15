"""The llama.cpp engine with a fake llama-server: chat format, one shared server, idle stop, configuration."""
import io
import json

import pytest

from readscout import backend, cli, hardware, llamacpp, paths, tasks, web
from readscout.backend import BackendError
from readscout.hardware import Hardware


class FakeServer:
    """Answers llamacpp._request; `up` maps a port to 'ok', 'loading' or absent (nothing listens)."""

    def __init__(self):
        self.up, self.bodies, self.busy = {}, [], False
        self.reply = {'choices': [{'message': {'content': '{"ok": true}'}, 'finish_reason': 'stop'}],
                      'usage': {'prompt_tokens': 11, 'completion_tokens': 2}}

    def __call__(self, url, body=None, timeout=600):
        port = int(url.split(':')[2].split('/')[0])
        path = '/' + url.split('/', 3)[3]
        status = self.up.get(port)
        if status is None:
            raise BackendError(f'Local model server unreachable at {url}: refused')
        if path == '/health':
            if status == 'loading':
                raise BackendError(f'HTTP 503 from {url}: loading')
            return io.BytesIO(b'{"status": "ok"}')
        if path == '/slots':
            return io.BytesIO(json.dumps([{'is_processing': self.busy}]).encode())
        self.bodies.append((port, path, body))
        return io.BytesIO(json.dumps(self.reply).encode())


@pytest.fixture
def server(monkeypatch, tmp_path):
    fake = FakeServer()
    spawned, killed, unloaded = [], [], []
    monkeypatch.setattr(backend, 'unload_all', lambda url='': unloaded.append(url) or [])   # never the real Ollama
    monkeypatch.setattr(llamacpp, '_request', fake)
    monkeypatch.setattr(llamacpp, '_start_watchdog', lambda cfg: None)
    monkeypatch.setattr(llamacpp, '_alive', lambda pid: True)
    ports = iter(range(9001, 9100))
    monkeypatch.setattr(llamacpp, '_free_port', lambda: next(ports))

    def spawn(m, cfg, port, token=''):
        spawned.append((m.gguf, port))
        fake.up[port] = 'ok'
        return 1000 + port

    def kill(pid):
        killed.append(pid)
        fake.up.pop(pid - 1000, None)
    monkeypatch.setattr(llamacpp, '_spawn', spawn)
    monkeypatch.setattr(llamacpp, '_kill', kill)
    llamacpp._OWN.clear()
    fake.spawned, fake.killed, fake.unloaded = spawned, killed, unloaded
    return fake


@pytest.fixture
def ollama(monkeypatch):
    """A fake Ollama with both default models installed; records the models it was asked to run."""
    calls = []
    monkeypatch.setattr(tasks, 'ensure_ollama', lambda url: None)
    monkeypatch.setattr(tasks, 'installed_models', lambda url: {'gemma4:e4b', 'gemma4:26b'})

    def request(url, body=None, timeout=600):
        if url.endswith('/api/tags'):
            return io.BytesIO(b'{"models": []}')
        calls.append(body['model'])
        return io.BytesIO(json.dumps({'message': {'content': '{"ok": true}'}, 'done_reason': 'stop'}).encode())
    monkeypatch.setattr(backend, '_request', request)
    return calls


def gguf(tmp_path, name):
    f = tmp_path / f'{name}.gguf'
    f.write_bytes(b'GGUF')
    return str(f)


def configure(tmp_path, **tiers):
    def apply(c):
        c['engine'] = 'llamacpp'
        c['llamacpp'] = {'models': {t: {'gguf': gguf(tmp_path, n), 'ctx': 8192} for t, n in tiers.items()}}
    return paths.update_config(apply)


def test_chat_asks_llama_server_for_schema_constrained_json_without_thinking(server, tmp_path):
    cfg = configure(tmp_path, fast='small')
    m = tasks.model_for(cfg, 'fast')
    assert (m.engine, m.name, m.ctx) == ('llamacpp', 'small', 8192)
    reply = backend.chat(m, 'sys', 'user', {'type': 'object'}, max_tokens=10)
    assert reply.data == {'ok': True} and (reply.prompt_tokens, reply.output_tokens) == (11, 2)
    _, path, body = server.bodies[-1]
    assert path == '/v1/chat/completions'
    assert body['response_format'] == {'type': 'json_schema', 'json_schema': {'name': 'answer', 'schema': {'type': 'object'}}}
    assert body['chat_template_kwargs'] == {'enable_thinking': False} and body['max_tokens'] == 10
    assert (body['repeat_penalty'], body['repeat_last_n']) == (1.1, 64)     # Ollama's defaults: Gemma 4 loops without them


def test_one_shared_server_reused_then_replaced_by_another_model(server, tmp_path):
    cfg = configure(tmp_path, fast='small', quality='big')
    small, big = tasks.model_for(cfg, 'fast'), tasks.model_for(cfg, 'quality')
    backend.chat(small, 's', 'u', {})
    backend.chat(small, 's', 'u', {})
    assert len(server.spawned) == 1                       # loaded once, reused
    backend.chat(big, 's', 'u', {})
    assert len(server.spawned) == 2 and server.killed == [1000 + server.spawned[0][1]]   # one model at a time
    assert json.loads((paths.home() / 'llamacpp.json').read_text())['key'].count('big.gguf') == 1


def test_a_server_stopped_by_someone_else_is_started_again(server, tmp_path):
    cfg = configure(tmp_path, fast='small')
    m = tasks.model_for(cfg, 'fast')
    backend.chat(m, 's', 'u', {})
    server.up.clear()                                     # another process stopped it, or it crashed
    backend.chat(m, 's', 'u', {})
    assert len(server.spawned) == 2


def test_idle_server_is_stopped_but_never_while_it_works(server, tmp_path):
    cfg = configure(tmp_path, fast='small')
    backend.chat(tasks.model_for(cfg, 'fast'), 's', 'u', {})
    assert llamacpp.idle_check(60) is False               # just used
    server.busy = True
    assert llamacpp.idle_check(0) is False                # a long request is running
    server.busy = False
    assert llamacpp.idle_check(0) is True and server.killed
    assert not (paths.home() / 'llamacpp.json').exists()


def test_stop_all_and_stop_owned(server, tmp_path):
    cfg = configure(tmp_path, fast='small')
    backend.chat(tasks.model_for(cfg, 'fast'), 's', 'u', {})
    assert llamacpp.stop_all() == 'small' and llamacpp.stop_all() is None
    llamacpp._OWN.update(pid=1000 + server.spawned[0][1])
    backend.chat(tasks.model_for(cfg, 'fast'), 's', 'u', {})
    llamacpp._OWN.update(pid=1000 + server.spawned[-1][1])
    backend.unload_used()                                 # the agent session ended
    assert not (paths.home() / 'llamacpp.json').exists() and not llamacpp._OWN


def test_server_that_dies_while_loading_reports_its_log(monkeypatch, tmp_path):
    class Dead:
        pid, returncode = 4242, 1

        def poll(self):
            return 1
    monkeypatch.setattr(llamacpp, '_request', lambda *a, **k: (_ for _ in ()).throw(BackendError('HTTP 503 from x: loading')))
    monkeypatch.setattr(llamacpp, '_start_watchdog', lambda cfg: None)

    def spawn(m, cfg, port, token=''):
        llamacpp.log_file().write_text('error: out of memory', encoding='utf-8')
        llamacpp._OWN.update(proc=Dead(), pid=4242)
        return 4242
    monkeypatch.setattr(llamacpp, '_spawn', spawn)
    cfg = configure(tmp_path, fast='small')
    with pytest.raises(BackendError, match='out of memory'):
        llamacpp.ensure(tasks.model_for(cfg, 'fast'), cfg)
    assert not (paths.home() / 'llamacpp.json').exists()


def test_users_own_server_is_used_as_is_and_must_be_local(server):
    server.up[8080] = 'ok'
    paths.update_config(lambda c: c.update(engine='llamacpp', llamacpp={'models': {'fast': {'url': 'http://127.0.0.1:8080'}}}))
    m = tasks.model_for(paths.load_config(), 'fast')
    backend.chat(m, 's', 'u', {})
    assert server.bodies[-1][0] == 8080 and not server.spawned
    paths.update_config(lambda c: c['llamacpp']['models']['fast'].update(url='http://10.0.0.5:8080'))
    with pytest.raises(BackendError, match='Non-loopback'):
        tasks.model_for(paths.load_config(), 'fast')


def test_missing_configuration_or_file_says_how_to_fix_it(tmp_path):
    paths.update_config(lambda c: c.update(engine='llamacpp', llamacpp={'models': {'fast': {'ctx': 8192}}}))
    with pytest.raises(BackendError, match='engine llamacpp --fast'):
        tasks.model_for(paths.load_config(), 'fast')
    paths.update_config(lambda c: c.update(llamacpp={'models': {'fast': {'gguf': str(tmp_path / 'gone.gguf')}}}))
    with pytest.raises(BackendError, match='not found'):
        tasks.model_for(paths.load_config(), 'fast')


def test_engine_command(tmp_path, capsys):
    f = gguf(tmp_path, 'small')
    assert cli.main(['engine', 'llamacpp']) == 1                          # no model named and none configured
    assert paths.load_config()['engine'] == 'ollama'
    assert cli.main(['engine', 'llamacpp', '--fast', str(tmp_path / 'x.txt')]) == 1
    assert cli.main(['engine', 'llamacpp', '--fast', 'http://192.168.1.2:8080']) == 1
    assert cli.main(['engine', 'llamacpp', '--fast', f, '--args', '--n-cpu-moe 30']) == 0
    cfg = paths.load_config()
    assert cfg['engine'] == 'llamacpp' and cfg['llamacpp']['args'] == ['--n-cpu-moe', '30']
    assert cfg['llamacpp']['models']['fast']['gguf'].endswith('small.gguf')
    capsys.readouterr()
    assert cli.main(['engine']) == 0 and 'small.gguf' in capsys.readouterr().out
    assert cli.main(['engine', 'ollama']) == 0 and paths.load_config()['engine'] == 'ollama'
    assert cli.main(['engine', 'llamacpp']) == 0 and paths.load_config()['engine'] == 'llamacpp'     # the models were kept


def test_quality_alone_on_llamacpp_keeps_the_fast_model_on_ollama(server, ollama, tmp_path, capsys):
    f = gguf(tmp_path, 'big')
    assert cli.main(['engine', 'llamacpp', '--quality', f]) == 0          # no --fast needed
    out = capsys.readouterr().out
    assert 'fast     ollama    gemma4:e4b' in out and 'quality  llamacpp' in out
    cfg = paths.load_config()
    fast, quality = tasks.model_for(cfg, 'fast'), tasks.model_for(cfg, 'quality')
    assert (fast.engine, fast.name) == ('ollama', 'gemma4:e4b') and (quality.engine, quality.name) == ('llamacpp', 'big')
    backend.chat(fast, 's', 'u', {})
    backend.chat(quality, 's', 'u', {})
    assert ollama == ['gemma4:e4b'] and server.spawned == [(f, 9001)]
    assert cli.main(['engine', 'llamacpp', '--quality', 'ollama']) == 0  # back to Ollama: nothing left on llama.cpp
    cfg = paths.load_config()
    assert cfg['engine'] == 'ollama' and tasks.model_for(cfg, 'quality').engine == 'ollama'


def test_engine_ollama_puts_every_model_back_on_ollama(server, ollama, tmp_path):
    configure(tmp_path, fast='small', quality='big')
    assert cli.main(['engine', 'ollama']) == 0
    cfg = paths.load_config()
    assert [tasks.model_for(cfg, t).engine for t in ('fast', 'quality')] == ['ollama', 'ollama']


def test_missing_ollama_quality_model_falls_back_to_the_llamacpp_fast_one(server, monkeypatch, tmp_path):
    configure(tmp_path, fast='small')
    monkeypatch.setattr(tasks, 'ensure_ollama', lambda url: None)
    monkeypatch.setattr(tasks, 'installed_models', lambda url: set())
    m = tasks.model_for(paths.load_config(), 'quality')
    assert (m.engine, m.name) == ('llamacpp', 'small') and 'gemma4:26b not installed' in m.note


def test_llamacpp_unloads_ollama_models_before_starting_one(server, tmp_path):
    cfg = configure(tmp_path, fast='small', quality='big')
    backend.chat(tasks.model_for(cfg, 'fast'), 's', 'u', {})
    backend.chat(tasks.model_for(cfg, 'fast'), 's', 'u', {})
    assert server.unloaded == ['http://127.0.0.1:11434']     # once, when it started, not on every call
    backend.chat(tasks.model_for(cfg, 'quality'), 's', 'u', {})
    assert len(server.unloaded) == 2


def test_ollama_call_stops_the_idle_llama_server_first(server, ollama, tmp_path):
    configure(tmp_path, quality='big')
    cfg = paths.load_config()
    backend.chat(tasks.model_for(cfg, 'quality'), 's', 'u', {})
    backend.chat(tasks.model_for(cfg, 'fast'), 's', 'u', {})
    assert server.killed == [1000 + server.spawned[0][1]] and not (paths.home() / 'llamacpp.json').exists()
    assert ollama == ['gemma4:e4b']
    backend.chat(tasks.model_for(cfg, 'fast'), 's', 'u', {})          # nothing to stop any more
    assert len(server.killed) == 1


def test_llama_server_is_never_stopped_while_it_loads_or_answers(server, tmp_path):
    cfg = configure(tmp_path, quality='big')
    backend.chat(tasks.model_for(cfg, 'quality'), 's', 'u', {})
    port = server.spawned[0][1]
    server.busy = True                                    # another session's request is running
    assert llamacpp.release() is False
    server.busy, server.up[port] = False, 'loading'       # another session is loading it
    assert llamacpp.release() is False and not server.killed
    server.up[port] = 'ok'
    assert llamacpp.release() is True and server.killed
    assert llamacpp.release() is False


def test_bench_defaults_to_each_model_on_its_engine(server, tmp_path, monkeypatch, capsys):
    from readscout.bench import runner
    configure(tmp_path, quality='big')
    seen = []
    monkeypatch.setattr(runner, 'run', lambda models, *a: seen.append(models) or {'file': 'x'})
    monkeypatch.setattr(runner, 'markdown', lambda report: '')
    assert cli.main(['bench']) == 0
    assert seen == [['gemma4:e4b', 'llamacpp:quality']]


def test_seconds_and_args():
    assert [llamacpp.seconds(v) for v in ('60s', '5m', '1h', 30, 'junk')] == [60, 300, 3600, 30, 60]
    m = llamacpp.from_spec({'llamacpp': {'args': ['-t', '8']}}, {'url': 'http://127.0.0.1:1', 'args': ['--n-cpu-moe', '4']})
    assert m.args == ('-t', '8', '--n-cpu-moe', '4')


def test_engine_reuses_the_gguf_ollama_already_downloaded(monkeypatch, tmp_path):
    weights, projector = tmp_path / 'sha256-weights', tmp_path / 'sha256-projector'
    weights.write_bytes(b'G' * 100)
    projector.write_bytes(b'G' * 10)

    class Done:
        returncode, stderr = 0, ''
        stdout = f'# Modelfile\nFROM {projector}\nFROM {weights}\nTEMPLATE x\n'
    monkeypatch.setattr(backend, 'ollama_binary', lambda: 'ollama')
    monkeypatch.setattr(llamacpp.subprocess, 'run', lambda *a, **k: Done())
    assert cli.main(['engine', 'llamacpp', '--fast', 'ollama:gemma4:e4b']) == 0
    spec = paths.load_config()['llamacpp']['models']['fast']
    assert spec['gguf'] == str(weights) and spec['name'] == 'gemma4:e4b'
    assert tasks.model_for(paths.load_config(), 'fast').name == 'gemma4:e4b'
    Done.returncode, Done.stdout, Done.stderr = 1, '', 'model not found'
    assert cli.main(['engine', 'llamacpp', '--quality', 'ollama:nope']) == 1


def test_finds_llama_server_in_the_winget_package_folder(monkeypatch, tmp_path):
    exe = tmp_path / 'Microsoft' / 'WinGet' / 'Packages' / 'ggml.llamacpp_Microsoft.Winget.Source_x' / 'llama-server.exe'
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b'')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(llamacpp.shutil, 'which', lambda name: None)
    assert llamacpp.binary({}) == str(exe)


LIST_DEVICES = ('Available devices:\n  CUDA0: NVIDIA GeForce RTX 4060 Ti (8187 MiB, 7075 MiB free)\n'
                '  Vulkan1: AMD Radeon(TM) Graphics (16186 MiB, 15377 MiB free)\n')


def fake_devices(monkeypatch, out=LIST_DEVICES):
    class Done:
        stdout = out
    monkeypatch.setattr(llamacpp, 'binary', lambda cfg: 'llama-server')
    monkeypatch.setattr(llamacpp.subprocess, 'run', lambda *a, **k: Done())


def test_devices_are_read_from_llama_server(monkeypatch):
    fake_devices(monkeypatch)
    assert llamacpp.devices({}) == [('CUDA0', 'NVIDIA GeForce RTX 4060 Ti', 8187), ('Vulkan1', 'AMD Radeon(TM) Graphics', 16186)]
    fake_devices(monkeypatch, 'load_backend: loaded CPU backend\n')
    assert llamacpp.devices({}) == []
    monkeypatch.setattr(llamacpp, 'binary', lambda cfg: None)
    assert llamacpp.devices({}) == []


def test_notes_say_which_build_to_take_and_which_device_to_pick():
    cuda, vulkan = [('CUDA0', 'RTX', 8187)], [('Vulkan0', 'RTX', 8187)]
    assert llamacpp.device_notes(cuda, 'nvidia-smi') == []
    (note,) = llamacpp.device_notes(vulkan, 'nvidia-smi')
    assert 'CUDA build' in note and 'driver 580' in note and 'slower than Ollama' in note
    assert llamacpp.device_notes([], 'nvidia-smi') and llamacpp.device_notes(vulkan, 'apple-unified') == []
    (note,) = llamacpp.device_notes(cuda + [('Vulkan1', 'iGPU', 16000)], 'nvidia-smi')
    assert '--device' in note


def test_doctor_shows_the_devices_and_the_cuda_advice(monkeypatch, tmp_path, capsys):
    configure(tmp_path, quality='big')
    fake_devices(monkeypatch, 'Available devices:\n  Vulkan0: NVIDIA GeForce RTX 4060 Ti (8187 MiB, 7075 MiB free)\n')
    monkeypatch.setattr(hardware, 'detect', lambda: Hardware(gpu='RTX', vram_gb=8.0, ram_gb=32.0, os='test', source='nvidia-smi'))
    cli.main(['doctor'])
    out = capsys.readouterr().out
    assert 'llama-server devices: Vulkan0 NVIDIA GeForce RTX 4060 Ti (7 GB)' in out and 'Take the CUDA build' in out


def test_setup_page_state_says_what_runs_each_model(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, 'health', lambda url, timeout=3: None)
    assert web.engines(paths.load_config())['used'] == {'fast': {'engine': 'ollama', 'name': 'gemma4:e4b'},
                                                         'quality': {'engine': 'ollama', 'name': 'gemma4:26b'}}
    configure(tmp_path, quality='big')
    fake_devices(monkeypatch)
    web._CACHE.clear()
    monkeypatch.setattr(web.hardware, 'detect', lambda: Hardware(gpu='RTX', vram_gb=8.0, ram_gb=32.0, os='test', source='nvidia-smi'))
    got = web.engines(paths.load_config())
    assert got['used']['quality'] == {'engine': 'llamacpp', 'name': 'big', 'ready': True}
    assert got['used']['fast']['engine'] == 'ollama'
    assert got['llamacpp']['devices'][0].startswith('CUDA0') and got['llamacpp']['binary'] == 'llama-server'
    web._CACHE.clear()


def test_llama_server_gets_a_secret_key_and_readscout_uses_it(monkeypatch, tmp_path):
    seen = {}

    class Proc:
        pid = 777

    def popen(cmd, **kw):
        seen['cmd'], seen['env'] = cmd, kw.get('env')
        return Proc()
    monkeypatch.setattr(llamacpp.subprocess, 'Popen', popen)
    monkeypatch.setattr(llamacpp, 'binary', lambda cfg: 'llama-server')
    monkeypatch.setattr(llamacpp.atexit, 'register', lambda fn: None)
    cfg = configure(tmp_path, fast='small')
    llamacpp._spawn(tasks.model_for(cfg, 'fast'), cfg, 9100, 'sekret')
    assert seen['env']['LLAMA_API_KEY'] == 'sekret' and 'sekret' not in ' '.join(seen['cmd'])    # env, not the command line
    assert '127.0.0.1' in seen['cmd']
    # the key is kept with the server's state, and added to the requests that go to that server only
    llamacpp._write_state({'pid': 777, 'port': 9100, 'key': 'k', 'token': 'sekret', 'last_used': 0})
    sent = []
    monkeypatch.setattr(llamacpp.backend, '_request', lambda url, body=None, timeout=600, headers=None: sent.append((url, headers)))
    llamacpp._request('http://127.0.0.1:9100/v1/chat/completions', {})
    llamacpp._request('http://127.0.0.1:8080/v1/chat/completions', {})        # the user's own server: no key
    assert sent == [('http://127.0.0.1:9100/v1/chat/completions', {'Authorization': 'Bearer sekret'}),
                    ('http://127.0.0.1:8080/v1/chat/completions', None)]


def test_every_started_server_has_its_own_key(server, tmp_path):
    cfg = configure(tmp_path, fast='small', quality='big')
    backend.chat(tasks.model_for(cfg, 'fast'), 's', 'u', {})
    first = json.loads((paths.home() / 'llamacpp.json').read_text())['token']
    backend.chat(tasks.model_for(cfg, 'quality'), 's', 'u', {})
    second = json.loads((paths.home() / 'llamacpp.json').read_text())['token']
    assert len(first) >= 24 and first != second
