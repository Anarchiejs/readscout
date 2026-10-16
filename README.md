# readscout

[![CI](https://github.com/Anarchiejs/readscout/actions/workflows/ci.yml/badge.svg)](https://github.com/Anarchiejs/readscout/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Local models read your files for your coding agent.** When Claude Code or Codex needs facts from big files, a long
log or a whole folder, it asks readscout instead of reading everything itself. A small model on your own GPU reads
the files and answers in a few lines, and **every claim comes with a quote that readscout checked word for word in the
source**, with its real `file:line`. The quote and the line are proven; the sentence next to them is still the model's
reading, so your agent opens the cited lines before any decision. Your agent keeps its context window (and your usage quota) for the real thinking.
Nothing ever leaves your machine.

[Version française](README.fr.md)

```text
> local_ask(["app.js"], "Which POST routes are registered WITHOUT passportConfig.isAuthenticated?")

[local_ask · gemma4:26b · 1 chunk(s), 21 KB read locally, 23 s · 18 verified quote(s), 0 dropped (quote not found in source) · quotes are verified, sentences are the model's]
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
- [First steps](#first-steps) · [Everyday use](#everyday-use) · [Commands](#commands) · [Models](#models) · [Faster with llama.cpp](#faster-with-llamacpp-optional)
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
- models free your RAM and VRAM by themselves, whichever engine runs them (Ollama, or llama.cpp's `llama-server`, which
  readscout starts and stops itself): they unload one minute after the last call, and as soon as the agent session
  ends. Nothing to stop by hand (`readscout stop` frees memory at once).

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
- **Optional, only to read big inputs faster with the 26B model: [llama.cpp](https://github.com/ggml-org/llama.cpp)**
  (`llama-server`; the installer does not install it, see [Faster with llama.cpp](#faster-with-llamacpp-optional)).
  It reuses the model files Ollama already downloaded. On an **NVIDIA** GPU take a **CUDA** build (about 150 MB, plus about
  400 MB of CUDA runtime on Windows): CUDA 13 builds need NVIDIA driver 580 or newer (`nvidia-smi` shows yours), take a
  CUDA 12 build for an older driver ([NVIDIA's compatibility table](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)).
  The Vulkan build that `winget install llama.cpp` installs ran slower than Ollama on an NVIDIA card. AMD (ROCm or Vulkan
  build) and Apple silicon (Metal build) have not been measured: compare with `readscout bench`.

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
download the models:

```sh
uvx --from https://github.com/Anarchiejs/readscout/releases/download/v0.1.6/readscout-0.1.6-py3-none-any.whl readscout setup
```

That opens the same setup page as option A: install the models there (skip
"Coding agents": the plugin already did it). Restart Claude Code.

Tip: to have a short `readscout` command for later, install it once with
`uv tool install https://github.com/Anarchiejs/readscout/releases/download/v0.1.6/readscout-0.1.6-py3-none-any.whl`.

### Option C: manual install

```sh
# 1. Ollama: https://ollama.com/download (then make sure it is running)
# 2. uv:     https://docs.astral.sh/uv/getting-started/installation/
# 3. readscout
uv tool install https://github.com/Anarchiejs/readscout/releases/download/v0.1.6/readscout-0.1.6-py3-none-any.whl

# 4. models recommended for your machine (see `readscout hardware` first if you are curious)
readscout pull

# 5. connect your agent(s)
readscout install-agent claude
readscout install-agent codex

# 6. check
readscout doctor
```

Restart Claude Code / Codex.

## First steps

1. **Check the setup:** `readscout doctor` must end with `All good.` (plugin users: use the `uvx ... readscout` form above).
2. **Open any project** in Claude Code or Codex.
3. **Ask something that needs a lot of reading**, in your own words. For example:
   - "Which API routes in `src/routes` don't check authentication?"
   - "Where is the session expiry handled in this repo?"
   - "Summarize what the `lib/` folder does."
   - "Run the tests and tell me why they fail" (the agent saves the output to a file and digests it).
4. **Watch the agent call `local_ask` or `local_digest`** and get a short receipt instead of opening every file.
   The first call loads the model into memory (10-30 s); later calls are faster.
5. **Inspect local reading:** `readscout stats`, or `readscout dashboard` for the usage page.
   The token-equivalent local text reduction is an estimate, not measured agent savings.

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

## Commands

```text
readscout setup                        open the setup page
readscout doctor                       check that everything is installed and wired
readscout hardware                     detected GPU/RAM and recommended models
readscout pull [MODEL ...]             download models (default: the recommended ones)
readscout install-agent claude|codex   register the MCP server and the skill (uninstall-agent to undo)
readscout ask PATH... -q QUESTION      run local_ask from the terminal (--summary, --quality)
readscout digest PATH                  run local_digest from the terminal
readscout edit PATH... -i TEXT --gate "CMD"   run local_edit from the terminal
readscout folders [add|remove DIR...]  limit the local models to these folders (no list: any folder)
readscout gate on|off                  allow or forbid local_edit's gate commands
readscout engine [ollama|llamacpp]     which engine runs each model (see "Faster with llama.cpp")
readscout stats                        what was read locally instead of by your agent
readscout dashboard                    usage page
readscout stop                         unload every model now, on both engines (they also unload by themselves)
readscout bench                        measure your models on the public benchmark
```

Settings and usage data live in your user folder, never in the package: `%APPDATA%\readscout` on Windows,
`~/Library/Application Support/readscout` on macOS, `~/.config/readscout` on Linux (`config.json`, `metrics.jsonl`,
and with llama.cpp `llamacpp.json`, `llama-server.log`).

## Models

Chosen per machine from [`catalog.json`](src/readscout/catalog.json), measured with the public benchmark:

| Your machine | Fast | Quality |
|---|---|---|
| less than ~6 GB VRAM | `gemma4:e2b` | `gemma4:e2b` |
| 6-7 GB VRAM | `gemma4:e4b` | `gemma4:e4b` |
| 8-9 GB VRAM, 16 GB RAM | `gemma4:e4b` | `gemma4:12b` (part of it runs from RAM) |
| 10 GB VRAM or more, 8 GB RAM or more, less than ~30 GB RAM | `gemma4:e4b` | `gemma4:12b` |
| 6-14 GB VRAM, 32 GB RAM or more | `gemma4:e4b` | `gemma4:26b` (MoE, experts in RAM) |
| 15 GB VRAM or more, 16 GB RAM or more | `gemma4:e4b` | `gemma4:26b`, mostly on the GPU |

The context size follows the machine too: 32k tokens by default, 64k for the fast model from 12 GB of VRAM, and for the
quality model from 24 GB (26B) or 14 GB (12B). A bigger context means fewer chunks on big files; it has not been
benchmarked yet, and you can change it in `config.json` (`models.<tier>.ctx`).

On an RTX 4060 Ti 8 GB + 32 GB RAM ([docs/BENCHMARK.md](docs/BENCHMARK.md)): `gemma4:12b` and `gemma4:26b` score 0.94 and
0.93 on 25 reading tasks from four pinned open-source repositories (about 24 and 23 s per task), `gemma4:e4b` 0.83 with
7/7 edits (about 6 s). Negative questions are where the small models fail (`gemma4:e4b` 0.28, `gemma4:e2b` 0.12, the
bigger ones 0.88), which is why readscout sends them to the quality model. Measure your own machine with `readscout bench`
and share the table in an issue.

### Faster with llama.cpp (optional)

Ollama is the default engine and stays the best choice on most machines. [llama.cpp](https://github.com/ggml-org/llama.cpp)
reads big prompts about twice as fast with a mixture-of-experts quality model, but writes more slowly. Measured on an
RTX 4060 Ti 8 GB + 32 GB RAM (Ollama 0.40.3, llama.cpp b11636 CUDA, the same GGUF files, Gemma 4,
[full results](docs/bench-results/rtx4060ti-8gb_32gb-ram_windows_ollama-vs-llamacpp.json)):

| | Ollama | llama.cpp (CUDA) |
|---|---|---|
| `gemma4:26b`, reading a prompt | 554-566 tokens/s | 1,008-1,205 tokens/s (`--n-cpu-moe 30`) |
| `gemma4:26b`, writing | 42-45 tokens/s | 24-25 tokens/s |
| `gemma4:26b`, a 181 KB folder, new files (3 chunks of ~25k tokens) | 181 s | 127 s |
| `gemma4:26b`, the same folder asked again (cached prompt) | 30 s | 54 s |
| `gemma4:26b`, public benchmark (small inputs) | 0.93, 23 s/task, edits 9.7 s | 0.94, 23 s/task, edits 14 s |
| `gemma4:12b`, public benchmark | 0.94, 24 s/task, edits 6/7 in 12 s | 0.93, 50 s/task (2x slower), edits 6.8/7 in 25 s |
| `gemma4:e4b`, public benchmark | 0.83, 5.8 s/task, edits 7/7 | 0.86, 16.9 s/task (3x slower), edits 6.8/7 |

So llama.cpp pays off for one thing: reading **new** big inputs with the 26B (here 1.4x faster overall, 2x on the prompt
alone). It loses when the same files are asked about again (Ollama keeps the start of the prompt in cache and writes
faster), and it is slower for the fast and the 12B models. That is why each model can run on its own engine. The Vulkan
build that `winget install llama.cpp` installs was slower than Ollama on an NVIDIA card: with NVIDIA, take the CUDA build
from the [releases](https://github.com/ggml-org/llama.cpp/releases) (`llama-bXXXX-bin-win-cuda-13.x-x64.zip` plus the
matching `cudart-...zip`; see [Requirements](#requirements) for the driver). On a machine with an integrated GPU too, add
`--args "--device CUDA0"` (or `Vulkan0`) so the model is not split onto it; `readscout doctor` shows the device ids.

```sh
readscout engine llamacpp --quality ollama:gemma4:26b --binary path/to/llama-server --args "--n-cpu-moe 30"
readscout engine                                         # fast: ollama gemma4:e4b, quality: llamacpp ...
readscout doctor
readscout bench --models gemma4:26b,llamacpp:quality     # compare both engines on your machine
```

Only the models you name move to llama.cpp: above, the fast model stays on Ollama (`--fast ollama:gemma4:e4b` would
move it too, `--quality ollama` moves the quality model back). `ollama:<model>` reuses the file Ollama already
downloaded (nothing to download again); a `.gguf` path works too. readscout then starts `llama-server` itself on a free loopback port (flash attention, 8-bit KV cache, 2048 micro-batch,
Ollama's repeat penalty), keeps a single model loaded, shared by all your agent sessions, and stops it after the same
idle delay as Ollama (one minute) or when the session ends; `readscout stop` stops it at once. On an 8 GB card the two
engines cannot both hold a model, so they take turns: before llama.cpp loads a model, readscout unloads Ollama's, and
before an Ollama call it stops its idle llama-server (never one in the middle of another session's request; switching
costs a model load, a few seconds from RAM). Extra flags go in
`--args`, for all models, or in `config.json` under `llamacpp.models.<tier>.args` for one (the 26B above used
`["--n-cpu-moe", "30"]`). Already running your own `llama-server`? Give its address instead: `--fast http://127.0.0.1:8080`
(readscout then never starts or stops it). Every model back on Ollama: `readscout engine ollama` (your llama.cpp
models are kept: `readscout engine llamacpp` brings them back). Restart your agent after switching.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Anything odd | `readscout doctor` lists what is missing, with the command that fixes it |
| "Ollama is not installed" / "Ollama did not start" | install or start Ollama (on Windows and macOS, readscout starts the app by itself) |
| "llama-server not found" or "model file not found" | you chose llama.cpp for a model: install it or fix the path (`readscout engine`), or go back with `readscout engine ollama` |
| llama.cpp is slower than Ollama on an NVIDIA GPU | `readscout doctor` lists the devices llama-server sees: with only `Vulkan0` or no GPU, take the CUDA build |
| llama.cpp split the model onto your integrated GPU | `readscout engine llamacpp --args "--device CUDA0"` (the id `doctor` shows for your GPU) |
| "Model ... is not installed yet" | `readscout pull` |
| A model fails to load with "out of memory" or "Gemma4Assistant requires ctx_other" although the GPU looks free | a `llama-server.exe` from Ollama's folder (`...\Ollama\lib\ollama`) was left running by an earlier Ollama session and still holds the GPU: quit Ollama from its tray icon, end that process, start Ollama again (seen on Windows after Ollama restarted itself during a long run) |
| The agent never uses readscout | restart the agent after installing; check with `readscout doctor` that it is connected |
| Answers are slow | normal on small GPUs for the quality model (20-60 s); the fast model answers in seconds |
| Bigger models run out of memory on Windows | setup page, **Apply** under "Recommended Ollama settings", then restart Ollama |

## Security and privacy

- Models run on `127.0.0.1` only; any other endpoint is refused in code, and so are Ollama cloud models (by name and
  when Ollama reports them as served by a remote host). readscout never calls an online model, even as a fallback. If you
  use Ollama itself with cloud features, that is outside readscout; the Ollama settings it offers also switch them off
  (`OLLAMA_NO_CLOUD=1`). With the optional llama.cpp engine, readscout starts `llama-server` itself, bound to
  `127.0.0.1` on a free port with a random secret key (so a web page cannot query it), only for the `.gguf` files you
  configured; a server you run yourself must be on `127.0.0.1` too.
- The model has **no tools**: it reads the text readscout gives it and returns JSON. Only readscout reads files: the ones your
  agent names, by default in any folder (nothing to register). `.env*`, `.git`, keys, credential files and binaries are
  always refused whatever the letter case; common secrets (provider keys and tokens, JWTs, passwords in URLs,
  `Authorization` headers, `password`/`secret`/`token` assignments, also in JSON) are masked before reaching the model,
  and `local_edit` refuses files that contain one. Masking is pattern based: it cannot catch every secret, so keep real
  credentials out of your projects.
- **If you restrict your agent** (no Bash, `Read` limited to some folders in Claude Code's permissions), readscout does
  not see those rules: it reads what the agent names and runs its `gate` commands. To keep the same limits, use
  `readscout folders add <folder>` (the local models then only read and write inside the listed folders; `readscout
  folders` shows the list, `readscout folders remove <folder>` drops one) and `readscout gate off` (`local_edit` then
  refuses any gate command). `readscout doctor` shows both settings.
- File contents and model answers are treated as data, never as instructions. Model-written text is flattened to short
  single lines in the receipts, but it stays unverified: the agent checks the cited lines before deciding.
- `local_edit` writes atomically, never overwrites a file that changed while the model was working, and restores only
  what it wrote. Its `gate` commands are run **as you**, without a shell, in the project folder: they are chosen by the
  calling agent, exactly like the tests it would run itself.
- Stored locally, in your user folder: `config.json` and `metrics.jsonl` (tool, model, sizes, timings and counts; never
  file contents, questions or answers), and with llama.cpp `llamacpp.json` (the running server's process, port and last
  use) and `llama-server.log` (model loading messages and timings; no file contents). Nothing is sent anywhere. Agent installers back up `~/.codex/config.toml` once
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
Roadmap: more model families in the catalog, GGUF downloads for the llama.cpp engine from the setup page, more
benchmark tasks.

## License

[MIT](LICENSE)
