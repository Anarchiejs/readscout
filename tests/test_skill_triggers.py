"""What the agent sees before it chooses: the skill's description line and the tools' descriptions name the tasks where delegating paid.

Measured on gpt-6-astra (natural adoption pilot of 18 October): with no instruction the agent never opened the skill before choosing,
it chose from the one-line skill description and the tool descriptions. It never delegated a folder's endpoint inventory (-28 % to
-41 % of tokens when it was told to), and delegated long logs, security questions on endpoints and small build logs only twice in three.
"""
import asyncio
import re

from readscout import agents, server

DESCRIPTION = re.search(r'(?m)^description: (.*)$', agents.SKILL.read_text(encoding='utf-8')).group(1)
TOOLS = {t.name: t.description for t in asyncio.run(server.mcp.list_tools())}
BODY = agents.SKILL.read_text(encoding='utf-8').split('---', 2)[2]


def test_the_description_names_the_tasks_where_delegating_pays_and_the_tool_for_each():
    text = DESCRIPTION.lower()
    for needle in ('log', 'command output', 'local_digest', 'endpoints', 'routes', 'local_ask', 'lack', 'protection'):
        assert needle in text, needle


def test_the_description_still_says_when_not_to_delegate():
    assert 'Skip it when one grep answers' in DESCRIPTION and 'named variable' in DESCRIPTION


def test_the_description_stays_a_single_short_line():
    assert '\n' not in DESCRIPTION and len(DESCRIPTION) <= 640


def test_the_description_says_to_choose_before_reading_or_grepping():
    assert re.search(r'(?i)before (reading|you read|grep)', DESCRIPTION)


def test_the_digest_tool_is_offered_instead_of_reading_a_log_oneself():
    text = TOOLS['local_digest']
    assert re.search(r'(?i)instead of (reading|loading|grepping)', text) and 'log' in text


def test_the_ask_tool_is_offered_for_endpoint_inventories_and_missing_protections():
    text = TOOLS['local_ask']
    assert 'extract=endpoints' in text.replace(' ', '') or "extract='endpoints" in text
    assert re.search(r'(?i)(lack|without|missing)', text) and re.search(r'(?i)routes? or endpoints|endpoints? of a', text)


def test_the_core_lists_what_pays_before_what_does_not():
    yes, no = BODY.index('**Yes**'), BODY.index('**No**')
    assert yes < no
    for needle in ('long log', 'endpoints', 'without auth', 'local_digest'):
        assert needle in BODY[yes:no], needle
    assert 'one `grep` answers' in BODY[no:]
