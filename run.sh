#!/bin/bash
# Moruk AI OS - Starter Script
# Stellt sicher dass die venv verwendet wird

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[ERROR] venv nicht gefunden: $VENV_PYTHON"
    echo "Erstelle venv mit: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

exec "$VENV_PYTHON" "$SCRIPT_DIR/main.py" "$@"
