"""Validate Codex transport/tool execution locally, with no online model or auth.

Run after token_savings.py prepare: python scripts/token_savings_probe.py mcp
The loopback Responses fixture requests one real reading call, then ends the turn.
Synthetic usage counters validate CLI accounting; they are never benchmark data.
"""
import argparse
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import token_savings as harness


def probe(work, kind='mcp'):
    from readscout import backend
    preexisting = set(backend.loaded_models('http://127.0.0.1:11434')) if kind == 'mcp' else set()
    pinned = json.loads((work / 'meta.json').read_text())
    home = work / 'probe-home'
    (home / '.codex').mkdir(parents=True, exist_ok=True)
    source_config = work / ('B' if kind == 'mcp' else 'A') / '.codex/config.toml'
    config = source_config.read_text(encoding='utf-8').split('[mcp_servers.readscout.env]')[0]
    metrics_dir = Path(tempfile.mkdtemp(prefix='probe-metrics-', dir=work))
    if kind == 'mcp':
        config += '\n[mcp_servers.readscout.env]\nREADSCOUT_HOME = ' + json.dumps(metrics_dir.as_posix()) + '\n'
    (home / '.codex/config.toml').write_text(config, encoding='utf-8')
    # Deliberately do not copy auth.json or provide any credential to this provider.
    fixture = work / 'probe-fixture'
    fixture.mkdir(exist_ok=True)
    (fixture / 'read.txt').write_text('unique_value = 12345\n', encoding='ascii')
    if kind == 'shell':
        harness.command(['icacls', str(fixture), '/grant', '*S-1-1-0:(OI)(CI)(RX)', '/T', '/Q'])
    requests = []
    tool_code = ('text(await tools.mcp__readscout__local_ask({paths:["read.txt"],'
                 'question:"Which unique_value is defined? Quote its defining line."}));' if kind == 'mcp' else
                 'text(await tools.exec_command({cmd:"Get-Content -LiteralPath read.txt",login:false}));')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            output = ({'id': 'fixture_call', 'type': 'custom_tool_call', 'call_id': 'fixture_call',
                       'namespace': 'functions', 'name': 'exec', 'input': tool_code} if len(requests) == 1 else
                      {'id': 'fixture_message', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                       'content': [{'type': 'output_text', 'text': 'DONE', 'annotations': []}]})
            response = {'id': 'fixture_response', 'object': 'response', 'status': 'completed',
                        'model': pinned['model'], 'output': [output], 'usage': {
                            'input_tokens': 100, 'input_tokens_details': {'cached_tokens': 25},
                            'output_tokens': 50, 'output_tokens_details': {'reasoning_tokens': 10}, 'total_tokens': 150}}
            events = [
                ('response.created', {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}}),
                ('response.output_item.added', {'type': 'response.output_item.added', 'output_index': 0, 'item': output}),
                ('response.output_item.done', {'type': 'response.output_item.done', 'output_index': 0, 'item': output}),
                ('response.completed', {'type': 'response.completed', 'response': response}),
            ]
            body = ''.join(f'event: {name}\ndata: {json.dumps(event)}\n\n' for name, event in events).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = harness.environment(work, 'probe-home', metrics_dir)
    args = harness.exec_args(pinned['model'], pinned['effort'], fixture, work / 'probe-answer.txt')
    args += ['-c', 'model_provider="fixture"', '-c', 'model_providers.fixture.name="fixture"',
             '-c', 'model_providers.fixture.wire_api="responses"', '-c',
             'model_providers.fixture.requires_openai_auth=false', '-c',
             f'model_providers.fixture.base_url="http://127.0.0.1:{server.server_port}"', 'Local transport fixture.']
    try:
        result = harness.command(args, env, timeout=90)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    parsed = harness.parse_events(result.stdout)
    metrics = ([json.loads(line) for line in (metrics_dir / 'metrics.jsonl').read_text().splitlines()]
               if (metrics_dir / 'metrics.jsonl').exists() else [])
    successful_shell = any(e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'command_execution'
                           and e['item'].get('exit_code') == 0 and 'unique_value = 12345' in e['item'].get('aggregated_output', '')
                           for e in (json.loads(line) for line in result.stdout.splitlines() if line.strip()))
    success = bool(result.returncode == 0 and len(requests) == 2 and
                   (metrics and any(m.get('verified') for m in metrics) and parsed['mcp_calls'].get('readscout.local_ask')
                    if kind == 'mcp' else successful_shell))
    report = {'synthetic': True, 'online_model_used': False, 'kind': kind, 'success': success,
              'requests': len(requests), 'usage': parsed['usage'], 'metrics': metrics,
              'mcp_calls': parsed['mcp_calls'], 'shell_calls': parsed['shell_calls']}
    harness.write_json(work / 'probe-result.json', report)
    if kind == 'mcp':
        # This isolated model use must not leak into subsequent measured sessions.
        for model in {m['model'] for m in metrics} - preexisting:
            backend.unload(model, 'http://127.0.0.1:11434')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['mcp', 'shell'])
    report = probe(harness.state(), parser.parse_args().kind)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['success'] else 1)
