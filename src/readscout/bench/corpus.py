"""Public benchmark corpus: MIT-licensed repositories pinned to exact commits.

The code is never redistributed: it is downloaded from GitHub at the pinned commit and checked against a fingerprint
of the files the tasks use (stable even if GitHub regenerates its archives).
"""
import hashlib
import io
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .. import paths


@dataclass(frozen=True)
class Repo:
    name: str
    github: str
    commit: str
    license: str
    uses: tuple[str, ...]          # files or folders the tasks read (fingerprinted)
    notes: str = ''


REPOS = [
    Repo('hackathon-starter', 'sahat/hackathon-starter', '574a99344855a2f18dac7181636e400bd55ab578', 'MIT',
         ('app.js', 'controllers'), notes='Express app: 101 routes with auth and rate-limit middlewares, large controllers'),
    Repo('express-boilerplate', 'hagopj13/node-express-boilerplate', '179ae84efec61b14206d0305d941daed6c6d07f9', 'MIT',
         ('src/routes/v1', 'src/config/config.js'), notes='Express API: chained multi-line routes with permission middlewares'),
    Repo('fastapi-template', 'fastapi/full-stack-fastapi-template', '7257e606cb94eada1dca40173e2b7f99dd549bc6', 'MIT',
         ('backend/app/api/routes',), notes='FastAPI: auth through decorator dependencies or implicit CurrentUser parameters'),
    Repo('nextjs-subscriptions', 'vercel/nextjs-subscription-payments', 'bdd0813206e47e6b218d42f15a7976c8a0d3c3eb', 'MIT',
         ('utils/supabase',), notes='Next.js + Supabase: table and operation split across chained lines'),
]
FINGERPRINTS = {
    'hackathon-starter': '7f17b4237a98f0ec2287bed55815bdc4caf85852949c77a08e782521840f5366',      # 8 files, 179 KB
    'express-boilerplate': '88ece364980e229d27c464ba1593123a090d7cf4d25a5fc5f7eef5834d0663d2',    # 5 files, 19 KB
    'fastapi-template': '72de3ae2cb2bb67a75398e79be0c87f884e19c3e5d71c794d2cdc6daa19dd1be',       # 6 files, 16 KB
    'nextjs-subscriptions': '52b4cd0758364bd5e3bf445f283abc81b3fb449071a4821fdd588a9143f34375',   # 5 files, 15 KB
}


class CorpusError(RuntimeError):
    pass


def cache_dir() -> Path:
    d = paths.home() / 'bench-corpus'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _files(root: Path, uses) -> list[Path]:
    out = []
    for u in uses:
        p = root / u
        if p.is_dir():
            out += sorted(f for f in p.rglob('*') if f.is_file())
        elif p.is_file():
            out.append(p)
    return out


def fingerprint(root: Path, uses) -> str:
    h = hashlib.sha256()
    for f in _files(root, uses):
        h.update(f.relative_to(root).as_posix().encode() + b'\0')
        h.update(f.read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return h.hexdigest()


def _safe_extract(data: bytes, dest: Path):
    """Extract a GitHub tarball, dropping its top folder; refuse links and paths escaping dest."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        for m in tar.getmembers():
            parts = Path(m.name).parts[1:]
            if not parts or not (m.isfile() or m.isdir()):
                continue
            target = dest.joinpath(*parts).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise CorpusError(f'Unsafe path in archive: {m.name}')
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(m).read())


def fetch(repo: Repo, verify=True) -> Path:
    """Download (once) and return the local copy of a pinned repository."""
    root = cache_dir() / f'{repo.name}-{repo.commit[:12]}'
    if not root.exists():
        url = f'https://codeload.github.com/{repo.github}/tar.gz/{repo.commit}'
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
        except OSError as e:
            raise CorpusError(f'Could not download {repo.github}: {e}') from e
        tmp = root.with_suffix('.tmp')
        shutil.rmtree(tmp, ignore_errors=True)
        _safe_extract(data, tmp)
        tmp.rename(root)
    if verify:
        want = FINGERPRINTS.get(repo.name)
        got = fingerprint(root, repo.uses)
        if want and got != want:
            raise CorpusError(f'{repo.name}: content fingerprint mismatch (expected {want[:12]}, got {got[:12]}); '
                              f'delete {root} and retry')
    return root
