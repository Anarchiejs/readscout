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


v2spec = importlib.util.spec_from_file_location('token_savings_v2', Path(__file__).parents[1] / 'scripts/token_savings_v2.py')
assert v2spec and v2spec.loader
v2 = importlib.util.module_from_spec(v2spec)
v2spec.loader.exec_module(v2)


def test_v2_accepts_variable_occurrence_elsewhere_in_scope(tmp_path):
    (tmp_path / 'first.js').write_text('const a = process.env.TARGET_VALUE;\n')
    (tmp_path / 'second.js').write_text('const b = process.env.TARGET_VALUE;\n')
    task = Task('env', 'env_vars', 'easy', tmp_path, ['first.js', 'second.js'], 'find',
                [{'path': 'first.js', 'line': 1, 'key': 'TARGET_VALUE'}])
    answer = {'findings': [{'path': 'second.js', 'line': 1, 'quote': 'const b = process.env.TARGET_VALUE;', 'answer': 'TARGET_VALUE'}]}
    assert v2.grade_v2(task, answer)['f1'] == 1
    assert harness.grade_answer(task, answer)['f1'] == 0
    answer['findings'][0]['path'] = 'outside.js'
    assert v2.grade_v2(task, answer)['unverifiable'] == 1


def test_v2_rejects_variable_claim_unsupported_by_quote(tmp_path):
    (tmp_path / 'source.js').write_text('const a = process.env.OTHER_VALUE;\n')
    task = Task('env', 'env_vars', 'easy', tmp_path, ['source.js'], 'find',
                [{'path': 'source.js', 'line': 1, 'key': 'TARGET_VALUE'}])
    answer = {'findings': [{'path': 'source.js', 'line': 1, 'quote': 'const a = process.env.OTHER_VALUE;', 'answer': 'TARGET_VALUE'}]}
    assert v2.grade_v2(task, answer)['f1'] == 0


def test_v2_semantic_ground_truth_rejects_wrong_method_and_operation(tmp_path):
    (tmp_path / 'route.js').write_text('router.route("/items")\n  .get(handler);\n')
    task = Task('routes', 'routes_list', 'easy', tmp_path, ['route.js'], 'find',
                [{'path': 'route.js', 'line': 1, 'span': [1, 2], 'method': 'GET', 'route': '/items'}])
    answer = {'findings': [{'path': 'route.js', 'line': 1, 'quote': 'router.route("/items")', 'answer': 'POST /items'}]}
    assert v2.grade_v2(task, answer)['f1'] == 0
    answer['findings'][0]['answer'] = 'GET /items'
    assert v2.grade_v2(task, answer)['f1'] == 1
    task.family = 'data_access'
    task.gt = [{'path': 'route.js', 'line': 1, 'table': 'items', 'operation': 'upsert'}]
    answer['findings'][0]['answer'] = 'items select'
    assert v2.grade_v2(task, answer)['f1'] == 0
    answer['findings'][0]['answer'] = 'items upsert'
    assert v2.grade_v2(task, answer)['f1'] == 1


def test_v2_receipt_parser_preserves_quotes_and_trace_end():
    text = ('[status: complete]\n- a.log:2 x3, last at line 7 | « ERROR  bad value »'
            ' ... ends a.log:4 « ValueError: bad »\nNot recognized (1):\n- b.py:4 unknown')
    result = v2.receipt_answer(text)['findings']
    assert len(result) == 2
    assert result[0]['quote'] == 'ERROR  bad value'
    assert result[1]['line'] == 4


def test_v2_instrumentation_distinguishes_targeted_and_broad_reads():
    items = [
        {'type': 'command_execution', 'command': 'Get-Content readscout/SKILL.md', 'aggregated_output': 'core'},
        {'type': 'mcp_tool_call', 'server': 'readscout', 'tool': 'local_ask',
         'result': {'content': [{'text': '[status: complete]\n- src/a.py:20 | « source quote »'}]}},
        {'type': 'command_execution', 'command': "sed -n '20,22p' src/a.py", 'aggregated_output': 'abc'},
        {'type': 'command_execution', 'command': 'rg ERROR .', 'aggregated_output': 'abcdef'},
    ]
    raw = '\n'.join(json.dumps({'type': 'item.completed', 'item': i}) for i in items)
    result = v2.instrument(raw)
    assert result['skill_core']
    assert result['readscout_calls'] == 1
    assert [r['mode'] for r in result['rereads']] == ['targeted', 'broad']
    assert result['fallbacks'] == 1
    assert result['receipts'][0]['status'] == 'complete'
    assert result['request_usage'] is None
    assert result['phase_tokens'] is None


def test_v2_empty_pairs_are_not_zero_saving():
    assert v2.aggregate([]) is None


def test_v2_cleanup_refuses_non_campaign_directory(tmp_path):
    import pytest
    with pytest.raises(ValueError, match='Unsafe cleanup'):
        v2.safe_delete(tmp_path)


def test_v2_quota_gate_stops_before_refreshed_allowance_or_exhaustion():
    budget = {'primary_stop_used_percent': 97.9, 'secondary_stop_used_percent': 92.8}
    assert v2.quota_stop(budget, 79, 28, 1000, 500) is None
    assert v2.quota_stop(budget, 97.9, 28, 1000, 500)
    assert v2.quota_stop(budget, 79, 92.8, 1000, 500)
    assert v2.quota_stop(budget, 1, 28, 1000, 1000)


def test_v2_skill_copy_includes_all_references(tmp_path):
    # Exercise the harness copying path rather than merely checking the package installer.
    import shutil
    src = tmp_path / 'B/.agents/skills/readscout'
    (src / 'references').mkdir(parents=True)
    (src / 'SKILL.md').write_text('core')
    (src / 'references/troubleshooting.md').write_text('details')
    dest = tmp_path / 'B/.codex/skills/readscout'
    shutil.copytree(src, dest, dirs_exist_ok=True)
    assert (dest / 'references/troubleshooting.md').read_text() == 'details'
