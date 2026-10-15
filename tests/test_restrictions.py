"""The optional folder allow-list, `readscout gate off`, and the wider secret masking."""
import sys

import pytest

from readscout import editing, tasks
from readscout.backend import Model, Reply
from readscout.text import AccessError, redact, resolve


@pytest.fixture
def two_folders(tmp_path, monkeypatch):
    work, other = tmp_path / 'work', tmp_path / 'other'
    work.mkdir()
    other.mkdir()
    (work / 'w.py').write_text('x = 1\n')
    (other / 'o.py').write_text('y = 2\n')
    cfg = {'models': {'quality': {'name': 'big'}, 'fast': {'name': 'small'}}, 'allowed_folders': [str(work)]}
    monkeypatch.setattr(tasks, 'load_config', lambda: (cfg, [work]))
    monkeypatch.setattr(editing, 'load_config', tasks.load_config)
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    monkeypatch.setattr(editing, 'record', lambda entry: None)
    monkeypatch.setattr(tasks, 'ensure_ollama', lambda url: None)
    monkeypatch.setattr(tasks, 'installed_models', lambda url: {'small', 'big'})
    return work, other, cfg


def test_without_a_list_any_folder_is_read(tmp_path):
    (tmp_path / 'a.py').write_text('a = 1\n')
    assert resolve(str(tmp_path / 'a.py'), [tmp_path / 'elsewhere'])[0] == (tmp_path / 'a.py').resolve()


def test_allow_list_refuses_files_and_folders_outside(two_folders):
    work, other, _ = two_folders
    assert tasks.gather(['w.py'], [work], [work.resolve()])[0].text == 'x = 1'
    for target in (str(other / 'o.py'), str(other), '../other/o.py'):
        with pytest.raises(AccessError, match='allowed folders'):
            tasks.gather([target], [work], [work.resolve()])


def test_ask_and_digest_follow_the_list(two_folders):
    _, other, _ = two_folders
    with pytest.raises(AccessError, match='allowed folders'):
        tasks.ask([str(other / 'o.py')], 'what?')
    with pytest.raises(AccessError, match='allowed folders'):
        tasks.digest(str(other / 'o.py'))


def test_edit_follows_the_list_for_existing_and_new_files(two_folders, monkeypatch):
    work, other, _ = two_folders
    monkeypatch.setattr(editing, 'chat', lambda *a, **k: Reply({'edits': [], 'summary': ''}, 1, 1, 0.1))
    for target in (str(other / 'o.py'), str(other / 'new.py')):
        with pytest.raises(AccessError, match='allowed folders'):
            editing.edit([target], 'x')
    assert not (other / 'new.py').exists()


def test_gate_off_refuses_gate_commands_but_not_edits(two_folders, monkeypatch):
    work, _, cfg = two_folders
    cfg['allow_gate'] = False
    monkeypatch.setattr(editing, 'chat', lambda *a, **k: Reply({'edits': [{'path': 'w.py', 'search': 'x = 1', 'replace': 'x = 3'}],
                                                              'summary': 's'}, 1, 1, 0.1))
    with pytest.raises(AccessError, match='gate off'):
        editing.edit(['w.py'], 'x', [[sys.executable, '-c', 'pass']])
    assert (work / 'w.py').read_text() == 'x = 1\n'
    out = editing.edit(['w.py'], 'x', None, model=Model('m'))
    assert out.startswith('APPLIED') and 'NO gate' in out


@pytest.mark.parametrize('secret', [
    'glpat-abcdefghijklmnopqrst12',
    'ASIAABCDEFGHIJKLMNOP',
    'sk_live_abcdefghijklmnop1234',
    'npm_' + 'a1' * 18,
    'hf_' + 'abcdefghij' * 3 + '12',
    'ya29.abcdefghijklmnopqrstuvwx',
    'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U',
    'https://hooks.slack.com/services/T000/B000/XXXXXXXX',
])
def test_provider_tokens_are_masked(secret):
    assert secret not in redact(f'value = "{secret}"  # comment')


def test_urls_headers_and_more_names_are_masked():
    assert 's3cr3tpass' not in redact('DATABASE_URL=postgres://app:s3cr3tpass@db:5432/app')
    assert 'postgres://app:[REDACTED]@db:5432/app' in redact('url = "postgres://app:s3cr3tpass@db:5432/app"')
    assert 'abc123def456ghi789' not in redact('headers = {"Authorization": "Bearer abc123def456ghi789"}')
    assert 'Zm9vYmFyMTIzNDU2Nzg5MA' not in redact('AccountKey=Zm9vYmFyMTIzNDU2Nzg5MA==;')
    assert 'correcthorsebattery' not in redact('passphrase: correcthorsebattery')


def test_masking_never_crosses_a_line_and_leaves_prose_alone():
    text = "if self.headers.get('X-Token') != TOKEN:\n    self.close_connection = True\n"
    assert redact(text) == text
    assert redact('Basic configuration_without_digits is fine') == 'Basic configuration_without_digits is fine'
    assert redact('see https://example.com/docs and git@github.com:me/repo.git') == 'see https://example.com/docs and git@github.com:me/repo.git'
