# End-to-end test of readscout on Windows with a real Ollama and GPU (run before a release).
# Isolated: own uv tool folder and own config, the user PATH is never touched.
# usage: powershell -File scripts\e2e.ps1 [-Source path\to\readscout] [-LlamaServer path\to\llama-server.exe]
# -LlamaServer (the CUDA build on an NVIDIA GPU) adds a llama.cpp stage: the quality model runs on llama.cpp from
# Ollama's own files, and doctor, a read and `readscout stop` are checked on that engine.
param([string]$Source = (Split-Path -Parent $PSScriptRoot), [string]$LlamaServer = '')
$ErrorActionPreference = 'Continue'
$T = Join-Path $env:TEMP 'rs-win-e2e'
Remove-Item -Recurse -Force $T -ErrorAction SilentlyContinue
New-Item -ItemType Directory $T | Out-Null
$env:UV_TOOL_DIR = "$T\tools"; $env:UV_TOOL_BIN_DIR = "$T\bin"; $env:READSCOUT_HOME = "$T\home"
$env:PATH = "$T\bin;$env:PATH"; $env:PYTHONIOENCODING = 'utf-8'
$script:pass = 0; $script:fail = 0
function Step($name, [scriptblock]$check) {
    $out = & $check 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -and $?) { Write-Output "PASS  $name"; $script:pass++ }
    else { Write-Output "FAIL  $name"; ($out -split "`n" | Select-Object -Last 6) | ForEach-Object { "      $_" }; $script:fail++ }
}
function Has($text, $needle) { if ($text -match [regex]::Escape($needle)) { $global:LASTEXITCODE = 0 } else { Write-Output $text; $global:LASTEXITCODE = 1 } }

Step 'install from local source (uv tool)' { uv tool install --force --python 3.12 $Source 2>&1 | Out-Null; $global:LASTEXITCODE = [int](-not (Test-Path "$T\bin\readscout.exe")) }
Step 'first run writes a hardware-based config' { readscout hardware | Out-Null; readscout doctor | Out-Null; Has (Get-Content "$T\home\config.json" -Raw) 'gemma4:26b' }
$py = "$T\tools\readscout\Scripts\python.exe"
& $py -c "from pathlib import Path; from readscout.bench import edits, logs; edits._make(Path(r'$T\demo')); logs.tasks(Path(r'$T\demo\logs'))"
Push-Location "$T\demo"
Step 'ask returns verified findings' { Has (readscout ask shop -q 'Which functions raise ValueError?' | Out-String) 'shop/catalog.py:13' }
Step 'negative question goes to the quality model' { Has (readscout ask shop -q 'Which functions do not validate their input?' | Out-String) 'gemma4:26b' }
Step 'digest finds the root cause' { Has (readscout digest "$T\demo\logs\service-3000.log" | Out-String) 'service-3000.log:1979' }
Step 'edit applied with a passing gate' { Has (readscout edit shop/catalog.py -i 'paginate returns the wrong page: page 1 must return the first per_page items. Fix it.' --gate "$py -m unittest discover -s tests -t ." | Out-String) 'APPLIED' }
Step 'edit result is correct' { & $py -c "from shop.catalog import paginate as p; L=list(range(25)); assert p(L,1)==L[:10]" }
Pop-Location
$mcp = @'
import asyncio, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client, get_default_environment
async def main():
    env = {**get_default_environment(), 'READSCOUT_HOME': os.environ['READSCOUT_HOME']}
    p = StdioServerParameters(command=os.path.join(os.environ['UV_TOOL_BIN_DIR'], 'readscout-mcp.exe'), args=[], cwd=os.path.join(os.environ['TEMP'], 'rs-win-e2e', 'demo'), env=env)
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = [t.name for t in (await s.list_tools()).tools]
            assert names == ['local_ask', 'local_digest', 'local_edit'], names
            txt = (await s.call_tool('local_ask', {'paths': ['shop/pricing.py'], 'question': 'What VAT rates exist?'})).content[0].text
            assert 'shop/pricing.py:' in txt, txt
asyncio.run(main())
'@
Set-Content -Encoding utf8 "$T\mcp_smoke.py" $mcp
Step 'MCP server over stdio' { & $py "$T\mcp_smoke.py" }
$web = Start-Process -FilePath "$T\bin\readscout.exe" -ArgumentList 'serve-web', '--port', '8798' -PassThru -WindowStyle Hidden
for ($i = 0; $i -lt 30; $i++) { try { Invoke-WebRequest http://127.0.0.1:8798/api/ping -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }
Step 'setup page served with a token' { Has (Invoke-WebRequest http://127.0.0.1:8798/setup -UseBasicParsing).Content 'X-Readscout-Token' }
Step 'POST without token refused' { try { Invoke-WebRequest http://127.0.0.1:8798/api/models -Method Post -Body '{}' -UseBasicParsing | Out-Null; $global:LASTEXITCODE = 1 } catch { $global:LASTEXITCODE = [int]($_.Exception.Response.StatusCode.value__ -ne 403) } }
Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue
Step 'doctor sees Ollama and the models' { Has (readscout doctor | Out-String) 'OK   quality model gemma4:26b installed' }
Step 'public bench (subset)' { Has (readscout bench --models gemma4:e4b --only log,data_access --no-edits | Out-String) '| gemma4:e4b |' }
if ($LlamaServer) {
    $quality = (Get-Content "$T\home\config.json" -Raw | ConvertFrom-Json).models.quality.name
    Push-Location "$T\demo"
    Step 'llama.cpp: quality model on llama.cpp, from Ollama files' { Has (readscout engine llamacpp --quality "ollama:$quality" --binary $LlamaServer | Out-String) 'quality  llamacpp' }
    Step 'llama.cpp: doctor lists the devices llama-server sees' { Has (readscout doctor | Out-String) 'llama-server devices:' }
    Step 'llama.cpp: a negative question is answered by llama-server' { Has (readscout ask shop -q 'Which functions do not validate their input?' | Out-String) 'verified quote' }
    Step 'llama.cpp: the fast model still answers on Ollama' { Has (readscout ask shop -q 'Which functions raise ValueError?' | Out-String) 'shop/catalog.py:13' }
    Step 'llama.cpp: stop frees every model' { readscout stop | Out-Null; $global:LASTEXITCODE = [int]([bool](Get-Process llama-server -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Resolve-Path $LlamaServer).Path })) }
    Step 'llama.cpp: back to Ollama for every model' { Has (readscout engine ollama | Out-String) 'ollama for every model' }
    Pop-Location
}
Step 'uninstall cleanly' { uv tool uninstall readscout 2>&1 | Out-Null; $global:LASTEXITCODE = [int](Test-Path "$T\bin\readscout.exe") }
"RESULT: $script:pass passed, $script:fail failed"
Remove-Item -Recurse -Force $T -ErrorAction SilentlyContinue
exit ([int]($script:fail -gt 0))
