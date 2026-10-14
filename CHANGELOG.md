# Changelog

## 0.1.0 (unreleased)

First public version.

- MCP server with `local_ask`, `local_digest` and `local_edit`; verified quotes, host-computed line numbers,
  chunking of large inputs, log pre-filtering, gated edits with byte-exact restore.
- Automatic model choice: bigger model for negative questions and when the fast one finds nothing.
- Cross-platform installers (Windows, macOS, Linux) that install uv and Ollama after asking.
- Local setup page: hardware detection with overridable sliders, model recommendations from `catalog.json`,
  one-click model install, agent wiring (Claude Code, Codex), project folders, readiness check.
- CLI: `setup`, `doctor`, `hardware`, `pull`, `install-agent`, `register`, `ask`, `digest`, `edit`, `stats`, `dashboard`, `bench`.
- Public benchmark: 25 reading tasks on 4 MIT repositories pinned by commit and content fingerprint, 7 edit tasks
  with hidden checks; `readscout bench` prints a report to share.
- Identical quotes (the same line repeated in a file) now land on distinct, correct lines; quotes glued across
  lines are recognised. Found by the public benchmark.
- `local_edit` refuses files that contain a secret, are not UTF-8 or exceed 60 KB, instead of sending them to the model.
- Receipts say when a list hit the per-chunk cap; credential files (`.npmrc`, `.netrc`, SSH keys...) are refused;
  very long lines (minified files) are cut so they cannot overflow the model context.
- Installers download the release wheel: Git is no longer required.
- Claude Code plugin (`/plugin marketplace add Anarchiejs/readscout`): skill + MCP server started with `uvx`;
  `doctor` and the setup page recognise it, and error hints give the right command in plugin mode.
