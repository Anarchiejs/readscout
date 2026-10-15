"""readscout command line.

  readscout setup                       open the setup page (hardware, models, agents)
  readscout doctor                      check that everything is installed and wired
  readscout hardware                    detected GPU/RAM and recommended models
  readscout pull [MODEL ...]            download models (default: the recommended ones)
  readscout install-agent claude|codex  register the MCP server and the skill (uninstall-agent to undo)
  readscout ask PATH... -q QUESTION     same as the local_ask tool  [--summary] [--quality]
  readscout digest PATH [-f FOCUS]      same as local_digest
  readscout edit PATH... -i TEXT        same as local_edit  [--gate "cmd args"]...
  readscout stats [--days N]            what delegation read locally instead of your agent
  readscout dashboard                   open the usage page
  readscout warm [fast|quality]         preload a model
  readscout stop                        unload every model now and free the memory
  readscout bench [--models A,B]        measure models on the public benchmark (report to share)
"""
import argparse
import shlex
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__, agents, backend, hardware, paths, stats, tasks


def doctor() -> int:
    ok = True

    def line(good, label, hint=''):
        nonlocal ok
        ok &= bool(good)
        print(f'{"OK  " if good else "FAIL"} {label}' + (f'  -> {hint}' if hint and not good else ''))

    cfg = paths.load_config()
    url = cfg['ollama_url']
    line(backend.ollama_binary() or backend.health(url), 'Ollama installed', 'install it from https://ollama.com, or run the readscout installer')
    version = backend.health(url)
    if not version:
        try:
            backend.ensure_ollama(url)
            version = backend.health(url)
        except backend.BackendError:
            pass
    line(version, f'Ollama running ({version or "not running"})', 'start the Ollama app')
    if version:
        have = backend.installed_models(url)
        for tier, spec in cfg['models'].items():
            line(spec['name'] in have, f'{tier} model {spec["name"]} installed', f'readscout pull {spec["name"]}')
    line(paths.config_file().exists(), f'config at {paths.config_file()}', 'readscout setup')
    st = agents.status()
    if st['claude_cli']:
        line(st['claude_wired'], 'Claude Code wired (plugin, or MCP + skill)', 'readscout install-agent claude')
    if st['codex_config']:
        line(st['codex_mcp'] and st['codex_skill'], 'Codex wired (MCP + skill)', 'readscout install-agent codex')
    if not st['claude_cli'] and not st['codex_config']:
        line(False, 'no coding agent found', 'install Claude Code or Codex, then readscout install-agent ...')
    print('\nAll good.' if ok else '\nFix the FAIL lines above.')
    return 0 if ok else 1


def print_stats(days):
    s = stats.summary(days)
    print(f"{s['calls']} call(s) in {days} days: {s['reads']} read(s), {s['edits']} edit(s), {s['edits_applied']} applied")
    print(f"{s['kb_read_locally']} KB read locally, {s['kb_returned']} KB returned -> about {s['tokens_avoided_est']:,} tokens kept out of your agent's context")
    print(f"verified findings {s['verified']}, dropped {s['dropped']}; empty answers {s['empty_answers']}; {s['seconds_local']} s of local compute")
    for m, v in s['by_model'].items():
        print(f"  {m:22} {v['calls']} call(s), {v['seconds']:.0f} s")


def print_hardware():
    hw = hardware.detect()
    print(f'GPU: {hw.gpu} ({hw.vram_gb} GB, via {hw.source})   RAM: {hw.ram_gb} GB   OS: {hw.os}')
    for tier, rec in hardware.recommend(hw.vram_gb, hw.ram_gb).items():
        print(f"{tier:8} {rec['model']:14} {rec['download_gb']} GB  {rec['why']}")


def pull(models: list[str]):
    cfg = paths.load_config()
    backend.ensure_ollama(cfg['ollama_url'])
    if not models:
        hw = hardware.detect()
        rec = hardware.recommend(hw.vram_gb, hw.ram_gb)
        models = sorted({r['model'] for r in rec.values()})
        paths.update_config(lambda c: c.__setitem__('models', hardware.models_config(rec)))
    for m in models:
        last = [0.0]

        def progress(status, done, total):
            if time.time() - last[0] > 1 or status == 'success':
                last[0] = time.time()
                pct = f' {100 * done / total:5.1f}%' if total else ''
                print(f'\r{m}: {status}{pct}'.ljust(70), end='', flush=True)
        backend.pull(m, cfg['ollama_url'], progress)
        print()


def open_page(path='/setup', port=8765):
    from . import web
    if not web.running(port):
        exe = Path(sys.executable)
        pyw = exe.with_name('pythonw.exe') if sys.platform == 'win32' and exe.with_name('pythonw.exe').exists() else exe
        flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        subprocess.Popen([str(pyw), '-m', 'readscout.cli', 'serve-web', '--port', str(port)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
                         start_new_session=sys.platform != 'win32', close_fds=True)
        for _ in range(50):
            if web.running(port):
                break
            time.sleep(0.2)
    url = f'http://127.0.0.1:{port}{path}'
    webbrowser.open(url)
    print(f'Opened {url}')


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(prog='readscout', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version', action='version', version=f'readscout {__version__}')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('setup')
    sub.add_parser('dashboard')
    p = sub.add_parser('serve-web')
    p.add_argument('--port', type=int, default=8765)
    sub.add_parser('doctor')
    sub.add_parser('hardware')
    p = sub.add_parser('pull')
    p.add_argument('models', nargs='*')
    for name in ('install-agent', 'uninstall-agent'):
        p = sub.add_parser(name)
        p.add_argument('agent', choices=['claude', 'codex'])
    p = sub.add_parser('ask')
    p.add_argument('paths', nargs='+')
    p.add_argument('-q', '--question', required=True)
    p.add_argument('--summary', action='store_true')
    p.add_argument('--quality', action='store_true')
    p = sub.add_parser('digest')
    p.add_argument('path')
    p.add_argument('-f', '--focus', default='')
    p = sub.add_parser('edit')
    p.add_argument('paths', nargs='+')
    p.add_argument('-i', '--instruction', required=True)
    p.add_argument('--gate', action='append', default=None, help='check command, repeatable')
    p = sub.add_parser('stats')
    p.add_argument('--days', type=int, default=30)
    p = sub.add_parser('bench')
    p.add_argument('--models', default='', help='comma-separated Ollama models (default: your fast and quality models)')
    p.add_argument('--only', default='', help='comma-separated families')
    p.add_argument('--no-edits', action='store_true')
    sub.add_parser('stop')
    p = sub.add_parser('warm')
    p.add_argument('tier', nargs='?', default='fast', choices=['fast', 'quality'])
    a = ap.parse_args(argv)
    hardware.ensure_config()

    if a.cmd == 'setup':
        open_page('/setup')
    elif a.cmd == 'dashboard':
        open_page('/')
    elif a.cmd == 'serve-web':
        from . import web
        web.serve(a.port)
    elif a.cmd == 'doctor':
        return doctor()
    elif a.cmd == 'hardware':
        print_hardware()
    elif a.cmd == 'pull':
        pull(a.models)
    elif a.cmd == 'install-agent':
        print(agents.INSTALL[a.agent]())
    elif a.cmd == 'uninstall-agent':
        print(agents.UNINSTALL[a.agent]())
    elif a.cmd == 'ask':
        print(tasks.ask(a.paths, a.question, 'summary' if a.summary else 'find', True if a.quality else None))
    elif a.cmd == 'digest':
        print(tasks.digest(a.path, a.focus))
    elif a.cmd == 'edit':
        gate = [[t.strip('"') for t in shlex.split(g, posix=sys.platform != 'win32')] for g in a.gate] if a.gate else None
        print(tasks.edit(a.paths, a.instruction, gate))
    elif a.cmd == 'stats':
        print_stats(a.days)
    elif a.cmd == 'bench':
        from .bench import runner
        cfg = paths.load_config()
        models = [m for m in a.models.split(',') if m] or list(dict.fromkeys(s['name'] for s in cfg['models'].values()))
        report = runner.run(models, [f for f in a.only.split(',') if f] or None, not a.no_edits)
        print()
        print(runner.markdown(report))
        print(f"\nFull results: {report['file']}")
        print('Share them: https://github.com/Anarchiejs/readscout/issues/new?title=bench')
    elif a.cmd == 'stop':
        url = paths.load_config()['ollama_url']
        if not backend.health(url):
            print('Ollama is not running: no model is in memory.')
        else:
            names = backend.unload_all(url)
            left = backend.loaded_models(url)
            print(f'Unloaded: {", ".join(n for n in names if n not in left)}' if names else 'No model was loaded.')
            if left:
                print(f'STILL LOADED (could not free): {", ".join(left)}. Quit Ollama from its tray icon or run `ollama stop <model>`.')
                return 1
    elif a.cmd == 'warm':
        cfg, _ = tasks.load_config()
        m = tasks.model_for(cfg, a.tier)
        t = time.time()
        backend.chat(m, 'Reply with {"ok": true}.', 'ping', {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}, max_tokens=10)
        print(f'{m.name} loaded in {time.time() - t:.0f} s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
