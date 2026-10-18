"""A local release tag cannot be silently reused for changed source contents."""
import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest


def test_changed_package_cannot_reuse_a_release_tag(tmp_path, monkeypatch):
    git = shutil.which('git')
    if not git:
        pytest.skip('Git is required to test release tag identity')
    spec = importlib.util.spec_from_file_location('version_check', Path(__file__).parents[1] / 'scripts/check_version.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    package = tmp_path / 'src/readscout'
    package.mkdir(parents=True)
    source = package / '__init__.py'
    source.write_text("__version__ = '9.8.7'\n")
    def run(*args):
        subprocess.run([git, *args], cwd=tmp_path, capture_output=True, check=True)
    run('init')
    run('add', '.')
    run('-c', 'user.name=ReadScout Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Fixture')
    run('tag', 'v9.8.7')
    assert not module.changed_release('9.8.7')
    source.write_text("__version__ = '9.8.7'\nx = 1\n")
    assert module.changed_release('9.8.7')
    assert not module.changed_release('9.8.8')
