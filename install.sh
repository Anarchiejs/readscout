#!/usr/bin/env sh
# readscout installer for macOS and Linux.
#   curl -fsSL https://raw.githubusercontent.com/Anarchiejs/readscout/main/install.sh | sh
# Installs what is missing (uv, Ollama) after asking, installs readscout, then opens the setup page.
# Environment: READSCOUT_YES=1 (no questions), READSCOUT_SOURCE=<pip spec or local path>, READSCOUT_NO_SETUP=1
set -eu
SOURCE="${READSCOUT_SOURCE:-https://github.com/Anarchiejs/readscout/releases/download/v0.1.5/readscout-0.1.5-py3-none-any.whl}"

ask() {
  [ "${READSCOUT_YES:-0}" = "1" ] && return 0
  # Without a terminal nobody can answer: never install third-party software silently.
  if ! { [ -r /dev/tty ] && : </dev/tty; } 2>/dev/null; then
    echo "$1 -> no terminal to ask: answering no (set READSCOUT_YES=1 to accept)"
    return 1
  fi
  printf '%s [Y/n] ' "$1"
  read -r answer </dev/tty || return 1
  case "$answer" in ""|[yYoO]*) return 0 ;; *) return 1 ;; esac
}
have() { command -v "$1" >/dev/null 2>&1; }

printf '\nreadscout installer\n\n'

# 1. uv: installs Python and readscout in an isolated environment.
if ! have uv; then
  ask "uv (Python package manager, astral.sh) is required. Install it now?" || { echo "uv is required."; exit 1; }
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"; export PATH
fi
echo "OK   $(uv --version)"

# 2. Ollama: runs the local models.
if ! have ollama && [ ! -d /Applications/Ollama.app ]; then
  if ask "Ollama (runs the local models, ollama.com) is required. Install it now?"; then
    case "$(uname -s)" in
      Darwin)
        if have brew; then brew install --cask ollama
        else echo "Download Ollama from https://ollama.com/download/mac, install it, then run this script again."; exit 1; fi ;;
      *) curl -fsSL https://ollama.com/install.sh | sh ;;
    esac
  else
    echo "Skipped: readscout will not work until Ollama is installed (https://ollama.com)."
  fi
fi
{ have ollama || [ -d /Applications/Ollama.app ]; } && echo "OK   Ollama"

# 3. readscout itself.
uv tool install --force --python 3.12 "$SOURCE"
uv tool update-shell >/dev/null 2>&1 || true
PATH="$HOME/.local/bin:$PATH"; export PATH
echo "OK   readscout installed"

# 4. Setup page: hardware, models (1 click), agents, project folders.
if [ "${READSCOUT_NO_SETUP:-0}" != "1" ]; then
  readscout setup
  echo
  echo "Finish in the page that just opened. Later: 'readscout doctor' checks everything, 'readscout setup' reopens the page."
fi
