"""stdio MCP server: three synchronous tools backed by local models. Nothing leaves the machine."""
from typing import Literal

from mcp.server.fastmcp import FastMCP

from . import paths, tasks
from .backend import BackendError
from .text import AccessError

mcp = FastMCP('readscout')
READ = {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except AccessError as e:
        hint = ''
        if 'registered project' in str(e):
            hint = f' If the user agrees, allow the project folder with `{paths.cli()} register <id> <folder>`, then retry.'
        return f'readscout ERROR: {e}.{hint} Otherwise do the task yourself.'
    except (BackendError, OSError) as e:
        return f'readscout ERROR: {e}. Do the task yourself (diagnose with `{paths.cli()} doctor`).'


@mcp.tool(annotations=READ)
def local_ask(paths: list[str], question: str, mode: Literal['find', 'summary'] = 'find', quality: bool | None = None,
              max_items: int = 40) -> str:
    """Read files or directories with a local model so you don't have to; get back a short answer.
    Use instead of Read/Grep when you need facts from large or many files but not the files themselves
    ("which routes lack auth", "where is X handled", "what does this module do").
    Each fact comes with a quote verified verbatim in the source and its real path:line; facts the model
    could not quote are dropped. mode='summary' adds a short unverified summary. quality: leave unset (auto:
    the bigger model for negative questions or when the fast one finds nothing), True to force it.
    Do not use for decisions (security, correctness) without opening the cited lines."""
    return _safe(tasks.ask, paths, question, mode, quality, max_items)


@mcp.tool(annotations=READ)
def local_digest(path: str, focus: str = '') -> str:
    """Triage a long log or command output file (CI log, test output, server log) locally.
    Returns the root-cause error and distinct failures with verified path:line quotes, instead of
    loading the whole file into context. Tip: redirect a noisy command to a file, then digest it."""
    return _safe(tasks.digest, path, focus)


@mcp.tool(annotations={'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': False})
def local_edit(paths: list[str], instruction: str, gate: list[list[str]] | None = None) -> str:
    """Apply a small, fully specified mechanical change with a local model (docstrings, comments, type hints,
    renames, boilerplate, test scaffolding, applying a decided pattern). Pass paths, not contents: do not
    Read the files first. gate = commands (argv lists) that must pass, e.g. [["python","-m","pytest","-q"]];
    if they fail after one retry the files are restored and the result is ESCALATE. Returns APPLIED with
    the diff to review, or ESCALATE. Never for design, debugging or security-sensitive code."""
    return _safe(tasks.edit, paths, instruction, gate)


def main():
    from .hardware import ensure_config
    ensure_config()
    mcp.run()


if __name__ == '__main__':
    main()
