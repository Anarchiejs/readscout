"""stdio MCP server: three synchronous tools backed by local models (Ollama or llama.cpp). Nothing leaves the machine."""
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import editing, paths, tasks
from .backend import BackendError
from .text import AccessError

mcp = FastMCP('readscout')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# structured_output=False: a `-> str` tool would also get a structured copy of its text, which the client sends the agent too.


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except AccessError as e:
        return f'readscout ERROR: {e}. Do the task yourself.'
    except (BackendError, OSError) as e:
        return f'readscout ERROR: {e}. Do the task yourself (diagnose with `{paths.cli()} doctor`).'


@mcp.tool(annotations=READ, structured_output=False)
def local_ask(paths: list[str], question: str, mode: Literal['find', 'summary'] = 'find', quality: bool | None = None,
              max_items: int = 40, extract: str = '') -> str:
    """Get facts from many or large files without reading them: pass paths (files or folders) and a question, never
    contents. Skip it when one grep or one short file answers. Each fact has its real path:line and a quote verified
    verbatim in the source; unquotable facts are dropped. mode='summary' adds an unverified summary; leave quality unset.
    Use it instead of reading route files: extract=endpoints lists the routes or endpoints of a folder, 'endpoints!A,B' those
    lacking A and B, without auth (textual, not proof). extract (exact, no model) env | routes | endpoints | supabase lists
    every item of that kind, filtering is yours.
    Header status: complete = answer from the receipt, no re-read (a model's sentence is not proof: open the cited
    lines before a security or correctness decision); partial = check only what it lists; undetermined = do it yourself."""
    return _safe(tasks.ask, paths, question, mode, quality, max_items, extract)


@mcp.tool(annotations=READ, structured_output=False)
def local_digest(path: str, focus: str = '') -> str:
    """Use this instead of reading or grepping a long log or command output (redirect a noisy command to a file first):
    every error-like event with path:line, short traces whole, the final lines; a model only for a varied log or a
    focus that is not about failures. Status: complete = cite from the receipt, no re-read; partial = read only the
    lines it names."""
    return _safe(tasks.digest, path, focus)


# destructiveHint is True on purpose: the files are overwritten and the gate commands run on the user's machine with their rights.
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False), structured_output=False)
def local_edit(paths: list[str], instruction: str, gate: list[list[str]] | None = None) -> str:
    """Apply a small, fully specified mechanical change with a local model (docstrings, comments, type hints,
    renames, boilerplate, test scaffolding, applying a decided pattern). Pass paths, not contents: do not
    Read the files first. gate = commands (argv lists, at most 5, no shell, run with the user's rights: only
    the project's own tests or linters) that must pass, e.g. [["python","-m","pytest","-q"]];
    if they fail after one retry the files are restored and the result is ESCALATE. Returns APPLIED with
    the diff to review, or ESCALATE. Never for design, debugging or security-sensitive code."""
    return _safe(editing.edit, paths, instruction, gate)


def main():
    import atexit
    from .backend import unload_used
    from .hardware import ensure_config
    ensure_config()
    atexit.register(unload_used)   # the agent session ended: free the memory now rather than in a minute
    mcp.run()


if __name__ == '__main__':
    main()
