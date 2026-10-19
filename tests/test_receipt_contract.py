"""Lot 2: a receipt says what the agent may do with it, the tool descriptions carry that contract, and receipts stay small.

Every receipt is replayed in each later request of the session: its size counts many times, so does a needless re-read.
"""
import asyncio
import json

from readscout import extract, logs, server, tasks
from readscout.backend import Model
from readscout.text import Line


def lines_of(path, text):
    return [Line(path, n, row) for n, row in enumerate(text.split('\n'), 1)]


def extracted(kind, **named):
    lines = [ln for path, text in named.items() for ln in lines_of(path, text)]
    res = extract.run(kind, lines)
    return res, tasks.extract_receipt(res, 1000, 40, f'local_ask extract={kind}')


# ---------------------------------------------------------------- what the agent may do with a receipt

def test_a_complete_extraction_says_no_re_read_is_needed():
    _, text = extracted('env', **{'a.js': 'x = process.env.A'})
    assert 'status: complete' in text and 'answer from this receipt' in text and 'no re-read' in text


def test_a_partial_extraction_says_to_check_only_what_it_lists():
    _, text = extracted('env', **{'a.js': 'x = process.env[n]\ny = process.env.B'})
    assert 'status: partial' in text and 'check only the lines under "Not recognized"' in text and 'do not re-read' in text


def test_an_empty_extraction_still_says_to_check_with_a_grep():
    _, text = extracted('env', **{'a.js': 'const x = 1;'})
    assert 'status: undetermined' in text and 'answer from this receipt' not in text


def test_a_complete_model_receipt_keeps_the_interpretation_caveat():
    out = tasks.Outcome(verified=[('a.py', 1, 1, 'x is set', 'x = 1')])
    text = tasks.receipt(out, Model('m'), 10, 5, 'local_ask')
    assert 'status: complete' in text and 'open them only if your conclusion depends on' in text


# ---------------------------------------------------------------- coverage stated against the question

def test_the_endpoint_receipt_states_which_router_prefixes_were_applied():
    _, text = extracted('endpoints', **{'items.py': 'router = APIRouter(prefix="/items")\n@router.get("/")\ndef read(): ...',
                                        'login.py': 'router = APIRouter()\n@router.post("/login")\ndef login(): ...'})
    assert 'Router prefixes applied: items.py "/items"; none in login.py.' in text


def test_the_endpoint_receipt_says_when_no_file_declares_a_prefix():
    _, text = extracted('endpoints', **{'a.py': 'router = APIRouter()\n@router.get("/x")\ndef x(): ...'})
    assert 'No router prefix is declared in these files.' in text


def test_an_unresolved_prefix_is_counted_in_the_coverage_line():
    _, text = extracted('endpoints', **{'a.py': 'router = APIRouter(prefix=PREFIX)\n@router.get("/x")\ndef x(): ...'})
    assert 'status: partial' in text and '1 prefix not resolved' in text


ERRORS_AND_NOISY_WARNINGS = ['2026-10-13T14:00:00Z ERROR db connection failed'] + [
    f'2026-10-13T14:00:{i:02d}Z WARN cache ratio {i}% high host=h{i}' for i in range(1, 10)]


def test_values_omitted_from_warnings_do_not_make_an_error_digest_partial():
    lines = lines_of('w.log', '\n'.join(ERRORS_AND_NOISY_WARNINGS))
    text, status = tasks.digest_receipt(lines, logs.group_events(lines), 500, 25)
    assert status == 'complete'
    assert 'distinct values of the event(s) at line(s) 2' in text and 'not error-level' in text


def test_values_omitted_from_an_error_still_make_the_digest_partial():
    # more repeats than are cited one by one (logs.MAX_OCCURRENCES), so some values stay unseen
    lines = [Line('log.txt', n + 1, f'ERROR worker-{n} failed retries={n}') for n in range(20)]
    assert tasks.digest_receipt(lines, logs.group_events(lines), 300, 25)[1] == 'partial'


def test_a_log_without_errors_keeps_its_warnings_in_the_status():
    lines = lines_of('w.log', '\n'.join(ERRORS_AND_NOISY_WARNINGS[1:]))
    assert tasks.digest_receipt(lines, logs.group_events(lines), 500, 25)[1] == 'partial'


def test_a_complete_digest_says_its_lines_can_be_cited_as_shown():
    lines = lines_of('b.log', 'INFO start\nERROR boom id=1\nINFO done')
    text, status = tasks.digest_receipt(lines, logs.group_events(lines), 50, 25)
    assert status == 'complete' and 'no re-read is needed to cite them' in text


# ---------------------------------------------------------------- the contract is in the tool descriptions

def test_tool_descriptions_carry_the_status_contract():
    tools = {t.name: t.description for t in asyncio.run(server.mcp.list_tools())}
    for name in ('local_ask', 'local_digest'):
        text = tools[name]
        assert 'complete' in text and 'partial' in text and 'no re-read' in text, name
    assert 'security' in tools['local_ask'] and 'one grep' in tools['local_ask']


CATALOG_BUDGET = 3680     # serialized characters of the three tools before lot 2: the contract must not make it grow


def test_the_tool_catalog_stays_within_its_budget():
    tools = asyncio.run(server.mcp.list_tools())
    size = sum(len(json.dumps(t.model_dump(mode='json', exclude_none=True))) for t in tools)
    assert size <= CATALOG_BUDGET, size


# ---------------------------------------------------------------- receipt size

def test_more_locations_in_the_same_file_are_line_numbers_only():
    _, text = extracted('env', **{'controllers/api.js': 'a = process.env.K\nb = process.env.K\nc = process.env.K',
                                  'controllers/b.js': 'd = process.env.K'})
    row = next(r for r in text.split('\n') if '| K' in r)
    assert '(+3 more: 2, 3, controllers/b.js:1)' in row


def test_the_default_detail_of_an_environment_read_is_not_repeated():
    _, text = extracted('env', **{'a.js': 'x = process.env.A'})
    assert '| A | « x = process.env.A »' in text and '| read |' not in text
