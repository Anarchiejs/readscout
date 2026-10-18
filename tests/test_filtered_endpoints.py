"""A filtered endpoint receipt ('endpoints!A,B') carries the source a protection check reads.

In the lot 3 pilot, every B session re-read the imports, the router declaration and the handlers of the listed endpoints
after this receipt, which cost one or two extra requests each time: the receipt now shows those lines itself.
"""
from readscout import extract, tasks
from readscout.text import Line

API = '''from fastapi import APIRouter, Depends
from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
)
def login(session: SessionDep, form: Form) -> Token:
    """Log in."""

    user = authenticate(session, form)
    return token_for(user)


@router.get("/me")
def me(user: CurrentUser) -> User:
    return user


@router.get("/health")
async def health() -> bool:
    return True
'''


def receipt(code=API, kind='endpoints!CurrentUser', path='auth.py'):
    lines = [Line(path, n, row) for n, row in enumerate(code.split('\n'), 1)]
    res = extract.run(kind, lines)
    return res, tasks.extract_receipt(res, 1000, 40, f'local_ask extract={kind}')


def shown(text):
    """{line number: text} of the source section."""
    section = text.split('Source of the listed endpoints', 1)[1]
    out = {}
    for row in section.split('\n')[1:]:
        number, bar, rest = row.strip().partition('| ')
        if bar and number.isdigit():
            out[int(number)] = rest
    return out


def test_the_handlers_of_the_listed_endpoints_are_shown_with_their_line_numbers():
    _, text = receipt()
    lines = shown(text)
    source = API.split('\n')
    for n in (7, 8, 9, 10, 11, 13, 14, 22, 23, 24):          # multi-line decorator, signature, docstring, body
        assert lines[n] == source[n - 1].rstrip(), n
    assert 12 not in lines                                   # blank lines are not repeated


def test_imports_and_the_router_declaration_are_shown_once_per_file():
    _, text = receipt()
    lines = shown(text)
    assert lines[1] == 'from fastapi import APIRouter, Depends' and lines[2] == 'from app.api.deps import CurrentUser, SessionDep'
    assert lines[4] == 'router = APIRouter(prefix="/auth", tags=["auth"])'
    assert text.count('router = APIRouter(prefix="/auth"') == 1


def test_endpoints_excluded_by_the_filter_are_not_shown():
    _, text = receipt()
    assert 18 not in shown(text) and 19 not in shown(text)    # /me mentions CurrentUser


def test_an_unfiltered_inventory_stays_compact():
    _, text = receipt(kind='endpoints')
    assert 'Source of the listed endpoints' not in text


def test_a_long_handler_is_cut_and_says_where_it_continues():
    body = '\n'.join(f'    step_{i}()' for i in range(60))
    code = f'router = APIRouter()\n@router.get("/long")\ndef long() -> None:\n{body}\n'
    _, text = receipt(code=code, kind='endpoints!Nothing', path='long.py')
    lines = shown(text)
    assert max(lines) < 2 + tasks.MAX_HANDLER_LINES + 1 and 'long.py:' in text and 'not shown' in text


def test_the_excerpt_budget_lists_what_it_leaves_out_without_hiding_endpoints():
    handlers = '\n'.join(f'@router.get("/e{i}")\ndef e{i}() -> None:\n' + '\n'.join(f'    call_{i}_{j}("{"x" * 40}")' for j in range(20)) + '\n'
                         for i in range(20))
    res, text = receipt(code='router = APIRouter()\n' + handlers, kind='endpoints!Nothing', path='many.py')
    assert 'status: complete' in text and all(f'GET /e{i} e{i}' in text for i in range(20))
    assert len(text.split('Source of the listed endpoints', 1)[1]) < tasks.MAX_EXCERPT_CHARS + 2000
    assert 'Source not shown for' in text


def test_an_unfiltered_inventory_for_a_negative_question_points_to_the_filter(tmp_path, monkeypatch):
    # Pilot repetition 1: the agent listed all 23 endpoints, filtered them itself, then re-read the candidates' files.
    (tmp_path / 'auth.py').write_text(API)
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    asked = tasks.ask(['auth.py'], 'Which endpoints can be called without CurrentUser?', extraction='endpoints')
    assert "extract='endpoints!Name1,Name2'" in asked
    plain = tasks.ask(['auth.py'], 'List every endpoint with its method and path.', extraction='endpoints')
    assert "endpoints!Name1" not in plain


def test_the_receipt_says_what_a_check_still_has_to_cover():
    _, text = receipt()
    assert 'authentication added outside these files' in text and 'no re-read' in text
