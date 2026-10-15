"""Per-user locations, so the package itself never stores personal data.

Windows: %APPDATA%\\readscout   macOS: ~/Library/Application Support/readscout   Linux: $XDG_CONFIG_HOME/readscout
Override everything with READSCOUT_HOME (used by the tests).
"""
import contextlib
import json
import os
import sys
import time
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
    'engine': 'ollama',          # or 'llamacpp' (`readscout engine`)
}


def load_config() -> dict:
    p = config_file()
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    cfg = json.loads(p.read_text(encoding='utf-8'))
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, json.loads(json.dumps(v)))
    return cfg


def allowed_folders(cfg: dict) -> list[Path]:
    """Optional allow-list: when set, the local models only read and write files inside these folders.
    Empty (the default) means any folder the agent names, like the agent itself."""
    return [Path(f).expanduser().resolve() for f in cfg.get('allowed_folders') or []]


def gate_allowed(cfg: dict) -> bool:
    """`readscout gate off` forbids local_edit's gate commands, for agents whose own shell access is restricted."""
    return cfg.get('allow_gate', True) is not False


def save_config(cfg: dict) -> None:
    p = config_file()
    tmp = p.with_suffix(f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(p)


@contextlib.contextmanager
def config_lock(timeout=10.0, stale=30.0, name='config'):
    """Serialize read-modify-write cycles of the config between processes (MCP servers, the web page, the CLI).
    `name` gives other shared files (the llama.cpp server state) their own lock."""
    lock = home() / f'{name}.lock'
    deadline = time.time() + timeout
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except (FileExistsError, PermissionError):      # Windows reports a lock held by another process as PermissionError
            try:
                if time.time() - lock.stat().st_mtime > stale:     # left behind by a crashed process
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError(f'readscout {name} is locked by another process')
            time.sleep(0.05)
    try:
        yield
    finally:
        for _ in range(20):         # Windows refuses to delete a file another process is opening right now
            try:
                lock.unlink(missing_ok=True)
                break
            except OSError:
                time.sleep(0.05)


def update_config(mutate) -> dict:
    """Load the config, let `mutate(cfg)` change it, save it: nobody else's change in between is lost."""
    with config_lock():
        cfg = load_config()
        mutate(cfg)
        save_config(cfg)
        return cfg
