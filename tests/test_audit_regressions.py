"""Behavioural regressions found during the complete baseline audit."""
import json

import pytest

from readscout import backend, editing, extract, llamacpp, logs, paths, stats, tasks
from readscout.text import Line, load_lines


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('READSCOUT_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('READSCOUT_NO_METRICS', '1')


def test_failed_gate_launch_restores_original(tmp_path, monkeypatch):
    file = tmp_path / 'a.py'
    file.write_text('x = 1\n')
    monkeypatch.setattr(editing, 'chat', lambda *a, **k: backend.Reply(
        {'edits': [{'path': 'a.py', 'search': 'x = 1', 'replace': 'x = 2'}], 'summary': 'change'}, 0, 0, 0))

    def denied(*a, **kw):
        raise PermissionError('audit: check executable cannot be launched')
    monkeypatch.setattr(editing.subprocess, 'run', denied)
    try:
        editing.edit(['a.py'], 'change x', [['blocked-check']], model=backend.Model('audit'), roots=[tmp_path])
    except PermissionError:
        pass
    assert file.read_text() == 'x = 1\n', 'Gate-launch exception leaves the model edit on disk'


def test_endpoints_router_names_are_scoped_per_file():
    code = {'a.py': 'router=APIRouter(dependencies=[Depends(auth)])\n@router.get("/private")\ndef private(): pass',
            'b.py': 'router=APIRouter()\n@router.get("/open")\ndef open_(): pass'}
    lines = [Line(path, no, row) for path, text in code.items() for no, row in enumerate(text.splitlines(), 1)]
    result = extract.run('endpoints!auth', lines)
    assert {f.key for f in result.facts} == {'GET /open open_'}


def test_deterministic_digest_marks_variant_loss_partial():
    lines = [Line('log.txt', n+1, f'ERROR worker-{n} failed retries={n}') for n in range(10)]
    groups = logs.group_events(lines)
    output, status = tasks.digest_receipt(lines, groups, 300, 25)
    assert status == 'partial' or all(f'worker-{n}' in output for n in range(10)), 'Distinct worker ids omitted while reporting complete'


def test_deterministic_digest_marks_long_trace_partial():
    text = ['ERROR first'] + ['  frame'] * 45 + ['  important=42']
    lines = [Line('log.txt', i, row) for i, row in enumerate(text, 1)]
    output, status = tasks.digest_receipt(lines, logs.group_events(lines), 200, 25)
    assert status == 'partial', 'Continuation cap discards trace content but reports complete'


def test_deterministic_digest_marks_truncated_line_partial():
    lines = [Line('log.txt', 1, 'ERROR truncated [line truncated]', True)]
    _, status = tasks.digest_receipt(lines, logs.group_events(lines), 5001, 25)
    assert status == 'partial'


def test_watchdog_does_not_kill_a_loading_model(monkeypatch):
    state = {'pid': 12345, 'port': 1, 'last_used': 0}
    stopped = []
    monkeypatch.setattr(llamacpp, '_read_state', lambda: state)
    monkeypatch.setattr(llamacpp, '_write_state', lambda *a: None)
    monkeypatch.setattr(llamacpp, 'probe', lambda *a: 'loading')
    monkeypatch.setattr(llamacpp, '_busy', lambda *a: False)
    monkeypatch.setattr(llamacpp, '_stop', lambda *a: stopped.append(True))
    monkeypatch.setattr(llamacpp.time, 'time', lambda: 61)
    llamacpp.idle_check(60)
    assert not stopped, 'Model loading may take 600s, but idle timeout kills it after 60s'


def test_replacement_model_does_not_kill_an_active_request(monkeypatch):
    state = {'pid': 12345, 'port': 1, 'last_used': 0, 'key': 'old-model'}
    stopped = []
    monkeypatch.setattr(llamacpp, '_read_state', lambda: state)
    monkeypatch.setattr(llamacpp, '_write_state', lambda *a: None)
    monkeypatch.setattr(llamacpp, '_stop', lambda *a: stopped.append(True))
    monkeypatch.setattr(llamacpp, '_spawn', lambda *a: 67890)
    monkeypatch.setattr(llamacpp, '_free_ollama', lambda *a: None)
    monkeypatch.setattr(llamacpp, '_start_watchdog', lambda *a: None)
    monkeypatch.setattr(llamacpp, '_free_port', lambda: 2)
    monkeypatch.setattr(llamacpp, 'probe', lambda *a: 'ok')
    monkeypatch.setattr(llamacpp, '_busy', lambda *a: True)
    with pytest.raises(backend.BackendError, match='another request'):
        llamacpp.ensure(backend.Model('new-model', engine='llamacpp', gguf='fake.gguf'), {})
    assert not stopped, 'Model switch ignores the active slot of another request'


def test_gather_enforces_actual_input_bytes(tmp_path, monkeypatch):
    (tmp_path / 'a.js').write_text('x' * 10000)
    (tmp_path / 'b.js').write_text('y' * 10000)
    monkeypatch.setattr(tasks, 'MAX_TOTAL_BYTES', 9000)
    from readscout.text import AccessError
    with pytest.raises(AccessError):
        tasks.gather(['a.js', 'b.js'], [tmp_path])


def test_malformed_metrics_do_not_break_dashboard():
    paths.metrics_file().write_text('[]\n' + json.dumps({'time': 99999999999, 'tool': 'ask', 'verified': 1})+'\n')
    assert stats.summary()['calls'] == 1


def test_iso_timestamp_is_removed_from_grouping_key():
    assert logs._strip_time('2026-10-13T14:06:14.313Z ERROR example') == 'ERROR example'


def test_string_literal_is_not_an_environment_read():
    lines = [Line('a.js', 1, 'const example="process.env.FAKE";'), Line('a.js', 2, 'const v=process.env.REAL;')]
    assert {f.key for f in extract.run('env', lines).facts} == {'REAL'}


@pytest.mark.parametrize('text', [
    'const example="process.env.FAKE"; const v=process.env.REAL;',
    "const example='process.env.FAKE'; const v=process.env.REAL;",
    'const example=`process.env.FAKE`; const v=process.env.REAL;',
    'const example=/process.env.FAKE/; const v=process.env.REAL;',
    'const v=process.env.REAL; // process.env.FAKE',
    '/* process.env.FAKE */ const v=process.env.REAL;',
    'const x="Joi.object({FAKE: Joi.string()})"; const v=process.env.REAL;',
    'const alias=process.env; const x="alias.FAKE"; const v=alias.REAL;',
])
def test_environment_lexical_filter_preserves_real_expressions(text):
    res = extract.run('env', [Line('a.js', 1, text)])
    assert {f.key for f in res.facts} == {'REAL'}
    assert not res.unrecognized


def test_python_strings_and_inline_comments_are_not_reads():
    text = '''import os
example = """os.getenv('FAKE')
os.environ['FAKE2']"""
value = os.environ['REAL'] # os.getenv('FAKE3')
'''
    lines = [Line('a.py', n, row) for n, row in enumerate(text.splitlines(), 1)]
    res = extract.run('env', lines)
    assert {f.key for f in res.facts} == {'REAL'}
    assert res.facts[0].line == 4


def test_template_interpolation_is_read_as_code():
    # Was "reported as unsupported" until the benchmark of 18 October: 4 of 34 variables were then missing.
    res = extract.run('env', [Line('a.js', 1, 'const s=`value ${process.env.REAL}`;')])
    assert {f.key for f in res.facts} == {'REAL'} and not res.unrecognized


def test_python_formatted_string_text_is_not_an_invented_read():
    # Interpolated expressions: see test_receipt_regressions.py (their handling depends on the Python version).
    text = 'import os\nexample = f"os.getenv(\'FAKE\') {42}"\nvalue = os.getenv("REAL")'
    lines = [Line('a.py', n, row) for n, row in enumerate(text.splitlines(), 1)]
    assert {f.key for f in extract.run('env', lines).facts} == {'REAL'}


def test_schema_quoted_keys_still_work_with_string_filter():
    res = extract.run('env', [Line('a.js', 1, 'const schema=Joi.object({"REAL": Joi.string()});')])
    assert {f.key for f in res.facts} == {'REAL'}


def test_unexpected_gate_exception_also_restores(tmp_path, monkeypatch):
    p = tmp_path / 'a.py'
    p.write_bytes(b'x = 1\r\n')
    monkeypatch.setattr(editing, 'chat', lambda *a, **k: backend.Reply(
        {'edits': [{'path': 'a.py', 'search': 'x = 1', 'replace': 'x = 2'}]}, 0, 0, 0))
    def crash(*a):
        raise RuntimeError('unexpected gate failure')
    monkeypatch.setattr(editing, '_run_gate', crash)
    with pytest.raises(RuntimeError, match='unexpected gate'):
        editing.edit(['a.py'], 'change x', [['check']], model=backend.Model('audit'), roots=[tmp_path])
    assert p.read_bytes() == b'x = 1\r\n'


def test_long_trace_is_preserved_for_prefilter():
    lines = [Line('a.log', i, row) for i, row in enumerate(['ERROR first'] + ['  frame'] * 100 + ['  critical=42'], 1)]
    assert len(logs.units(lines)[0]) == 102
    assert len(logs.prefilter(lines, keep_head=0, keep_tail=0, context=0)) == 102


@pytest.mark.parametrize('text', [
    '2026-10-13T14:06:14.313Z ERROR example',
    '[2026-10-13T14:06:14+02:00] ERROR example',
    '2026-10-13 14:06:14,313 ERROR example',
    '[14:06:14] ERROR example',
    '2026-10-13 ERROR example',
])
def test_timestamp_formats_normalize_to_same_event(text):
    assert logs._strip_time(text) == 'ERROR example'


def test_input_bytes_are_measured_before_redaction_and_include_utf8(tmp_path, monkeypatch):
    from readscout.text import AccessError, input_bytes
    raw = ('é' * 100 + '\r\n').encode('utf-8')
    (tmp_path / 'a.js').write_bytes(raw)
    assert input_bytes(load_lines('a.js', [tmp_path])) == len(raw)
    monkeypatch.setattr(tasks, 'MAX_TOTAL_BYTES', 150)
    with pytest.raises(AccessError, match='byte budget'):
        tasks.gather(['a.js'], [tmp_path])


def test_directory_traversal_cannot_skip_a_total_budget_error(tmp_path, monkeypatch):
    from readscout.text import AccessError
    (tmp_path / 'a.js').write_text('x' * 100)
    (tmp_path / 'b.js').write_text('y' * 100)
    monkeypatch.setattr(tasks, 'MAX_TOTAL_BYTES', 150)
    with pytest.raises(AccessError, match='byte budget'):
        tasks.gather([str(tmp_path)], [tmp_path])


@pytest.mark.parametrize('bad', [[], None, 42, {'time': 'oops'}, {'time': 99999999999, 'model': []},
                                      {'time': 99999999999, 'seconds': 'oops'}, {'time': float('nan')},
                                      {'time': 99999999999, 'seconds': 10**400}])
def test_damaged_metric_rows_do_not_prevent_valid_rows(bad):
    paths.metrics_file().write_text(json.dumps(bad) + '\n' + json.dumps({'time': 99999999999, 'tool': 'ask'}) + '\n')
    assert stats.summary()['calls'] == 1


def test_failed_slot_probe_prevents_destructive_idle_check(monkeypatch):
    def unavailable(*a, **k):
        raise backend.BackendError('slots endpoint unavailable')
    monkeypatch.setattr(llamacpp, '_request', unavailable)
    assert llamacpp._busy('http://127.0.0.1:1') is True


def test_session_exit_does_not_stop_another_sessions_request(monkeypatch):
    state = {'pid': 12345, 'port': 1}
    stopped = []
    monkeypatch.setattr(llamacpp, '_read_state', lambda: state)
    monkeypatch.setattr(llamacpp, 'probe', lambda *a: 'ok')
    monkeypatch.setattr(llamacpp, '_busy', lambda *a: True)
    monkeypatch.setattr(llamacpp, '_stop', lambda *a: stopped.append(True))
    monkeypatch.setattr(llamacpp, '_OWN', {'pid': 12345})
    llamacpp.stop_owned()
    assert not stopped and not llamacpp._OWN
