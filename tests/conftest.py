import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """No test may read or write the real per-user readscout folder."""
    monkeypatch.setenv('READSCOUT_HOME', str(tmp_path / 'readscout-home'))
    monkeypatch.setenv('READSCOUT_NO_METRICS', '1')
