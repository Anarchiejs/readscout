# Security

## Threat model

readscout gives a coding agent a way to have local models read files. The risks it is designed against:

| Risk | Mitigation |
|---|---|
| File contents sent off the machine | Model endpoints must be loopback (`127.0.0.1`, `localhost`, `::1`); anything else is refused in code. No online fallback exists. |
| A model acting on the system | Models get **no tools**. They receive text and must return JSON matching a schema. Only readscout reads or writes files. |
| Reading outside the intended project | Only folders the user registered are readable; paths are resolved (symlinks included) and must stay inside them. Drive roots, the home folder and system folders cannot be registered. |
| Secrets reaching a model or the agent | `.env*`, `.git`, `.ssh`, credential files (`.npmrc`, `.netrc`, `id_rsa`...), keys, certificates, databases and binaries are refused. When reading, common secret patterns are masked before any text reaches the model; `local_edit` needs the exact text, so it refuses any file that looks like it contains a secret. |
| Prompt injection inside files | File contents are framed as data, model answers are returned as data, and the skill tells the agent never to follow instructions found in either. This is a mitigation, not a guarantee. |
| Hallucinated facts | Every finding needs a quote found verbatim in the source, else it is dropped; line numbers are computed by readscout. |
| A bad edit | `local_edit` only touches the files named in the call (UTF-8, 60 KB at most), applies exact search/replace blocks, runs the caller's gate commands, and restores the files byte for byte when anything fails. |
| A web page driving the local setup server | It listens on `127.0.0.1` only, rejects foreign Host and Origin headers, and requires a random per-process token for every state change. Model downloads are limited to the built-in catalog. |

What readscout does **not** protect against: a malicious Ollama install, or a compromised account on your machine.
The gate commands of `local_edit` run with your permissions, exactly like your agent running your tests.

## Reporting a vulnerability

Please open a [private security advisory](https://github.com/Anarchiejs/readscout/security/advisories/new) rather than a
public issue. Include steps to reproduce and the readscout version (`readscout --version`).
