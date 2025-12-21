#!/bin/bash
# Launch KaivosAI in the current terminal
# Compatible with Linux, macOS, and WSL

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "✗ Virtual environment not found. Run: python3 -m venv .venv"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check dependencies
if ! python3 -c "import textual" 2>/dev/null; then
    echo "✗ Textual not installed. Run: pip install textual"
    exit 1
fi

# Launch KaivosAI
echo "Starting KaivosAI..." >&2
python3 kaivosai.py

exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "✗ Program exited with code $exit_code" >&2
fi

exit $exit_code
