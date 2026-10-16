# How readscout works

- The `quality` parameter: leave it unset. The bigger model is used automatically for negative questions ("without", "not", "missing"...) or when the fast one finds nothing. Set `quality=True` only for a subtle question.
- When two files would show the same name, the receipt prefixes the folder name. Absolute paths work for any folder, nothing needs to be registered. Sensitive and excluded files inside a folder are skipped.
- Findings whose quote was not found in the source have already been dropped. A verified quote proves the line exists, not that the interpretation is right.
- Sensitive files (`.env*`, keys, `.git`, credential files) are refused. Common secret patterns are masked before reaching the model; masking is pattern based, not perfect.
- The models run on this machine, through Ollama or llama.cpp's `llama-server` on `127.0.0.1`. readscout refuses remote endpoints and Ollama cloud models.
- Never start, pull, load or switch models, engines or inference servers yourself (`ollama run`, `ollama pull`, `llama-server`, `readscout engine`...).
