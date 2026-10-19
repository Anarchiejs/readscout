"""Regressions found in lot 5 (19 October 2026, unseen logs): three common log formats sent the digest to the model.

The model path takes 9 to 31 s, so the agent polled the unfinished call (one request each) and then re-read the log to
check a partial receipt. Each case below must be answered deterministically, quickly, with every error-level line cited:
J  JSON lines with a hex trace id per line (every line became its own event shape) and the level field past column 48,
A  an access log whose 5xx responses carry no error wording (they were not events at all),
M  a Maven build with more distinct warnings than the deterministic limit (the errors were few).
"""
import json
import time

import pytest

from readscout import logs, tasks
from readscout.text import Line


def lines_of(path, rows):
    return [Line(path, n, row) for n, row in enumerate(rows, 1)]


def jline(i, level, svc, msg, **extra):
    return json.dumps({'ts': f'2026-10-14T09:{i // 60 % 60:02d}:{i % 60:02d}.{i % 1000:03d}Z', 'level': level, 'svc': svc,
                       'trace': f'{(i * 2654435761) % 16**8:08x}', 'msg': msg, **extra}, separators=(',', ':'))


JSON_ROWS = []
for i in range(3000):
    if i == 1500:
        JSON_ROWS.append(jline(i, 'ERROR', 'ledger-client', 'connection reset by peer calling ledger.internal:7443', attempt=3))
    elif i in (1503, 1520, 1544):
        JSON_ROWS.append(jline(i, 'ERROR', 'checkout', f'order {90000 + i} failed: ledger unavailable', order=90000 + i))
    elif i % 7 == 0:
        JSON_ROWS.append(jline(i, 'WARN', 'catalog', f'slow query {300 + i % 900}ms on products'))
    elif i % 11 == 0:
        JSON_ROWS.append(jline(i, 'INFO', 'ledger-client', f'retry succeeded after timeout ({i % 5} attempts)'))
    else:
        JSON_ROWS.append(jline(i, 'INFO', 'pricing', 'order accepted', order=80000 + i, ms=i % 900))

ACCESS_ROWS = []
for i in range(3000):
    status = 502 if i in (1200, 1201, 2500) else (404 if i % 97 == 0 else 200)
    ACCESS_ROWS.append(f'10.0.{i % 5}.{i % 250} - - [14/Oct/2026:09:{i // 60 % 60:02d}:{i % 60:02d} +0000] '
                       f'"{"POST" if i % 3 else "GET"} /api/items/{i} HTTP/1.1" {status} {1000 + i} "-" "Mozilla/5.0" rt=0.{i % 900:03d}')
    if i == 1199:
        ACCESS_ROWS.append('2026/10/14 09:20:00 [error] 1234#0: *9981 upstream timed out (110: Connection timed out) while reading response header')

MAVEN_ROWS = ['[INFO] Scanning for projects...']
for k in range(30):
    MAVEN_ROWS.append(f'[WARNING] Tests run with deprecated API Api{k}.call in com.acme.shop.m{k}.ClientTest')
    MAVEN_ROWS += [f'[INFO] Tests run: 4, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.{k:03d} s - in com.acme.shop.m{k}.ClientTest'] * 3
MAVEN_ROWS += ['[ERROR] Tests run: 5, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.931 s <<< FAILURE! - in com.acme.shop.invoice.ServiceTest',
               '[ERROR] refundsPartialAmount  Time elapsed: 0.044 s  <<< FAILURE!',
               'org.opentest4j.AssertionFailedError: expected: <12.50> but was: <12.00>',
               '\tat com.acme.shop.invoice.ServiceTest.refundsPartialAmount(ServiceTest.java:88)']
MAVEN_ROWS += ['[INFO] Downloading from central: https://repo.maven.apache.org/maven2/org/acme/lib/1.0/lib.jar'] * 50
MAVEN_ROWS += ['[ERROR] Tests run: 3, Failures: 0, Errors: 1, Skipped: 0, Time elapsed: 1.2 s <<< ERROR! - in com.acme.shop.cart.RepositoryTest',
               '[INFO] BUILD FAILURE',
               '[ERROR] Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:3.2.2:test (default-test) on project shop-service']


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    for name, rows in (('checkout.log', JSON_ROWS), ('access.log', ACCESS_ROWS), ('build.log', MAVEN_ROWS)):
        (tmp_path / name).write_text('\n'.join(rows) + '\n', encoding='utf-8')
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    monkeypatch.setattr(tasks, 'model_for', lambda *a: pytest.fail('a common log format must not start a model'))
    return tmp_path


def error_lines(rows, test):
    return [n for n, row in enumerate(rows, 1) if test(row)]


# ---------------------------------------------------------------- J: JSON lines

def test_a_hex_id_does_not_make_each_line_its_own_event_shape():
    a = '{"level":"INFO","trace":"4f30036a","msg":"retry succeeded after timeout"}'
    b = '{"level":"INFO","trace":"ecc8d678","msg":"retry succeeded after timeout"}'
    assert logs.shape(a) == logs.shape(b)
    assert logs.shape('commit 3f9a2c1d deployed') == logs.shape('commit 9b0e77aa deployed')
    assert logs.shape('user alice logged in') != logs.shape('user bob logged in')      # ordinary words stay distinct


def test_the_level_of_a_json_line_is_read_from_its_field_wherever_it_is():
    assert logs.is_error(jline(5, 'ERROR', 'checkout', 'order 1 failed'))
    assert not logs.is_error(jline(5, 'INFO', 'ledger-client', 'retry succeeded after error'))
    assert not logs.is_error(jline(5, 'WARN', 'catalog', 'exception swallowed'))
    assert logs.is_error('{"time":"t","severity":"CRITICAL","message":"disk full"}')


@pytest.mark.parametrize('focus', ['', 'Which orders failed? One finding per failed order, quoting its error line.',
                                   'What went wrong? Identify the root cause.'])
def test_a_json_log_is_digested_without_a_model(logdir, focus):
    text = tasks.digest('checkout.log', focus)
    assert 'deterministic, no model' in text and 'status: complete' in text
    for n in error_lines(JSON_ROWS, lambda r: '"level":"ERROR"' in r):
        assert f'checkout.log:{n} ' in text
    assert '2 at error level' in text                 # the connection reset, and the three failed orders as one shape


# ---------------------------------------------------------------- A: access logs

def test_a_5xx_access_line_is_an_error_level_event_and_a_4xx_is_not():
    assert logs.is_error(ACCESS_ROWS[1200]) and logs.is_event(ACCESS_ROWS[1200])
    assert not logs.is_error(ACCESS_ROWS[97]) and logs.is_event(ACCESS_ROWS[97])
    assert not logs.is_event(ACCESS_ROWS[1])
    assert not logs.is_error('10.0.0.1 - - [14/Oct/2026:09:00:00 +0000] "GET /api/items/502 HTTP/1.1" 200 502 "-" "x" rt=0.1')


def test_each_5xx_request_is_cited_on_its_own_line(logdir):
    text = tasks.digest('access.log', 'Which requests received a 5xx status in the access log? One finding per request line.')
    assert 'deterministic, no model' in text and 'status: complete' in text
    for n in error_lines(ACCESS_ROWS, lambda r: '" 502 ' in r):
        assert f'access.log:{n} ' in text              # repeats of one shape are still distinct requests: none is folded away
    assert 'upstream timed out' in text


# ---------------------------------------------------------------- M: many distinct warnings, few errors

def test_a_build_with_many_warnings_lists_every_error_without_a_model(logdir):
    text = tasks.digest('build.log', 'Which test classes reported a failure or error?')
    assert 'deterministic, no model' in text and 'status: complete' in text
    for n in error_lines(MAVEN_ROWS, lambda r: r.startswith('[ERROR]')):
        assert f'build.log:{n} ' in text
    assert 'AssertionFailedError' in text
    assert 'not error-level' in text                  # the warnings are counted, not silently dropped
    assert len(text) < 6000


def test_digests_are_fast_enough_that_the_agent_never_polls(logdir):
    for name in ('checkout.log', 'access.log', 'build.log'):
        start = time.perf_counter()
        tasks.digest(name, 'what went wrong?')
        assert time.perf_counter() - start < 3
