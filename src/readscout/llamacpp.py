"""llama.cpp engine: readscout runs llama-server itself, on a loopback port, and stops it once idle.

Why: on mixture-of-experts models llama.cpp reads prompts about 3.5x faster than Ollama with a large micro-batch
(docs/BENCHMARK.md). Ollama stays the default engine; `readscout engine llamacpp --quality X.gguf` moves a tier to it,
the other tiers stay on Ollama.

One llama-server at a time, shared by every readscout process through a small state file (like Ollama with
OLLAMA_MAX_LOADED_MODELS=1): a process that needs another model replaces it, and the server is stopped when it has
been idle for `unload_after`, so the memory is freed even if the agent forgets. A model given by `url` instead of
`gguf` is a llama-server the user runs: readscout only talks to it, never starts or stops it.

The two engines take turns on the GPU (an 8 GB card holds one 26B model, not two): llama.cpp unloads Ollama's models
before it starts one, and an Ollama call first stops the shared llama-server unless it is answering a request.
"""
import atexit
import ctypes
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import paths
from . import backend
from .backend import BackendError, Model, Reply, _parse

# Measured on an 8 GB GPU (docs/BENCHMARK.md): flash attention and an 8-bit KV cache let 26B MoE models fit, and a
# large micro-batch is what makes prompt reading fast. 4096 was the fastest with CUDA, but its 5 GB compute buffer
# cannot be allocated by the Vulkan build (the one winget installs) next to a 26B model on 8 GB: 2048 works on both and
# keeps most of the gain. One slot keeps the whole context for one request. Recent llama-server builds fit the layers
# and experts to the GPU memory by themselves; `args` adds or overrides flags.
DEFAULT_ARGS = ['-fa', 'on', '-ctk', 'q8_0', '-ctv', 'q8_0', '-b', '4096', '-ub', '2048', '-np', '1', '--jinja', '--no-webui']
LOAD_TIMEOUT = 600          # a 16 GB model read from a slow disk
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
_OWN: dict = {}             # the llama-server this process started: {'proc': Popen, 'pid': int}
_WATCHDOG: list = []
_ATEXIT: list = []


def settings(cfg: dict) -> dict:
    return cfg.get('llamacpp') or {}


def binary(cfg: dict) -> str | None:
    """llama-server from the config, the PATH, or where winget and Homebrew put it."""
    given = settings(cfg).get('binary')
    if given:
        return given if Path(given).expanduser().is_file() else None
    found = shutil.which('llama-server')
    if found:
        return found
    winget = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet'
    # winget puts llama.cpp in its package folder; an agent started before the install does not have it on its PATH yet.
    candidates = [str(winget / 'Links' / 'llama-server.exe'), *sorted(str(p) for p in winget.glob('Packages/ggml.llamacpp*/llama-server.exe')),
                  '/opt/homebrew/bin/llama-server', '/usr/local/bin/llama-server']
    return next((c for c in candidates if os.path.isfile(c)), None)


def ollama_gguf(name: str) -> str:
    """The GGUF file of a model Ollama already downloaded, so llama.cpp can use it without a second download.
    Ollama lists the weights and, for multimodal models, a smaller vision projector: the weights are the largest file."""
    from .backend import ollama_binary
    exe = ollama_binary()
    if not exe:
        raise BackendError('Ollama is not installed: give a .gguf file instead')
    p = subprocess.run([exe, 'show', name, '--modelfile'], capture_output=True, text=True, encoding='utf-8', errors='replace',
                       stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=60)
    files = [Path(line[5:].strip()) for line in p.stdout.splitlines() if line.startswith('FROM ')]
    files = [f for f in files if f.is_file()]
    if p.returncode or not files:
        raise BackendError(f'Ollama has no local model {name} ({(p.stderr or p.stdout).strip()[:200]})')
    return str(max(files, key=lambda f: f.stat().st_size))


DEVICE_LINE = re.compile(r'^\s+(\w+\d+):\s+(.+?)\s+\((\d+) MiB')


def devices(cfg: dict) -> list[tuple[str, str, int]]:
    """The devices this llama-server build can use, as (id, name, MiB): `CUDA0`, `Vulkan0`, `Metal`... An empty list
    means CPU only, or a llama-server that does not run."""
    exe = binary(cfg)
    if not exe:
        return []
    try:
        out = subprocess.run([exe, '--list-devices'], capture_output=True, text=True, encoding='utf-8', errors='replace',
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [(m[1], m[2], int(m[3])) for m in map(DEVICE_LINE.match, out.splitlines()) if m]


def device_notes(found: list[tuple[str, str, int]], gpu_source: str) -> list[str]:
    """What to tell the user about the build they installed. `gpu_source` is how readscout found their GPU
    (`nvidia-smi`, `rocm-smi`, `apple-unified`...): an NVIDIA card without a CUDA device means a slow build."""
    notes = []
    if gpu_source == 'nvidia-smi' and not any(d.startswith('CUDA') for d, _, _ in found):
        notes.append('You have an NVIDIA GPU but this llama.cpp build has no CUDA device: it was slower than Ollama when '
                     'measured (Vulkan build). Take the CUDA build from https://github.com/ggml-org/llama.cpp/releases '
                     '(llama-bXXXX-bin-win-cuda-13.x-x64.zip plus the matching cudart zip; CUDA 13 needs NVIDIA driver 580 '
                     'or newer, take a CUDA 12 build for an older driver) and pass it with `readscout engine llamacpp --binary`.')
    if len([d for d, _, _ in found if not d.startswith('CPU')]) > 1:
        notes.append('Several devices: add `--args "--device <id>"` (for example CUDA0) so the model is not split onto an '
                     'integrated GPU.')
    return notes


def seconds(value) -> int:
    """'60s', '5m', '1h' or a number of seconds (the Ollama keep_alive syntax readscout's config already uses)."""
    text = str(value).strip().lower()
    unit = {'s': 1, 'm': 60, 'h': 3600}.get(text[-1:], 0)
    try:
        return int(float(text[:-1] if unit else text) * (unit or 1))
    except ValueError:
        return 60


def tiers(cfg: dict) -> dict:
    """The tiers that run on llama.cpp: those listed under llamacpp.models while the engine is llamacpp. Every other
    tier runs on Ollama, so the fast model can stay on Ollama (faster there) while the 26B runs on llama.cpp."""
    if cfg.get('engine') != 'llamacpp':
        return {}
    return {t: s for t, s in (settings(cfg).get('models') or {}).items() if s}


def engine_of(cfg: dict, tier: str) -> str:
    return 'llamacpp' if tier in tiers(cfg) else 'ollama'


def model(cfg: dict, tier: str) -> Model:
    """The llama.cpp Model configured for a tier (whatever the engine setting, so `bench` can compare engines)."""
    spec = (settings(cfg).get('models') or {}).get(tier)
    if not spec or not (spec.get('gguf') or spec.get('url')):
        raise BackendError(f'No llama.cpp {tier} model configured. Run `{paths.cli()} engine llamacpp --{tier} <file.gguf>` '
                           f'or `{paths.cli()} engine ollama`')
    return from_spec(cfg, spec)


def from_spec(cfg: dict, spec: dict) -> Model:
    gguf = str(Path(spec['gguf']).expanduser()) if spec.get('gguf') else ''
    if gguf and not Path(gguf).is_file():
        raise BackendError(f'llama.cpp model file not found: {gguf} (fix it with `{paths.cli()} engine llamacpp ...`)')
    name = spec.get('name') or (Path(gguf).stem if gguf else 'llama-server')
    return Model(name=name, url=spec.get('url') or 'http://127.0.0.1', ctx=int(spec.get('ctx', 32768)),
                 keep_alive=str(cfg.get('unload_after', '60s')), engine='llamacpp', gguf=gguf,
                 args=tuple(settings(cfg).get('args') or []) + tuple(spec.get('args') or []))


# ---------------------------------------------------------------- the shared server

def _state_file() -> Path:
    return paths.home() / 'llamacpp.json'


def _read_state() -> dict | None:
    try:
        st = json.loads(_state_file().read_text(encoding='utf-8'))
        return st if isinstance(st, dict) and isinstance(st.get('port'), int) else None
    except (OSError, ValueError):
        return None


def _write_state(st: dict | None) -> None:
    f = _state_file()
    if st is None:
        f.unlink(missing_ok=True)
        return
    tmp = f.with_suffix(f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(st), encoding='utf-8')
    tmp.replace(f)


def _touch() -> None:
    with paths.config_lock(name='llamacpp'):
        st = _read_state()
        if st:
            st['last_used'] = time.time()
            _write_state(st)


def _request(url, body=None, timeout=600):
    """backend._request, with the secret key of the llama-server readscout started (the user's own server has none)."""
    st = _read_state()
    key = st and st.get('token') and url.startswith(f'http://127.0.0.1:{st["port"]}/')
    return backend._request(url, body, timeout, {'Authorization': f'Bearer {st["token"]}'} if key else None)  # type: ignore[index]


def probe(url: str) -> str | None:
    """'ok' when the model answers, 'loading' while it loads (llama-server answers 503), None when nothing listens."""
    try:
        with _request(url.rstrip('/') + '/health', timeout=3):
            return 'ok'
    except BackendError as e:
        return 'loading' if 'HTTP 503' in str(e) else None


def _busy(url: str) -> bool:
    try:
        with _request(url.rstrip('/') + '/slots', timeout=3) as r:
            return any(s.get('is_processing') for s in json.load(r))
    except (BackendError, ValueError, TypeError, AttributeError):
        return False


def _key(m: Model) -> str:
    return json.dumps([str(Path(m.gguf).resolve()), m.ctx, list(m.args)])


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _kill(pid: int) -> None:
    try:
        if sys.platform == 'win32':
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def _alive(pid: int) -> bool:
    """Never os.kill(pid, 0) on Windows: there it terminates the process."""
    if sys.platform == 'win32':
        k32 = ctypes.windll.kernel32           # type: ignore[attr-defined]
        h = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return code.value == 259                        # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _stop(st: dict) -> None:
    """Stop the shared server described by `st`, only if something still answers on its port (a dead server's pid may
    belong to another program by now)."""
    if probe(f'http://127.0.0.1:{st["port"]}') and _alive(st['pid']):
        _kill(st['pid'])
    if _OWN.get('pid') == st['pid']:
        _OWN.clear()


def log_file() -> Path:
    return paths.home() / 'llama-server.log'


def _spawn(m: Model, cfg: dict, port: int, token: str = '') -> int:
    exe = binary(cfg)
    if not exe:
        raise BackendError('llama-server not found. Install llama.cpp (winget install llama.cpp, brew install llama.cpp, '
                           f'or https://github.com/ggml-org/llama.cpp/releases), or `{paths.cli()} engine ollama`')
    cmd = [exe, '-m', m.gguf, '-c', str(m.ctx), '--host', '127.0.0.1', '--port', str(port), *DEFAULT_ARGS, *m.args]
    log = log_file().open('w', encoding='utf-8', errors='replace')
    # llama-server allows every web origin and has no key by default: any web page open in the browser could talk to a
    # model on a guessed port. A random key, handed over in the environment (not the command line), shuts that door.
    env = {**os.environ, 'LLAMA_API_KEY': token} if token else None
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                                close_fds=True, env=env)
    finally:
        log.close()
    if not _ATEXIT:
        # Every process that starts a server stops it when it ends: the MCP server, and also a terminal `readscout ask`,
        # whose idle watchdog dies with it and would otherwise leave the model in memory.
        atexit.register(stop_owned)
        _ATEXIT.append(True)
    _OWN.update(proc=proc, pid=proc.pid)
    return proc.pid


def ensure(m: Model, cfg: dict) -> str:
    """URL of a llama-server serving `m`, started if needed. Waits until the model is loaded."""
    if not m.gguf:
        return m.url                     # the user's own server
    key = _key(m)
    with paths.config_lock(name='llamacpp'):
        st = _read_state()
        if st and st.get('key') == key and probe(f'http://127.0.0.1:{st["port"]}'):
            pass                         # already serving this model, or loading it for another process
        else:
            if st:
                _stop(st)                # one model at a time, like Ollama with OLLAMA_MAX_LOADED_MODELS=1
            _free_ollama(cfg)
            port = _free_port()
            token = secrets.token_urlsafe(24)
            st = {'pid': _spawn(m, cfg, port, token), 'port': port, 'key': key, 'token': token, 'last_used': time.time()}
            _write_state(st)
    _start_watchdog(cfg)
    url = f'http://127.0.0.1:{st["port"]}'
    deadline = time.time() + LOAD_TIMEOUT
    while time.time() < deadline:
        if probe(url) == 'ok':
            return url
        proc = _OWN.get('proc')
        if proc is not None and _OWN.get('pid') == st['pid'] and proc.poll() is not None:
            with paths.config_lock(name='llamacpp'):
                if (_read_state() or {}).get('pid') == st['pid']:
                    _write_state(None)
            tail = log_file().read_text(encoding='utf-8', errors='replace')[-600:].strip()
            raise BackendError(f'llama-server stopped while loading {m.name} (exit {proc.returncode}): {tail}')
        time.sleep(0.5)
    raise BackendError(f'llama-server did not load {m.name} within {LOAD_TIMEOUT}s (see {log_file()})')


def _free_ollama(cfg: dict) -> None:
    """Ollama keeps a model loaded for `unload_after`: on an 8 GB GPU llama-server would then run out of memory or
    spill to the CPU. Ollama finishes a request in progress before it unloads."""
    from .backend import unload_all
    unload_all(cfg.get('ollama_url', 'http://127.0.0.1:11434'))


def release() -> bool:
    """Before an Ollama call: stop the shared llama-server so the two engines never hold a model at once. Never while it
    loads or answers a request (another session's): both then share the memory for that one request. True if stopped."""
    if not _state_file().exists():
        return False
    with paths.config_lock(name='llamacpp'):
        st = _read_state()
        if not st:
            return False
        url = f'http://127.0.0.1:{st["port"]}'
        status = probe(url)
        if status == 'loading' or (status == 'ok' and _busy(url)):
            return False
        if status:
            _stop(st)
        _write_state(None)
        return bool(status)


def idle_check(idle: int) -> bool:
    """Stop the shared server when nobody used it for `idle` seconds and it is not answering. True if it was stopped."""
    with paths.config_lock(name='llamacpp'):
        st = _read_state()
        if not st:
            return False
        url = f'http://127.0.0.1:{st["port"]}'
        if not probe(url):
            _write_state(None)           # it died or was stopped: forget it
            return False
        if time.time() - st.get('last_used', 0) < idle or _busy(url):
            return False
        _stop(st)
        _write_state(None)
        return True


def _start_watchdog(cfg: dict) -> None:
    if _WATCHDOG:
        return
    idle = seconds(cfg.get('unload_after', '60s'))

    def loop():
        while True:
            time.sleep(min(15, max(1, idle // 4)))
            try:
                idle_check(idle)
            except (OSError, TimeoutError):
                pass
    t = threading.Thread(target=loop, daemon=True, name='readscout-llamacpp-idle')
    _WATCHDOG.append(t)
    t.start()


def stop_all() -> str | None:
    """`readscout stop`: stop the shared server whoever started it. Returns the model it served, if any."""
    with paths.config_lock(name='llamacpp'):
        st = _read_state()
        if not st:
            return None
        served = json.loads(st.get('key', '[""]'))[0]
        _stop(st)
        _write_state(None)
    return Path(served).stem or 'llama-server'


def stop_owned() -> None:
    """When this process exits (the agent session ended), stop the server it started, as Ollama would unload it."""
    if not _OWN:
        return
    try:
        with paths.config_lock(name='llamacpp', timeout=3):
            st = _read_state()
            if st and st.get('pid') == _OWN.get('pid'):
                _stop(st)
                _write_state(None)
    except (OSError, TimeoutError):
        pass
    proc = _OWN.get('proc')
    if proc is not None and proc.poll() is None:
        proc.terminate()
    _OWN.clear()


# ---------------------------------------------------------------- chat

def chat(m: Model, system: str, user: str, schema: dict, max_tokens=2048, timeout=600, temperature=0.0) -> Reply:
    cfg = paths.load_config()
    body = {'model': m.name, 'stream': False, 'temperature': temperature, 'max_tokens': max_tokens,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'answer', 'schema': schema}},
            'chat_template_kwargs': {'enable_thinking': False}, 'repeat_penalty': 1.1, 'repeat_last_n': 64}
    t = time.time()
    for attempt in (1, 2):
        url = ensure(m, cfg)
        if m.gguf:
            _touch()
        try:
            with _request(url.rstrip('/') + '/v1/chat/completions', body, timeout) as r:
                out = json.load(r)
            break
        except BackendError as e:
            # Another readscout process may have replaced or stopped the shared server meanwhile: start it again once.
            if attempt == 2 or not m.gguf or 'unreachable' not in str(e):
                raise
    if m.gguf:
        _touch()
    choice = (out.get('choices') or [{}])[0]
    if choice.get('finish_reason') == 'length':
        raise BackendError('Model output truncated (max_tokens reached)')
    usage = out.get('usage') or {}
    return Reply(_parse((choice.get('message') or {}).get('content')), usage.get('prompt_tokens', 0),
                 usage.get('completion_tokens', 0), time.time() - t)
