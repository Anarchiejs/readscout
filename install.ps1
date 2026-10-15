# readscout installer for Windows.
#   irm https://raw.githubusercontent.com/Anarchiejs/readscout/main/install.ps1 | iex
# Installs what is missing (uv, Ollama) after asking, installs readscout, then opens the setup page.
# Options (when run as a file): -Yes (no questions), -Source <pip spec or local path>, -NoSetup
param([switch]$Yes, [string]$Source = 'https://github.com/Anarchiejs/readscout/releases/download/v0.1.4/readscout-0.1.4-py3-none-any.whl', [switch]$NoSetup)
# Native tools (uv, winget) write progress to stderr; Windows PowerShell 5.1 would treat that as an error
# under 'Stop', so failures are detected through exit codes instead.
$ErrorActionPreference = 'Continue'

function Ask($question) {
    if ($Yes) { return $true }
    $a = Read-Host "$question [Y/n]"
    return ($a -eq '' -or $a -match '^[yYoO]')
}
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

Write-Host "`nreadscout installer`n" -ForegroundColor Cyan

# 1. uv: installs Python and readscout in an isolated environment.
if (-not (Have 'uv')) {
    if (-not (Ask 'uv (Python package manager, astral.sh) is required. Install it now?')) { throw 'uv is required.' }
    Invoke-RestMethod https://astral.sh/uv/install.ps1 -ErrorAction Stop | Invoke-Expression
    Refresh-Path
}
Write-Host "OK   $(uv --version)"

# 2. Ollama: runs the local models.
$ollamaApp = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if (-not ((Have 'ollama') -or (Test-Path $ollamaApp))) {
    if (Ask 'Ollama (runs the local models, ollama.com) is required. Install it now with winget?') {
        if (Have 'winget') {
            winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
            Refresh-Path
        } else {
            Start-Process 'https://ollama.com/download/windows'
            Read-Host 'winget is not available: install Ollama from the page that just opened, then press Enter'
        }
    } else {
        Write-Host 'Skipped: readscout will not work until Ollama is installed (https://ollama.com).' -ForegroundColor Yellow
    }
}
if ((Have 'ollama') -or (Test-Path $ollamaApp)) { Write-Host 'OK   Ollama' }

# 3. readscout itself.
# On Windows a running readscout (your agent's MCP server, the setup page) locks its files and the reinstall fails with
# "Access denied": close those processes first (restart your coding agent afterwards).
$toolDir = Join-Path ((uv tool dir 2>$null) | Select-Object -First 1) 'readscout'
$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like "$toolDir\*" })
if ($running.Count) {
    Write-Host "Closing $($running.Count) running readscout process(es); restart your coding agent afterwards." -ForegroundColor Yellow
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
uv tool install --force --python 3.12 $Source
if ($LASTEXITCODE) { throw 'readscout installation failed.' }
uv tool update-shell 2>$null | Out-Null
Refresh-Path
Write-Host 'OK   readscout installed' -ForegroundColor Green

# 4. Setup page: hardware, models (1 click), agents, project folders.
if (-not $NoSetup) {
    & readscout setup
    Write-Host "`nFinish in the page that just opened. Later: 'readscout doctor' checks everything, 'readscout setup' reopens the page."
}

