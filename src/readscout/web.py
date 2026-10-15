"""Local web UI on 127.0.0.1: /setup (hardware, 1-click model install, agents) and / (usage).

Every state-changing request needs the per-process token embedded in the page, and the Host and Origin
headers must be local, so a web site open in the browser cannot drive this server.
"""
import json
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, agents, backend, hardware, paths, stats

TOKEN = secrets.token_urlsafe(24)
PULLS: dict[str, dict] = {}
PAGE = (paths.PACKAGE / 'web' / 'index.html')
MODEL_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}')


def _pull_worker(name, url):
    state = PULLS[name] = {'status': 'starting', 'completed': 0, 'total': 0, 'error': None, 'done': False}

    def progress(status, completed, total):
        state.update(status=status, completed=completed or state['completed'], total=total or state['total'])
    try:
        backend.ensure_ollama(url)
        backend.pull(name, url, progress)
        state.update(status='installed', done=True)
    except Exception as e:  # noqa: BLE001 - shown to the user as is
        state.update(error=str(e)[:300], done=True)


_CACHE: dict[str, tuple[float, object]] = {}


def _cached(key, ttl, fn):
    """nvidia-smi and `claude mcp get` take seconds; the page polls every few seconds."""
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _CACHE[key] = (time.time(), value)
    return value


def state(vram=None, ram=None) -> dict:
    cfg = paths.load_config()
    url = cfg['ollama_url']
    hw = _cached('hardware', 3600, hardware.detect)
    v = float(vram) if vram else max(0.0, min(24.0, round(hw.vram_gb)))
    r = float(ram) if ram else max(4.0, min(64.0, round(hw.ram_gb)))
    version = backend.health(url)
    installed = sorted(backend.installed_models(url)) if version else []
    count = len({n for n in installed if not n.endswith(':latest')})
    return {'version': __version__, 'hardware': hardware.as_dict(hw), 'chosen': {'vram_gb': v, 'ram_gb': r},
            'recommended': hardware.recommend(v, r), 'catalog': hardware.catalog()['models'],
            'ollama': {'count': count if version else 0, 'version': version, 'binary': backend.ollama_binary(), 'installed': installed, 'loaded': backend.loaded_models(url) if version else []},
            'config': {'models': cfg['models']},
            'agents': _cached('agents', 30, agents.status), 'pulls': PULLS, 'stats': stats.summary(30)}


def apply_ollama_env() -> str:
    if sys.platform != 'win32':
        return 'Set these variables in the environment of the Ollama service: ' + ' '.join(f'{k}={v}' for k, v in backend.OLLAMA_ENV.items())
    for k, v in backend.OLLAMA_ENV.items():
        subprocess.run(['setx', k, v], capture_output=True, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    return ('Saved as user environment variables (' + ', '.join(backend.OLLAMA_ENV) + '). They apply to every use of Ollama on this '
            'account. Quit Ollama from the tray icon once so it restarts with them.')


class Handler(BaseHTTPRequestHandler):
    server_version = 'readscout'

    def _local(self) -> bool:
        port = self.server.server_address[1]
        if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return False
        origin = self.headers.get('Origin')
        return origin in (None, f'http://127.0.0.1:{port}', f'http://localhost:{port}')

    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == 'application/json' else body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if 'text' in ctype or 'json' in ctype else ''))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._local():
            return self._send(403, {'error': 'forbidden'})
        path, _, query = self.path.partition('?')
        q = dict(p.split('=', 1) for p in query.split('&') if '=' in p)
        if path in ('/', '/setup'):
            html = PAGE.read_text(encoding='utf-8').replace('__TOKEN__', TOKEN).replace('__VIEW__', 'setup' if path == '/setup' else 'usage')
            return self._send(200, html, 'text/html')
        if path == '/api/ping':
            return self._send(200, {'ok': True})
        if path == '/api/state':
            try:
                return self._send(200, state(q.get('vram'), q.get('ram')))
            except Exception as e:  # noqa: BLE001 - the page must get an answer it can show, whatever went wrong
                return self._send(503, {'error': str(e)[:300] or type(e).__name__})
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        # Always consume the request body first: answering before reading it makes some TCP stacks (macOS) reset
        # the connection, and the client never sees the 403.
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(min(length, 65536)) if length > 0 else b''
        if length > 65536 or not self._local() or self.headers.get('X-Readscout-Token') != TOKEN:
            self.close_connection = True
            return self._send(403 if length <= 65536 else 413, {'error': 'forbidden' if length <= 65536 else 'body too large'})
        try:
            body = json.loads(raw or b'{}')
            assert isinstance(body, dict)
        except (ValueError, AssertionError):
            return self._send(400, {'error': 'invalid JSON body'})
        try:
            return self._post(body)
        except Exception as e:  # noqa: BLE001 - always answer with JSON the page can show
            return self._send(500, {'error': str(e)[:300] or type(e).__name__})

    def _post(self, body):
        cfg = paths.load_config()
        if self.path == '/api/pull':
            name = body.get('model', '')
            if name not in hardware.catalog()['models']:
                return self._send(400, {'error': 'model not in catalog'})
            if not PULLS.get(name) or PULLS[name]['done']:
                threading.Thread(target=_pull_worker, args=(name, cfg['ollama_url']), daemon=True).start()
            return self._send(200, {'ok': True})
        if self.path == '/api/models':
            chosen = {}
            for tier in ('fast', 'quality'):
                name = body.get(tier)
                if name is None:
                    continue
                if not isinstance(name, str) or not MODEL_NAME.fullmatch(name) or backend.CLOUD_NAME.search(name):
                    return self._send(400, {'error': f'invalid or cloud model name for {tier}'})
                chosen[tier] = name

            def apply(c):
                for tier, name in chosen.items():
                    c['models'][tier] = {'name': name, 'ctx': c['models'].get(tier, {}).get('ctx', 32768)}
            paths.update_config(apply)
            return self._send(200, {'ok': True})
        if self.path == '/api/agent':
            table = {'install': agents.INSTALL, 'uninstall': agents.UNINSTALL}.get(body.get('action'))
            fn = table.get(body.get('agent')) if table else None
            if fn is None:
                return self._send(400, {'error': 'unknown action or agent'})
            _CACHE.pop('agents', None)
            return self._send(200, {'message': fn()})
        if self.path == '/api/ollama-env':
            return self._send(200, {'message': apply_ollama_env()})
        self._send(404, {'error': 'not found'})

    def log_message(self, *a):
        pass


def serve(port=8765):
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


def running(port=8765) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/ping', timeout=2):
            return True
    except Exception:
        return False
