"""Lots C, D, F, G: logs read deterministically, receipt status, one cap for findings, bounded receipts."""
import pytest

from readscout import editing, logs, tasks
from readscout.backend import Model, Reply
from readscout.text import Line


def L(*texts, path='app.log'):
    return [Line(path, i, t) for i, t in enumerate(texts, 1)]


LOG = L('2024-05-01 10:00:00 INFO boot ok',
        '2024-05-01 10:00:01 ERROR db timeout host=db-1 port=5432',
        '2024-05-01 10:00:02 INFO request 7 done',
        '2024-05-01 10:00:03 ERROR db timeout host=db-2 port=5432',
        '2024-05-01 10:00:04 ERROR db timeout host=db-1 port=5432',
        '2024-05-01 10:00:05 Traceback (most recent call last):',
        '  File "a.py", line 3, in run',
        '    boom()',
        'ValueError: bad input',
        '2024-05-01 10:00:06 INFO shutting down')


def test_repeats_become_one_group_with_first_last_count_and_distinct_values():
    groups = logs.group_events(LOG)
    timeout = next(g for g in groups if 'timeout' in g.shape)
    assert (timeout.first[0].no, timeout.last_start.no, timeout.count) == (2, 5, 3)
    assert 'db-1' in timeout.variants and 'db-2' in timeout.variants     # the numbers were normalized, the values were not lost
    assert len(groups) == 2


def test_a_traceback_is_one_unit_including_its_closing_exception_line():
    unit = next(u for u in logs.units(LOG) if 'Traceback' in u[0].text)
    assert [ln.no for ln in unit] == [6, 7, 8, 9]


def test_prefilter_keeps_first_and_last_occurrence_of_each_group():
    noisy = L(*(['INFO tick'] * 200 + ['ERROR boom id=1'] + ['INFO tick'] * 200 + ['ERROR boom id=2'] + ['INFO tick'] * 200))
    kept = logs.prefilter(noisy, keep_head=3, keep_tail=3)
    assert {ln.no for ln in kept} >= {201, 402} and len(kept) < 30


def test_digest_is_deterministic_for_a_simple_log(tmp_path, monkeypatch):
    (tmp_path / 'build.log').write_text('\n'.join(l.text for l in LOG) + '\n')
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    monkeypatch.setattr(tasks, 'model_for', lambda *a: pytest.fail('a simple log must not start a model'))
    text = tasks.digest('build.log')
    assert 'deterministic, no model' in text and 'status: complete' in text
    assert 'build.log:2 x3, last at line 5' in text and 'distinct values' in text and 'db-2' in text
    assert '\n    build.log:7 ' in text and '\n    build.log:9 « ValueError: bad input »' in text    # the short trace is one unit, shown whole
    assert 'no cause is inferred' in text and 'Final lines:' in text and 'Kept 7 event line(s)' in text


def test_digest_with_a_focus_or_many_events_goes_to_the_model(tmp_path, monkeypatch):
    (tmp_path / 'b.log').write_text('\n'.join(f'ERROR kind{chr(97 + i)} failed' for i in range(15)) + '\n')
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    monkeypatch.setattr(tasks, 'model_for', lambda *a: Model('m'))
    calls = []
    monkeypatch.setattr(tasks, 'chat', lambda *a, **k: calls.append(a[3]) or Reply({'findings': []}, 1, 1, 0.1))
    tasks.digest('b.log')
    tasks.digest('b.log', 'only the first one')
    assert len(calls) == 2


# ---------------------------------------------------------------- receipt status, roles, context, budget

def test_status_is_computed_from_what_the_host_saw():
    out = tasks.Outcome(verified=[('a.py', 1, 1, 'x', 'x = 1')])
    assert 'status: complete' in tasks.receipt(out, Model('m'), 10, 5, 'q')
    out.cut = 1
    assert 'status: partial' in tasks.receipt(out, Model('m'), 10, 5, 'q')
    assert 'status: undetermined' in tasks.receipt(tasks.Outcome(), Model('m'), 10, 5, 'q')


def test_hidden_findings_make_the_receipt_partial():
    out = tasks.Outcome(verified=[('a.py', i, i, f'f{i}', f'line number {i}') for i in range(1, 6)])
    text = tasks.receipt(out, Model('m'), 10, 2, 'q')
    assert 'status: partial' in text and '3 more finding(s) not shown' in text


def test_a_digest_without_a_final_state_says_what_is_missing():
    out = tasks.Outcome(verified=[('a.log', 3, 3, 'ROOT CAUSE: db down', 'ERROR db down')])
    text = tasks.receipt(out, Model('m'), 10, 5, 'local_digest', roles=tasks.DIGEST_ROLES)
    assert 'No finding labelled FINAL' in text and 'No finding labelled ROOT CAUSE' not in text and 'status: partial' in text


def test_the_receipt_is_bounded_and_counts_what_it_leaves_out(monkeypatch):
    monkeypatch.setattr(tasks, 'MAX_RECEIPT_CHARS', 600)
    out = tasks.Outcome(verified=[('a.py', i, i, 'finding ' + 'w ' * 30, 'quote ' + 'q' * 100) for i in range(1, 30)])
    text = tasks.receipt(out, Model('m'), 10, 40, 'q')
    assert len(text) < 1500 and 'more finding(s) not shown' in text


def test_context_lines_come_from_the_file():
    lines = L('before line', 'ERROR the quoted one', 'after line')
    out = tasks.Outcome()
    out.verified.append(('app.log', 2, 2, 'x', 'ERROR the quoted one'))
    out.context[('app.log', 2, 2)] = ('before line', 'after line')
    text = tasks.receipt(out, Model('m'), 10, 5, 'q')
    assert 'above: before line' in text and 'below: after line' in text and lines


# ---------------------------------------------------------------- one cap

def test_max_items_raises_the_generation_cap_and_its_room(monkeypatch):
    assert tasks.cap_for(10) == tasks.MAX_FINDINGS and tasks.cap_for(60) == 60 and tasks.cap_for(500) == tasks.MAX_CAP
    seen = {}

    def chat(model, system, user, schema, max_tokens=2048, **k):
        seen['cap'], seen['max_tokens'] = schema['properties']['findings']['maxItems'], max_tokens
        return Reply({'findings': []}, 1, 1, 0.1)
    monkeypatch.setattr(tasks, 'chat', chat)
    tasks.run_ask(L('a = 1'), 'q', Model('m'), cap=60)
    assert seen == {'cap': 60, 'max_tokens': 60 * tasks.TOKENS_PER_FINDING}
    out = tasks.run_ask(L('a = 1'), 'q', Model('m'))
    assert out.cap == tasks.MAX_FINDINGS and seen['max_tokens'] == 2048 and seen['cap'] == tasks.MAX_FINDINGS


def test_ask_with_extraction_never_starts_a_model(tmp_path, monkeypatch):
    (tmp_path / 'a.js').write_text('const x = process.env.TOKEN_A;\n')
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    monkeypatch.setattr(tasks, 'model_for', lambda *a: pytest.fail('extraction must not start a model'))
    text = tasks.ask(['a.js'], 'which variables?', extraction='env')
    assert 'a.js:1' in text and 'TOKEN_A' in text and 'status: complete' in text
    with pytest.raises(tasks.AccessError, match='Unknown extraction'):
        tasks.ask(['a.js'], 'q', extraction='nope')


def test_editing_module_still_importable():
    assert editing


# ---------------------------------------------------------------- the metrics record the status the receipt printed

def _header_status(text):
    return text.splitlines()[0].rsplit('status: ', 1)[1].rstrip(']')


def test_metrics_status_is_the_one_in_the_receipt_header(tmp_path, monkeypatch):
    rows = []
    monkeypatch.setattr(tasks, 'record', rows.append)
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    (tmp_path / 'a.js').write_text('x = 1;\n')
    text = tasks.ask(['a.js'], 'q', extraction='env')                       # empty extraction: undetermined
    assert rows[-1]['status'] == _header_status(text) == 'undetermined'
    (tmp_path / 'b.log').write_text('INFO fine\n')
    text = tasks.digest('b.log')                                            # no error-like line: undetermined
    assert rows[-1]['status'] == _header_status(text) == 'undetermined'
    (tmp_path / 'c.log').write_text('\n'.join(f'ERROR kind{chr(97 + i)} failed' for i in range(15)) + '\n')
    monkeypatch.setattr(tasks, 'model_for', lambda *a: Model('m'))
    # a model digest that hides findings and has no FINAL label: the receipt says partial, so must the metrics
    findings = [{'file': 'c.log', 'line': i, 'quote': f'ERROR kind{chr(96 + i)} failed', 'answer': f'ROOT CAUSE: {i}'} for i in range(1, 6)]
    monkeypatch.setattr(tasks, 'chat', lambda *a, **k: Reply({'findings': findings}, 1, 1, 0.1))
    text = tasks.digest('c.log', max_items=2)
    assert rows[-1]['status'] == _header_status(text) == 'partial' and 'No finding labelled FINAL' in text and 'more finding(s) not shown' in text
