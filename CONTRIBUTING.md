# Contributing

Thanks for helping. Two kinds of contributions matter most right now:

1. **Measurements on other hardware.** Run `readscout bench` and paste the table it prints into an issue (it already
   contains GPU, VRAM, RAM, OS, models, scores and seconds per task). This is how the catalog improves.
2. **Code and docs**, through pull requests.

## Development

```sh
git clone https://github.com/Anarchiejs/readscout && cd readscout
uv venv && uv pip install -e ".[dev]"      # or: python -m venv .venv && pip install -e ".[dev]"
pytest -q
```

The tests use a fake model (and, for the llama.cpp engine, a fake `llama-server`) and need neither Ollama, llama.cpp nor a
GPU. CI runs them on Windows, macOS and Linux.

Before a release, run the end-to-end check on a machine with Ollama and a GPU (it is not part of CI): it installs
readscout in its own temporary folders (your installation and your config are left alone), pulls the recommended models
and exercises every tool, the MCP server, the setup page and the benchmark. Both scripts exit with a non-zero code when a
step fails. Pass the path of a `llama-server` (`READSCOUT_E2E_LLAMA_SERVER` for the shell script, `-LlamaServer` for the
PowerShell one; the CUDA build on an NVIDIA GPU) to add the llama.cpp stage: the quality model on llama.cpp from Ollama's
files, `doctor`, a read, and `readscout stop`. The Release workflow runs the unit tests on Windows, macOS and Linux and `scripts/check_version.py` first.

```sh
bash scripts/e2e.sh                                          # Linux / macOS
powershell -ExecutionPolicy Bypass -File scripts\e2e.ps1     # Windows
```

Testing the Claude Code plugin from a local checkout: `claude plugin validate . --strict`, and run its MCP command
with `uvx --no-cache --from . readscout-mcp` (uv caches local builds, so without `--no-cache` you may get stale code).
Release: run `python scripts/bump_version.py X.Y.Z` (it writes the version in `src/readscout/__init__.py`, the plugin
manifest and every pinned wheel URL: READMEs, `install.sh`, `install.ps1`, `.claude-plugin/plugin.json`), fill in the
`CHANGELOG.md` section and `.github/release-notes/vX.Y.Z.md` it started, run `python scripts/check_version.py` (CI runs
it too and fails on any stale URL), then push the tag `vX.Y.Z`: the Release workflow tests, builds the package and
publishes the release with those notes and `SHA256SUMS`.

Before updating an agent, build and test a wheel in isolation, run `readscout info` from that environment, then install
that exact wheel and run `readscout install-agent codex` and/or `readscout install-agent claude`. Compare version,
distribution version and content fingerprint with the tested build, and reconnect the clients. A checkout, a global
installation and an already-running MCP process are three different states. Never reuse an already-tagged version for
changed package contents; the version check also detects changed sources when that release tag is available locally.

## Commits

One change per commit, with a subject that says what changed in the imperative, under 72 characters, and a body when
the reason is not obvious:

```text
llamacpp: stop the shared llama-server after the idle delay

The watchdog checks /slots first, so a long request is never cut.
```

A prefix naming the area (`llamacpp:`, `edit:`, `docs:`, `ci:`) helps reading `git log`. No one-letter subjects:
the history is how the next person learns why the code is the way it is.

## Rules of the house

- Keep the three-tool surface small: every tool schema is re-sent to the agent on every turn.
- Any change of default model or of the catalog's rules must come with benchmark numbers (`readscout bench`, on both
  engines when the change touches llama.cpp: a build that is fast in `llama-bench` can still lose in the real pipeline).
- Never add a network call to anything other than the local Ollama server or the local llama-server.
- Style: no em dash characters anywhere (code, docs, messages); use ":" or "-" depending on context.
- Write tests for behaviour, especially anything touching file access, quote verification or edits.
