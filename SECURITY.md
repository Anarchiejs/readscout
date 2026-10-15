# Security

## Threat model

readscout gives a coding agent a way to have local models read files. The risks it is designed against:

| Risk | Mitigation |
|---|---|
| File contents sent off the machine | Model endpoints must be loopback (`127.0.0.1`, `localhost`, `::1`); anything else is refused in code. A loopback address alone is not enough (Ollama can forward some models to its cloud), so models named `...-cloud` or `...:cloud`, and models Ollama reports with a remote host, are refused too; Ollama is started with `OLLAMA_NO_CLOUD=1`. No online fallback exists. |
| A model acting on the system | Models get **no tools**. They receive text and must return JSON matching a schema. Only readscout reads or writes files. |
| Reading files the user did not mean to share | The local model only receives the files and folders the coordinating agent names in a tool call. By default that can be any folder, because the model runs on this machine and an unrestricted agent already has the user's file access. When the agent's own permissions are narrower (Claude Code `Read` deny rules, no Bash), readscout cannot see them: `readscout folders add <dir>` sets an allow-list that every read and write (new files included) must fall in, and `readscout gate off` forbids `local_edit` gate commands. Sensitive files stay refused in every case (next row). Paths are resolved, symlinks included, before both checks. |
| Secrets reaching a model or the agent | `.env*`, `.git`, `.ssh`, credential files (`.npmrc`, `.netrc`, `id_rsa`...), keys, certificates, databases and binaries are refused, whatever the letter case, when reading and when creating files. When reading, common secret patterns (private keys; OpenAI, Anthropic, GitHub, GitLab, AWS, Slack, Google, Stripe, npm, PyPI, Hugging Face and SendGrid tokens; JWTs; Slack webhooks; passwords in URLs; `Authorization` headers; `password`/`secret`/`token`/`api key`/`credentials`/`connection string` assignments including JSON, never across a line break) are masked before any text reaches the model, keeping line numbers intact; `local_edit` needs the exact text, so it refuses any file that looks like it contains a secret. Masking is pattern based and cannot be complete. |
| Prompt injection inside files | File contents are framed as data, model answers are returned as data (one flattened, length-bounded line per finding), and the skill tells the agent never to follow instructions found in either. The prose of an answer is not verified, only the quotes are. This is a mitigation, not a guarantee. |
| Hallucinated facts | Every finding needs a quote found in the source, else it is dropped; the quote may differ only by whitespace and by line breaks between adjacent lines. Line numbers are computed by readscout. |
| A bad edit | `local_edit` only touches the files named in the call (UTF-8, 60 KB at most, one project at a time), applies exact search/replace blocks, writes atomically, refuses to overwrite a file that changed while the model was working, runs the caller's gate commands, and restores what it wrote, byte for byte, when anything fails. A file somebody else modified in the meantime is left alone and reported. |
| A web page driving the local setup server | It listens on `127.0.0.1` only, rejects foreign Host and Origin headers, and requires a random per-process token for every state change. Model downloads are limited to the built-in catalog. |

What readscout does **not** protect against: a malicious Ollama install, or a compromised account on your machine.
The gate commands of `local_edit` (at most 5, argv lists, no shell) run with your permissions, exactly like your agent running your tests: whoever can call the tool can run them, unless you turn them off with `readscout gate off`.

Supply chain: CI and release actions are pinned by commit, the release workflow runs the tests before building, and each release publishes `SHA256SUMS`. Installers download the wheel from the GitHub release of the same version; they do not verify a signature.

## Reporting a vulnerability

Please open a [private security advisory](https://github.com/Anarchiejs/readscout/security/advisories/new) rather than a
public issue. Include steps to reproduce and the readscout version (`readscout --version`).
