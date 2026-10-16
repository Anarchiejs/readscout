# Errors and waiting

- "File not found": check the path (relative paths start at your working folder).
- "Outside the allowed folders" or "gate commands are disabled": the user restricted readscout on purpose. Do not try to work around it; read the file yourself if your own permissions allow it, or run the checks yourself.
- "llama-server not found", "model file not found" or "Model ... is not installed yet": the user's setup is incomplete, not something to fix from here. Do the task yourself and suggest `readscout doctor`, which says what is missing and how to fix it.
- Any other error: do the task yourself; `readscout doctor` diagnoses the setup. Ollama is started automatically, and so is llama.cpp's `llama-server` when the user configured it.

## Speed

Calls are synchronous. The first call after a pause loads a model (10 to 30 s for the fast one, up to a minute for the 26B quality model on a cold disk). A question that needs the other model (a negative question, or a retry with the quality model) may load it too, because on a small GPU only one model stays in memory. Wait for the answer: do not cancel, repeat the call or start a second one. The receipt header names the model that answered and how long it took.

## Memory

readscout frees the models by itself, whichever engine runs them: they unload one minute after the last call, and when your session ends. Do nothing to stop them, and do not check. If the user asks to free the memory right now, run `readscout stop`.
