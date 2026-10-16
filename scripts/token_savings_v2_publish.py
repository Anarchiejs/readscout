"""Offline publication only: never starts an agent or changes measurement code."""
import json
import statistics

import token_savings_v2 as campaign


def main():
    campaign.report()
    meta = campaign.read_json(campaign.OUT / 'results.json')
    report_path = campaign.ROOT / 'docs/TOKEN-SAVINGS-V2.md'
    text = report_path.read_text(encoding='utf-8')
    pairs = campaign.comparisons(meta, 'tuning', 'A')
    oldpairs = campaign.comparisons(meta, 'tuning', 'B1')
    summary = [
        'Campaign incomplete: the mandatory pilot gate failed because B2 made no MCP call.',
        f"Measured sessions spent {meta['spent_total_tokens']:,} reported tokens; holdout, controls and work sessions were not measured.",
    ]
    if pairs:
        a, b = (sum(campaign.old.total(p[k]) for p in pairs) for k in ('base', 'B2'))
        b1 = sum(campaign.old.total(p['base']) for p in oldpairs)
        summary += [f"Matched tuning subset only ({len(pairs)} task): reused A {a:,}, reused B1 {b1:,}, B2 {b:,}; descriptive saving {(a-b)/a:.1%} versus A and {(b1-b)/b1:.1%} versus B1.",
                    'B2 did not read the skill or call readscout: these differences do not establish improvement-driven savings.']
        aa = [r for r in meta['attempts'] if r['config'] == 'A' and r['phase'] == 'pilot']
        fresh = sum(campaign.old.total(r) for r in aa)
        summary += [f"Fresh pilot A {fresh:,} versus B2 {b:,}: {(fresh-b)/fresh:.1%} lower tokens on this single task; final F1 v1/v2 is {pairs[0]['B2']['grade']['f1']}/{pairs[0]['B2']['grade_v2']['f1']}."]
    begin = text.index('## TL;DR') + len('## TL;DR')
    end = text.index('## Setup')
    text = text[:begin] + '\n\n' + '\n'.join(summary) + '\n\n' + text[end:]
    additional = ['### Accuracy and quality on the observed subset', '']
    regraded = {(r['task'], r['config']): r['v2'] for r in meta['baseline_regraded']}
    for label, pp in [('A', pairs), ('B1', oldpairs)]:
        if pp:
            basef = statistics.mean(regraded[p['task'], label]['f1'] for p in pp)
            newf = statistics.mean(p['B2']['grade_v2']['f1'] for p in pp)
            additional.append(f'- Scorer v2 mean F1 {label}/B2: {basef:.3f}/{newf:.3f}.')
    additional += ['', 'These are subset checks, not confirmation of campaign-wide accuracy or generalization.', '']
    marker = '## Real work sessions'
    text = text.replace(marker, '\n'.join(additional) + marker)
    text = text.replace('`v2 next --quota-used PERCENT`', '`v2 next --quota-used PERCENT --quota-secondary-used PERCENT --quota-resets-at UNIX`')
    text = text.replace('`v2 report` is offline', '`python scripts/token_savings_v2_publish.py` generates this report offline')
    text += ('\nReport publication is separate from the frozen measurement harness. Its exact execution hashes are stored in results.json. '
             'The pilot was stopped, not discarded or rerun. No postcampaign source fix or skill tuning was applied.\n')
    report_path.write_text(text, encoding='utf-8')
    # Append the one expressly requested pointer; preserve all campaign 1 content.
    path = campaign.ROOT / 'docs/TOKEN-SAVINGS.md'
    original = path.read_text(encoding='utf-8')
    pointer = '\n## Campaign 2\n\nSee [Campaign 2](TOKEN-SAVINGS-V2.md) for the separately preregistered follow-up and its mandatory pilot stop.\n'
    if '\n## Campaign 2\n' not in original:
        with path.open('a', encoding='utf-8', newline='') as f:
            f.write(pointer)
    for filename, fr in [('README.md', False), ('README.fr.md', True)]:
        path = campaign.ROOT / filename
        content = path.read_text(encoding='utf-8')
        marker = '<!-- token-savings:end -->'
        if '(docs/TOKEN-SAVINGS-V2.md)' not in content:
            note = ('La [campagne 2](docs/TOKEN-SAVINGS-V2.md) a été arrêtée au pilote sans appel MCP : '
                    "elle ne permet pas de conclure à une économie due aux améliorations, avec une seule tâche observée et aucun résultat de validation indépendante."
                    if fr else 'The [second campaign](docs/TOKEN-SAVINGS-V2.md) stopped at its pilot without an MCP call: '
                    'one observed task and no holdout results cannot establish savings caused by the improvements.')
            content = content.replace(marker, note + '\n\n' + marker)
            path.write_text(content, encoding='utf-8')
    path = campaign.ROOT / 'CHANGELOG.md'
    content = path.read_text(encoding='utf-8')
    entry = '- Preregister token-savings campaign 2 and publish its stopped pilot, structural coverage and separate scorer results.\n'
    if entry not in content:
        path.write_text(content.replace('## Unreleased\n', '## Unreleased\n\n' + entry, 1), encoding='utf-8')
    (campaign.OUT / 'SOURCES.md').write_text('# Source notices\n\nRaw runs contain excerpts from the same pinned MIT repositories as campaign 1. See [the complete source notices](../SOURCES.md). ReadScout holdout questions and the build-log fixture are authored in the frozen preparation script.\n', encoding='utf-8')
    print(json.dumps({'report': 'docs/TOKEN-SAVINGS-V2.md', 'measured_sessions': len(meta['attempts']),
                      'spent_total_tokens': meta['spent_total_tokens']}, indent=2))


if __name__ == '__main__':
    main()
