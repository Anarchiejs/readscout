"""Offline identity and exact skill/reference synchronization."""
import json
from pathlib import Path

from readscout import agents, cli, hardware, provenance


def test_info_does_not_probe_hardware_or_start_servers(monkeypatch, capsys):
    def forbidden():
        raise AssertionError('info must stay offline')
    monkeypatch.setattr(hardware, 'ensure_config', forbidden)
    assert cli.main(['info']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['version'] and data['distribution_version'] and len(data['content_sha256']) == 64
    assert Path(data['package_path']).is_dir()


def test_identity_changes_with_package_contents_not_bytecode(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance, 'PACKAGE', tmp_path)
    (tmp_path / 'a.py').write_text('x=1')
    before = provenance.package_info()['content_sha256']
    cache = tmp_path / '__pycache__'
    cache.mkdir()
    (cache / 'a.py').write_text('generated')
    assert provenance.package_info()['content_sha256'] == before
    (tmp_path / 'a.py').write_text('x=2')
    assert provenance.package_info()['content_sha256'] != before


def test_missing_or_stale_reference_is_not_a_synchronized_skill(tmp_path):
    dest = tmp_path / 'readscout' / 'SKILL.md'
    agents._copy_skill(dest)
    assert agents._skill_matches(dest)
    reference = dest.parent / 'references/local_edit.md'
    reference.write_text('obsolete')
    assert not agents._skill_matches(dest)
    reference.unlink()
    assert not agents._skill_matches(dest)


def test_agent_registration_uses_its_own_environment_not_another_on_path(tmp_path, monkeypatch):
    interpreter = tmp_path / 'python.exe'
    interpreter.touch()
    entry = tmp_path / 'readscout-mcp.exe'
    entry.touch()
    monkeypatch.setattr(agents.sys, 'executable', str(interpreter))
    monkeypatch.setattr(agents.sys, 'platform', 'win32')
    monkeypatch.setattr(agents.shutil, 'which', lambda *a: 'obsolete-environment/readscout-mcp.exe')
    assert agents.server_command() == [str(entry)]
    entry.unlink()
    assert agents.server_command() == [str(interpreter), '-m', 'readscout.server']
