"""Lot A: exact verified quotes in the receipt, the file named by the model, and secret references kept readable."""
from readscout import tasks
from readscout.backend import Model
from readscout.text import Line, exact_text, locate, redact


def L(*texts, path='a.py'):
    return [Line(path, i, t) for i, t in enumerate(texts, 1)]


def test_exact_text_is_verbatim_for_a_substring():
    lines = L('const s = "a  b";  // two spaces')
    assert exact_text('"a  b"', lines, ('a.py', 1, 1)) == ('"a  b"', 'exact')


def test_exact_text_comes_from_the_source_when_whitespace_differs():
    lines = L('def f():', '    return   compute(x,  y)')
    text, kind = exact_text('return compute(x, y)', lines, ('a.py', 2, 2))
    assert (text, kind) == ('return   compute(x,  y)', 'normalized')


def test_exact_text_of_a_multiline_quote_is_the_source_lines():
    lines = L('app.get("/a",', '  auth,', '  handler)')
    text, kind = exact_text('app.get("/a", auth, handler)', lines, ('a.py', 1, 3))
    assert text == 'app.get("/a", auth, handler)' and kind == 'normalized'


def test_locate_uses_the_named_file_among_identical_quotes():
    lines = L('router.get("/x", handler)', path='a.py') + L('router.get("/x", handler)', path='b.py')
    assert locate('router.get("/x", handler)', lines, file='b.py') == ('b.py', 1, 1)
    assert locate('router.get("/x", handler)', lines, file='src/b.py') == ('b.py', 1, 1)
    # an unknown file name never rejects a quote that is really there
    assert locate('router.get("/x", handler)', lines, file='nope.py') == ('a.py', 1, 1)
    assert locate('router.get("/y", handler)', lines, file='b.py') is None


def test_receipt_never_truncates_a_verified_quote_with_an_ellipsis():
    out = tasks.Outcome()
    quote = 'x = "' + 'a' * 100 + '"'            # 106 characters: the old 90 character cut would have shown "..."
    out.verified.append(('a.py', 1, 1, 'sets x', quote))
    text = tasks.receipt(out, Model('m'), 10, 5, 'local_ask')
    assert f'« {quote} »' in text and '...' not in text


def test_receipt_long_line_is_a_contiguous_fragment_that_says_so():
    out = tasks.Outcome()
    quote = 'y' * 350
    out.verified.append(('a.py', 1, 1, 'long', quote))
    text = tasks.receipt(out, Model('m'), 10, 5, 'local_ask')
    assert f'« {"y" * tasks.MAX_QUOTE_SHOWN} » (fragment of 350 characters)' in text and '...' not in text


def test_receipt_keeps_the_spaces_of_a_quote():
    out = tasks.Outcome()
    out.verified.append(('a.py', 1, 1, 'two spaces', 'x = "a  b"'))
    assert '« x = "a  b" »' in tasks.receipt(out, Model('m'), 10, 5, 'local_ask')


def test_receipt_counts_quotes_that_needed_whitespace_normalization():
    out = tasks.Outcome()
    out.verified.append(('a.py', 1, 1, 'f', 'return   g(x)'))
    out.normalized.add(('a.py', 1, 1, 'return   g(x)'))
    assert '(1 with whitespace normalized)' in tasks.receipt(out, Model('m'), 10, 5, 'local_ask')


def test_redact_keeps_references_to_a_secret_source():
    for code in ['apiKey: process.env.OPENAI_API_KEY', 'password = os.environ["DB_PASSWORD"]',
                 'token: ${GITHUB_TOKEN_VALUE}', 'client_secret = os.getenv("CLIENT_SECRET")',
                 'apiKey: import.meta.env.VITE_API_KEY', 'authToken: this.settings.authTokenValue']:
        assert redact(code) == code, code


def test_redact_still_masks_real_values():
    for code in ['apiKey: "sk-abc123def456ghi789jkl"', 'password = "Zx9!qL2mPw8Rt"', '"secret": "a1B2c3D4e5F6g7"',
                 'apiKey: "process.env.OPENAI_API_KEY_AAAA"', 'password: hunter2hunter2hunter2']:
        masked = redact(code)
        assert '[REDACTED]' in masked, code
