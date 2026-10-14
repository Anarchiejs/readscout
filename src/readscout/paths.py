"""Per-user locations, so the package itself never stores personal data.

Windows: %APPDATA%\\readscout   macOS: ~/Library/Application Support/readscout   Linux: $XDG_CONFIG_HOME/readscout
Override everything with READSCOUT_HOME (used by the tests).
"""
import json
import os
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def home() -> Path:
    if os.environ.get('READSCOUT_HOME'):
        base = Path(os.environ['READSCOUT_HOME'])
    elif sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming')) / 'readscout'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support' / 'readscout'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'readscout'
    base.mkdir(parents=True, exist_ok=True)
    return base


def cli() -> str:
    """How the user runs the readscout command: plain `readscout`, or the uvx line the Claude Code plugin sets."""
    return os.environ.get('READSCOUT_CLI', 'readscout')


def config_file() -> Path:
    return home() / 'config.json'


def metrics_file() -> Path:
    return home() / 'metrics.jsonl'


DEFAULT_CONFIG = {
    'models': {
        'fast': {'name': 'gemma4:e4b', 'ctx': 32768},
        'quality': {'name': 'gemma4:26b', 'ctx': 32768},
    },
    'ollama_url': 'http://127.0.0.1:11434',
    'projects': {},
}


def load_config() -> dict:
    p = config_file()
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    cfg = json.loads(p.read_text(encoding='utf-8'))
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, json.loads(json.dumps(v)))
    return cfg


def save_config(cfg: dict) -> None:
    p = config_file()
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(p)
