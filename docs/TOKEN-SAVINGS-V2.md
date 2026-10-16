# Campaign 2: measured token savings

## TL;DR

Campaign incomplete: the mandatory pilot gate failed because B2 made no MCP call.
Measured sessions spent 106,350 reported tokens; holdout, controls and work sessions were not measured.
Matched tuning subset only (1 task): reused A 63,831, reused B1 65,446, B2 41,880; descriptive saving 34.4% versus A and 36.0% versus B1.
B2 did not read the skill or call readscout: these differences do not establish improvement-driven savings.
Fresh pilot A 64,470 versus B2 41,880: 35.0% lower tokens on this single task; final F1 v1/v2 is 0.897/1.0.

## Setup

Frozen source `580320e5c1b873db8e48fcc40aa3de4a59a95193`; CLI `codex-cli 0.163.0-alpha.10.2`; model `gpt-6.1-sol`; effort `medium`.
A and B1 reused from campaign 1 for tuning, with identical CLI, pinned model and effort. Fresh pilot A is separate.

## Method

[Frozen protocol](token-savings/v2/PROTOCOL.md). [Machine-readable evidence](token-savings/v2/results.json).

## Changes and expectations

| Change | Expected effect |
|---|---|
| Source quotes, file field, code-reference redaction | Avoid quote repairs |
| Short skill and references | Reduce fixed overhead |
| Status receipts and narrow verification rules | Reduce broad re-reads |
| Deterministic simple logs | Avoid local inference and broad reads |
| Syntax extraction | Improve structural coverage |
| Shared findings cap | Make truncation visible |

## Tuning set

| Task | A total | B1 total | B2 total | F1 v1/v2 B2 |
|---|---|---|---|---|
| logs:service-9000.log | 104022 | 95198 | not measured | not measured |
| hackathon:routes_limited | 61265 | 40701 | not measured | not measured |
| logs:service-800.log | 51677 | 65651 | not measured | not measured |
| boilerplate:routes_without_auth | 57243 | 55346 | not measured | not measured |
| fastapi:endpoints_all | 50568 | 50302 | not measured | not measured |
| hackathon:locate:ai-agent.js:263 | 42351 | 41939 | not measured | not measured |
| hackathon:env_controllers | 63831 | 65446 | 41880 | 0.897/1.0 |
| hackathon:routes_auth | 40167 | 40752 | not measured | not measured |
| boilerplate:env_schema | 30418 | 30714 | not measured | not measured |
| logs:service-3000.log | 104328 | 97790 | not measured | not measured |
| hackathon:locate:ai.js:359 | 41876 | 40975 | not measured | not measured |
| fastapi:public_endpoints | 50447 | 90152 | not measured | not measured |
| hackathon:post_without_auth | 62912 | 63399 | not measured | not measured |
| nextjs:supabase_access | 49802 | 51686 | not measured | not measured |
| boilerplate:routes_all | 35635 | 35921 | not measured | not measured |
## Holdout set

| Task | A total | B1 total | B2 total | F1 v1/v2 B2 |
|---|---|---|---|---|
| boilerplate:routes_manage | not measured | not measured | not measured | not measured |
| hackathon:locate:user.js:851 | not measured | not measured | not measured | not measured |
| readscout:env_locations | not measured | not measured | not measured | not measured |
| readscout:routes_without_token | not measured | not measured | not measured | not measured |
| readscout:config_data_access | not measured | not measured | not measured | not measured |
| logs:ingest-4000.log | not measured | not measured | not measured | not measured |
| readscout:build_log | not measured | not measured | not measured | not measured |
| readscout:http_routes | not measured | not measured | not measured | not measured |

## Both averages and per-family/group breakdown

Only completed matched pairs enter these descriptive aggregates. Partial subsets cannot establish the full-set hypotheses.

### tuning/A

```json
{
  "pairs": 1,
  "base": 63831,
  "B2": 41880,
  "saving": 0.34389246604314516,
  "mean_task_saving": 0.34389246604314516,
  "wins": 1,
  "ties": 0,
  "losses": 0,
  "F1_base_v1": 0.897,
  "F1_B2_v1": 0.897,
  "unverifiable_base": 0,
  "unverifiable_B2": 0,
  "cache_sensitivity": {
    "0": {
      "base": 24023,
      "B2": 22680
    },
    "0.1": {
      "base": 28003.799999999996,
      "B2": 24600.0
    },
    "1": {
      "base": 63831,
      "B2": 41880
    }
  }
}
```

group: W

```json
{
  "pairs": 1,
  "base": 63831,
  "B2": 41880,
  "saving": 0.34389246604314516,
  "mean_task_saving": 0.34389246604314516,
  "wins": 1,
  "ties": 0,
  "losses": 0,
  "F1_base_v1": 0.897,
  "F1_B2_v1": 0.897,
  "unverifiable_base": 0,
  "unverifiable_B2": 0,
  "cache_sensitivity": {
    "0": {
      "base": 24023,
      "B2": 22680
    },
    "0.1": {
      "base": 28003.799999999996,
      "B2": 24600.0
    },
    "1": {
      "base": 63831,
      "B2": 41880
    }
  }
}
```

family: env_vars

```json
{
  "pairs": 1,
  "base": 63831,
  "B2": 41880,
  "saving": 0.34389246604314516,
  "mean_task_saving": 0.34389246604314516,
  "wins": 1,
  "ties": 0,
  "losses": 0,
  "F1_base_v1": 0.897,
  "F1_B2_v1": 0.897,
  "unverifiable_base": 0,
  "unverifiable_B2": 0,
  "cache_sensitivity": {
    "0": {
      "base": 24023,
      "B2": 22680
    },
    "0.1": {
      "base": 28003.799999999996,
      "B2": 24600.0
    },
    "1": {
      "base": 63831,
      "B2": 41880
    }
  }
}
```

### tuning/B1

```json
{
  "pairs": 1,
  "base": 65446,
  "B2": 41880,
  "saving": 0.3600831219631452,
  "mean_task_saving": 0.3600831219631452,
  "wins": 1,
  "ties": 0,
  "losses": 0,
  "F1_base_v1": 0.941,
  "F1_B2_v1": 0.897,
  "unverifiable_base": 0,
  "unverifiable_B2": 0,
  "cache_sensitivity": {
    "0": {
      "base": 24998,
      "B2": 22680
    },
    "0.1": {
      "base": 29042.799999999996,
      "B2": 24600.0
    },
    "1": {
      "base": 65446,
      "B2": 41880
    }
  }
}
```

group: W

```json
{
  "pairs": 1,
  "base": 65446,
  "B2": 41880,
  "saving": 0.3600831219631452,
  "mean_task_saving": 0.3600831219631452,
  "wins": 1,
  "ties": 0,
  "losses": 0,
  "F1_base_v1": 0.941,
  "F1_B2_v1": 0.897,
  "unverifiable_base": 0,
  "unverifiable_B2": 0,
  "cache_sensitivity": {
    "0": {
      "base": 24998,
      "B2": 22680
    },
    "0.1": {
      "base": 29042.799999999996,
      "B2": 24600.0
    },
    "1": {
      "base": 65446,
      "B2": 41880
    }
  }
}
```

family: env_vars

```json
{
  "pairs": 1,
  "base": 65446,
  "B2": 41880,
  "saving": 0.3600831219631452,
  "mean_task_saving": 0.3600831219631452,
  "wins": 1,
  "ties": 0,
  "losses": 0,
  "F1_base_v1": 0.941,
  "F1_B2_v1": 0.897,
  "unverifiable_base": 0,
  "unverifiable_B2": 0,
  "cache_sensitivity": {
    "0": {
      "base": 24998,
      "B2": 22680
    },
    "0.1": {
      "base": 29042.799999999996,
      "B2": 24600.0
    },
    "1": {
      "base": 65446,
      "B2": 41880
    }
  }
}
```

### holdout/A

```json
null
```

### holdout/B1

```json
null
```

## Cost by phase

Phase token usage: not measured. Ephemeral CLI exposes turn aggregates, not request-level attribution. Tool returned characters are proxies:

```json
{
  "discovery": 17130,
  "skill": 0,
  "readscout": 0,
  "verification": 0,
  "fallback": 0,
  "final": 9548
}
```

## Re-read rate

Command/file overlap is a conservative proxy; ambiguous broad search scope is labelled separately.

- B1: 4 reading calls; 7 re-reads; 192060 broad returned chars; broad chars/call: 48015.0; targeted reads: 1.
- B2: 0 reading calls; 0 re-reads; 0 broad returned chars; broad chars/call: not measured; targeted reads: 0.

## Skill loading and fixed overhead

```json
{
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
}
```

Exact serialized schema/core characters; estimated tokens use 4 chars/token. Skill presence does not imply the core was read.
Measured core reads: 0; references reads: 0.

Controls:

```json
[]
```

## Logs and extraction: structural coverage

Offline only, no agent or model. Unfiltered route extraction is scored against each question and can include unwanted routes. Structural completeness does not guarantee semantic relevance.

| Task | Path | Status | Unrecognized | Precision v1/v2 | Recall v1/v2 | F1 v1/v2 |
|---|---|---|---|---|---|---|
| hackathon:routes_auth | routes | partial | 2 | 0.45/0.45 | 0.696/0.696 | 0.546/0.546 |
| hackathon:routes_authorized | routes | partial | 2 | 0.0/0.0 | 0.0/0.0 | 0.0/0.0 |
| hackathon:routes_limited | routes | partial | 2 | 0.5/0.5 | 0.857/0.857 | 0.632/0.632 |
| hackathon:post_without_auth | routes | partial | 2 | 0.525/0.525 | 0.526/0.526 | 0.526/0.526 |
| hackathon:env_controllers | env | complete | 0 | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 |
| boilerplate:routes_all | routes | complete | 0 | 0.615/0.615 | 0.615/0.615 | 0.615/0.615 |
| boilerplate:routes_manage | routes | complete | 0 | 0.0/0.0 | 0.0/0.0 | 0.0/0.0 |
| boilerplate:routes_without_auth | routes | complete | 0 | 0.615/0.615 | 1.0/1.0 | 0.762/0.762 |
| boilerplate:env_schema | env | complete | 0 | 0.0/0.0 | 0.0/0.0 | 0.0/0.0 |
| fastapi:endpoints_all | endpoints | partial | 1 | 1.0/1.0 | 0.783/0.783 | 0.878/0.878 |
| fastapi:superuser_only | endpoints | partial | 1 | 0.278/0.278 | 0.833/0.833 | 0.417/0.417 |
| fastapi:public_endpoints | endpoints!CurrentUser | partial | 1 | 0.429/0.429 | 0.5/0.5 | 0.462/0.462 |
| nextjs:supabase_access | supabase | complete | 0 | 1.0/1.0 | 0.923/0.923 | 0.96/0.96 |
| logs:service-800.log | digest | complete | 0 | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 |
| logs:service-3000.log | digest | complete | 0 | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 |
| logs:service-9000.log | digest | complete | 0 | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 |
| logs:ingest-4000.log | digest | complete | 0 | 1.0/1.0 | 1.0/1.0 | 1.0/1.0 |

Citation checks: 349; failures: 0.

## Accuracy: scorer v1 and v2

Campaign 1 recomputed without editing its files:

| Task | Config | F1 v1 | F1 v2 |
|---|---|---|---|
| hackathon:env_controllers | A | 0.897 | 1.0 |
| hackathon:env_controllers | B1 | 0.941 | 1.0 |
| boilerplate:env_schema | B1 | 1.0 | 1.0 |
| boilerplate:env_schema | A | 1.0 | 1.0 |
| boilerplate:routes_without_auth | A | 1.0 | 1.0 |
| boilerplate:routes_without_auth | B1 | 1.0 | 1.0 |
| hackathon:routes_auth | B1 | 1.0 | 1.0 |
| hackathon:routes_auth | A | 1.0 | 1.0 |
| hackathon:locate:ai.js:359 | A | 1.0 | 1.0 |
| hackathon:locate:ai.js:359 | B1 | 1.0 | 1.0 |
| logs:service-3000.log | B1 | 1.0 | 1.0 |
| logs:service-3000.log | A | 1.0 | 1.0 |
| boilerplate:routes_all | B1 | 1.0 | 1.0 |
| boilerplate:routes_all | A | 1.0 | 1.0 |
| nextjs:supabase_access | A | 1.0 | 1.0 |
| nextjs:supabase_access | B1 | 1.0 | 1.0 |
| logs:service-9000.log | B1 | 1.0 | 1.0 |
| logs:service-9000.log | A | 1.0 | 1.0 |
| hackathon:locate:ai-agent.js:263 | A | 1.0 | 1.0 |
| hackathon:locate:ai-agent.js:263 | B1 | 1.0 | 1.0 |
| hackathon:post_without_auth | B1 | 0.947 | 0.947 |
| hackathon:post_without_auth | A | 1.0 | 1.0 |
| hackathon:routes_limited | A | 0.929 | 0.929 |
| hackathon:routes_limited | B1 | 1.0 | 1.0 |
| logs:service-800.log | B1 | 1.0 | 1.0 |
| logs:service-800.log | A | 1.0 | 1.0 |
| fastapi:public_endpoints | A | 1.0 | 1.0 |
| fastapi:public_endpoints | B1 | 1.0 | 1.0 |
| fastapi:endpoints_all | A | 1.0 | 1.0 |
| fastapi:endpoints_all | B1 | 1.0 | 1.0 |

Receipt-only grades and final v1/v2 grades are retained per session in results.json.

### Accuracy and quality on the observed subset

- Scorer v2 mean F1 A/B2: 1.000/1.000.
- Scorer v2 mean F1 B1/B2: 1.000/1.000.

These are subset checks, not confirmation of campaign-wide accuracy or generalization.
## Real work sessions

Noninteractive resume requires saved sessions; frozen isolation requires --ephemeral

## Estimate accuracy

tokens_avoided_est is a local text-size proxy. No full-campaign calibration without complete paired data.

## Hypotheses

- H1: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H2: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H3: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H4: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H5: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H6: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H7: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H8: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H9: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H10: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H11: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.
- H12: inconclusive. Campaign incomplete or required measurement unavailable; see frozen numeric falsifier.

## Which improvement contributed what

No ablation was run: individual contributions cannot be separated. Offline overhead and structural accuracy are directly measurable; agent token benefits need completed paired sessions.

## Bugs and oddities observed before runs

- Extraction telemetry computes status from unrecognized constructs only; hidden results can make the receipt partial while metrics say complete.
- Model receipt telemetry omits hidden findings and digest missing-role checks used by the receipt.
- The env extractor reads named accesses, not Joi schema declarations: a complete empty receipt can miss variables a question asks the configuration to validate.
- Deterministic logs group errors and show head/tail; their complete status does not prove the first event is the semantic root cause.

## Limitations

One run per cell, one agent model, one machine, project-authored corpus, tuning tasks seen during development, caching, run order, cold load time, nondeterminism, no variance estimate. Holdout is task-level and partly authored on this project. No per-request token use, post-truncation model input, phase token costs, separate load/inference timings, or maximum token allowance available. New tool schema/skill/digest behavior makes conditions different; no ablation.

## Reproduction

`python scripts/token_savings.py v2 prepare`, commit protocol/harness/tests, then invoke `v2 next --quota-used PERCENT --quota-secondary-used PERCENT --quota-resets-at UNIX` once per fresh account checkpoint. `python scripts/token_savings_v2_publish.py` generates this report offline; `v2 cleanup` removes fake homes. Never repeat an existing cell. Preserve raw evidence and stop state.

## Deviations

- User authorized five new ReadScout holdout tasks because unused corpus families are insufficient.
- Numeric token ceiling unavailable: user authorized remaining quota; use percentage gate and record tokens actually spent.
- B1 trivial control reused from campaign 1; A and B2 controls remeasured.
- Work sessions not run: CLI resume exists but --ephemeral prevents persistence needed to resume. No four-question batching substituted.
- Only session-used models are unloaded, instead of global readscout stop, to preserve unrelated processes.
- Stopped after the first B2 pilot cell under the immediate no-MCP stop rule; the second pilot pair was not spent.

Report publication is separate from the frozen measurement harness. Its exact execution hashes are stored in results.json. The pilot was stopped, not discarded or rerun. No postcampaign source fix or skill tuning was applied.
