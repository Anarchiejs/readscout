# Campaign 2 frozen protocol

Freeze before any measured session. Append deviations only. Source under test is
committed separately and checked by hashes before every cell. Campaign 1 remains
unchanged except the expressly requested Campaign 2 report pointer.

## Question, conditions, and isolation

B2 versus reused B1 is primary; B2 versus reused A is secondary. Model, effort,
CLI, exact source commit and file hashes are below. Fresh pilot A cells are
diagnostics, excluded from tuning comparisons. B2 pilot cells count if harness
does not change. One run per cell, sequential; no warmup, 1200-second timeout.
No extra retries or repetitions automatically. Preserve failed attempts. Stop
on isolation failure, absent pilot MCP execution, more than three failed cells,
or B2 cumulative token total at least 10% above B1 after six tuning tasks.
The numeric definition of clearly worse is pre-registered here as 10%.

Use only temporary HOME/USERPROFILE/CODEX_HOME/APPDATA/READSCOUT_HOME, copied
authentication never logged, isolated complete skill directory, no account apps
or plugins, and read-only sandbox. Existing models/processes remain untouched;
skip online execution if a model is already resident because shared GPU handoff
could unload it. The B2 server uses this venv explicitly. Stop only campaign-owned
models. Delete fake homes at completion. CLI flags checked against local help:
--json --ephemeral --skip-git-repo-check --sandbox read-only -c approval_policy="never"
-m MODEL -c model_reasoning_effort=EFFORT -C ROOT --output-schema SCHEMA -o FINAL.
Controls use no output schema. --no-daemon and isolation overrides follow the
campaign 1 verified option positions. Do not mutate user config or Ollama settings.

## Tasks and budget

Tuning IDs and groups copied from campaign 1 without recomputation. They were
visible during improvement development. Holdout is reported separately: three
unused corpus tasks plus five newly authored ReadScout tasks, as authorized by
the user. This is task-level holdout, not a claim of independently held-out source
repositories. Synthetic build log is fixed before any run. Exact questions,
ground truth, seed, randomized order, cell list, budget and stop rules are below.
User authorized remaining quota. Account tool exposes percentages, not a token
allowance: max_tokens is not measured, never inferred from percentages. Observe
account limits before each cell and stop at the recorded 90% thresholds or reset.
Use a fresh external quota checkpoint per invocation; never loop online cells.
Unreported failed usage blocks continuation until reconciled.

## Prompt and schema

Identical to campaign 1, with no delegation hints:

```text
Answer a question about the code in the current directory. Do not modify any file. Question: {question}
Scope: only these files or folders, relative to the current directory: {paths}.
Answer only with JSON matching the schema: `findings` is a list of objects with `path` (relative to the current directory), `line`, `quote` (the verbatim code line, 10 to 120 characters) and `answer` (at most 30 words).
```

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "findings"
  ],
  "properties": {
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "path",
          "line",
          "quote",
          "answer"
        ],
        "properties": {
          "path": {
            "type": "string"
          },
          "line": {
            "type": "integer"
          },
          "quote": {
            "type": "string",
            "minLength": 10,
            "maxLength": 120
          },
          "answer": {
            "type": "string"
          }
        }
      }
    }
  }
}
```

## Metrics, attribution, and scoring

All usage fields verbatim. Primary = input + output; secondary = input - cached
input + output; sensitivity discounts cached input to 10% (assumption, not price).
Both sum-weighted savings and mean task percentages, per task/family/group/set.
Win above 5% saving, tie within inclusive +/-5%, loss below -5%. Savings require
mean F1 loss <=0.05, no extra unverifiable findings, incomplete results visible.
Only completed pairs enter paired comparisons; report missing/failed cells.

Scorer v1: unchanged campaign 1 benchmark plus its source verification penalty.
Scorer v2: same scope and locate check. An env variable can be cited anywhere in
scope if its exact identifier is in the verified source quote. A claim unsupported
by its quote does not count. All explicit method, route, table, operation and
description ground-truth fields must appear case-insensitively in quote plus
answer. Original corpus GT only has locations/keys/spans, so semantic properties
absent from that GT are not invented; new ReadScout route/data tasks carry them.
Compute recall over targets, precision over findings including unverifiable ones;
preserve v1 special log/locate precision. Regrade original A/B1 separately.
No configuration label enters either scorer. Record receipt-only and final F1.

Tool phase rules (ordered): skill core or references read = skill; readscout MCP
= readscout; after delegation explicit cited-file line window = verification;
other read/search after delegation = fallback; listing/instructions and reads
before delegation = discovery; agent final = final. These are command proxies.
Count re-reads when a later read command names a receipt file, or a broad search
may cover it (mark uncertain overlap). Targeted = sed explicit numeric line range,
Select-Object -Skip plus -First, or numeric index slice, and a named cited file;
ambiguous commands are broad. Record returned chars, targeted share, broad chars
per reading MCP call. Receipt status comes from header, not inconsistent metrics.
Next action = stopped, targeted check, or fallback. Skill read detection is based
on readscout + SKILL.md or references/ in completed shell commands.
--ephemeral has no rollout; JSON turn usage is aggregate. Per-request usage,
phase token costs, true post-truncation context and separate local load/inference
time are not measured unless directly exposed. Never allocate aggregate tokens
to commands. Preserve local telemetry verbatim and flag unavailable fields.

## Hypotheses and falsifiers

- H1: W B2/A saving >=10%; refuted below 10%.
- H2: L B2 >= A; refuted by positive aggregate savings.
- H3: mean B2 F1 >= A F1 -0.05; refuted below, for both scorers.
- H4: tokens_avoided_est > measured A-B2; refuted otherwise.
- H5: at least one B2 task does not call readscout; refuted if all call it.
- H6: B2 control tokens < B1 control; refuted if >=.
- H7: B2 broad re-read chars per reading call < B1; refuted if >=.
- H8: logs B2 tokens < B1, small-log overhead versus A <27%; refuted otherwise.
- H9: extraction receipts complete with no broad/full-file later reads; refuted
  by any broad re-read after a complete extraction receipt.
- H10: B2 mean F1 >= B1 -0.05 in tuning and holdout with both scorers; refuted
  below. Holdout/B1 is inconclusive because B1 was not measured there.
- H11: holdout B2/A saving >= half tuning B2/A saving; refuted below.
- H12: tuning sum-weighted B2/A saving >=30%; refuted below.

Missing required evidence = inconclusive. No significance claim from one cell.
No ablation: contributions of the six changes cannot be independently estimated.
Changes include source quotes/file schema, shorter skill and references, bounded
status receipts, deterministic logs, syntax extraction, and unified findings cap.
Original and new conditions differ in schema/skill/digest/tool descriptions.

## Frozen metadata

```json
{
  "campaign": 2,
  "date": "2026-10-16",
  "seed": 2026101602,
  "model": "gpt-6.1-sol",
  "effort": "medium",
  "codex": "codex-cli 0.163.0-alpha.10.2",
  "source_commit": "580320e5c1b873db8e48fcc40aa3de4a59a95193",
  "source_hashes": {
    "src/readscout/__init__.py": "2e049d3680ca287b0cfb0e502bbe25cabe3934689722b0a3f1622736e20359c0",
    "src/readscout/agents.py": "cfc47650b5ff634ba2ca925d6be827a37ff90b15d74668584cfa93dd94f16749",
    "src/readscout/backend.py": "98930446c483fb1a1358b90b1d3ebdeada94a19fd8343fba5c63b2c17d7d0072",
    "src/readscout/bench/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/readscout/bench/corpus.py": "7f25484bd64f87f14665d37601ccd896bf03104d2e0781eeebae505b84da4363",
    "src/readscout/bench/edits.py": "42a2d6e9314348af77e5b25e728c2fdc3c21578834787c81bebe752ecc948f99",
    "src/readscout/bench/generate.py": "4d5b51855635378a054c37b0565225250976caea02a585381c2fe01915189068",
    "src/readscout/bench/logs.py": "edac9b5ee9cf6199d0325d19dbb761d68a8c904a424abc0c07d9433368ff84ab",
    "src/readscout/bench/runner.py": "d3398bd85c3d31f77298abb3d860622bee330e6860f866436003f15d829b755a",
    "src/readscout/catalog.json": "b7afc7098f63ea91926eef928e7c3795de9ebf62cd8cdcf0e678b9ef95957307",
    "src/readscout/cli.py": "d3f982cab503f39d8878bce2b16481bcd59cbd87297e5466f28be955be272994",
    "src/readscout/editing.py": "28772f1701aa3e18d27067c38c3401c1641f6d4ffb47180bb7daecc6912d07b5",
    "src/readscout/extract.py": "45227f86e3644a7f4f2cd3c03944626ce1b7894658327f6c4181afd45d0d6909",
    "src/readscout/hardware.py": "11bae77647aeef043a65bc08c34cbcd346e0c130f6cb4bb9eda123b2ef6a0364",
    "src/readscout/llamacpp.py": "7b8403fd439e6e7aa4536510d0362a2bee476e514a45e7f31c4b62d47fec754f",
    "src/readscout/logs.py": "9e2bf0cc9e540ac3e322b420b9f5c5820be733c8e8d1a7889d4161eda14fb359",
    "src/readscout/paths.py": "0923af6a7b20c5a6aff7d9487a84ca133020a75285a69008eb278d4a9efae42a",
    "src/readscout/server.py": "9feaf8fd578ac2bd9faf076799013f9ceabfd03c54a2315c42af469b01f915d6",
    "src/readscout/skill/references/how-it-works.md": "17cfa3ac777720357665857512fa4b9630f8562b13df561d235c2857082f450b",
    "src/readscout/skill/references/local_edit.md": "bff79ae4a87d6c4243f9e8378091d8edc08f63defce6c90a61320e319507982c",
    "src/readscout/skill/references/troubleshooting.md": "48d260170a68960e2bf9b4095ae2ab363b5064bde8c10570c1c85cf059362da2",
    "src/readscout/skill/SKILL.md": "f259bf460de942aa175808eea0174ca0ff2ca230456bea3a71b4aa9da70ed757",
    "src/readscout/stats.py": "4491e174b596961a5daeec18bc05845e439dac81bbc87149322802a8a109b09d",
    "src/readscout/tasks.py": "e63fbeceff231381bc54811294c457fd64dc2c737c69cefdd17bce328dfbe75d",
    "src/readscout/text.py": "694b028ea9af1ea4de796f376ca115ed32cd832c9693b3f1647dfa4e63dee5aa",
    "src/readscout/web/index.html": "3bacdf38f28e7bac6d18a5a86f1b7d08b8f2465483a30e2bbc804323f387fb20",
    "src/readscout/web.py": "2dd2cb22b3094c1ecb1246f5ab1c0f4bd483c42bda7a68335641307d7f19123f"
  },
  "baseline_sha256": "b6750d3e5624756e9f1e7de8f3ca94fc6ba9f3e4bee5b19dde3afb4de2b27606",
  "baseline_source_commit": "6bb283e073254c9e19eedb025a750d50e541f46f",
  "tasks": [
    {
      "id": "logs:service-9000.log",
      "group": "W",
      "bytes": 753803,
      "paths": [
        "service-9000.log"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 1,
      "family": "log",
      "set": "tuning"
    },
    {
      "id": "hackathon:routes_limited",
      "group": "M",
      "bytes": 21033,
      "paths": [
        "app.js"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 14,
      "family": "routes_filter",
      "set": "tuning"
    },
    {
      "id": "logs:service-800.log",
      "group": "L",
      "bytes": 67366,
      "paths": [
        "service-800.log"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 1,
      "family": "log",
      "set": "tuning"
    },
    {
      "id": "boilerplate:routes_without_auth",
      "group": "N",
      "bytes": 15482,
      "paths": [
        "src/routes/v1/user.route.js",
        "src/routes/v1/auth.route.js"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 7,
      "family": "routes_negation",
      "set": "tuning"
    },
    {
      "id": "fastapi:endpoints_all",
      "group": "W",
      "bytes": 16012,
      "paths": [
        "backend/app/api/routes"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 23,
      "family": "routes_list",
      "set": "tuning"
    },
    {
      "id": "hackathon:locate:ai-agent.js:263",
      "group": "L",
      "bytes": 25858,
      "paths": [
        "controllers/ai-agent.js"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 1,
      "family": "locate",
      "set": "tuning"
    },
    {
      "id": "hackathon:env_controllers",
      "group": "W",
      "bytes": 158897,
      "paths": [
        "controllers"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 34,
      "family": "env_vars",
      "set": "tuning"
    },
    {
      "id": "hackathon:routes_auth",
      "group": "M",
      "bytes": 21033,
      "paths": [
        "app.js"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 23,
      "family": "routes_filter",
      "set": "tuning"
    },
    {
      "id": "boilerplate:env_schema",
      "group": "L",
      "bytes": 2424,
      "paths": [
        "src/config/config.js"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 13,
      "family": "env_vars",
      "set": "tuning"
    },
    {
      "id": "logs:service-3000.log",
      "group": "W",
      "bytes": 251485,
      "paths": [
        "service-3000.log"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 1,
      "family": "log",
      "set": "tuning"
    },
    {
      "id": "hackathon:locate:ai.js:359",
      "group": "L",
      "bytes": 32396,
      "paths": [
        "controllers/ai.js"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 1,
      "family": "locate",
      "set": "tuning"
    },
    {
      "id": "fastapi:public_endpoints",
      "group": "N",
      "bytes": 16012,
      "paths": [
        "backend/app/api/routes"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 6,
      "family": "routes_negation",
      "set": "tuning"
    },
    {
      "id": "hackathon:post_without_auth",
      "group": "N",
      "bytes": 21033,
      "paths": [
        "app.js"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 19,
      "family": "routes_negation",
      "set": "tuning"
    },
    {
      "id": "nextjs:supabase_access",
      "group": "W",
      "bytes": 15480,
      "paths": [
        "utils/supabase"
      ],
      "order": [
        "B2"
      ],
      "ground_truth_count": 13,
      "family": "data_access",
      "set": "tuning"
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
        "B2"
      ],
      "ground_truth_count": 13,
      "family": "routes_list",
      "set": "tuning"
    },
    {
      "id": "boilerplate:routes_manage",
      "set": "holdout",
      "group": "holdout",
      "family": "routes_filter",
      "paths": [
        "src/routes/v1/user.route.js",
        "src/routes/v1/auth.route.js"
      ],
      "bytes": 15482,
      "order": [
        "A",
        "B2"
      ]
    },
    {
      "id": "hackathon:locate:user.js:851",
      "set": "holdout",
      "group": "holdout",
      "family": "locate",
      "paths": [
        "controllers/user.js"
      ],
      "bytes": 38893,
      "order": [
        "B2",
        "A"
      ]
    },
    {
      "id": "readscout:env_locations",
      "set": "holdout",
      "group": "holdout",
      "family": "env_vars",
      "paths": [
        "src/readscout/paths.py"
      ],
      "bytes": 4194,
      "order": [
        "A",
        "B2"
      ]
    },
    {
      "id": "readscout:routes_without_token",
      "set": "holdout",
      "group": "holdout",
      "family": "routes_negation",
      "paths": [
        "src/readscout/web.py"
      ],
      "bytes": 10226,
      "order": [
        "B2",
        "A"
      ]
    },
    {
      "id": "readscout:config_data_access",
      "set": "holdout",
      "group": "holdout",
      "family": "data_access",
      "paths": [
        "src/readscout/paths.py"
      ],
      "bytes": 4194,
      "order": [
        "A",
        "B2"
      ]
    },
    {
      "id": "logs:ingest-4000.log",
      "set": "holdout",
      "group": "holdout",
      "family": "log",
      "paths": [
        "ingest-4000.log"
      ],
      "bytes": 245314,
      "order": [
        "B2",
        "A"
      ]
    },
    {
      "id": "readscout:build_log",
      "set": "holdout",
      "group": "holdout",
      "family": "log",
      "paths": [
        "build.log"
      ],
      "bytes": 223,
      "order": [
        "A",
        "B2"
      ]
    },
    {
      "id": "readscout:http_routes",
      "set": "holdout",
      "group": "holdout",
      "family": "routes_list",
      "paths": [
        "src/readscout/web.py"
      ],
      "bytes": 10226,
      "order": [
        "B2",
        "A"
      ]
    }
  ],
  "cells": [
    {
      "task": "hackathon:env_controllers",
      "config": "A",
      "phase": "pilot"
    },
    {
      "task": "hackathon:env_controllers",
      "config": "B2",
      "phase": "pilot"
    },
    {
      "task": "boilerplate:env_schema",
      "config": "A",
      "phase": "pilot"
    },
    {
      "task": "boilerplate:env_schema",
      "config": "B2",
      "phase": "pilot"
    },
    {
      "task": "control",
      "config": "A",
      "phase": "controls"
    },
    {
      "task": "control",
      "config": "B2",
      "phase": "controls"
    },
    {
      "task": "hackathon:locate:ai-agent.js:330",
      "config": "B2",
      "extra_control": true,
      "phase": "controls"
    },
    {
      "task": "logs:service-9000.log",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "hackathon:routes_limited",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "logs:service-800.log",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "boilerplate:routes_without_auth",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "fastapi:endpoints_all",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "hackathon:locate:ai-agent.js:263",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "hackathon:routes_auth",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "logs:service-3000.log",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "hackathon:locate:ai.js:359",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "fastapi:public_endpoints",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "hackathon:post_without_auth",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "nextjs:supabase_access",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "boilerplate:routes_all",
      "config": "B2",
      "phase": "tuning"
    },
    {
      "task": "boilerplate:routes_manage",
      "config": "A",
      "phase": "holdout"
    },
    {
      "task": "boilerplate:routes_manage",
      "config": "B2",
      "phase": "holdout"
    },
    {
      "task": "hackathon:locate:user.js:851",
      "config": "B2",
      "phase": "holdout"
    },
    {
      "task": "hackathon:locate:user.js:851",
      "config": "A",
      "phase": "holdout"
    },
    {
      "task": "readscout:env_locations",
      "config": "A",
      "phase": "holdout"
    },
    {
      "task": "readscout:env_locations",
      "config": "B2",
      "phase": "holdout"
    },
    {
      "task": "readscout:routes_without_token",
      "config": "B2",
      "phase": "holdout"
    },
    {
      "task": "readscout:routes_without_token",
      "config": "A",
      "phase": "holdout"
    },
    {
      "task": "readscout:config_data_access",
      "config": "A",
      "phase": "holdout"
    },
    {
      "task": "readscout:config_data_access",
      "config": "B2",
      "phase": "holdout"
    },
    {
      "task": "logs:ingest-4000.log",
      "config": "B2",
      "phase": "holdout"
    },
    {
      "task": "logs:ingest-4000.log",
      "config": "A",
      "phase": "holdout"
    },
    {
      "task": "readscout:build_log",
      "config": "A",
      "phase": "holdout"
    },
    {
      "task": "readscout:build_log",
      "config": "B2",
      "phase": "holdout"
    },
    {
      "task": "readscout:http_routes",
      "config": "B2",
      "phase": "holdout"
    },
    {
      "task": "readscout:http_routes",
      "config": "A",
      "phase": "holdout"
    }
  ],
  "fixed_overhead": {
    "B1": {
      "skill": {
        "chars": 5735,
        "tokens_est": 1433.75,
        "estimator": "4 characters/token; not tokenizer-exact"
      },
      "tools": {
        "chars": 3650,
        "tokens_est": 912.5,
        "estimator": "4 characters/token; not tokenizer-exact"
      }
    },
    "B2": {
      "skill": {
        "chars": 2890,
        "tokens_est": 722.5,
        "estimator": "4 characters/token; not tokenizer-exact"
      },
      "tools": {
        "chars": 3999,
        "tokens_est": 999.75,
        "estimator": "4 characters/token; not tokenizer-exact"
      }
    }
  },
  "isolation_audit": {
    "A": {
      "readscout_skill": false,
      "real_global_skill_root": false,
      "prompt_sha256": "8718f4ef3b74663fe4fdf65c06fa2998714f10aa9b0addbcdbe0f189cc0434cb"
    },
    "B": {
      "readscout_skill": true,
      "real_global_skill_root": false,
      "prompt_sha256": "674224bbd2b153b9fbd77759ca9e9c22b8f79c9f1efca2218963f967ad6072f2"
    }
  },
  "sandbox_probe": {
    "read_exit": 0,
    "read_output": "READ_OK",
    "write_exit": 1,
    "write_created": false
  },
  "preexisting_models": [],
  "budget": {
    "max_tokens": null,
    "reason": "User authorized remaining account quota, exposed as percentages only",
    "initial_primary_used_percent": 79,
    "initial_secondary_used_percent": 28,
    "primary_stop_used_percent": 97.9,
    "secondary_stop_used_percent": 92.8,
    "reset_policy": "Stop at initial window reset; do not spend refreshed quota",
    "stop_at_fraction": 0.9,
    "initial_primary_resets_at": 1792168339
  },
  "deviations": [
    "User authorized five new ReadScout holdout tasks because unused corpus families are insufficient.",
    "Numeric token ceiling unavailable: user authorized remaining quota; use percentage gate and record tokens actually spent.",
    "B1 trivial control reused from campaign 1; A and B2 controls remeasured.",
    "Work sessions not run: CLI resume exists but --ephemeral prevents persistence needed to resume. No four-question batching substituted.",
    "Only session-used models are unloaded, instead of global readscout stop, to preserve unrelated processes."
  ],
  "work_sessions": {
    "status": "not measured",
    "reason": "Noninteractive resume requires saved sessions; frozen isolation requires --ephemeral"
  },
  "repetitions": {
    "status": "not measured",
    "reason": "None by default; no automatic repetitions authorized"
  },
  "custom_ground_truth": [
    {
      "id": "readscout:env_locations",
      "family": "env_vars",
      "paths": [
        "src/readscout/paths.py"
      ],
      "question": "List the environment variables read by name in paths.py, one finding per variable.",
      "gt": [
        {
          "path": "src/readscout/paths.py",
          "line": 18,
          "key": "READSCOUT_HOME"
        },
        {
          "path": "src/readscout/paths.py",
          "line": 20,
          "key": "APPDATA"
        },
        {
          "path": "src/readscout/paths.py",
          "line": 24,
          "key": "XDG_CONFIG_HOME"
        },
        {
          "path": "src/readscout/paths.py",
          "line": 31,
          "key": "READSCOUT_CLI"
        }
      ],
      "negatives": []
    },
    {
      "id": "readscout:http_routes",
      "family": "routes_list",
      "paths": [
        "src/readscout/web.py"
      ],
      "question": "List each explicit HTTP path handled by Handler, one finding per method and path. Exclude 404 fallbacks.",
      "gt": [
        {
          "path": "src/readscout/web.py",
          "line": 119,
          "span": [
            119,
            120
          ],
          "method": "GET",
          "route": "/"
        },
        {
          "path": "src/readscout/web.py",
          "line": 119,
          "span": [
            119,
            120
          ],
          "method": "GET",
          "route": "/setup"
        },
        {
          "path": "src/readscout/web.py",
          "line": 122,
          "span": [
            122,
            123
          ],
          "method": "GET",
          "route": "/api/ping"
        },
        {
          "path": "src/readscout/web.py",
          "line": 124,
          "span": [
            124,
            125
          ],
          "method": "GET",
          "route": "/api/state"
        },
        {
          "path": "src/readscout/web.py",
          "line": 155,
          "span": [
            155,
            156
          ],
          "method": "POST",
          "route": "/api/pull"
        },
        {
          "path": "src/readscout/web.py",
          "line": 162,
          "span": [
            162,
            163
          ],
          "method": "POST",
          "route": "/api/models"
        },
        {
          "path": "src/readscout/web.py",
          "line": 184,
          "span": [
            184,
            185
          ],
          "method": "POST",
          "route": "/api/agent"
        },
        {
          "path": "src/readscout/web.py",
          "line": 191,
          "span": [
            191,
            192
          ],
          "method": "POST",
          "route": "/api/ollama-env"
        }
      ],
      "negatives": []
    },
    {
      "id": "readscout:routes_without_token",
      "family": "routes_negation",
      "paths": [
        "src/readscout/web.py"
      ],
      "question": "Which explicit HTTP paths have handlers that do not check X-Readscout-Token? Give one finding per method and path. Check only Handler in this file.",
      "gt": [
        {
          "path": "src/readscout/web.py",
          "line": 119,
          "span": [
            119,
            120
          ],
          "method": "GET",
          "route": "/"
        },
        {
          "path": "src/readscout/web.py",
          "line": 119,
          "span": [
            119,
            120
          ],
          "method": "GET",
          "route": "/setup"
        },
        {
          "path": "src/readscout/web.py",
          "line": 122,
          "span": [
            122,
            123
          ],
          "method": "GET",
          "route": "/api/ping"
        },
        {
          "path": "src/readscout/web.py",
          "line": 124,
          "span": [
            124,
            125
          ],
          "method": "GET",
          "route": "/api/state"
        }
      ],
      "negatives": [
        {
          "path": "src/readscout/web.py",
          "line": 155,
          "span": [
            155,
            156
          ],
          "method": "POST",
          "route": "/api/pull"
        },
        {
          "path": "src/readscout/web.py",
          "line": 162,
          "span": [
            162,
            163
          ],
          "method": "POST",
          "route": "/api/models"
        },
        {
          "path": "src/readscout/web.py",
          "line": 184,
          "span": [
            184,
            185
          ],
          "method": "POST",
          "route": "/api/agent"
        },
        {
          "path": "src/readscout/web.py",
          "line": 191,
          "span": [
            191,
            192
          ],
          "method": "POST",
          "route": "/api/ollama-env"
        }
      ]
    },
    {
      "id": "readscout:config_data_access",
      "family": "data_access",
      "paths": [
        "src/readscout/paths.py"
      ],
      "question": "List direct configuration file data accesses in load_config and save_config: the read, temporary write and atomic replacement. Name function and operation in each finding.",
      "gt": [
        {
          "path": "src/readscout/paths.py",
          "line": 56,
          "description": "load_config",
          "operation": "read"
        },
        {
          "path": "src/readscout/paths.py",
          "line": 76,
          "description": "save_config",
          "operation": "write"
        },
        {
          "path": "src/readscout/paths.py",
          "line": 77,
          "description": "save_config",
          "operation": "replace"
        }
      ],
      "negatives": []
    },
    {
      "id": "readscout:build_log",
      "family": "log",
      "paths": [
        "build.log"
      ],
      "question": "What went wrong? Give first the earliest root-cause error, then the consequences. Ignore noise.",
      "gt": [
        {
          "path": "build.log",
          "line": 2,
          "key": "missing header",
          "span": [
            2,
            2
          ]
        }
      ],
      "negatives": []
    }
  ],
  "holdout_hashes": {
    "src/readscout/paths.py": "0923af6a7b20c5a6aff7d9487a84ca133020a75285a69008eb278d4a9efae42a",
    "src/readscout/web.py": "2dd2cb22b3094c1ecb1246f5ab1c0f4bd483c42bda7a68335641307d7f19123f",
    "build.log": "769d77120cd7ccd289e9935fa02a1773185fdb6aed3d06a1f837a18cd3949bb6"
  },
  "derived": {
    "tuning/A": null,
    "tuning/B1": null,
    "holdout/A": null,
    "holdout/B1": null
  },
  "spent_total_tokens": 0,
  "usage_missing_attempts": 0,
  "raw_bytes": 0
}
```

## Observed stop: no real B2 MCP execution

Mandatory stop: first completed B2 pilot session made no readscout MCP call. Remaining pilot, controls and main cells not started. No synthetic replacement and no extra sessions.
