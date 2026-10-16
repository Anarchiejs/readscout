"""The MCP tools: errors become short instructions for the agent, and the tools reach the right operation."""
import asyncio

from readscout import editing, server, tasks
from readscout.backend import BackendError
from readscout.text import AccessError


def test_errors_tell_the_agent_to_do_it_itself(monkeypatch):
    monkeypatch.setenv('READSCOUT_CLI', 'readscout')

    def refuse():
        raise AccessError('Sensitive or binary file refused: .env')

    def down():
        raise BackendError('Ollama unreachable')
    assert server._safe(refuse) == 'readscout ERROR: Sensitive or binary file refused: .env. Do the task yourself.'
    out = server._safe(down)
    assert out.startswith('readscout ERROR: Ollama unreachable') and '`readscout doctor`' in out
    assert 'Do the task yourself' in server._safe(lambda: (_ for _ in ()).throw(PermissionError('denied')))
    assert server._safe(lambda x: x * 2, 21) == 42


def test_tools_call_the_operations(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, 'ask', lambda *a: calls.append(('ask', a)) or 'ASK')
    monkeypatch.setattr(tasks, 'digest', lambda *a: calls.append(('digest', a)) or 'DIGEST')
    monkeypatch.setattr(editing, 'edit', lambda *a: calls.append(('edit', a)) or 'EDIT')
    assert server.local_ask(['src'], 'where?') == 'ASK'
    assert server.local_digest('build.log', 'tests') == 'DIGEST'
    assert server.local_edit(['a.py'], 'add types', [['pytest']]) == 'EDIT'
    assert calls == [('ask', (['src'], 'where?', 'find', None, 40, '')), ('digest', ('build.log', 'tests')),
                     ('edit', (['a.py'], 'add types', [['pytest']]))]


def test_tools_are_registered_with_honest_hints():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert set(tools) == {'local_ask', 'local_digest', 'local_edit'}
    assert tools['local_ask'].annotations.readOnlyHint and tools['local_digest'].annotations.readOnlyHint
    assert tools['local_edit'].annotations.destructiveHint and not tools['local_edit'].annotations.readOnlyHint
