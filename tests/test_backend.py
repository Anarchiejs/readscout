"""The Ollama client with a fake HTTP layer, and the synthetic benchmark logs."""
import io
import json

import pytest

from readscout import backend
from readscout.backend import BackendError, Model
from readscout.bench import logs


class FakeOllama:
    """Answers backend._request by path; records the bodies it received."""

    def __init__(self, **routes):
        self.routes, self.bodies = routes, []

    def __call__(self, url, body=None, timeout=600):
        path = '/' + url.split('/', 3)[3]
        self.bodies.append((path, body))
        answer = self.routes[path]
        if isinstance(answer, Exception):
            raise answer
        raw = answer if isinstance(answer, bytes) else json.dumps(answer).encode()
        return io.BytesIO(raw)


@pytest.fixture
def ollama(monkeypatch):
    backend.CHECKED.clear()
    backend.USED.clear()

    def install(**routes):
        fake = FakeOllama(**routes)
        monkeypatch.setattr(backend, '_request', fake)
        return fake
    return install


def test_model_refuses_remote_endpoints_and_cloud_names():
    with pytest.raises(BackendError, match='Non-loopback'):
        Model('m', url='http://10.0.0.2:11434')
    with pytest.raises(BackendError, match='Cloud model'):
        Model('gpt-oss:120b-cloud')
    assert Model('m', url='http://localhost:11434').name == 'm'


def test_chat_sends_the_schema_and_parses_the_answer(ollama):
    fake = ollama(**{'/api/tags': {'models': [{'name': 'm'}]},
                     '/api/chat': {'message': {'content': '```json\n{"ok": true}\n```'}, 'prompt_eval_count': 7, 'eval_count': 3}})
    reply = backend.chat(Model('m', ctx=4096), 'sys', 'user', {'type': 'object'}, max_tokens=10)
    assert reply.data == {'ok': True} and (reply.prompt_tokens, reply.output_tokens) == (7, 3)
    body = fake.bodies[-1][1]
    assert body['format'] == {'type': 'object'} and body['options']['num_ctx'] == 4096 and body['stream'] is False
    assert ('http://127.0.0.1:11434', 'm') in backend.USED


def test_chat_refuses_models_served_remotely(ollama):
    ollama(**{'/api/tags': {'models': [{'name': 'm', 'remote_host': 'https://ollama.com'}]}})
    with pytest.raises(BackendError, match='remote host'):
        backend.chat(Model('m'), 's', 'u', {})


def test_chat_errors_on_truncated_or_invalid_output(ollama):
    ollama(**{'/api/tags': {'models': []}, '/api/chat': {'message': {'content': '{'}, 'done_reason': 'length'}})
    with pytest.raises(BackendError, match='truncated'):
        backend.chat(Model('m'), 's', 'u', {})
    ollama(**{'/api/tags': {'models': []}, '/api/chat': {'message': {'content': 'not json'}}})
    with pytest.raises(BackendError, match='invalid JSON'):
        backend.chat(Model('m'), 's', 'u', {})


def test_models_listing_and_unloading(ollama):
    fake = ollama(**{'/api/tags': {'models': [{'name': 'a:latest'}, {'name': 'b:1b'}]},
                     '/api/ps': {'models': [{'name': 'b:1b'}]}, '/api/generate': {}})
    assert backend.installed_models() == {'a:latest', 'a', 'b:1b'}
    assert backend.loaded_models() == ['b:1b']
    assert backend.unload_all() == ['b:1b']
    assert fake.bodies[-1] == ('/api/generate', {'model': 'b:1b', 'keep_alive': 0})


def test_unreachable_ollama_is_not_fatal_for_status_calls(ollama):
    ollama(**{'/api/ps': BackendError('down'), '/api/generate': BackendError('down')})
    assert backend.loaded_models() == [] and backend.unload('x') is False


def test_unload_used_frees_what_this_process_loaded(ollama):
    fake = ollama(**{'/api/generate': {}})
    backend.USED.add(('http://127.0.0.1:11434', 'm'))
    backend.unload_used()
    assert fake.bodies == [('/api/generate', {'model': 'm', 'keep_alive': 0})]


def test_pull_reports_progress_and_errors(ollama):
    stream = b'{"status": "pulling", "completed": 5, "total": 10}\n\n{"status": "success"}\n'
    ollama(**{'/api/pull': stream})
    seen = []
    backend.pull('m', progress=lambda *a: seen.append(a))
    assert seen == [('pulling', 5, 10), ('success', 0, 0)]
    ollama(**{'/api/pull': b'{"error": "model not found"}\n'})
    with pytest.raises(BackendError, match='not found'):
        backend.pull('m')


def test_ensure_ollama_says_how_to_install_it(monkeypatch):
    monkeypatch.setattr(backend, 'health', lambda url, timeout=3: None)
    monkeypatch.setattr(backend, 'ollama_binary', lambda: None)
    monkeypatch.setattr(backend.os.path, 'exists', lambda p: False)
    with pytest.raises(BackendError, match='not installed'):
        backend.ensure_ollama()


def test_benchmark_logs_hide_the_root_cause_at_the_announced_line(tmp_path):
    found = logs.tasks(tmp_path)
    assert len(found) == 4
    for task in found:
        gt = task.gt[0]
        text = (tmp_path / task.paths[0]).read_text(encoding='utf-8').splitlines()
        assert gt['key'] in text[gt['line'] - 1]
        assert sum(gt['key'] in line for line in text) == 1      # the cause appears once, in the noise
