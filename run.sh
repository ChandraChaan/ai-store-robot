#!/usr/bin/env bash
# One-command start: creates the venv on first run, starts Ollama if installed, launches the robot.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x venv/bin/python ]; then
  echo "Creating virtualenv..."
  python3 -m venv venv
  venv/bin/pip install -q --upgrade pip
  venv/bin/pip install -q -r requirements.txt
fi

if command -v ollama >/dev/null 2>&1; then
  if ! curl -s localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Starting Ollama..."
    (ollama serve >/tmp/ollama.log 2>&1 &)
    sleep 2
  fi
  if ! ollama list 2>/dev/null | grep -q "qwen3:4b-instruct"; then
    echo "Downloading the local language model (one time, ~2.5 GB)..."
    ollama pull qwen3:4b-instruct || true
  fi
fi

exec venv/bin/python main.py "$@"
