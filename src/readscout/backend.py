"""Talks to the local Ollama server: schema-constrained chat, health, auto-start, model pulls.

Only loopback endpoints are accepted, so file contents can never leave the machine through this module.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

LOOPBACK = {'127.0.0.1', 'localhost', '::1'}
# Ollama itself unloads a model this long after its last request, so memory is freed automatically even if the
# agent forgets, crashes or never stops. Calls made close together still reuse the loaded model.
UNLOAD_AFTER = '60s'
USED: set[tuple[str, str]] = set()   # (url, model) used by this process, unloaded when it exits
# Settings that let 26B MoE models fit next to an 8 GB GPU (flash attention + 8-bit KV cache).
OLLAMA_ENV = {'OLLAMA_FLASH_ATTENTION': '1', 'OLLAMA_KV_CACHE_TYPE': 'q8_0', 'OLLAMA_MAX_LOADED_MODELS': '1',
              'OLLAMA_NO_CLOUD': '1'}   # also switches off Ollama's cloud features (https://docs.ollama.com/faq)
CLOUD_NAME = re.compile(r'(^|[:/_-])cloud$', re.I)
CHECKED: set[tuple[str, str]] = set()    # models already confirmed to run on this machine


class BackendError(RuntimeError):
    pass


@dataclass
class Model:
    name: str
    url: str = 'http://127.0.0.1:11434'
    ctx: int = 32768
    chars_per_token: float = 3.2
    keep_alive: str = UNLOAD_AFTER
    note: str = ''              # shown in receipts, e.g. when a fallback model was used

    def __post_init__(self):
        if urlparse(self.url).hostname not in LOOPBACK:
            raise BackendError(f'Non-loopback endpoint refused: {self.url}')
        if CLOUD_NAME.search(self.name):
            raise BackendError(f'Cloud model refused: {self.name} (readscout only uses models that run on this machine)')


def check_local(model: 'Model') -> None:
    """A loopback address is not enough: Ollama can forward some models to its cloud. Refuse those (once per model)."""
    key = (model.url, model.name)
    if key in CHECKED:
        return
    with _request(model.url.rstrip('/') + '/api/tags', timeout=5) as r:
        tags = json.load(r).get('models', [])
    for m in tags:
        if model.name in (m.get('name'), m.get('model')) and (m.get('remote_host') or m.get('remote_model')):
            raise BackendError(f'Cloud model refused: {model.name} is served by a remote host')
    CHECKED.add(key)


@dataclass
class Reply:
    data: dict
    prompt_tokens: int
    output_tokens: int
    seconds: float


def _request(url, body=None, timeout=600):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data, {'Content-Type': 'application/json'})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise BackendError(f'HTTP {e.code} from {url}: {e.read()[:300].decode(errors="replace")}') from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise BackendError(f'Ollama unreachable at {url}: {e}') from e


def _parse(text):
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.strip('`').removeprefix('json').strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise BackendError(f'Model returned invalid JSON ({e}): {text[:200]}') from e


def chat(model: Model, system: str, user: str, schema: dict, max_tokens=2048, timeout=600, temperature=0.0) -> Reply:
    check_local(model)
    t = time.time()
    USED.add((model.url, model.name))
    body = {'model': model.name, 'stream': False, 'think': False, 'format': schema, 'keep_alive': model.keep_alive,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            'options': {'temperature': temperature, 'num_predict': max_tokens, 'num_ctx': model.ctx}}
    with _request(model.url.rstrip('/') + '/api/chat', body, timeout) as r:
        out = json.load(r)
    if out.get('done_reason') == 'length':
        raise BackendError('Model output truncated (max_tokens reached)')
    return Reply(_parse(out['message']['content']), out.get('prompt_eval_count', 0), out.get('eval_count', 0), time.time() - t)


def health(url='http://127.0.0.1:11434', timeout=3) -> str | None:
    """Ollama version if the server answers, else None."""
    try:
        with urllib.request.urlopen(url.rstrip('/') + '/api/version', timeout=timeout) as r:
            return json.load(r).get('version', '?')
    except Exception:
        return None


def installed_models(url='http://127.0.0.1:11434') -> set[str]:
    with _request(url.rstrip('/') + '/api/tags', timeout=5) as r:
        names = {m['name'] for m in json.load(r).get('models', [])}
    return names | {n.removesuffix(':latest') for n in names}


def unload(name: str, url='http://127.0.0.1:11434') -> bool:
    """Free a model's memory now (Ollama unloads it when keep_alive is 0). False if the request failed."""
    try:
        with _request(url.rstrip('/') + '/api/generate', {'model': name, 'keep_alive': 0}, timeout=30):
            return True
    except BackendError:
        return False


def unload_used() -> None:
    """Called when the MCP server exits (the agent session ended): nothing stays in memory after it."""
    for url, name in list(USED):
        unload(name, url)


def unload_all(url='http://127.0.0.1:11434') -> list[str]:
    names = loaded_models(url)
    return [name for name in names if unload(name, url)]


def loaded_models(url='http://127.0.0.1:11434') -> list[str]:
    try:
        with _request(url.rstrip('/') + '/api/ps', timeout=3) as r:
            return [m['name'] for m in json.load(r).get('models', [])]
    except BackendError:
        return []


def ollama_binary() -> str | None:
    found = shutil.which('ollama')
    if found:
        return found
    candidates = []
    if sys.platform == 'win32':
        candidates.append(os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'ollama.exe'))
    elif sys.platform == 'darwin':
        candidates.append('/Applications/Ollama.app/Contents/Resources/ollama')
    else:
        candidates += ['/usr/local/bin/ollama', '/usr/bin/ollama']
    return next((c for c in candidates if os.path.exists(c)), None)


def ensure_ollama(url='http://127.0.0.1:11434', wait=60) -> None:
    """Start Ollama if it is installed but not running."""
    if health(url):
        return
    flags = 0
    if sys.platform == 'win32':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        app = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'ollama app.exe')
        cmd = [app] if os.path.exists(app) else None
    elif sys.platform == 'darwin' and os.path.exists('/Applications/Ollama.app'):
        cmd = ['open', '-a', 'Ollama']
    else:
        cmd = None
    if cmd is None:
        binary = ollama_binary()
        if not binary:
            from .paths import cli
            raise BackendError(f'Ollama is not installed. Install it from https://ollama.com, then run `{cli()} setup`.')
        cmd = [binary, 'serve']
    env = {**os.environ, **{k: os.environ.get(k, v) for k, v in OLLAMA_ENV.items()}}
    spawn = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                 start_new_session=sys.platform != 'win32', close_fds=True)
    explorer = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'explorer.exe')
    if sys.platform == 'win32' and cmd[0].endswith('ollama app.exe') and os.path.exists(explorer):
        # Agents run MCP servers inside a Windows job that kills every child when the session ends. Asking Explorer
        # to open the app starts Ollama outside that job, like a double-click, so it outlives the session.
        subprocess.Popen([explorer, cmd[0]], **spawn)
    else:
        subprocess.Popen(cmd, creationflags=flags, **spawn)
    deadline = time.time() + wait
    while time.time() < deadline:
        if health(url):
            return
        time.sleep(1)
    raise BackendError(f'Ollama did not start within {wait}s')


def pull(name: str, url='http://127.0.0.1:11434', progress=None) -> None:
    """Download a model; progress(status, completed_bytes, total_bytes) is called as data arrives."""
    with _request(url.rstrip('/') + '/api/pull', {'model': name, 'stream': True}, timeout=24 * 3600) as r:
        for raw in r:
            if not raw.strip():
                continue
            ev = json.loads(raw)
            if 'error' in ev:
                raise BackendError(ev['error'])
            if progress:
                progress(ev.get('status', ''), ev.get('completed', 0), ev.get('total', 0))
