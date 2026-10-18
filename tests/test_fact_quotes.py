"""A long source line is quoted around the extracted fact, not from its start.

Full pilot v2 (18 October): three variables of controllers/api.js sit past character 120 of their line. The agent needed a
short verbatim quote of each, found none in the receipt and searched the file again: one more request.
"""
import re

from readscout import extract, tasks
from readscout.text import Line

OAUTH = ("const oauth = new OAuth('https://www.tumblr.com/oauth/request_token', 'https://www.tumblr.com/oauth/access_token', "
         "process.env.TUMBLR_KEY, process.env.TUMBLR_SECRET, '1.0A', null, 'HMAC-SHA1');")
URL = "  const url = `https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=MSFT&outputsize=compact&apikey=${process.env.ALPHA_VANTAGE_KEY}`;"


def receipt(*rows, kind='env', path='api.js'):
    res = extract.run(kind, [Line(path, n, row) for n, row in enumerate(rows, 1)])
    return tasks.extract_receipt(res, 1000, 40, f'local_ask extract={kind}')


def quote_of(text, key):
    row = next(r for r in text.split('\n') if f'| {key}' in r)
    return re.search(r'« (.*) »', row).group(1), row


def test_a_fact_past_the_quote_limit_is_quoted_around_its_own_name():
    text = receipt(OAUTH)
    for key in ('TUMBLR_KEY', 'TUMBLR_SECRET'):
        q, row = quote_of(text, key)
        assert f'process.env.{key}' in q and len(q) <= tasks.MAX_FACT_QUOTE
        assert q in OAUTH.strip()                           # a contiguous part of the line, unchanged
        assert f'fragment of the {len(OAUTH)}-character line' in row


def test_a_fragment_starts_at_a_word_boundary_when_one_is_close():
    for key in ('TUMBLR_KEY', 'TUMBLR_SECRET'):
        q, _ = quote_of(receipt(OAUTH), key)
        at = OAUTH.index(q)
        assert at == 0 or not OAUTH[at - 1].isalnum(), q[:20]
        assert f'process.env.{key}' in q


def test_an_interpolated_read_near_the_end_of_a_long_line():
    q, _ = quote_of(receipt(URL), 'ALPHA_VANTAGE_KEY')
    assert 'process.env.ALPHA_VANTAGE_KEY' in q and len(q) <= tasks.MAX_FACT_QUOTE and q in URL.strip()


def test_a_short_line_is_still_quoted_whole():
    q, row = quote_of(receipt('const k = process.env.SHORT_ONE;'), 'SHORT_ONE')
    assert q == 'const k = process.env.SHORT_ONE;' and 'fragment' not in row


def test_a_long_line_whose_fact_is_near_the_start_keeps_the_start():
    line = 'const v = process.env.EARLY; // ' + 'x' * 200
    q, _ = quote_of(receipt(line), 'EARLY')
    assert q.startswith('const v = process.env.EARLY;') and len(q) <= tasks.MAX_FACT_QUOTE


def test_an_endpoint_on_a_long_decorator_line_is_quoted_around_its_path():
    deco = '@router.get("/' + 'very-long-segment/' * 8 + 'target", response_model=SomeVeryLongResponseModelName, status_code=200)'
    text = receipt(deco, 'def target(): ...', kind='endpoints', path='r.py')
    row = next(r for r in text.split('\n') if r.startswith('- r.py:'))
    q = re.search(r'« (.*) »', row).group(1)
    assert 'target' in q and len(q) <= tasks.MAX_FACT_QUOTE and q in deco
