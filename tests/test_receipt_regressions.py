"""Regressions found in the paired benchmark of 18 October 2026: each one cost the agent an extra request.

D1 template interpolations hid real environment reads, D2 router prefixes were missing from endpoint paths,
D3 every receipt was sent twice (text and structured copy), D4 a focused log digest started a model and missed errors.
"""
import asyncio
import sys

import pytest

from readscout import extract, logs, server, tasks
from readscout.backend import Model, Reply
from readscout.text import Line


def lines_of(path, text):
    return [Line(path, n, row) for n, row in enumerate(text.split('\n'), 1)]


# ---------------------------------------------------------------- D3: one copy of the receipt

def test_tools_return_text_only_without_a_structured_copy():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name: t.outputSchema for t in tools} == {'local_ask': None, 'local_digest': None, 'local_edit': None}


def test_a_tool_call_carries_the_receipt_once(monkeypatch):
    monkeypatch.setattr(tasks, 'digest', lambda *a: 'RECEIPT')
    result = asyncio.run(server.mcp.call_tool('local_digest', {'path': 'build.log'}))
    content = result[0] if isinstance(result, tuple) else result
    structured = result[1] if isinstance(result, tuple) else None
    assert [c.text for c in content] == ['RECEIPT'] and not structured


# ---------------------------------------------------------------- D1: template interpolations are code

@pytest.mark.parametrize('text, names', [
    ('const h = { authorization: `Bearer ${process.env.FOURSQUARE_APIKEY}` };', {'FOURSQUARE_APIKEY'}),
    ('const a = Buffer.from(`${process.env.PAYPAL_ID}:${process.env.PAYPAL_SECRET}`);', {'PAYPAL_ID', 'PAYPAL_SECRET'}),
    ('const u = `https://x/q?apikey=${process.env.ALPHA_VANTAGE_KEY}&s=1`;', {'ALPHA_VANTAGE_KEY'}),
    ('const n = `${ok ? `in ${process.env.NESTED}` : "no"}`;', {'NESTED'}),
    ('const b = `${pick("}") + process.env.AFTER_BRACE}`;', {'AFTER_BRACE'}),
    ('const o = `${({ k: process.env.IN_OBJECT }).k}`;', {'IN_OBJECT'}),
    ('const t = `process.env.FAKE ${process.env.REAL}`;', {'REAL'}),          # the literal part stays text
    ('const c = `${process.env.REAL /* process.env.FAKE */}`;', {'REAL'}),
])
def test_env_reads_inside_template_interpolations_are_found(text, names):
    res = extract.run('env', [Line('a.js', 1, text)])
    assert {f.key for f in res.facts} == names
    assert not res.unrecognized


def test_a_template_without_environment_access_is_not_reported():
    res = extract.run('env', lines_of('a.js', 'const m = `Hello ${user.name}, ${count} items`;\nconst v = process.env.REAL;'))
    assert {f.key for f in res.facts} == {'REAL'} and not res.unrecognized


def test_interpolations_on_later_lines_of_a_multiline_template_keep_their_line():
    text = 'const q = `\n  select *\n  from ${process.env.TABLE_NAME}\n`;\nconst v = process.env.AFTER;'
    res = extract.run('env', lines_of('a.js', text))
    assert {(f.key, f.line) for f in res.facts} == {('TABLE_NAME', 3), ('AFTER', 5)}


def test_an_unterminated_template_does_not_hide_the_rest_of_the_file_silently():
    res = extract.run('env', lines_of('a.js', 'const v = process.env.BEFORE;\nconst s = `open ${process.env.INSIDE'))
    assert {'BEFORE', 'INSIDE'} <= {f.key for f in res.facts}


def test_the_receipt_of_a_template_heavy_file_is_complete(tmp_path):
    code = '\n'.join([f'log(`step {i}: ${{state}}`);' for i in range(40)] + ['const k = `${process.env.KEY}`;'])
    res = extract.run('env', lines_of('a.js', code))
    text = tasks.extract_receipt(res, 1000, 40, 'local_ask extract=env')
    assert 'status: complete' in text and 'Not recognized' not in text and '| KEY |' in text


@pytest.mark.skipif(sys.version_info < (3, 12), reason='formatted string expressions are separate tokens from Python 3.12')
def test_python_formatted_string_expressions_are_code():
    text = 'import os\na = f"value {os.getenv(\'INNER\')}"\nb = f"os.getenv(\'FAKE\') {42}"\nc = os.getenv("REAL")'
    res = extract.run('env', lines_of('a.py', text))
    assert {f.key for f in res.facts} == {'INNER', 'REAL'}
    assert not res.unrecognized


@pytest.mark.skipif(sys.version_info >= (3, 12), reason='before Python 3.12 a formatted string is one opaque token')
def test_python_formatted_strings_are_reported_only_when_they_mention_the_environment():
    text = 'import os\na = f"value {os.getenv(\'INNER\')}"\nb = f"hello {name}"\nc = os.getenv("REAL")'
    res = extract.run('env', lines_of('a.py', text))
    assert {f.key for f in res.facts} == {'REAL'}
    assert [n for _, n, _ in res.unrecognized] == [2]


# ---------------------------------------------------------------- D2: router prefixes in endpoint paths

PREFIXED = '''from fastapi import APIRouter, Depends
router = APIRouter(prefix="/items", tags=["items"])
admin = APIRouter()
other = APIRouter(prefix=settings.API_PREFIX)

@router.get("/")
def read_items(): ...

@router.get("/{id}")
def read_item(id: int): ...

@admin.delete("/purge")
def purge(): ...

@other.get("/x")
def computed(): ...

router.include_router(admin, prefix="/admin")
'''


def test_endpoint_paths_include_the_router_prefix_declared_in_the_file():
    res = extract.run('endpoints', lines_of('items.py', PREFIXED))
    by = {g[0].key: g[0] for g in res.groups()}
    assert 'GET /items/ read_items' in by and 'GET /items/{id} read_item' in by
    # this file applies two prefixes ("/items" and "/items/admin"): each row says which one, and from which declared path
    assert 'declared path "/" under router prefix "/items"' in by['GET /items/ read_items'].detail


def test_a_single_prefix_per_file_is_stated_once_not_on_every_row():
    lines = lines_of('items.py', 'router = APIRouter(prefix="/items")\n@router.get("/")\ndef a(): ...\n@router.get("/{id}")\ndef b(): ...')
    res = extract.run('endpoints', lines)
    assert all('declared path' not in f.detail for f in res.facts)
    assert res.coverage == ['Router prefixes applied: items.py "/items".']


def test_include_router_prefixes_in_the_same_file_are_combined():
    res = extract.run('endpoints', lines_of('items.py', PREFIXED))
    assert 'DELETE /items/admin/purge purge' in {g[0].key for g in res.groups()}


def test_a_computed_router_prefix_is_reported_not_guessed():
    res = extract.run('endpoints', lines_of('items.py', PREFIXED))
    assert 'GET /x computed' in {g[0].key for g in res.groups()}
    assert any(n == 4 and 'prefix' in why for _, n, why in res.unrecognized)


def test_a_prefix_added_to_a_router_from_another_file_is_reported():
    res = extract.run('endpoints', lines_of('main.py', 'from app import items\napp.include_router(items.router, prefix="/v1")'))
    assert any('prefix' in why and 'not resolved' in why for _, _, why in res.unrecognized)


def test_the_scope_says_which_prefixes_are_resolved():
    assert 'prefix' in extract.run('endpoints', lines_of('a.py', '@r.get("/x")\ndef x(): ...')).scope


# ---------------------------------------------------------------- D4: logs read deterministically when the focus asks for errors

INCIDENT = ['2026-10-13T14:00:00.606Z INFO api request id=1 handled in 487ms status=200'] * 30 + [
    '2026-10-13T14:06:13.000Z WARN db-pool slow acquire 900ms',
    '2026-10-13T14:06:14.313Z ERROR db-pool connection to postgres://db:5432/app failed: FATAL: remaining connection slots are reserved',
    '2026-10-13T14:06:14.313Z ERROR worker job sync-3 aborted: Error: Pool exhausted after 30000ms',
    '    at Pool.acquire (node_modules/pg-pool/index.js:210:11)',
    '    at async syncJob (lib/sync.js:88:19)',
] + ['2026-10-13T14:10:00.000Z INFO api request id=2 handled in 300ms status=200'] * 30 + [
    '2026-10-13T15:00:00.000Z ERROR api POST /api/sync 500 Internal Server Error (upstream worker failed)',
    '2026-10-13T15:00:01.000Z INFO scheduler shutting down after 1 failed job',
]


@pytest.fixture
def incident(tmp_path, monkeypatch):
    (tmp_path / 'service.log').write_text('\n'.join(INCIDENT) + '\n')
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    return tmp_path


@pytest.mark.parametrize('focus', [
    'Identify the earliest root-cause error first, followed by its consequences. Ignore noise.',
    'what went wrong?',
    'pourquoi le job a échoué',
])
def test_an_error_focused_digest_of_a_simple_log_needs_no_model(incident, monkeypatch, focus):
    monkeypatch.setattr(tasks, 'model_for', lambda *a: pytest.fail('a simple log must not start a model'))
    text = tasks.digest('service.log', focus)
    assert 'deterministic, no model' in text and 'status: complete' in text
    for line in (32, 33, 66):
        assert f'service.log:{line}' in text                         # every error, including the late consequence
    assert 'scheduler shutting down' in text                          # the final outcome is shown
    assert '3 at error level' in text


def test_a_short_error_trace_is_shown_whole(incident):
    text = tasks.digest('service.log', 'what went wrong?')
    assert 'service.log:34' in text and 'Pool.acquire' in text           # the middle of a short trace is no longer hidden


def test_a_partial_digest_names_what_it_did_not_show():
    rows = ['2026-10-13T14:00:00Z INFO start'] + [f'2026-10-13T14:00:{i:02d}Z ERROR worker failed host=h{i}' for i in range(1, 10)]
    lines = [Line('w.log', n, row) for n, row in enumerate(rows, 1)]
    text, status = tasks.digest_receipt(lines, logs.group_events(lines), 500, 25)
    assert status == 'partial'
    assert 'distinct values of the event(s) at line(s) 2' in text and 'read the source for the full event' not in text


def test_a_focus_on_something_other_than_errors_still_uses_the_model(incident, monkeypatch):
    monkeypatch.setattr(tasks, 'model_for', lambda *a: Model('m'))
    calls = []
    monkeypatch.setattr(tasks, 'chat', lambda *a, **k: calls.append(1) or Reply({'findings': []}, 1, 1, 0.1))
    tasks.digest('service.log', 'which requests were the slowest?')
    assert calls


def test_error_level_is_read_from_the_level_field_not_from_words_in_the_message():
    assert logs.is_error('2026-10-13T14:06:14Z ERROR worker aborted')
    assert logs.is_error('[2026-10-13 14:06:14] CRITICAL disk full')
    assert not logs.is_error('2026-10-13T14:06:14Z INFO retry after timeout succeeded, no error')
    assert not logs.is_error('2026-10-13T14:06:14Z WARN connection failed, retrying')
    assert logs.is_error('Traceback (most recent call last):')                 # no level field: wording decides


def test_a_model_digest_that_skips_an_error_level_event_says_so(tmp_path, monkeypatch):
    rows = [f'2026-10-13T14:00:{i % 60:02d}Z ERROR kind{chr(97 + i)} failed' for i in range(15)]
    (tmp_path / 'many.log').write_text('\n'.join(rows) + '\n')
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    monkeypatch.setattr(tasks, 'model_for', lambda *a: Model('m'))
    found = {'findings': [{'file': 'many.log', 'line': 1, 'quote': rows[0], 'answer': 'ROOT CAUSE: kinda failed'},
                          {'file': 'many.log', 'line': 15, 'quote': rows[14], 'answer': 'FINAL: kindo failed'}]}
    monkeypatch.setattr(tasks, 'chat', lambda *a, **k: Reply(found, 1, 1, 0.1))
    text = tasks.digest('many.log')
    assert 'status: partial' in text
    assert '13 error-level event group(s) not cited' in text and 'many.log:2' in text
