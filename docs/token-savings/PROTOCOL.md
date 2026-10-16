# Pre-registered token savings protocol

This file is frozen before measured sessions. Amendments may only be appended.

## Setup and selection

Environment, exact source hashes, pinned corpus, versions, model, effort, seed and
selected tasks are recorded below and in results.json. The repository venv is used
at exactly v0.1.6; src/readscout stays frozen throughout the campaign.
Each cell runs once, strictly sequentially. One retry is allowed only for a crash
or timeout, retaining the original attempt. A session timeout is 1200 seconds.
The pilot executes the two specified task pairs in their randomized relative order;
remaining pairs retain their randomized order. Pair first configuration alternates
by the original randomized index. Pilot data counts unless the harness changes.
Controls run after the pilot and are excluded from task aggregates.

## Isolation and execution

Two temporary HOME/USERPROFILE/CODEX_HOME/APPDATA directories contain only minimal
configuration and copied authentication. B is installed using install-agent codex.
A has no skill or MCP. B gets a fresh READSCOUT_HOME per session, explicitly in
the MCP env table. No real user configuration is written, no existing process is
killed. Codex exec uses --json, --ephemeral, --skip-git-repo-check, --sandbox read-only,
-c approval_policy="never", -m, -c model_reasoning_effort, -C, --output-schema, -o.
No model warmup. Stop is called after B only when no pre-existing Ollama model
would be affected; otherwise only models used by this session may be unloaded.
The MCP remains the installed three-tool surface; local_edit is outside scope.
Final answers and JSONL events are scrubbed before storage. Temporary homes are
deleted after the experiment. No credentials are printed or committed.

## Prompt and schema

The identical prompt template for A and B is:

```text
Answer a question about the code in the current directory. Do not modify any file. Question: {question}
Scope: only these files or folders, relative to the current directory: {paths}.
Answer only with JSON matching the schema: `findings` is a list of objects with `path` (relative to the current directory), `line`, `quote` (the verbatim code line, 10 to 120 characters) and `answer` (at most 30 words).
```

The controls use exactly `Reply with the word OK.` without a findings schema.
The task schema is stored in the harness. No tool-use hints are added.

## Metrics and grading

Store every turn.completed usage field verbatim and sum fields across turns.
Primary total = reported input_tokens + output_tokens. Secondary total = input
minus cached input plus output. Sensitivity assumes cached input costs 10% of
uncached input: input - 0.9 * cached + output. This is not an actual price.
Cached-input inclusion and reasoning-output inclusion will be checked against
available local session telemetry; if not empirically identifiable they remain
unverified, with no invented reasoning counts or double counting.
Savings = (A - B) / A, using sums for group/overall and paired savings for median,
min and max. Count completed shell/MCP items once, measure returned characters,
wall time, exit/timeout, read calls, model/loading telemetry and session metrics.
Grade final JSON without using the configuration label. Normalize source paths,
enforce scope, recompute quote locations with locate and call the existing score.
Keep its raw scores; count unlocatable/out-of-scope findings as wrong by multiplying
precision by verified/(verified + unverifiable) and recomputing F1. Report both.
An empty or invalid final answer has zero F1. Same grading for both configurations.
No empirical break-even threshold is inferred unless the observed pairs support it.

## Hypotheses and falsification

- H1: W total tokens fall clearly, defined before running as at least 10%.
  Refuted when W savings are below 10%; inconclusive if W pairs are incomplete.
- H2: L B total is at least A total. Refuted by positive aggregate L savings.
- H3: mean task F1 B is no more than 0.05 below A. Refuted by a larger loss.
- H4: sum dashboard tokens_avoided_est exceeds A-B measured tokens. Refuted
  when estimate is no greater than actual saving. Negative savings are reported.
- H5: at least one B task does not call local_ask/local_digest. Refuted if every
  completed B task calls one. Incomplete campaign verdicts remain inconclusive.

## Limitations

One run per cell, no significance claim; one agent, one machine; project-authored
public corpus, caching, run order, cold model loading and nondeterminism. A pilot
without real successful MCP execution does not authorize the remaining campaign.
Missing metrics are not measured, never zero-filled as measurements.

## Frozen environment and tasks

```json
{
  "date": "2026-10-16",
  "seed": 20261016,
  "model": "gpt-6.1-sol",
  "effort": "medium",
  "readscout": "0.1.6",
  "codex": "codex-cli 0.163.0-alpha.10.2",
  "ollama": "ollama version is 0.40.3",
  "models": "NAME                    ID              SIZE      MODIFIED     \ngemma4:26b              001e5dafc3c7    18 GB     44 hours ago    \ngemma4:12b              6114515d63c1    8.0 GB    44 hours ago    \ngemma4:e2b              b37049369adf    4.6 GB    44 hours ago    \ngemma4:e4b              dc35e8d9c606    6.6 GB    45 hours ago    \nrp-gemma4-26b:latest    0973f4c231ae    18 GB     3 days ago      \nrp-gemma4-e4b:latest    f52667d3bc70    6.6 GB    3 days ago      \n",
  "hardware": {
    "vram_gb": 8.0,
    "ram_gb": 31.1,
    "gpu": "NVIDIA GeForce RTX 4060 Ti",
    "source": "nvidia-smi",
    "os": "windows"
  },
  "platform": "Windows-11-10.0.26300-SP0",
  "cpu": "AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD",
  "source_commit": "6bb283e073254c9e19eedb025a750d50e541f46f",
  "source_hashes": {
    "src\\readscout\\__init__.py": "2e049d3680ca287b0cfb0e502bbe25cabe3934689722b0a3f1622736e20359c0",
    "src\\readscout\\agents.py": "22ab11dc2678611adba916ede2738758341c1fc28107cd354a3bf038ef7135ab",
    "src\\readscout\\backend.py": "98930446c483fb1a1358b90b1d3ebdeada94a19fd8343fba5c63b2c17d7d0072",
    "src\\readscout\\bench\\__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src\\readscout\\bench\\corpus.py": "7f25484bd64f87f14665d37601ccd896bf03104d2e0781eeebae505b84da4363",
    "src\\readscout\\bench\\edits.py": "42a2d6e9314348af77e5b25e728c2fdc3c21578834787c81bebe752ecc948f99",
    "src\\readscout\\bench\\generate.py": "4d5b51855635378a054c37b0565225250976caea02a585381c2fe01915189068",
    "src\\readscout\\bench\\logs.py": "edac9b5ee9cf6199d0325d19dbb761d68a8c904a424abc0c07d9433368ff84ab",
    "src\\readscout\\bench\\runner.py": "d3398bd85c3d31f77298abb3d860622bee330e6860f866436003f15d829b755a",
    "src\\readscout\\catalog.json": "b7afc7098f63ea91926eef928e7c3795de9ebf62cd8cdcf0e678b9ef95957307",
    "src\\readscout\\cli.py": "499d763453fc0a87ce9011c05897d2cc6a974765ec38993d9d11245f834c6296",
    "src\\readscout\\editing.py": "28772f1701aa3e18d27067c38c3401c1641f6d4ffb47180bb7daecc6912d07b5",
    "src\\readscout\\hardware.py": "11bae77647aeef043a65bc08c34cbcd346e0c130f6cb4bb9eda123b2ef6a0364",
    "src\\readscout\\llamacpp.py": "7b8403fd439e6e7aa4536510d0362a2bee476e514a45e7f31c4b62d47fec754f",
    "src\\readscout\\paths.py": "0923af6a7b20c5a6aff7d9487a84ca133020a75285a69008eb278d4a9efae42a",
    "src\\readscout\\server.py": "83818b76b3a92a1ff12d725cb008b68c8749b313d30497841a3c6e2610ae805a",
    "src\\readscout\\skill\\SKILL.md": "f4e90aea6bb4d6e2e331bff718d99af20e808cf7d3344bc8056a344eeedb0e66",
    "src\\readscout\\stats.py": "9b92cf08c495b7e3201ab819b2d806ca807ec9c6efc5b7361645494ed3c5d3d1",
    "src\\readscout\\tasks.py": "4463ab0ec37f6f2ac15d63a6e07286d4749c65e98aadca6dfd79146eb071e9b1",
    "src\\readscout\\text.py": "c292bace5ee725b33875b7d88d4079aeb9b8b48538a410c7b84ccb6c53cdf8a4",
    "src\\readscout\\web\\index.html": "663093c7d38cc69780bd6e9b78477df087b2c55c64b5c83665260ce6ae8c0195",
    "src\\readscout\\web.py": "2dd2cb22b3094c1ecb1246f5ab1c0f4bd483c42bda7a68335641307d7f19123f"
  },
  "tasks": [
    {
      "id": "boilerplate:routes_without_auth",
      "group": "N",
      "bytes": 15482,
      "paths": [
        "src/routes/v1/user.route.js",
        "src/routes/v1/auth.route.js"
      ],
      "order": [
        "A",
        "B"
      ]
    },
    {
      "id": "hackathon:routes_auth",
      "group": "M",
      "bytes": 21033,
      "paths": [
        "app.js"
      ],
      "order": [
        "B",
        "A"
      ]
    },
    {
      "id": "hackathon:locate:ai.js:359",
      "group": "L",
      "bytes": 32396,
      "paths": [
        "controllers/ai.js"
      ],
      "order": [
        "A",
        "B"
      ]
    },
    {
      "id": "logs:service-3000.log",
      "group": "W",
      "bytes": 251485,
      "paths": [
        "service-3000.log"
      ],
      "order": [
        "B",
        "A"
      ]
    },
    {
      "id": "hackathon:env_controllers",
      "group": "W",
      "bytes": 158897,
      "paths": [
        "controllers"
      ],
      "order": [
        "A",
        "B"
      ]
    },
    {
      "id": "boilerplate:routes_all",
      "group": "W",
      "bytes": 15482,
      "paths": [
        "src/routes/v1/user.route.js",
        "src/routes/v1/auth.route.js"
      ],
      "order": [
        "B",
        "A"
      ]
    },
    {
      "id": "nextjs:supabase_access",
      "group": "W",
      "bytes": 15480,
      "paths": [
        "utils/supabase"
      ],
      "order": [
        "A",
        "B"
      ]
    },
    {
      "id": "logs:service-9000.log",
      "group": "W",
      "bytes": 753803,
      "paths": [
        "service-9000.log"
      ],
      "order": [
        "B",
        "A"
      ]
    },
    {
      "id": "hackathon:locate:ai-agent.js:263",
      "group": "L",
      "bytes": 25858,
      "paths": [
        "controllers/ai-agent.js"
      ],
      "order": [
        "A",
        "B"
      ]
    },
    {
      "id": "hackathon:post_without_auth",
      "group": "N",
      "bytes": 21033,
      "paths": [
        "app.js"
      ],
      "order": [
        "B",
        "A"
      ]
    },
    {
      "id": "hackathon:routes_limited",
      "group": "M",
      "bytes": 21033,
      "paths": [
        "app.js"
      ],
      "order": [
        "A",
        "B"
      ]
    },
    {
      "id": "logs:service-800.log",
      "group": "L",
      "bytes": 67366,
      "paths": [
        "service-800.log"
      ],
      "order": [
        "B",
        "A"
      ]
    },
    {
      "id": "fastapi:public_endpoints",
      "group": "N",
      "bytes": 16012,
      "paths": [
        "backend/app/api/routes"
      ],
      "order": [
        "A",
        "B"
      ]
    },
    {
      "id": "boilerplate:env_schema",
      "group": "L",
      "bytes": 2424,
      "paths": [
        "src/config/config.js"
      ],
      "order": [
        "B",
        "A"
      ]
    },
    {
      "id": "fastapi:endpoints_all",
      "group": "W",
      "bytes": 16012,
      "paths": [
        "backend/app/api/routes"
      ],
      "order": [
        "A",
        "B"
      ]
    }
  ],
  "deviations": [],
  "install": "Codex: [mcp_servers.readscout] written to <HOME>\\AppData\\Local\\Temp\\readscout-token-savings-l79mvh5x\\B\\.codex\\config.toml (backup: config.toml.readscout-bak), skill copied to <HOME>\\AppData\\Local\\Temp\\readscout-token-savings-l79mvh5x\\B\\.agents\\skills\\readscout\\SKILL.md. Restart Codex.\nNote: local_edit runs the check commands your agent picks, with your rights, even if the agent itself may not use a shell. If you restrict your agent, run `readscout gate off`.\n",
  "doctor": "OK   Ollama installed\nOK   Ollama running (0.40.3)\nOK   fast model gemma4:e4b installed\nOK   quality model gemma4:26b installed\nOK   config at <HOME>\\AppData\\Local\\Temp\\readscout-token-savings-l79mvh5x\\doctor\\config.json\n     folders: any folder the agent names; local_edit gate commands: on\n     note: local_edit runs the check commands your agent picks, with your rights, even if the agent itself may not use a shell. If you restrict your agent, run `readscout gate off`.\nOK   Codex wired (MCP + skill)\n\nAll good.\n",
  "doctor_ok": true
}
```

## Deviation: interrupted pilot

Coordinator interrupted the first pilot before its buffered output was saved. No completed final answer or usage was recoverable. The pilot is discarded after a harness change that persists raw events immediately. The interrupted attempt is retained with missing telemetry, not treated as zero tokens. No other measured session had started.

## Deviation: Windows isolation preflight

Discarded the pilot after offline verification showed Windows Codex discovers OS-profile global skills despite fake HOME/USERPROFILE. A also rejected all shell reads because the Windows sandbox backend was unspecified. A completed with an empty answer; B was cancelled after diagnosis to avoid wasting quota. Both traces and available usage/metrics are retained as discarded data. The corrected harness disables discovered global skills only in temporary configs, copies the installed B skill to the fake CODEX_HOME skill directory, disables account apps/plugins identically, sets --no-daemon and windows.sandbox=unelevated, and verifies that public temporary corpus reads succeed while writes fail. Copied authentication remains private. The remaining campaign has not run.

## Deviation: exec option placement

A second pilot was discarded after local deterministic HTTP mock diagnostics demonstrated that this CLI does not apply the top-level -c Windows sandbox override when exec has its own overrides. With the backend override before exec, the identical mock Get-Content call was rejected; after exec, it returned READ_OK with exit zero. Mock traffic used a localhost provider and no real credentials or model quota. All session config overrides and feature switches now follow exec. A separate mock confirmed the successful command_execution event shape. Failed real pilot A usage and partial B metrics remain in discarded_attempts and runs/discarded-options. No saving is inferred from these invalid runs.

## Telemetry validation: deterministic local transport

A localhost Responses mock, with no real credentials and no model quota, sent two responses, each with input_tokens=100, cached_tokens=25, output_tokens=50 and reasoning_tokens=10. The CLI reported input_tokens=200, cached_input_tokens=50, output_tokens=100 and reasoning_output_tokens=20. Thus the CLI preserves upstream total input/output counters and reports cached/reasoning components separately; neither component is added again to primary total. The mock verifies parser/accounting behavior, not provider billing. The diagnostic values will be stored in results.json and excluded from campaign aggregates.
