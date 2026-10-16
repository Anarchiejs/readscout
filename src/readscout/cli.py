"""readscout command line.

  readscout setup                       open the setup page (hardware, models, agents)
  readscout doctor                      check that everything is installed and wired
  readscout hardware                    detected GPU/RAM and recommended models
  readscout pull [MODEL ...]            download models (default: the recommended ones)
  readscout install-agent claude|codex  register the MCP server and the skill (uninstall-agent to undo)
  readscout ask PATH... -q QUESTION     same as the local_ask tool  [--summary] [--quality]
  readscout digest PATH [-f FOCUS]      same as local_digest
  readscout edit PATH... -i TEXT        same as local_edit  [--gate "cmd args"]...
  readscout folders [add|remove PATH...] limit the local models to these folders (empty list: any folder)
  readscout gate on|off                 allow or forbid the gate commands of local_edit
  readscout engine [ollama|llamacpp]    which engine runs each model  [--fast X.gguf|ollama:NAME|ollama] [--quality ...] [--args "..."]
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

from . import __version__, agents, backend, editing, hardware, llamacpp, paths, stats, tasks

def doctor() -> int:
    ok = True

    def line(good, label, hint=''):
        nonlocal ok
        ok &= bool(good)
        print(f'{"OK  " if good else "FAIL"} {label}' + (f'  -> {hint}' if hint and not good else ''))

    cfg = paths.load_config()
    on_llamacpp = llamacpp.tiers(cfg)
    if cfg.get('engine') == 'llamacpp':
        doctor_llamacpp(cfg, line)
    if any(t not in on_llamacpp for t in cfg['models']):
        doctor_ollama(cfg, line, [t for t in cfg['models'] if t not in on_llamacpp])
    line(paths.config_file().exists(), f'config at {paths.config_file()}', 'readscout setup')
    allowed = paths.allowed_folders(cfg)
    print(f'     folders: {", ".join(str(f) for f in allowed) if allowed else "any folder the agent names"}'
          f'; local_edit gate commands: {"on" if paths.gate_allowed(cfg) else "off"}')
    if paths.gate_allowed(cfg):
        print(f'     note: {agents.GATE_NOTICE}')
    st = agents.status()
    if st['claude_cli']:
        line(st['claude_wired'], 'Claude Code wired (plugin, or MCP + skill)', 'readscout install-agent claude')
    if st['codex_config']:
        line(st['codex_mcp'] and st['codex_skill'], 'Codex wired (MCP + skill)', 'readscout install-agent codex')
    if not st['claude_cli'] and not st['codex_config']:
        line(False, 'no coding agent found', 'install Claude Code or Codex, then readscout install-agent ...')
    print('\nAll good.' if ok else '\nFix the FAIL lines above.')
    return 0 if ok else 1


def doctor_llamacpp(cfg, line):
    exe = llamacpp.binary(cfg)
    line(exe, f'llama-server found ({exe or "not found"})', 'winget install llama.cpp / brew install llama.cpp, or readscout engine ollama')
    if exe:
        found = llamacpp.devices(cfg)
        print('     llama-server devices: ' + (', '.join(f'{d} {n} ({mib // 1024} GB)' for d, n, mib in found) or 'none (CPU only)'))
        for note in llamacpp.device_notes(found, hardware.detect().source):
            print(f'     note: {note}')
    tiers = llamacpp.tiers(cfg)
    line(tiers, 'a model configured for llama.cpp', 'readscout engine llamacpp --quality <file.gguf>, or readscout engine ollama')
    for tier, spec in tiers.items():
        if spec.get('gguf'):
            f = Path(spec['gguf']).expanduser()
            line(f.is_file(), f'{tier} model file {f}', f'readscout engine llamacpp --{tier} <file.gguf>')
        elif spec.get('url'):
            line(llamacpp.probe(spec['url']) == 'ok', f'{tier} model: your llama-server at {spec["url"]} answers', 'start it')
        else:
            line(False, f'{tier} model: no .gguf file or url', f'readscout engine llamacpp --{tier} <file.gguf>')


def doctor_ollama(cfg, line, tiers):
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
        for tier in tiers:
            spec = cfg['models'][tier]
            line(spec['name'] in have, f'{tier} model {spec["name"]} installed', f'readscout pull {spec["name"]}')


def print_stats(days):
    s = stats.summary(days)
    print(f"{s['calls']} call(s) in {days} days: {s['reads']} read(s), {s['edits']} edit(s), {s['edits_applied']} applied")
    print(f"{s['kb_read_locally']} KB read locally, {s['kb_returned']} KB returned -> about {s['tokens_avoided_est']:,} token-equivalent local text reduction")
    print('Estimate only, not measured agent savings: grep choices and tool overhead are not included.')
    print(f"verified findings {s['verified']}, dropped {s['dropped']}; empty answers {s['empty_answers']}; {s['seconds_local']} s of local compute")
    for m, v in s['by_model'].items():
        print(f"  {m:22} {v['calls']} call(s), {v['seconds']:.0f} s")


def folders(action: str | None, given: list[str]) -> int:
    if action and not given:
        print(f'readscout folders {action} needs at least one folder')
        return 2
    wanted = list(dict.fromkeys(Path(f).expanduser().resolve() for f in given))
    missing = [str(f) for f in wanted if action == 'add' and not f.is_dir()]
    if missing:
        print(f'Not a folder: {", ".join(missing)}')
        return 1

    def apply(c):
        current = [Path(f) for f in c.get('allowed_folders') or []]
        if action == 'add':
            current += [f for f in wanted if f not in current]
        elif action == 'remove':
            current = [f for f in current if f not in wanted]
        c['allowed_folders'] = [str(f) for f in current]
    cfg = paths.update_config(apply) if action else paths.load_config()
    allowed = paths.allowed_folders(cfg)
    if allowed:
        print('The local models only read and write files in:')
        for f in allowed:
            print(f'  {f}')
    else:
        print('No folder list: the local models read the files the agent names, in any folder (sensitive files excepted).')
    return 0


def set_gate(state: str):
    paths.update_config(lambda c: c.__setitem__('allow_gate', state == 'on'))
    print('local_edit may run gate commands (the project tests) chosen by the agent.' if state == 'on' else
          'local_edit gate commands are off: the agent must run its checks itself.')


def show_engines(cfg) -> None:
    on_llamacpp = llamacpp.tiers(cfg)
    for tier in dict.fromkeys([*cfg['models'], *on_llamacpp]):
        spec = on_llamacpp.get(tier)
        if spec:
            print(f'  {tier:8} llamacpp  {spec.get("gguf") or spec.get("url")}  ctx {spec.get("ctx", hardware.DEFAULT_CTX)}')
        else:
            print(f'  {tier:8} ollama    {cfg["models"][tier]["name"]}')
    if on_llamacpp:
        lc = llamacpp.settings(cfg)
        print(f'  llama-server: {llamacpp.binary(cfg) or "NOT FOUND"}' + (f', extra flags: {" ".join(lc["args"])}' if lc.get('args') else ''))


def engine(name, fast, quality, args, binary) -> int:
    if name is None:
        print('engine per model:')
        show_engines(paths.load_config())
        return 0
    if name == 'ollama':
        paths.update_config(lambda c: c.__setitem__('engine', 'ollama'))
        print('engine: ollama for every model. Restart your coding agent so its readscout server uses it.')
        return 0
    given: dict = {}
    for tier, value in (('fast', fast), ('quality', quality)):
        if not value:
            continue
        if value == 'ollama':
            given[tier] = None                                  # this tier goes back to Ollama
        elif value.startswith(('http://', 'https://')):
            try:
                backend.Model('llama-server', url=value)        # loopback only
            except backend.BackendError as e:
                print(e)
                return 1
            given[tier] = {'url': value}
        elif value.startswith('ollama:'):
            try:
                given[tier] = {'gguf': llamacpp.ollama_gguf(value.removeprefix('ollama:')), 'name': value.removeprefix('ollama:')}
            except (backend.BackendError, OSError, subprocess.SubprocessError) as e:
                print(e)
                return 1
        else:
            f = Path(value).expanduser().resolve()
            if not f.is_file() or f.suffix.lower() != '.gguf':
                print(f'Not a .gguf file: {value}')
                return 1
            given[tier] = {'gguf': str(f)}

    def apply(c):
        lc = c.setdefault('llamacpp', {})
        models = lc.setdefault('models', {})
        for tier, spec in given.items():
            if spec is None:
                models.pop(tier, None)
                continue
            spec['ctx'] = c['models'].get(tier, {}).get('ctx', hardware.DEFAULT_CTX)
            models[tier] = spec
        if args is not None:
            lc['args'] = shlex.split(args, posix=sys.platform != 'win32')
        if binary:
            lc['binary'] = str(Path(binary).expanduser().resolve())
        c['engine'] = 'llamacpp' if models else 'ollama'
    cfg = paths.update_config(apply)
    if not llamacpp.tiers(cfg):
        print('engine: ollama for every model. To run one on llama.cpp: readscout engine llamacpp --quality ollama:gemma4:26b')
        return 0 if any(v is None for v in given.values()) else 1
    print('engine per model:')
    show_engines(cfg)
    print('readscout starts llama-server itself when a llama.cpp model is needed and stops it when idle.'
          + (' The other models stay on Ollama; the two engines take turns on the GPU.'
             if any(t not in llamacpp.tiers(cfg) for t in cfg['models']) else ''))
    if not llamacpp.binary(cfg):
        print('llama-server was not found: install llama.cpp (winget install llama.cpp, brew install llama.cpp) or pass --binary')
    print('Restart your coding agent so its readscout server uses the new engines.')
    return 0


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
    p = sub.add_parser('folders')
    p.add_argument('action', nargs='?', choices=['add', 'remove'])
    p.add_argument('folders', nargs='*')
    p = sub.add_parser('gate')
    p.add_argument('state', choices=['on', 'off'])
    p = sub.add_parser('engine')
    p.add_argument('name', nargs='?', choices=['ollama', 'llamacpp'])
    p.add_argument('--fast', help='run the fast model on llama.cpp: a .gguf file, ollama:<model> (reuse what Ollama downloaded), '
                   'or the URL of your own llama-server; "ollama" puts it back on Ollama. A model not named keeps its engine')
    p.add_argument('--quality', help='quality model: same choices as --fast')
    p.add_argument('--args', default=None, help='extra llama-server flags, e.g. "--n-cpu-moe 30"')
    p.add_argument('--binary', help='path of llama-server when it is not on the PATH')
    p = sub.add_parser('stats')
    p.add_argument('--days', type=int, default=30)
    p = sub.add_parser('bench')
    p.add_argument('--models', default='', help='comma-separated Ollama models, or llamacpp:fast, llamacpp:quality, '
                   'llamacpp:<file.gguf> (default: your fast and quality models, each on its engine)')
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
        print(editing.edit(a.paths, a.instruction, gate))
    elif a.cmd == 'folders':
        return folders(a.action, a.folders)
    elif a.cmd == 'gate':
        set_gate(a.state)
    elif a.cmd == 'engine':
        return engine(a.name, a.fast, a.quality, a.args, a.binary)
    elif a.cmd == 'stats':
        print_stats(a.days)
    elif a.cmd == 'bench':
        from .bench import runner
        cfg = paths.load_config()
        default = list(dict.fromkeys('llamacpp:' + t if llamacpp.engine_of(cfg, t) == 'llamacpp' else s['name']
                                     for t, s in cfg['models'].items()))
        models = [m for m in a.models.split(',') if m] or default
        report = runner.run(models, [f for f in a.only.split(',') if f] or None, not a.no_edits)
        print()
        print(runner.markdown(report))
        print(f"\nFull results: {report['file']}")
        print('Share them: https://github.com/Anarchiejs/readscout/issues/new?title=bench')
    elif a.cmd == 'stop':
        served = llamacpp.stop_all()
        if served:
            print(f'Stopped llama-server ({served}).')
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
