"""Write a new version everywhere it appears, so a release never ships a stale URL.

usage: python scripts/bump_version.py X.Y.Z

Updates src/readscout/__init__.py, .claude-plugin/plugin.json, install.sh, install.ps1, README.md and README.fr.md
(the pinned wheel URLs: the installers and the plugin pin an exact release on purpose, it is what SHA256SUMS covers),
and starts the CHANGELOG section and the release notes when they are missing. Then run scripts/check_version.py.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINNED = ['.claude-plugin/plugin.json', 'install.sh', 'install.ps1', 'README.md', 'README.fr.md']


def main(new: str) -> int:
    if not re.fullmatch(r'\d+\.\d+\.\d+', new):
        print('usage: python scripts/bump_version.py X.Y.Z')
        return 2
    init = ROOT / 'src/readscout/__init__.py'
    old = re.search(r"__version__ = '([^']+)'", init.read_text(encoding='utf-8'))[1]
    init.write_text(init.read_text(encoding='utf-8').replace(f"__version__ = '{old}'", f"__version__ = '{new}'"), encoding='utf-8')
    for name in PINNED:
        f = ROOT / name
        text = f.read_text(encoding='utf-8')
        text = text.replace(f'download/v{old}/readscout-{old}-', f'download/v{new}/readscout-{new}-')
        if name.endswith('plugin.json'):
            text = text.replace(f'"version": "{old}"', f'"version": "{new}"')
        f.write_text(text, encoding='utf-8')
    changelog = ROOT / 'CHANGELOG.md'
    text = changelog.read_text(encoding='utf-8')
    if not re.search(rf'^## {re.escape(new)}\b', text, re.M):
        first = re.search(r'^## ', text, re.M)
        at = first.start() if first else len(text)
        changelog.write_text(text[:at] + f'## {new}\n\n- \n\n' + text[at:], encoding='utf-8')
    notes = ROOT / f'.github/release-notes/v{new}.md'
    if not notes.exists():
        notes.write_text(f'readscout {new}\n', encoding='utf-8')
    print(f'{old} -> {new}. Fill in CHANGELOG.md and {notes.relative_to(ROOT).as_posix()}, then run scripts/check_version.py')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ''))
