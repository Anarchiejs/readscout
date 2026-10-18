# Errors and waiting

- "File not found": check the path (relative paths start at your working folder).
- "Outside the allowed folders" or "gate commands are disabled": the user restricted readscout on purpose. Do not try to work around it; read the file yourself if your own permissions allow it, or run the checks yourself.
- "llama-server not found", "model file not found" or "Model ... is not installed yet": the user's setup is incomplete, not something to fix from here. Do the task yourself and suggest `readscout doctor`, which says what is missing and how to fix it.
- Any other error: do the task yourself; `readscout doctor` diagnoses the setup. Ollama is started automatically, and so is llama.cpp's `llama-server` when the user configured it.

## Speed

Calls are synchronous. The first call after a pause loads a model (10 to 30 s for the fast one, up to a minute for the 26B quality model on a cold disk). A question that needs the other model (a negative question, or a retry with the quality model) may load it too, because on a small GPU only one model stays in memory. Wait for the answer: do not cancel, repeat the call or start a second one. The receipt header names the model that answered and how long it took.

## Memory

readscout frees the models by itself, whichever engine runs them: they unload one minute after the last call, and when your session ends. Do nothing to stop them, and do not check. If the user asks to free the memory right now, run `readscout stop`.

When sessions share llama.cpp, an active request or a loading model is not stopped automatically. A request for another model fails with a retry message while that server is busy. An unavailable slots endpoint is treated as busy. Retry only after the other request finishes; do not kill or switch the server yourself.

## Version and installation

When the user asks to diagnose or update the installation, `readscout info` prints the source version, installed distribution version, package path and content fingerprint without starting a model. A source checkout is separate from the installed MCP package. After installing a tested wheel, run `readscout install-agent codex` and/or `readscout install-agent claude` to copy the core and every reference and register that environment's MCP server. Reconnect the clients afterwards: open sessions keep their loaded modules and skill text until restarted.
