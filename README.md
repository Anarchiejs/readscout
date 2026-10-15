# readscout

[![CI](https://github.com/Anarchiejs/readscout/actions/workflows/ci.yml/badge.svg)](https://github.com/Anarchiejs/readscout/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Local models read your files for your coding agent.** When Claude Code or Codex needs facts from big files, a long
log or a whole folder, it asks readscout instead of reading everything itself. A small model on your own GPU reads
the files and answers in a few lines, and **every claim comes with a quote that readscout checked word for word in the
source**, with its real `file:line`. Your agent keeps its context window (and your usage quota) for the real thinking.
Nothing ever leaves your machine.

[Version française](README.fr.md)

```text
> local_ask(["app.js"], "Which POST routes are registered WITHOUT passportConfig.isAuthenticated?")

[local_ask · gemma4:26b · 1 chunk(s), 21 KB read locally, 23 s · 18 verified quote(s), 0 dropped (quote not found in source)]
- app.js:253 : The POST route '/login' is registered without passportConfig.isAuthenticated. « app.post('/login', loginLimiter, userController.postLogin); »
- app.js:256 : The POST route '/login/2fa' is registered without passportConfig.isAuthenticated. « app.post('/login/2fa', login2FALimiter, userController.postTwoFactor); »
- app.js:269 : The POST route '/signup' is registered without passportConfig.isAuthenticated. « app.post('/signup', userController.postSignup); »
...
```

That is a real run on [hackathon-starter](https://github.com/sahat/hackathon-starter)'s 101-route `app.js`: 21 KB stayed
out of the agent's context, 18 of the 19 matching routes came back, none wrong, every line number real. The question
contains "WITHOUT", so readscout picked the bigger model by itself.

## Contents

- [What it does](#what-it-does) · [Why](#why) · [Requirements](#requirements)
- Install: [one-line installer](#option-a-one-line-installer-recommended) · [Claude Code plugin](#option-b-claude-code-plugin) · [manual](#option-c-manual-install)
- [First steps](#first-steps) · [Everyday use](#everyday-use) · [Commands](#commands) · [Models](#models)
- [Troubleshooting](#troubleshooting) · [Security and privacy](#security-and-privacy) · [Limits](#limits) · [Uninstall](#uninstall)

## What it does

readscout is an [MCP](https://modelcontextprotocol.io) server with three tools, plus a skill that tells your agent
when to use them:

| Tool | Your agent gives it | It gets back |
|---|---|---|
| `local_ask(paths, question)` | files or folders (up to 1.5 MB) and a question | a few findings, each with a verified quote and its real `file:line` (`mode="summary"` adds a short summary) |
| `local_digest(path)` | a long log or command output | the root cause and the distinct failures, with verified quotes |
| `local_edit(paths, instruction, gate)` | files, a precise change, and check commands (your tests) | `APPLIED` + the diff if your checks pass, else `ESCALATE` with the files restored byte for byte |

How the answers stay trustworthy:
- the model's output is constrained by a JSON schema, so it always parses;
- any finding whose quote is not found in the source is **dropped**; line numbers are computed by readscout, never by the model;
- large inputs are split into chunks instead of being refused; logs are pre-filtered (errors with context, start, end, no duplicates);
- negative questions ("without", "not", "missing") go to the bigger model automatically, because small models get them wrong;
- an edit is kept only if your tests pass;
- models free your RAM and VRAM by themselves: Ollama unloads them one minute after the last call, and readscout
  unloads them as soon as the agent session ends. Nothing to stop by hand (`readscout stop` frees memory at once).

## Why

Every turn of an agent session re-sends the whole conversation, so each big file or log your agent reads keeps
costing tokens until the session ends. Most of that reading is mechanical: finding where something is, listing what
matches a pattern, spotting the error in a log. A small local model does that well **if it must prove what it says**.

Earlier "delegate to a local model" setups (including the one this project replaces) failed for measurable reasons:
they delegated judgement (code review, fact checking), refused large inputs, and cost the agent more tokens to drive
than doing the task itself. readscout delegates reading only, adapts to any input size, and returns a short receipt.
The story and the numbers: [docs/DESIGN.md](docs/DESIGN.md) and [docs/BENCHMARK.md](docs/BENCHMARK.md).

## Requirements

- **Windows, macOS or Linux.**
- **A coding agent:** [Claude Code](https://claude.com/claude-code) and/or [Codex](https://developers.openai.com/codex).
- **[Ollama](https://ollama.com)** to run the models (the installer can install it for you).
- **Hardware:** a GPU with 6 GB of memory or more is recommended (NVIDIA, AMD, or Apple silicon), and 16 GB of RAM.
  With 8 GB of VRAM and 32 GB of RAM you get the best measured setup. It also runs on CPU only, slowly.
- **Disk:** 7 to 25 GB for the models, depending on your machine.

## Installation

Pick one option. **A** sets up everything for Claude Code and Codex. **B** is the quickest way if you only use Claude
Code. **C** is the same as A, done by hand.

### Option A: one-line installer (recommended)

Windows (PowerShell):
```powershell
irm https://raw.githubusercontent.com/Anarchiejs/readscout/main/install.ps1 | iex
```
macOS / Linux:
```sh
curl -fsSL https://raw.githubusercontent.com/Anarchiejs/readscout/main/install.sh | sh
```

The installer asks before installing anything:
1. **uv**, a Python manager from [Astral](https://docs.astral.sh/uv/) (it brings its own Python; you need nothing else);
2. **Ollama**, if it is missing (winget on Windows, Homebrew on macOS, the official script on Linux);
3. **readscout** itself;
4. then it opens the **setup page** in your browser (`http://127.0.0.1:8765/setup`):
   - **Your machine:** GPU memory and RAM are detected and pre-filled; adjust the sliders (VRAM 6-24 GB, RAM 16-64 GB) if needed;
   - **Models:** the models recommended for that machine, each with an **Install** button (one click, with a progress bar), then **Use these models**;
   - **Coding agents:** **Connect** Claude Code and/or Codex (registers the MCP server and copies the skill);
   - **Project folders:** add the folders the local models are allowed to read;
   - **Check:** everything should be green.

Restart Claude Code / Codex, and continue with [First steps](#first-steps).

### Option B: Claude Code plugin

For Claude Code only. You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Ollama](https://ollama.com)
installed first. In Claude Code, run:

```text
/plugin marketplace add Anarchiejs/readscout
/plugin install readscout@readscout
```

The plugin brings the skill and the MCP server (started with `uvx`, nothing else to install). Then, in a terminal,
download the models and allow a project folder:

```sh
uvx --from https://github.com/Anarchiejs/readscout/releases/download/v0.1.2/readscout-0.1.2-py3-none-any.whl readscout setup
```

That opens the same setup page as option A: install the models and add your project folders there (skip
"Coding agents": the plugin already did it). Restart Claude Code.

Tip: to have a short `readscout` command for later, install it once with
`uv tool install https://github.com/Anarchiejs/readscout/releases/download/v0.1.2/readscout-0.1.2-py3-none-any.whl`.

### Option C: manual install

```sh
# 1. Ollama: https://ollama.com/download (then make sure it is running)
# 2. uv:     https://docs.astral.sh/uv/getting-started/installation/
# 3. readscout
uv tool install https://github.com/Anarchiejs/readscout/releases/download/v0.1.2/readscout-0.1.2-py3-none-any.whl

# 4. models recommended for your machine (see `readscout hardware` first if you are curious)
readscout pull

# 5. connect your agent(s)
readscout install-agent claude
readscout install-agent codex

# 6. allow a project folder (repeat for each project)
readscout register my-app /path/to/my-app

# 7. check
readscout doctor
```

Restart Claude Code / Codex.

## First steps

1. **Check the setup:** `readscout doctor` must end with `All good.` (plugin users: use the `uvx ... readscout` form above).
2. **Open a project you allowed** in Claude Code or Codex.
3. **Ask something that needs a lot of reading**, in your own words. For example:
   - "Which API routes in `src/routes` don't check authentication?"
   - "Where is the session expiry handled in this repo?"
   - "Summarize what the `lib/` folder does."
   - "Run the tests and tell me why they fail" (the agent saves the output to a file and digests it).
4. **Watch the agent call `local_ask` or `local_digest`** and get a short receipt instead of opening every file.
   The first call loads the model into memory (10-30 s); later calls are faster.
5. **See what it saved:** `readscout stats`, or `readscout dashboard` for the usage page.

You can also call the tools from a terminal, without any agent, to see what they return:
```sh
cd /path/to/my-app
readscout ask src -q "Which functions read environment variables?"
readscout digest build.log
```

## Everyday use

You keep working as usual: the skill tells the agent when to delegate. It uses readscout for:
- facts spread over files it has not read yet (more than a few hundred lines in total);
- understanding a module or folder without reading it;
- long logs, test or build output;
- small, fully specified mechanical edits (docstrings, type hints, renames, a new parameter, test scaffolding),
  always with your tests as the gate.

It keeps for itself: anything a quick `grep` answers, short files it reads anyway, and every **judgement**
(code review, "is there a bug", architecture, real-world facts).

Things you may see in a receipt:
- `retried with quality model`: the fast model found nothing quotable, the bigger one was used;
- `quality model ... not installed, used ...`: install it with `readscout pull <model>` for better answers;
- `The list may be incomplete`: the agent should narrow the question or add a `grep`;
- `File not found inside a registered project`: the agent will ask you before allowing that folder.

## Commands

```text
readscout setup                        open the setup page
readscout doctor                       check that everything is installed and wired
readscout hardware                     detected GPU/RAM and recommended models
readscout pull [MODEL ...]             download models (default: the recommended ones)
readscout install-agent claude|codex   register the MCP server and the skill (uninstall-agent to undo)
readscout register ID PATH             allow a project folder (unregister ID to remove it)
readscout projects                     list allowed folders
readscout ask PATH... -q QUESTION      run local_ask from the terminal (--summary, --quality)
readscout digest PATH                  run local_digest from the terminal
readscout edit PATH... -i TEXT --gate "CMD"   run local_edit from the terminal
readscout stats                        what was read locally instead of by your agent
readscout dashboard                    usage page
readscout stop                         unload every model now (they also unload by themselves)
readscout bench                        measure your models on the public benchmark
```

Settings and usage data live in your user folder, never in the package: `%APPDATA%\readscout` on Windows,
`~/Library/Application Support/readscout` on macOS, `~/.config/readscout` on Linux (`config.json`, `metrics.jsonl`).

## Models

Chosen per machine from [`catalog.json`](src/readscout/catalog.json), measured with the public benchmark:

| Your machine | Fast | Quality |
|---|---|---|
| less than ~6 GB VRAM | `gemma4:e2b` | `gemma4:e2b` |
| 6-9 GB VRAM, less than ~30 GB RAM | `gemma4:e4b` | `gemma4:e4b` |
| 10-14 GB VRAM, less than ~30 GB RAM | `gemma4:e4b` | `gemma4:12b` |
| 6-14 GB VRAM, 32 GB RAM or more | `gemma4:e4b` | `gemma4:26b` (MoE, experts in RAM) |
| 16 GB VRAM or more | `gemma4:e4b` | `gemma4:26b`, mostly on the GPU |

On an RTX 4060 Ti 8 GB + 32 GB RAM ([docs/BENCHMARK.md](docs/BENCHMARK.md)): `gemma4:26b` and `gemma4:12b` score 0.91
on 25 reading tasks from four pinned open-source repositories (about 20 s per task), `gemma4:e4b` 0.85 with 7/7 edits
(about 5 s). Measure your own machine with `readscout bench` and share the table in an issue.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Anything odd | `readscout doctor` lists what is missing, with the command that fixes it |
| "Ollama is not installed" / "Ollama did not start" | install or start Ollama (on Windows and macOS, readscout starts the app by itself) |
| "Model ... is not installed yet" | `readscout pull` |
| "File not found inside a registered project" | `readscout register <id> <project folder>` |
| The agent never uses readscout | restart the agent after installing; check with `readscout doctor` that it is connected |
| Answers are slow | normal on small GPUs for the quality model (20-60 s); the fast model answers in seconds |
| Bigger models run out of memory on Windows | setup page, **Apply** under "Recommended Ollama settings", then restart Ollama |

## Security and privacy

- Models run on `127.0.0.1` only; any other endpoint is refused in code, and so are Ollama cloud models (by name and
  when Ollama reports them as served by a remote host). readscout never calls an online model, even as a fallback. If you
  use Ollama itself with cloud features, that is outside readscout; the Ollama settings it offers also switch them off
  (`OLLAMA_NO_CLOUD=1`).
- The model has **no tools**: it reads the text readscout gives it and returns JSON. Only readscout reads files, and only
  inside folders you allowed; `.env*`, `.git`, keys, credential files and binaries are refused whatever the letter case;
  common secret patterns (keys, tokens, `password`/`secret`/`token` assignments, also in JSON) are masked before reaching
  the model, and `local_edit` refuses files that contain one. Masking is pattern based: it cannot catch every secret, so
  keep real credentials out of the folders you allow.
- File contents and model answers are treated as data, never as instructions. Model-written text is flattened to short
  single lines in the receipts, but it stays unverified: the agent checks the cited lines before deciding.
- `local_edit` writes atomically, never overwrites a file that changed while the model was working, and restores only
  what it wrote. Its `gate` commands are run **as you**, without a shell, in the project folder: they are chosen by the
  calling agent, exactly like the tests it would run itself.
- Stored locally, in your user folder: `config.json` and `metrics.jsonl` (tool, model, sizes, timings and counts; never
  file contents, questions or answers). Nothing is sent anywhere. Agent installers back up `~/.codex/config.toml` once
  (`config.toml.readscout-bak`) and only touch the `mcp_servers.readscout` entry.
- The setup page listens on `127.0.0.1`, checks Host and Origin, and requires a per-session token for every change. The
  "Recommended Ollama settings" button saves permanent user environment variables on Windows after asking.
- Installers ask before installing uv or Ollama (and install nothing when no terminal is available unless you set
  `READSCOUT_YES=1`). Each release publishes `SHA256SUMS` for the wheel, the sdist and the installers.

Details and reporting: [SECURITY.md](SECURITY.md).

## Limits

- Small models are good readers and poor authorities: do not delegate code review, bug hunting or fact checking.
- A verified quote proves the line exists, not that the model understood it; the agent opens the cited lines before
  any decision (the skill says so).
- Lists can be incomplete (the receipt says so when a cap was hit); when completeness matters, add a targeted `grep`.
- Lines longer than 4000 characters (minified files) are cut and the receipt says so; only the start was read.
- A quote may differ from the source by whitespace and by line breaks between adjacent lines, nothing else.
- Tests run without Ollama or a GPU (a fake model); real-model checks (`scripts/e2e.sh`, `scripts/e2e.ps1`) are run by
  hand before a release and are not part of CI.

## Uninstall

```sh
readscout uninstall-agent claude      # or: /plugin uninstall readscout@readscout
readscout uninstall-agent codex
uv tool uninstall readscout
```
Models stay in Ollama (`ollama rm gemma4:26b`); settings stay in the user folder listed under [Commands](#commands).

## Contributing

Benchmark reports from other GPUs, bug reports and pull requests are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).
Roadmap: more model families in the catalog, an optional llama.cpp backend (3.5x faster prompt reading on MoE models,
measured), more benchmark tasks.

## License

[MIT](LICENSE)
