"""Offline package identity, to distinguish source checkouts from installed builds."""
import hashlib
import sys
from importlib.metadata import PackageNotFoundError, version

from . import __version__
from .paths import PACKAGE


def package_info() -> dict:
    digest = hashlib.sha256()
    for path in sorted(PACKAGE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py', '.json', '.md', '.html'):
            digest.update(path.relative_to(PACKAGE).as_posix().encode('utf-8') + b'\0')
            digest.update(path.read_bytes() + b'\0')
    try:
        installed = version('readscout')
    except PackageNotFoundError:
        installed = None
    return {'version': __version__, 'distribution_version': installed, 'package_path': str(PACKAGE),
            'python': sys.executable, 'content_sha256': digest.hexdigest()}
