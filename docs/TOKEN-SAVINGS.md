# Measured Codex token savings

## TL;DR

Observed paired total: A 846,542 tokens; B 865,972; B uses 2.3% more tokens.
By group: W 2.9%; N -22.4%; M 19.7%; L -7.8%.
Tasks saving/tied/costing more: 7/0/8. Mean F1 A 0.988; B 0.993.
Excluding cached input, A 327,246 versus B 315,828: 3.5% saved. Only 4 of 15 B tasks called readscout; this does not establish a general saving.

## Setup

Date: 2026-10-16; seed: 20261016; Codex: codex-cli 0.163.0-alpha.10.2; model: gpt-6.1-sol; reasoning effort: medium; readscout: 0.1.6.

```json
{
  "hardware": {
    "vram_gb": 8.0,
    "ram_gb": 31.1,
    "gpu": "NVIDIA GeForce RTX 4060 Ti",
    "source": "nvidia-smi",
    "os": "windows"
  },
  "cpu": "AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD",
  "platform": "Windows-11-10.0.26300-SP0",
  "ollama": "ollama version is 0.40.3",
  "models": "NAME                    ID              SIZE      MODIFIED     \ngemma4:26b              001e5dafc3c7    18 GB     44 hours ago    \ngemma4:12b              6114515d63c1    8.0 GB    44 hours ago    \ngemma4:e2b              b37049369adf    4.6 GB    44 hours ago    \ngemma4:e4b              dc35e8d9c606    6.6 GB    45 hours ago    \nrp-gemma4-26b:latest    0973f4c231ae    18 GB     3 days ago      \nrp-gemma4-e4b:latest    f52667d3bc70    6.6 GB    3 days ago      \n"
}
```

## Method

See the frozen [protocol](token-savings/PROTOCOL.md). Identical task prompts, temporary isolated homes, read-only Codex sessions, sequential paired runs, existing benchmark scoring and source-verified quotes. All numbers on this page are generated from [results.json](token-savings/results.json).

W: large inputs; N: negative questions; M: medium; L: small or easy-to-grep. Positive savings favor B; a negative saving means B consumed more tokens.

CPU: AMD Ryzen 5 7600X 6-Core Processor. Models actually used by retained reading calls: gemma4:26b, gemma4:e4b. The repository source matches the release under test; exact source hashes are recorded.

Primary totals include cached input and reasoning output. A deterministic localhost transport test confirmed that the CLI preserves upstream input/output totals and reports cache/reasoning components separately. The synthetic test is excluded from all measurements. CLI turns count user turns, not model requests. Returned MCP characters serialize the complete result including wrappers; readscout chars_returned counts the receipt alone. Wall time covers Codex execution and excludes stop/cleanup.

## Per-task results

| Task | Group | A in/cache/out/total | B in/cache/out/total | Saving | Shell A/B | MCP A/B | Seconds A/B | F1 A/B | Read calls B |
|---|---|---|---|---|---|---|---|---|---|
| boilerplate:routes_without_auth | N | 56715/47104/528/57243 | 54811/19712/535/55346 | 3.3% | 2/2 | 0/0 | 15.212/16.585 | 1.0/1.0 | 0 |
| hackathon:routes_auth | M | 39107/19072/1060/40167 | 39688/19200/1064/40752 | -1.5% | 1/1 | 0/0 | 19.787/19.706 | 1.0/1.0 | 0 |
| hackathon:locate:ai.js:359 | L | 41720/19072/156/41876 | 40824/19200/151/40975 | 2.2% | 1/1 | 0/0 | 7.957/8.827 | 1.0/1.0 | 0 |
| logs:service-3000.log | W | 103836/72960/492/104328 | 97060/71680/730/97790 | 6.3% | 3/4 | 0/1 | 23.848/31.204 | 1.0/1.0 | 1 |
| hackathon:env_controllers | W | 62393/39808/1438/63831 | 63886/40448/1560/65446 | -2.5% | 2/2 | 0/0 | 32.924/30.749 | 0.897/0.941 | 0 |
| boilerplate:routes_all | W | 34907/14208/728/35635 | 35195/14336/726/35921 | -0.8% | 1/1 | 0/0 | 16.769/16.781 | 1.0/1.0 | 0 |
| nextjs:supabase_access | W | 49243/30848/559/49802 | 51050/30976/636/51686 | -3.8% | 2/4 | 0/0 | 18.51/18.26 | 1.0/1.0 | 0 |
| logs:service-9000.log | W | 103571/72960/451/104022 | 94623/70528/575/95198 | 8.5% | 3/3 | 0/1 | 17.146/26.908 | 1.0/1.0 | 1 |
| hackathon:locate:ai-agent.js:263 | L | 42184/19072/167/42351 | 41787/19200/152/41939 | 1.0% | 1/1 | 0/0 | 10.079/14.463 | 1.0/1.0 | 0 |
| hackathon:post_without_auth | N | 61800/39808/1112/62912 | 62317/59136/1082/63399 | -0.8% | 2/2 | 0/0 | 23.411/25.258 | 1.0/0.947 | 0 |
| hackathon:routes_limited | M | 60506/38656/759/61265 | 40049/31616/652/40701 | 33.6% | 2/1 | 0/0 | 19.724/15.704 | 0.929/1.0 | 0 |
| logs:service-800.log | L | 51168/31744/509/51677 | 65101/30336/550/65651 | -27.0% | 3/2 | 0/1 | 19.637/26.342 | 1.0/1.0 | 1 |
| fastapi:public_endpoints | N | 49958/28672/489/50447 | 89406/67456/746/90152 | -78.7% | 2/4 | 0/1 | 15.942/55.243 | 1.0/1.0 | 1 |
| boilerplate:env_schema | L | 29712/14080/706/30418 | 30005/14208/709/30714 | -1.0% | 1/1 | 0/0 | 12.472/17.284 | 1.0/1.0 | 0 |
| fastapi:endpoints_all | W | 49608/31232/960/50568 | 49331/42112/971/50302 | 0.5% | 2/2 | 0/0 | 23.557/23.994 | 1.0/1.0 | 0 |

## Aggregates

| Group | Pairs | A total | B total | Saving | Median | Min | Max | F1 A/B | Seconds A/B | Read calls B |
|---|---|---|---|---|---|---|---|---|---|---|
| W | 6 | 408186 | 396343 | 2.9% | -0.1% | -3.8% | 8.5% | 0.983/0.990 | 132.754/147.896 | 2 |
| N | 3 | 170602 | 208897 | -22.4% | -0.8% | -78.7% | 3.3% | 1.000/0.982 | 54.565/97.086 | 1 |
| M | 2 | 101432 | 81453 | 19.7% | 16.1% | -1.5% | 33.6% | 0.965/1.000 | 39.511/35.41 | 0 |
| L | 4 | 166322 | 179279 | -7.8% | -0.0% | -27.0% | 2.2% | 1.000/1.000 | 50.145/66.916 | 1 |
| overall | 15 | 846542 | 865972 | -2.3% | -0.8% | -78.7% | 33.6% | 0.988/0.993 | 276.975/347.308 | 4 |

Secondary views (cached input discount is an assumption, not a price):

| Cache weight | A | B | Saving |
|---|---|---|---|
| 0% | 327246.0 | 315828.0 | 3.5% |
| 10% | 379175.6 | 370842.4 | 2.2% |
| 100% | 846542.0 | 865972.0 | -2.3% |

## Accuracy

- boilerplate:routes_without_auth: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
- hackathon:routes_auth: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
- hackathon:locate:ai.js:359: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
- logs:service-3000.log: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
  A: missing frozen targets: none; non-target verified findings: 2 (supporting log consequences are permitted by the scorer).
  B: missing frozen targets: none; non-target verified findings: 2 (supporting log consequences are permitted by the scorer).
- hackathon:env_controllers: F1 A/B 0.897/0.941; unverifiable A/B 0/0.
  A: missing frozen targets: controllers/ai-agent.js:90 (GROQ_API_KEY), controllers/api.js:951 (BASE_URL), controllers/contact.js:92 (SITE_CONTACT_EMAIL); non-target verified findings: 4.
  B: missing frozen targets: controllers/api.js:951 (BASE_URL), controllers/contact.js:92 (SITE_CONTACT_EMAIL); non-target verified findings: 2.
- boilerplate:routes_all: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
- nextjs:supabase_access: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
- logs:service-9000.log: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
  A: missing frozen targets: none; non-target verified findings: 2 (supporting log consequences are permitted by the scorer).
  B: missing frozen targets: none; non-target verified findings: 2 (supporting log consequences are permitted by the scorer).
- hackathon:locate:ai-agent.js:263: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
- hackathon:post_without_auth: F1 A/B 1.0/0.947; unverifiable A/B 0/1.
  B: missing frozen targets: app.js:312; non-target verified findings: 0.
  B unverifiable quote: `app.post('/api/upload', strictLimiter, apiController.uploadMiddleware, lusca({ csrf: true }), apiController.postFile it`. Quote not found.
- hackathon:routes_limited: F1 A/B 0.929/1.0; unverifiable A/B 1/0.
  A: missing frozen targets: app.js:312; non-target verified findings: 0.
  A unverifiable quote: `app.post('/api/upload', strictLimiter, apiController.uploadMiddleware, lusca({ csrf: true }), apiController.postFileFile`. Quote not found.
- logs:service-800.log: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
  A: missing frozen targets: none; non-target verified findings: 2 (supporting log consequences are permitted by the scorer).
  B: missing frozen targets: none; non-target verified findings: 2 (supporting log consequences are permitted by the scorer).
- fastapi:public_endpoints: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
- boilerplate:env_schema: F1 A/B 1.0/1.0; unverifiable A/B 0/0.
- fastapi:endpoints_all: F1 A/B 1.0/1.0; unverifiable A/B 0/0.

The lower-scoring negative and rate-limit answers both identify the upload route at app.js:312, but alter its quoted code. The source verifier correctly rejects those quotes. Unverifiable findings: A 1, B 1. The environment-task scorer also requires the ground-truth file, although the question asks for one finding per variable: a valid occurrence of the same variable in another controller is penalized. Those location penalties are retained for comparability and should not be read as invented variable names. A also returns an additional GROQ_MODEL occurrence, reducing precision. The existing scorer, not a new semantic judge, determines all primary F1 scores.

## Where readscout helps, hurts, and break-even

Observed winners: boilerplate:routes_without_auth, hackathon:locate:ai.js:359, logs:service-3000.log, logs:service-9000.log, hackathon:locate:ai-agent.js:263, hackathon:routes_limited, fastapi:endpoints_all.
Observed costs/ties: hackathon:routes_auth, hackathon:env_controllers, boilerplate:routes_all, nextjs:supabase_access, hackathon:post_without_auth, logs:service-800.log, fastapi:public_endpoints, boilerplate:env_schema.
- Delegated logs:service-3000.log, 251,485 source bytes: saving 6.3%, wall A/B 23.848/31.204 seconds.
- Delegated logs:service-9000.log, 753,803 source bytes: saving 8.5%, wall A/B 17.146/26.908 seconds.
- Delegated logs:service-800.log, 67,366 source bytes: saving -27.0%, wall A/B 19.637/26.342 seconds.
- Delegated fastapi:public_endpoints, 16,012 source bytes: saving -78.7%, wall A/B 15.942/55.243 seconds.
The observed log transition lies between the losing 67,366-byte sample and the smallest winning 251,485-byte sample. This is an observed bracket, not a validated threshold.
Only 4 B tasks actually delegated. Savings on the other 11 tasks reflect agent strategy, skill overhead and nondeterminism, not content displaced by a local model. In particular, the rate-limit task changes shell strategy without calling readscout. The negative FastAPI call returns an incomplete receipt; the agent reads the source afterwards, paying for both paths.
A reliable general size break-even is not measured: task shape and grep strategy confound size, and there is no replication. No delegation threshold is changed from these data.
Delegated-task A-B difference: -38,317 tokens. Nondelegated-task A-B difference: 18,887 tokens.

## Fixed-overhead controls

| Config | Tokens | Seconds | Status |
|---|---|---|---|
| A | 14090 | 3.912 | 0 |
| B | 14234 | 4.062 | 0 |

B adds 144 reported tokens on the trivial control (1.0%). This measures idle discovery overhead; loading the skill and making tool calls adds further overhead during real tasks.

## Dashboard estimate versus measured savings

Dashboard estimate sum: 306684 tokens. Actual paired difference: -19430 tokens.
A positive savings ratio is not defined.

| Task with a reading call | Estimated avoided | Actual A-B | Ratio when saving |
|---|---|---|---|
| logs:service-3000.log | 70,810 | 6,538 | 10.83 |
| logs:service-9000.log | 212,619 | 8,824 | 24.10 |
| logs:service-800.log | 18,838 | -13,974 | not defined |
| fastapi:public_endpoints | 4,417 | -39,705 | not defined |

The estimate subtracts receipt length from locally read text, as if the agent would read all of it. The baseline often greps instead. Tool schemas, skill loading, reasoning, repeated prompts and fallback source reads are excluded from the estimate. A single calibrated multiplier would be unjustified; the formula is left unchanged.

| Local call | Model | Bytes read | Receipt chars | Verified/dropped | Local seconds |
|---|---|---|---|---|---|
| logs:service-3000.log | gemma4:e4b | 248480 | 645 | 2/0 | 5.6 |
| logs:service-9000.log | gemma4:e4b | 744798 | 633 | 2/0 | 5.6 |
| logs:service-800.log | gemma4:e4b | 66561 | 629 | 2/0 | 5.8 |
| fastapi:public_endpoints | gemma4:26b | 15786 | 327 | 1/0 | 30.9 |

## Hypotheses

- H1: refuted. Evidence: the aggregate and per-task measurements above; definitions in the protocol.
- H2: confirmed. Evidence: the aggregate and per-task measurements above; definitions in the protocol.
- H3: confirmed. Evidence: the aggregate and per-task measurements above; definitions in the protocol.
- H4: confirmed. Evidence: the aggregate and per-task measurements above; definitions in the protocol.
- H5: confirmed. Evidence: the aggregate and per-task measurements above; definitions in the protocol.

H1: W 2.9% versus the preregistered minimum 10%. H2: L -7.8%. H3: mean F1 difference B-A +0.0041. H4: proxy 306,684 versus measured difference -19,430; numerical overestimation, not evidence of real savings. H5: 11 of 15 B tasks made no reading call.

## Limitations and threats to validity

One run per cell supports no significance claim. One model and machine, a public corpus authored by this project, prompt caching, pilot-first order, model loading and nondeterminism limit generalization. Actual cache hits differ between configurations; discounted totals are sensitivity analyses, not currency costs. All CLI usage fields, including reasoning output, are retained. Separate model-load duration and per-call residency were not measured: the harness captured local wall time, not Ollama load telemetry. No per-session warmup was performed. Some retained pilot work overlapped lightweight local transport diagnostics; the shared machine was not otherwise reserved. The scorer checks locations and selected variable keys, not the full correctness of every natural-language method/path description. Missing sessions are not zero-token successes.

### Deviations and observed failures

Coordinator interrupted the first pilot before its buffered output was saved. No completed final answer or usage was recoverable. The pilot is discarded after a harness change that persists raw events immediately. The interrupted attempt is retained with missing telemetry, not treated as zero tokens. No other measured session had started.
Discarded the pilot after offline verification showed Windows Codex discovers OS-profile global skills despite fake HOME/USERPROFILE. A also rejected all shell reads because the Windows sandbox backend was unspecified. A completed with an empty answer; B was cancelled after diagnosis to avoid wasting quota. Both traces and available usage/metrics are retained as discarded data. The corrected harness disables discovered global skills only in temporary configs, copies the installed B skill to the fake CODEX_HOME skill directory, disables account apps/plugins identically, sets --no-daemon and windows.sandbox=unelevated, and verifies that public temporary corpus reads succeed while writes fail. Copied authentication remains private. The remaining campaign has not run.
A second pilot was discarded after local deterministic HTTP mock diagnostics demonstrated that this CLI does not apply the top-level -c Windows sandbox override when exec has its own overrides. With the backend override before exec, the identical mock Get-Content call was rejected; after exec, it returned READ_OK with exit zero. Mock traffic used a localhost provider and no real credentials or model quota. All session config overrides and feature switches now follow exec. A separate mock confirmed the successful command_execution event shape. Failed real pilot A usage and partial B metrics remain in discarded_attempts and runs/discarded-options. No saving is inferred from these invalid runs.
The corrected natural pilot completed all four cells with successful source reads and no MCP calls: the agent chose grep for both B tasks. Rather than bias the task prompt or repeat cells, MCP executability was validated separately with a deterministic localhost Responses stream requesting local_ask. The real readscout MCP returned a verified quote, and its fresh metrics.jsonl was found. This replaces the natural-pilot MCP-call gate, with no online agent quota, and is recorded as a validation deviation. The reading skill and task prompts remain unchanged. Synthetic diagnostic usage is excluded from measured results. The smoke model was unloaded before campaign continuation.
After all measured sessions, narrowed evidence redaction to preserve public source expressions and JSON escaping. Restored retained and discarded streams from private originals; all usage counters and blind F1 scores remained identical.
After all retained sessions and the measurement-data commit, CLI/dashboard and README labels were clarified to describe a local-text token equivalent rather than measured agent savings. Every recorded run predates this wording change. The estimate formula and delegation skill remain unchanged; the report data do not support a universal size threshold.

Discarded preparation attempts: 5; 2 have completed usage counters, summing to 378,813 reported tokens. Other preparation usage is not measured. These are additional setup consumption, excluded from paired comparisons and never hidden as free runs.

Retained raw evidence: 1834103 bytes, including discarded traces. The original source under test was not changed during any measured session.

## Reproduce

Use a temporary checkout of frozen source `6bb283e073254c9e19eedb025a750d50e541f46f`, copy the final harness and local probe from this branch into scripts/, create its development venv and use the recorded Codex/Ollama versions. For a new campaign, move any published generated artifacts aside in that temporary checkout; prepare refuses to overwrite an existing campaign. Run `python scripts/token_savings.py prepare`, review and commit the protocol and harness, then `pilot`, `controls`, `remaining`, `grade`, `report`, and `cleanup` in that order. If the natural pilot makes no reading call, run `python scripts/token_savings.py validate-mcp` and commit its protocol amendment before controls; the [local probe](../scripts/token_savings_probe.py) uses a deterministic loopback provider with no online model or credentials. Do not repeat the pilot. The run commands resume without repeating existing cells. Never reinterpret a failed pilot as a savings result. The report subcommand works offline using only results.json. All retained raw attempts are in [runs/](token-savings/runs/).

## Campaign 2

See [Campaign 2](TOKEN-SAVINGS-V2.md) for the separately preregistered follow-up and its mandatory pilot stop.
