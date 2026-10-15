# Design: why readscout works this way

readscout replaced a first design that was measured on real work and failed. This page keeps the lessons.

## What failed (66 real delegated tasks)

The first design sent tasks to small local models through a Docker sandbox and an agent runtime, with a JSON contract,
asynchronous jobs and a review step where the coordinating agent accepted a fingerprint. Result: 8 tasks accepted,
27 failures, 17 rejections, 9 cancellations.

| Cause | Evidence |
|---|---|
| **Judgement was delegated** (code review, "find the errors", fact checking of course notes) | Most rejections were false findings: a correct date called "in the future", two poems confused, a voluntary mistake in an exercise flagged as an error. |
| **Limits refused input instead of adapting** | 14 failures were "file exceeds context size limit" (12 KB cap while the model accepted about 90 KB), plus "report too large" and strict schema rejections. |
| **Heavy runtime** | 40-80 s per task and a fully broken service whenever Docker stopped, while the model alone answered in 2-15 s. |
| **A protocol that cost the coordinator more than the task** | Writing the contract, polling, reading and accepting cost about 700 tokens for tasks the agent could do in about 600. |
| **A toy benchmark** | Six synthetic tasks scored 1.00 while real tasks failed. |

## What readscout does instead

| Principle | Source |
|---|---|
| The model never sees anything but the text it must read; the coordinator never sees that text, only a receipt. | MinionS, Stanford HazyResearch (local reads chunks, remote never reads the document: 5.7x cheaper for 97.9 % of the quality) |
| Delegation must *displace* content, not add a hop: send paths, get a receipt. | ollama_mcp (Rikiza89) |
| A small model is a good reader and a poor authority; fit oversized inputs instead of refusing them. | local-worker (Sour-Dev-Home) |
| A local model never fails over to an online one. | claude-code-delegate-local (fegone) |
| Every finding must quote the source verbatim; the host checks the quote and computes the line numbers. | readscout |
| Output is constrained by a JSON schema, so it always parses. | Ollama structured outputs |
| An edit is kept only if the project's own checks pass; otherwise the files are restored byte for byte. | ollama_mcp's gate idea, readscout's restore |
| Three tools, synchronous, no job queue: tool schemas are re-sent to the agent on every turn. | ollama_mcp |

## What was measured and rejected

- **Asking the same small model to re-check each finding** lowered scores (0.80 to 0.75 for the fast model, and
  lower for the big one too): small models judge their own output poorly. Choosing the right model up front works better.
- **Smaller chunks** (12 KB) did not change scores; bigger chunks mean fewer calls.
- **Dense 27B models on an 8 GB GPU**: excellent answers, but 51 tokens/s reading and 3 tokens/s writing, so 2.5-8 minutes
  per question. Mixture-of-experts models (4B active) are the right fit for small GPUs.
- **llama.cpp vs Ollama**: llama.cpp reads prompts 3.5x faster on MoE models with a large micro-batch (`-ub 4096`),
  but the end-to-end gain on the quality model was about 30 %. Ollama stays the default for simplicity (one-click model
  downloads); llama.cpp is an optional engine (`readscout engine llamacpp`): readscout runs a single shared
  `llama-server` on a loopback port and stops it when idle, like Ollama's `keep_alive`. Re-measured through readscout
  with Gemma 4 (llama.cpp b11636 CUDA): `-ub 4096` was slower than 2048 with CUDA and could not be allocated at all with
  Vulkan next to the 26B on 8 GB; prompt reading is 2x faster for the 26B but writing is 1.8x slower, so only big new
  inputs gain (181 s to 127 s; asked again, Ollama's prompt cache and faster writing win, 30 s against 54 s), and the
  fast E4B and the 12B are 3x and 2x slower than on Ollama. Ollama's default repeat penalty (1.1 over 64
  tokens) is required: without it Gemma 4 loops until the output limit under a JSON schema. Hence an engine per
  model (the fast one on Ollama, the 26B on llama.cpp); on 8 GB the engines take turns on the GPU (each frees the
  other's idle model before loading), since two resident models would push the 26B's experts out of VRAM.
