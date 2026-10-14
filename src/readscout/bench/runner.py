"""Run the public benchmark on this machine and produce a report to paste into a GitHub issue."""
import json
import os
import platform
import time

from .. import __version__, backend, hardware, paths, tasks
from ..text import load_lines
from . import edits, generate

FAMILIES = ['routes_list', 'routes_filter', 'routes_negation', 'data_access', 'env_vars', 'locate', 'log']


def _hit(item, v, family) -> bool:
    path, a, b, text, quote = v
    if item.get('path') and item['path'] != path:
        return False
    if 'span' in item:
        return a <= item['span'][1] and b >= item['span'][0]
    key = item.get('key') or ''
    if len(key) >= 4 and (key in quote or (family == 'env_vars' and key in text)):
        return True
    return item['line'] - 1 <= a <= item['line'] + 1


def score(task: generate.Task, verified) -> dict:
    found = {i for i, g in enumerate(task.gt) for v in verified if _hit(g, v, task.family)}
    good = sum(1 for v in verified if any(_hit(g, v, task.family) for g in task.gt))
    wrong_neg = sum(1 for v in verified if any(_hit(n, v, task.family) for n in task.negatives)
                    and not any(_hit(g, v, task.family) for g in task.gt))
    recall = len(found) / len(task.gt) if task.gt else 1.0
    if task.family == 'locate':
        precision = 1.0 if verified and _hit(task.gt[0], verified[0], task.family) else (good / len(verified) if verified else 0.0)
    elif task.family == 'log':
        precision = 1.0 if verified else 0.0      # consequences are legitimate extra findings
    else:
        precision = good / len(verified) if verified else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {'recall': round(recall, 3), 'precision': round(precision, 3), 'f1': round(f1, 3), 'negatives_returned': wrong_neg}


def run_reading(model: backend.Model, task_list, progress=print) -> list[dict]:
    rows = []
    for t in task_list:
        lines = []
        for p in tasks.expand(t.paths, [t.root]):
            lines += load_lines(p, [t.root])
        if t.family == 'log' and sum(len(l.text) for l in lines) > 20_000:
            lines = tasks.prefilter(lines)
        start = time.time()
        res = tasks.run_ask(lines, t.question, model, 'find')
        s = score(t, res.verified)
        row = {'model': model.name, 'task': t.id, 'family': t.family, 'difficulty': t.difficulty, **s,
               'verified': len(res.verified), 'dropped': res.dropped, 'chunks': res.chunks, 'errors': res.errors[:2],
               'seconds': round(time.time() - start, 1)}
        rows.append(row)
        progress(f"  {model.name:16} {t.id[:44]:44} F1 {s['f1']:.2f}  {row['seconds']:5.1f}s" + ('  ERROR' if res.errors else ''))
    return rows


def summarize(read_rows, edit_rows) -> dict:
    out = {}
    for m in sorted({r['model'] for r in read_rows} | {r['model'] for r in edit_rows}):
        rr = [r for r in read_rows if r['model'] == m]
        fam = {f: round(sum(r['f1'] for r in rr if r['family'] == f) / n, 2)
               for f in FAMILIES if (n := sum(1 for r in rr if r['family'] == f))}
        er = [r for r in edit_rows if r['model'] == m]
        out[m] = {'read_score': round(sum(fam.values()) / len(fam), 3) if fam else None, 'by_family': fam,
                  'read_seconds_per_task': round(sum(r['seconds'] for r in rr) / len(rr), 1) if rr else None,
                  'edit_score': f"{sum(r['score'] for r in er):.1f}/{len(er)}" if er else None,
                  'edit_seconds_per_task': round(sum(r['seconds'] for r in er) / len(er), 1) if er else None,
                  'errors': sum(1 for r in rr if r['errors'])}
    return out


def markdown(report) -> str:
    hw = report['hardware']
    lines = [f"### readscout bench {report['readscout']} · {hw['gpu']} {hw['vram_gb']} GB · {hw['ram_gb']} GB RAM · {hw['os']}",
             f"Ollama {report['ollama']} · corpus {report['corpus']} · {report['tasks']} reading tasks, {len(edits.TASKS)} edit tasks", '',
             '| model | ' + ' | '.join(FAMILIES) + ' | **read** | s/task | **edit** | s/task |',
             '|---|' + '---|' * (len(FAMILIES) + 4)]
    for m, s in report['summary'].items():
        fam = ' | '.join(f"{s['by_family'][f]:.2f}" if f in s['by_family'] else '-' for f in FAMILIES)
        lines.append(f"| {m} | {fam} | **{s['read_score'] if s['read_score'] is not None else '-'}** | {s['read_seconds_per_task'] or '-'} "
                     f"| **{s['edit_score'] or '-'}** | {s['edit_seconds_per_task'] or '-'} |")
    return '\n'.join(lines)


def run(models: list[str], families: list[str] | None = None, do_edits=True, progress=print) -> dict:
    os.environ['READSCOUT_NO_METRICS'] = '1'   # benchmark calls are not real usage
    cfg = paths.load_config()
    url = cfg['ollama_url']
    backend.ensure_ollama(url)
    have = backend.installed_models(url)
    missing = [m for m in models if m not in have]
    if missing:
        raise SystemExit(f'Not installed: {", ".join(missing)} (readscout pull {" ".join(missing)})')
    progress('Preparing the corpus (first run downloads 4 pinned MIT-licensed repositories, about 2 MB)...')
    task_list = generate.build()
    if families:
        task_list = [t for t in task_list if t.family in families]
    read_rows, edit_rows = [], []
    for name in models:
        model = backend.Model(name=name, url=url, ctx=32768)
        progress(f'Reading tasks with {name} ({len(task_list)} tasks)')
        read_rows += run_reading(model, task_list, progress)
        if do_edits:
            progress(f'Edit tasks with {name} ({len(edits.TASKS)} tasks)')
            for r in edits.run(model, tasks.edit):
                edit_rows.append({'model': name, **r})
                progress(f"  {name:16} edit:{r['task']:38} {r['status']:9} {r['score']:.2f}  {r['seconds']:5.1f}s")
    hw = hardware.detect()
    report = {'readscout': __version__, 'date': time.strftime('%Y-%m-%d'), 'ollama': backend.health(url),
              'platform': platform.platform(), 'hardware': hardware.as_dict(hw), 'corpus': 'v1', 'tasks': len(task_list),
              'summary': summarize(read_rows, edit_rows), 'reading': read_rows, 'edits': edit_rows}
    out_dir = paths.home() / 'bench-results'
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"bench-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    report['file'] = str(out)
    return report
