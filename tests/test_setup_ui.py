"""Execute the actual setup-page JavaScript against HTTP and network failures."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_setup_page_reports_http_failures():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute the setup-page JavaScript')
    script = Path(__file__).with_name('setup_ui.cjs')
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
