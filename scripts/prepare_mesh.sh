#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment (.venv) not found. Run ./scripts/setup-ensemble.sh first."
else
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    fi


    if command -v python3 &>/dev/null && python3 -c "import sys" 2>/dev/null; then
        PYTHON_EXEC="python3"
    elif command -v python &>/dev/null && python -c "import sys" 2>/dev/null; then
        PYTHON_EXEC="python"
    else
        echo "❌ ERROR: Python is not installed or not working correctly."
        exit 1
    fi

    $PYTHON_EXEC scripts/prepare_model_mesh.py "$@"
fi
