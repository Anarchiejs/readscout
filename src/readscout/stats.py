"""Local reading usage from metrics.jsonl; token equivalents are not measured agent savings."""
import json
import time

from . import paths


def rows(days=30) -> list[dict]:
    p = paths.metrics_file()
    if not p.exists():
        return []
    since = time.time() - days * 86400
    out = []
    for line in p.read_text(encoding='utf-8').splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get('time', 0) >= since:
            out.append(r)
    return out


def summary(days=30) -> dict:
    rs = rows(days)
    reads = [r for r in rs if r.get('tool') in ('ask', 'digest')]
    edits = [r for r in rs if r.get('tool') == 'edit']
    read_bytes = sum(r.get('bytes_read', 0) for r in reads)
    returned = sum(r.get('chars_returned', 0) for r in reads)
    by_model: dict[str, dict] = {}
    for r in rs:
        m = by_model.setdefault(r.get('model', '?'), {'calls': 0, 'seconds': 0.0})
        m['calls'] += 1
        m['seconds'] = round(m['seconds'] + r.get('seconds', 0), 1)
    return {'days': days, 'calls': len(rs), 'reads': len(reads), 'edits': len(edits),
            'edits_applied': sum(r.get('status') == 'applied' for r in edits),
            'empty_answers': sum(r.get('verified', 0) == 0 for r in reads),
            'kb_read_locally': round(read_bytes / 1000), 'kb_returned': round(returned / 1000),
            # Gross local-text proxy at ~3.5 characters/token; not net savings against an agent using grep.
            'tokens_avoided_est': max(0, round((read_bytes - returned) / 3.5)),
            'verified': sum(r.get('verified', 0) for r in reads), 'dropped': sum(r.get('dropped', 0) for r in reads),
            'seconds_local': round(sum(r.get('seconds', 0) for r in rs)), 'by_model': by_model, 'recent': rs[-15:][::-1]}
