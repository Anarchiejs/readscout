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

The tests use a fake model and need neither Ollama nor a GPU. CI runs them on Windows, macOS and Linux.

Before a release, run the end-to-end check on a machine with Ollama and a GPU: it installs readscout, pulls the
recommended models and exercises every tool, the MCP server, the setup page and the benchmark.

```sh
bash scripts/e2e.sh                                          # Linux / macOS
powershell -ExecutionPolicy Bypass -File scripts\e2e.ps1     # Windows
```

Testing the Claude Code plugin from a local checkout: `claude plugin validate . --strict`, and run its MCP command
with `uvx --no-cache --from . readscout-mcp` (uv caches local builds, so without `--no-cache` you may get stale code).
Release: bump the version in `src/readscout/__init__.py`, the wheel URLs (README, installers, `.claude-plugin/plugin.json`)
and `CHANGELOG.md`, write `.github/release-notes/vX.Y.Z.md`, then push the tag `vX.Y.Z`: the Release workflow builds the
package and publishes the release with those notes.

## Rules of the house

- Keep the three-tool surface small: every tool schema is re-sent to the agent on every turn.
- Any change of default model or of the catalog's rules must come with benchmark numbers.
- Never add a network call to anything other than the local Ollama server.
- Style: no em dash characters anywhere (code, docs, messages); use ":" or "-" depending on context.
- Write tests for behaviour, especially anything touching file access, quote verification or edits.
