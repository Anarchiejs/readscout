# local_edit

For a mechanical change that is already decided and fully specified: docstrings, type hints, a rename, a new parameter, test scaffolding.

- Give one or two sentences: what, where, what must not change. Do not read the files first.
- Pass a `gate` when the project has tests or a linter, e.g. `[["python","-m","pytest","-q"]]` or `[["npm","test","--silent"]]`. Without a gate, review the whole diff.
- `APPLIED`: files changed and the gate passed; review the returned diff.
- `ESCALATE`: nothing was kept, do it yourself. This also happens when a file changed while the model was working: re-read it first.
- `gate` commands run on the user's machine with their permissions and no shell: only pass the project's own tests or linters.
- Never use it for design, debugging, security-sensitive code, or a change you cannot describe precisely.
- It refuses files over 60 KB in total, non-UTF-8 files and files that contain a secret: edit those yourself.
