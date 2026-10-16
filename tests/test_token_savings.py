"""Pure parsing and blind grading checks for the standalone experiment harness."""
import importlib.util
import json
from pathlib import Path

from readscout.bench.generate import Task

spec = importlib.util.spec_from_file_location('token_savings', Path(__file__).parents[1] / 'scripts/token_savings.py')
assert spec and spec.loader
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_usage_and_calls_are_not_double_counted():
    item = {'type': 'command_execution', 'aggregated_output': 'hello'}
    events = [{'type': 'item.started', 'item': item}, {'type': 'item.completed', 'item': item},
              {'type': 'turn.completed', 'usage': {'input_tokens': 123, 'cached_input_tokens': 100,
                                                'output_tokens': 7, 'reasoning_output_tokens': 2}}]
    parsed = harness.parse_events('\n'.join(map(json.dumps, events)))
    assert parsed['shell_calls'] == 1
    assert parsed['shell_chars'] == 5
    assert parsed['usage']['input_tokens'] == 123
    assert parsed['usage']['reasoning_output_tokens'] == 2
    assert 'reasoning_output_tokens' not in harness.parse_events('')['usage']


def test_mcp_and_invalid_events():
    row = {'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'server': 'readscout',
                                           'tool': 'local_ask', 'result': {'content': []}}}
    parsed = harness.parse_events(json.dumps(row) + '\nnot json')
    assert parsed['mcp_calls'] == {'readscout.local_ask': 1}
    assert parsed['invalid_events'] == ['not json']


def test_normalize_paths(tmp_path):
    assert harness.normalize_path(str(tmp_path / 'src/test.py'), tmp_path) == 'src/test.py'
    assert harness.normalize_path('.\\src\\test.py', tmp_path) == 'src/test.py'
    import pytest
    with pytest.raises(ValueError):
        harness.normalize_path('../escape.py', tmp_path)


def test_grade_relocates_and_penalizes_unverifiable(tmp_path):
    (tmp_path / 'source.py').write_text('header\nvalue = TARGET_VALUE\n')
    task = Task('example', 'env_vars', 'easy', tmp_path, ['source.py'], 'find',
                [{'path': 'source.py', 'line': 2, 'key': 'TARGET_VALUE'}])
    correct = {'path': 'source.py', 'line': 99, 'quote': 'value = TARGET_VALUE', 'answer': 'TARGET_VALUE'}
    grade = harness.grade_answer(task, {'findings': [correct]})
    assert grade['f1'] == 1
    assert grade['locations'][0]['actual'] == 2
    bad = {**correct, 'quote': 'invented quote'}
    grade = harness.grade_answer(task, {'findings': [correct, bad]})
    assert grade['unverifiable'] == 1
    assert grade['precision'] == 0.5
    assert grade['f1'] == 0.667
    assert grade['benchmark_score']['f1'] == 1


def test_directory_scope(tmp_path):
    (tmp_path / 'folder').mkdir()
    (tmp_path / 'folder/source.py').write_text('value = TARGET_VALUE\n')
    task = Task('example', 'env_vars', 'easy', tmp_path, ['folder'], 'find',
                [{'path': 'folder/source.py', 'line': 1, 'key': 'TARGET_VALUE'}])
    finding = {'path': 'folder/source.py', 'line': 1, 'quote': 'value = TARGET_VALUE', 'answer': 'TARGET_VALUE'}
    assert harness.grade_answer(task, {'findings': [finding]})['f1'] == 1


def test_public_code_scrubbing_preserves_json_and_source():
    raw = json.dumps({'path': r'C:\Users\someone\source\file.py',
                      'text': 'apiKey: process.env.SERVICE_TOKEN,', 'credential': 'sk-' + 'A1' * 24})
    cleaned = json.loads(harness.scrub(raw))
    assert cleaned['text'] == 'apiKey: process.env.SERVICE_TOKEN,'
    assert 'someone' not in cleaned['path']
    assert cleaned['credential'] == '[REDACTED]'


def test_usage_totals_keep_cache_and_reasoning_components_separate():
    row = {'usage': {'input_tokens': 100, 'cached_input_tokens': 40,
                     'output_tokens': 20, 'reasoning_output_tokens': 8}}
    assert harness.total(row) == 120
    assert harness.total(row, 0) == 80
    assert harness.total(row, 0.1) == 84
    assert harness.total({'usage': {}}) is None


def test_exec_overrides_follow_subcommand(tmp_path):
    args = harness.exec_args('pinned-model', 'medium', tmp_path, tmp_path / 'answer.json', tmp_path / 'schema.json')
    index = args.index('exec')
    assert all(i > index for i, v in enumerate(args) if v in ('-c', '--disable', '--sandbox'))
    assert args[args.index('-m') + 1] == 'pinned-model'
    assert args[args.index('--sandbox') + 1] == 'read-only'
    assert 'approval_policy="never"' in args
    assert 'model_reasoning_effort="medium"' in args


def test_only_complete_pairs_enter_aggregates():
    def row(task, config, tokens):
        return {'task': task, 'config': config, 'exit_code': 0, 'usage': {'input_tokens': tokens, 'output_tokens': 10},
                'grade': {'f1': 1}, 'wall_seconds': 2, 'mcp_calls': {}}
    meta = {'tasks': [{'id': 'pair', 'group': 'W'}, {'id': 'missing', 'group': 'L'}],
            'attempts': [row('pair', 'A', 90), row('pair', 'B', 70), row('missing', 'A', 1000)]}
    paired, summaries = harness.aggregates(meta)
    assert len(paired) == 1
    assert summaries['overall']['A'] == 100
    assert summaries['overall']['B'] == 80
    assert summaries['overall']['saving'] == 0.2
    assert summaries['L'] is None


def test_read_calls_exclude_edits_and_other_servers():
    row = {'mcp_calls': {'readscout.local_ask': 2, 'readscout.local_digest': 1,
                         'readscout.local_edit': 3, 'codex.list_mcp_resources': 1}}
    assert harness.read_calls(row) == 3
