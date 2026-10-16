# Changelog

## Unreleased

- Clarify the CLI/dashboard local-text estimate after the campaign. It is not measured agent savings;
  the estimate formula and delegation rules are unchanged, and all recorded runs predate this wording change.

## 0.1.6

- **Models re-measured (2026-10-15)** with the current scoring and chunk size: `gemma4:12b` 0.94, `gemma4:26b` 0.93,
  `gemma4:e4b` 0.83 (negative questions 0.28), `gemma4:e2b` 0.70; catalog scores, timings and the texts shown in the
  setup page follow. New tables in docs/BENCHMARK.md: the benchmark per engine, a large read per engine, raw speeds.
- **Fix: chunks no longer overfill the context.** Chunk sizes assumed 3.2 characters per token; Python source measured
  2.8 with Gemma 4, so a "32k" chunk was 31k tokens and left almost no room for the answer. llama.cpp then cut the
  answer, and Ollama silently drops the start of the prompt (the instructions and the top of the excerpt) instead.
  Now 2.6, with the same 10 % margin.
- **Optional llama.cpp engine.** `readscout engine llamacpp --fast ollama:gemma4:e4b --quality ollama:gemma4:26b` makes
  readscout run `llama-server` itself on the files Ollama already downloaded (or any `.gguf`), with flash attention,
  an 8-bit KV cache, a 2048 micro-batch and Ollama's repeat penalty (without it Gemma 4 looped until the output limit),
  one model at a time shared by every session, stopped after the idle delay or when the process ends. A `url` instead
  uses your own llama-server as is. `doctor`, `stop` and `bench` (`--models llamacpp:quality`) know the new engine;
  `llama-server` is found in winget's package folder too. Ollama stays the default: on an RTX 4060 Ti 8 GB the CUDA build
  reads prompts 2x faster with `gemma4:26b` (a 181 KB folder of new files: 181 s on Ollama, 127 s on llama.cpp) but writes
  1.8x slower (the same folder asked again: 30 s on Ollama thanks to its prompt cache, 54 s on llama.cpp), ties on the
  public benchmark, and is 2x to 3x slower with `gemma4:12b` and `gemma4:e4b`; the Vulkan build winget installs was slower
  than Ollama (README, "Faster with llama.cpp", docs/BENCHMARK.md).
- **Engine per model.** Only the models named in `readscout engine llamacpp` run on llama.cpp, the others stay on
  Ollama: `readscout engine llamacpp --quality ollama:gemma4:26b` (no `--fast` needed) keeps `gemma4:e4b` on Ollama,
  where it is 3x faster, and reads with the 26B on llama.cpp, 2x faster. `--fast ollama` moves a model back;
  `readscout engine ollama` still puts every model on Ollama and keeps the llama.cpp ones for later. The engines take
  turns on the GPU: llama.cpp unloads Ollama's models before it starts one, and an Ollama call first stops readscout's
  idle llama-server (never during another session's request). `readscout engine` and `doctor` show and check each model
  on its engine, and `bench` measures each one on its engine by default.
- `readscout bench` frees each model before the next one, so two engines never share the GPU during a run.
- **llama.cpp: secret key, devices, CUDA advice.** readscout starts `llama-server` with a random per-server key
  (`LLAMA_API_KEY`, in the environment, kept in `llamacpp.json`), because llama-server allows every web origin and has no
  key by default: any web page open in the browser could otherwise query it on a guessed loopback port. `readscout doctor`
  lists the devices llama-server sees (`CUDA0`, `Vulkan0`...) and, on an NVIDIA GPU without a CUDA device, says to take the
  CUDA build (CUDA 13 builds need NVIDIA driver 580 or newer) and, with several devices, to pick one with `--device`.
- The setup page shows which engine runs each model (llama.cpp, with the devices and the same advice, or Ollama) and checks
  each model on its own engine; `scripts/e2e.sh` and `scripts/e2e.ps1` have an optional llama.cpp stage
  (`READSCOUT_E2E_LLAMA_SERVER`, `-LlamaServer`).
- Docs: requirements (llama.cpp and CUDA, optional), troubleshooting rows, SECURITY.md (the llama.cpp server threat) and
  the skill (the first call loads a model, with two engines the two models take turns on the GPU) say what the code now does.
- `local_edit`'s gate risk is said when an agent is connected and by `readscout doctor`: the gate commands run with
  your rights even when the agent itself may not use a shell (`readscout gate off`).
- Receipts and READMEs say plainly that the quote and its line are verified, not the model's sentence next to them.
- Questions such as "whether or not", "or not", "not only", "n'importe", "ou pas" no longer count as negative questions
  (they were sent to the slower quality model for nothing).
- `scripts/bump_version.py X.Y.Z` writes a new version everywhere; `check_version.py` now also checks the READMEs and
  fails on any stale release URL. CONTRIBUTING.md gains commit message rules.
- The setup page decodes its query parameters (`%20`, `+`).
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
- **Fix: short quotes no longer verify a claim.** A quote under 10 characters (`None`, `return`) was accepted wherever it
  appeared in a line, so it "proved" almost anything; it is now accepted only when it is a whole line.
- **Fix:** an empty `search` block from the model is refused on an existing file. On a file with exactly one blank line
  it used to replace that line.
- `local_edit` moved to its own module, `editing.py`; `tasks.py` keeps the reading tools. Tests for the MCP tools.
- CI type-checks the package with mypy (Windows, macOS and Linux).

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
