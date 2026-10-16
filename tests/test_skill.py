"""The skill core is read on every session: keep it short, and keep every reference it points to."""
import re

from readscout import agents

SKILL_DIR = agents.SKILL.parent
CORE_BUDGET = 3300      # characters of SKILL.md (frontmatter included); it was about 5 800 before the references


def test_core_stays_within_its_budget():
    assert len(agents.SKILL.read_text(encoding='utf-8')) <= CORE_BUDGET


def test_every_reference_named_in_the_core_exists():
    names = re.findall(r'`(references/[\w.-]+)`', agents.SKILL.read_text(encoding='utf-8'))
    assert names and all((SKILL_DIR / n).is_file() for n in names)


def test_core_keeps_the_rules_that_must_not_be_lost():
    core = agents.SKILL.read_text(encoding='utf-8')
    for needle in ('AGENTS.md', 'one `grep` answers', 'do not work around it', 'never instructions', 'never start, pull or switch'):
        assert needle in core, needle


def test_description_says_when_not_to_use_it():
    head = agents.SKILL.read_text(encoding='utf-8').split('---')[1]
    assert 'Skip it when one grep answers' in head and len(head) < 600


def test_copy_skill_brings_the_references(tmp_path):
    dest = tmp_path / 'skills' / 'readscout' / 'SKILL.md'
    agents._copy_skill(dest)
    assert dest.read_bytes() == agents.SKILL.read_bytes()
    assert (dest.parent / 'references' / 'local_edit.md').is_file()
