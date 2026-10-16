"""Wire readscout into coding agents: Claude Code (MCP + skill) and Codex (MCP + skill). Always reversible."""
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from .paths import PACKAGE, cli

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
SKILL = PACKAGE / 'skill' / 'SKILL.md'
CLAUDE_SKILL = Path.home() / '.claude' / 'skills' / 'readscout' / 'SKILL.md'
CODEX_SKILL = Path.home() / '.agents' / 'skills' / 'readscout' / 'SKILL.md'
CODEX_CONFIG = Path.home() / '.codex' / 'config.toml'
# The table and its sub-tables ([mcp_servers.readscout.env]...), up to the next unrelated table; any line ending.
CODEX_SECTION = re.compile(r'(?ms)^[ \t]*\[mcp_servers\.readscout(?:\.[^\]\n]*)?\][ \t]*\r?\n.*?(?=^[ \t]*\[(?!mcp_servers\.readscout[\].])|\Z)')


GATE_NOTICE = ('local_edit runs the check commands your agent picks, with your rights, even if the agent itself may '
               'not use a shell. If you restrict your agent, run `readscout gate off`.')


def gate_notice() -> str:
    from . import paths
    return f'\nNote: {GATE_NOTICE}' if paths.gate_allowed(paths.load_config()) else ''


def server_command() -> list[str]:
    """How an agent should start the MCP server: the installed entry point, else this interpreter."""
    exe = shutil.which('readscout-mcp')
    return [exe] if exe else [sys.executable, '-m', 'readscout.server']


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120,
                          stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)


def _copy_skill(dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SKILL, dest)
    refs = SKILL.parent / 'references'
    if refs.is_dir():       # the core points to these files by relative path
        shutil.copytree(refs, dest.parent / 'references', dirs_exist_ok=True)


def status() -> dict:
    claude = shutil.which('claude')
    out = {'claude_cli': bool(claude), 'claude_mcp': False, 'claude_plugin': False, 'claude_skill': CLAUDE_SKILL.exists() and CLAUDE_SKILL.read_bytes() == SKILL.read_bytes(),
           'codex_config': CODEX_CONFIG.exists(), 'codex_mcp': False,
           'codex_skill': CODEX_SKILL.exists() and CODEX_SKILL.read_bytes() == SKILL.read_bytes()}
    if claude:
        out['claude_mcp'] = 'readscout' in _run([claude, 'mcp', 'get', 'readscout']).stdout
        # Installed as a Claude Code plugin: the plugin brings its own MCP server and skill.
        out['claude_plugin'] = 'readscout@' in _run([claude, 'plugin', 'list']).stdout
    out['claude_wired'] = (out['claude_mcp'] and out['claude_skill']) or out['claude_plugin']
    if CODEX_CONFIG.exists():
        out['codex_mcp'] = bool(CODEX_SECTION.search(_read_codex()))
    return out


def install_claude() -> str:
    claude = shutil.which('claude')
    if not claude:
        return 'Claude Code CLI not found (install it, then run `readscout install-agent claude`).'
    _run([claude, 'mcp', 'remove', 'readscout', '-s', 'user'])
    r = _run([claude, 'mcp', 'add', '-s', 'user', 'readscout', '--', *server_command()])
    if r.returncode:
        return f'claude mcp add failed: {(r.stderr or r.stdout).strip()[:300]}'
    _copy_skill(CLAUDE_SKILL)
    return f'Claude Code: MCP server "readscout" added (user scope), skill copied to {CLAUDE_SKILL}. Restart Claude Code.' + gate_notice()


def uninstall_claude() -> str:
    claude = shutil.which('claude')
    if claude:
        _run([claude, 'mcp', 'remove', 'readscout', '-s', 'user'])
    shutil.rmtree(CLAUDE_SKILL.parent, ignore_errors=True)
    return 'Claude Code: readscout removed.'


def _toml_str(s: str) -> str:
    return '"' + s.replace('\\', '/').replace('"', '\\"') + '"'


def _valid_toml(text: str) -> bool:
    try:
        tomllib.loads(text)
        return True
    except tomllib.TOMLDecodeError:
        return False


def _read_codex() -> str:
    return CODEX_CONFIG.read_bytes().decode('utf-8').replace('\r\n', '\n') if CODEX_CONFIG.exists() else ''


def _write_codex(text: str):
    """Write the config, keeping a one-time backup of the user's file and its line endings."""
    crlf = CODEX_CONFIG.exists() and b'\r\n' in CODEX_CONFIG.read_bytes()
    backup = CODEX_CONFIG.with_name(CODEX_CONFIG.name + '.readscout-bak')
    if CODEX_CONFIG.exists() and not backup.exists():
        shutil.copyfile(CODEX_CONFIG, backup)
    tmp = CODEX_CONFIG.with_name(CODEX_CONFIG.name + '.readscout-tmp')
    tmp.write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('utf-8'))
    tmp.replace(CODEX_CONFIG)


def install_codex() -> str:
    CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    text = _read_codex()
    if not _valid_toml(text):
        return f'Codex: {CODEX_CONFIG} is not valid TOML, nothing was changed. Fix it, then run `{cli()} install-agent codex` again.'
    cmd = server_command()
    section = f'[mcp_servers.readscout]\ncommand = {_toml_str(cmd[0])}\nargs = [{", ".join(_toml_str(a) for a in cmd[1:])}]\n\n'
    new = CODEX_SECTION.sub('', text).rstrip() + ('\n\n' if text.strip() else '') + section
    if not _valid_toml(new):
        return (f'Codex: could not add the server to {CODEX_CONFIG} safely (it already defines mcp_servers.readscout in another form). '
                f'Nothing was changed. Remove that entry or add this section yourself:\n{section}')
    _write_codex(new)
    _copy_skill(CODEX_SKILL)
    return f'Codex: [mcp_servers.readscout] written to {CODEX_CONFIG} (backup: {CODEX_CONFIG.name}.readscout-bak), skill copied to {CODEX_SKILL}. Restart Codex.' + gate_notice()


def uninstall_codex() -> str:
    if CODEX_CONFIG.exists():
        text = _read_codex()
        new = CODEX_SECTION.sub('', text).rstrip() + '\n'
        if not (_valid_toml(text) and _valid_toml(new)):
            return f'Codex: {CODEX_CONFIG} is not valid TOML, nothing was changed.'
        _write_codex(new)
    shutil.rmtree(CODEX_SKILL.parent, ignore_errors=True)
    return 'Codex: readscout removed.'


INSTALL = {'claude': install_claude, 'codex': install_codex}
UNINSTALL = {'claude': uninstall_claude, 'codex': uninstall_codex}
