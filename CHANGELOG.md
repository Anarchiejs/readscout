# Changelog

## Unreleased

- **Optional limits for restricted agents.** `readscout folders add <dir>` limits the local models to a list of folders
  (reads, edits and new files), `readscout gate off` forbids `local_edit` gate commands. readscout cannot see Claude
  Code's own permission rules, so an agent without Bash or with `Read` deny rules could otherwise get around them. By
  default nothing changes: any folder, gate on. `readscout doctor` shows both settings.
- **Wider secret masking:** GitLab, Stripe, npm, PyPI, Hugging Face, SendGrid and Google OAuth tokens, AWS temporary
  keys, JWTs, Slack webhooks, passwords in URLs (`postgres://user:pass@host`), `Authorization: Bearer/Basic` headers,
  and more names (`passphrase`, `credentials`, `AccountKey`, `connection_string`...).
- **Fix:** a `token:` or `password =` at the end of a line no longer masks the start of the next line.
- `local_edit` split into small, separately readable steps (targets, reading, applying, writing and restoring); no
  behaviour change. The setup server no longer relies on `assert` to validate request bodies (`python -O` drops them).
- The French README no longer mentions the project-folder list removed in 0.1.3.
- Tests for the command line, the Ollama client and the benchmark logs: coverage from 62 % to 76 %; CI now requires 72 %.

## 0.1.5

- **Model recommendations.** The 12B is now offered from 8 GB of VRAM with 16 GB of RAM (it was measured on 8 GB of VRAM
  with 32 GB of RAM) and from 10 GB of VRAM with 8 GB of RAM, instead of needing 15 GB of RAM.
- **Context size follows the machine:** 64k tokens for big cards (fast model from 12 GB of VRAM, quality model from 24 GB
  or, for the 12B, 14 GB), 32k otherwise. Not benchmarked yet.

## 0.1.4

- **Windows installer:** it closes a running readscout (your agent's MCP server, the setup page) before reinstalling.
  Those processes locked the files and the reinstall failed with "Access denied". Restart your coding agent afterwards.

## 0.1.3

- **No more folder allow-list.** The local models read whatever files and folders the coordinating agent names, in any
  folder; the "Project folders" card, `readscout register`, `unregister` and `projects` are gone. The model is local and
  the agent already has the user's file access, so the list protected nothing. Sensitive files (`.env*`, `.git`, keys,
  credentials) and binaries are still refused.

## 0.1.2

Fixes from a full audit of the code, the skill and the release process.

- **Files and secrets.** Exclusions (`.env*`, `.git`, credentials...) ignore the letter case and also apply to files
  `local_edit` creates; secrets in JSON and in prefixed names (`client_secret`, `DB_PASSWORD`...) are masked; masking a
  multi-line key no longer shifts the line numbers below it; a folder containing a credentials file is read instead of
  failing, and excluded folders such as `node_modules` are not walked.
- **Quotes.** Only whitespace and line breaks between adjacent lines may differ from the source; text from distant lines
  of a filtered log can no longer be glued into a quote. Two projects with the same relative path are told apart.
- **local_edit.** Atomic writes, nothing is written when the file changed while the model was working, a failed gate or
  a write error restores only what was written, one project per call, gate shape validated.
- **Local only.** Ollama cloud models are refused (by name and by remote host) and Ollama is started with
  `OLLAMA_NO_CLOUD=1`. `readscout stop` says when a model could not be unloaded.
- **Reading.** The context budget counts the prompt, the question and the merge of summaries; long lines that were cut
  are reported; model prose in receipts is flattened to one bounded line.
- **Setup.** Small machines (no GPU, 8 GB RAM) get a matching recommendation; unknown web actions are rejected instead of
  uninstalling; errors reach the page; config writes are locked and atomic; the Codex install validates the TOML, handles
  sub-tables and CRLF and keeps a backup.
- **Benchmark.** A finding about the wrong subject on the right line no longer counts, and a log task needs the root
  cause. Scores published before this change used the lenient rule and are to be re-measured.
- **Release.** Tests and a version check run before a release is built; `SHA256SUMS` is published; actions are pinned;
  permissions are per job; the e2e scripts are isolated and return a real exit code; `install.sh` installs nothing
  without a terminal to ask; `mcp>=1.23`.

## 0.1.1

- **Models free the memory by themselves.** Ollama now unloads a model one minute after the last call (it kept it
  30 minutes before, so a 26B model could hold about 14 GB of RAM long after the agent was done), and readscout
  unloads the models it used as soon as the agent session ends. Nothing for the agent to remember or check.
- `readscout stop` frees the memory immediately; the skill tells agents never to start models or inference servers
  themselves.
- On Windows, when readscout has to start Ollama, Ollama now outlives the agent session instead of being killed with it.

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
