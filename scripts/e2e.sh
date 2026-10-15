#!/usr/bin/env bash
# End-to-end test of readscout on Linux or macOS with a real Ollama and GPU (run before a release).
# Isolated, like scripts/e2e.ps1: its own uv tool folder, its own readscout config and its own PATH entry. It never
# touches your installed readscout, your ~/.config/readscout or your shell setup. Ollama and its models are shared.
# usage: bash scripts/e2e.sh [path/to/readscout/source]      exit code: 0 when every step passed, 1 otherwise
SRC="$(cd "${1:-$(dirname "$0")/..}" && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/readscout-e2e.XXXXXX")" || exit 2
trap 'kill "${WEB:-}" 2>/dev/null; rm -rf "$T"' EXIT
export UV_TOOL_DIR="$T/tools" UV_TOOL_BIN_DIR="$T/bin" READSCOUT_HOME="$T/home" XDG_CONFIG_HOME="$T/xdg"
export PATH="$T/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/lib/wsl/lib"
WORK="$T/work"
pass=0; fail=0
step() { if eval "$2" >"$T/step.out" 2>&1; then echo "PASS  $1"; pass=$((pass+1)); else echo "FAIL  $1"; tail -8 "$T/step.out" | sed 's/^/      /'; fail=$((fail+1)); fi; }

mkdir -p "$WORK/src" && (cd "$SRC" && tar --exclude=.venv --exclude=.git -cf - .) | tar -xf - -C "$WORK/src"
step "install from local source (uv tool)" "uv tool install --force --python 3.12 \"$WORK/src\""
step "first run writes a hardware-based config" "readscout doctor; grep -q gemma4:e4b \"$READSCOUT_HOME/config.json\""
step "pull recommended models" "readscout pull"
TOOLPY="$UV_TOOL_DIR/readscout/bin/python"

# A small project to work on.
"$TOOLPY" -c "from pathlib import Path; from readscout.bench import edits; edits._make(Path('$WORK/demo'))"
"$TOOLPY" -c "from pathlib import Path; from readscout.bench import logs; logs.tasks(Path('$WORK/demo/logs'))"
step "ask returns verified findings" "cd \"$WORK/demo\" && readscout ask shop -q 'Which functions raise ValueError?' | tee /dev/stderr | grep -q 'shop/catalog.py:13'"
step "negative question works (quality tier = fast here)" "cd \"$WORK/demo\" && readscout ask shop -q 'Which functions do not validate their input?' | grep -q 'verified quote'"
step "digest finds the root cause" "readscout digest \"$WORK/demo/logs\"/service-3000.log | tee /dev/stderr | grep -q 'service-3000.log:1979'"
step "edit applied with a passing gate" "cd \"$WORK/demo\" && readscout edit shop/catalog.py -i 'paginate returns the wrong page: page 1 must return the first per_page items. Fix it.' --gate 'python3 -m unittest discover -s tests -t .' | tee /dev/stderr | grep -q '^APPLIED'"
step "edit result is correct" "cd \"$WORK/demo\" && python3 -c 'from shop.catalog import paginate as p; L=list(range(25)); assert p(L,1)==L[:10]'"
step "edit refuses sensitive new files" "cd \"$WORK/demo\" && ! readscout edit .env -i 'create it' 2>&1 | grep -q APPLIED && [ ! -e .env ]"

# MCP server over stdio, as an agent would use it.
cat > "$T/mcp_smoke.py" <<'EOF'
import asyncio, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client, get_default_environment
async def main():
    env = {**get_default_environment(), 'READSCOUT_HOME': os.environ['READSCOUT_HOME']}
    p = StdioServerParameters(command=os.path.join(os.environ['UV_TOOL_BIN_DIR'], 'readscout-mcp'), args=[], cwd=os.environ['E2E_DEMO'], env=env)
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = [t.name for t in (await s.list_tools()).tools]
            assert names == ['local_ask', 'local_digest', 'local_edit'], names
            txt = (await s.call_tool('local_ask', {'paths': ['shop/pricing.py'], 'question': 'What VAT rates exist?'})).content[0].text
            assert 'shop/pricing.py:' in txt, txt
            print(txt[:300])
asyncio.run(main())
EOF
step "MCP server over stdio" "E2E_DEMO=\"$WORK/demo\" $TOOLPY \"$T/mcp_smoke.py\""

# Setup web server protections.
readscout serve-web --port 8799 >"$T/web.log" 2>&1 & WEB=$!
for i in $(seq 1 30); do curl -s 127.0.0.1:8799/api/ping >/dev/null && break; sleep 0.5; done
step "setup page served with a token" "curl -s 127.0.0.1:8799/setup | grep -q X-Readscout-Token"
step "POST without token refused" "[ \"\$(curl -s -o /dev/null -w '%{http_code}' -X POST 127.0.0.1:8799/api/models -d '{}')\" = 403 ]"
step "foreign Host refused" "[ \"\$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: evil.example' 127.0.0.1:8799/setup)\" = 403 ]"
step "state API answers" "curl -s 127.0.0.1:8799/api/state | grep -q '\"hardware\"'"
kill "$WEB" 2>/dev/null

step "doctor" "readscout doctor | tee /dev/stderr | grep -q 'Ollama running'"
step "stats recorded the calls" "readscout stats | tee /dev/stderr | grep -q 'read(s)'"
step "unit tests on this machine" "cd \"$WORK/src\" && uv run --quiet --python 3.12 --with pytest pytest -q"
step "public bench (corpus download + fingerprints + scoring)" "readscout bench --models gemma4:e4b --only log,routes_filter,data_access,routes_list | tee /dev/stderr | grep -q '| gemma4:e4b |'"
step "uninstall cleanly" "uv tool uninstall readscout && hash -r && [ ! -e \"$UV_TOOL_BIN_DIR/readscout\" ]"

echo; echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
