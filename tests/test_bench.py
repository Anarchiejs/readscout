"""Benchmark machinery without network or GPU: scoring, archive safety, fingerprints, task generators."""
import io
import tarfile
import tempfile
from pathlib import Path

import pytest

from readscout.bench import corpus, edits, generate, runner


def T(gt, negatives=(), family='routes_filter'):
    return generate.Task('t', family, 'medium', Path('.'), ['a.js'], 'q', list(gt), list(negatives))


def V(line, quote='x', text='y', path='a.js'):
    return (path, line, line, text, quote)


def test_score_rewards_exact_lines_and_penalises_negatives():
    task = T([{'line': 10, 'path': 'a.js'}, {'line': 20, 'path': 'a.js'}], [{'line': 30, 'path': 'a.js'}])
    perfect = runner.score(task, [V(10), V(20)])
    assert perfect['f1'] == 1.0
    noisy = runner.score(task, [V(10), V(20), V(30)])
    assert noisy['recall'] == 1.0 and noisy['precision'] < 1 and noisy['negatives_returned'] == 1
    assert runner.score(task, [V(10, path='b.js')])['recall'] == 0.0      # right line, wrong file


def test_score_spans_keys_and_short_keys():
    span = T([{'line': 5, 'span': [3, 8], 'path': 'a.js'}], family='locate')
    assert runner.score(span, [V(7)])['f1'] == 1.0
    env = T([{'line': 1, 'key': 'SMTP_HOST', 'path': 'a.js'}], family='env_vars')
    assert runner.score(env, [V(99, text='reads SMTP_HOST')])['f1'] == 1.0
    short = T([{'line': 1, 'key': '/', 'path': 'a.js'}])
    assert runner.score(short, [V(50, quote='app.get("/x")')])['recall'] == 0.0   # a 1-char key must not match anything


def _tarball(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_safe_extract_drops_top_folder_and_refuses_escapes(tmp_path):
    corpus._safe_extract(_tarball({'repo-abc/app.js': b'x', 'repo-abc/src/a.py': b'y'}), tmp_path / 'ok')
    assert (tmp_path / 'ok' / 'app.js').read_bytes() == b'x' and (tmp_path / 'ok' / 'src' / 'a.py').exists()
    with pytest.raises(corpus.CorpusError):
        corpus._safe_extract(_tarball({'repo-abc/../../evil.txt': b'z'}), tmp_path / 'bad')
    assert not (tmp_path / 'evil.txt').exists()


def test_fingerprint_ignores_line_endings_but_not_content(tmp_path):
    (tmp_path / 'a.js').write_bytes(b'one\ntwo\n')
    fp = corpus.fingerprint(tmp_path, ['a.js'])
    (tmp_path / 'a.js').write_bytes(b'one\r\ntwo\r\n')
    assert corpus.fingerprint(tmp_path, ['a.js']) == fp
    (tmp_path / 'a.js').write_bytes(b'one\nthree\n')
    assert corpus.fingerprint(tmp_path, ['a.js']) != fp


def test_fastapi_generator_classifies_auth(tmp_path):
    routes = tmp_path / 'backend' / 'app' / 'api' / 'routes'
    routes.mkdir(parents=True)
    (routes / 'demo.py').write_text(
        '@router.get("/public")\n'
        'def a() -> Any:\n    pass\n\n'
        '@router.post(\n    "/admin",\n    dependencies=[Depends(get_current_active_superuser)],\n)\n'
        'def b(session: SessionDep) -> Any:\n    pass\n\n'
        '@router.get("/me")\n'
        'def c(\n    current_user: CurrentUser,\n) -> Any:\n    pass\n')
    by_id = {t.id: t for t in generate.fastapi(tmp_path)}
    assert [g['line'] for g in by_id['fastapi:superuser_only'].gt] == [5]
    assert [g['line'] for g in by_id['fastapi:public_endpoints'].gt] == [1]
    assert len(by_id['fastapi:endpoints_all'].gt) == 3


def test_boilerplate_generator_follows_chained_routes(tmp_path):
    d = tmp_path / 'src' / 'routes' / 'v1'
    d.mkdir(parents=True)
    (d / 'user.route.js').write_text("router\n  .route('/')\n  .post(auth('manageUsers'), c.create)\n  .get(auth('getUsers'), c.list);\n")
    (d / 'auth.route.js').write_text("router.post('/login', validate(v.login), c.login);\n")
    (tmp_path / 'src' / 'config').mkdir()
    (tmp_path / 'src' / 'config' / 'config.js').write_text("const s = Joi.object().keys({\n    PORT: Joi.number(),\n  });\n")
    by_id = {t.id: t for t in generate.boilerplate(tmp_path)}
    assert [g['line'] for g in by_id['boilerplate:routes_manage'].gt] == [3]
    assert [(g['path'].split('/')[-1], g['line']) for g in by_id['boilerplate:routes_without_auth'].gt] == [('auth.route.js', 1)]
    assert [g['key'] for g in by_id['boilerplate:env_schema'].gt] == ['PORT']


def test_edit_fixture_is_green_and_checks_are_strict():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        edits._make(root)
        assert edits._tests_pass(root)
        assert not edits._docstrings(root)          # nothing done yet
        assert edits._written_tests(root) == 0.0    # no test file yet


def test_a_wrong_answer_cannot_score_perfectly():
    env = T([{'line': 10, 'key': 'SMTP_HOST', 'path': 'a.js'}], family='env_vars')
    assert runner.score(env, [V(10, quote='PORT', text='port')])['f1'] == 0.0       # right line, wrong subject
    log = T([{'line': 40, 'path': 'a.js'}], family='log')
    assert runner.score(log, [V(5)])['f1'] == 0.0                                    # any quote is not enough
    assert runner.score(log, [V(40), V(41)])['f1'] == 1.0
