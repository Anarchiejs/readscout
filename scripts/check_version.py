"""Fail when the version written in several places disagrees (run by CI and by the release workflow).

usage: python scripts/check_version.py [vX.Y.Z]     (the tag, when releasing: it must match too)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(tag: str | None) -> int:
    version = re.search(r"__version__ = '([^']+)'", (ROOT / 'src/readscout/__init__.py').read_text(encoding='utf-8'))[1]
    wheel = f'releases/download/v{version}/readscout-{version}-py3-none-any.whl'
    problems = []
    if tag and tag != f'v{version}':
        problems.append(f'tag {tag} does not match the package version {version}')
    plugin = json.loads((ROOT / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
    if plugin.get('version') != version:
        problems.append(f'.claude-plugin/plugin.json says {plugin.get("version")}')
    for name in ('.claude-plugin/plugin.json', 'install.sh', 'install.ps1'):
        text = (ROOT / name).read_text(encoding='utf-8')
        if wheel not in text:
            problems.append(f'{name} does not point at {wheel}')
    if not (ROOT / f'.github/release-notes/v{version}.md').exists():
        problems.append(f'.github/release-notes/v{version}.md is missing')
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    if not re.search(rf'^## {re.escape(version)}\b', changelog, re.M):
        problems.append(f'CHANGELOG.md has no "## {version}" section')
    for p in problems:
        print('FAIL', p)
    if not problems:
        print(f'OK version {version} is consistent')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
