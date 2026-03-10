#!/bin/bash
# ============================================================
#  Moruk OS — Runtime Launcher
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
CONFIG_FILE="$SCRIPT_DIR/config/settings.json"
ONBOARDING="$SCRIPT_DIR/onboarding.py"
MAIN="$SCRIPT_DIR/main.py"

echo ""
echo "▶ Starting Moruk OS"
echo ""

# ── Check venv ──────────────────────────────────────────────

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[ERROR] Python virtual environment not found."
    echo ""
    echo "Run installer first:"
    echo "  ./install.sh"
    echo ""
    exit 1
fi

# ── First Run Detection ─────────────────────────────────────

if [ ! -f "$CONFIG_FILE" ]; then
    echo "First launch detected."
    echo "Starting Moruk OS onboarding..."
    echo ""

    exec "$VENV_PYTHON" "$ONBOARDING"
fi

# ── Start Moruk Core ────────────────────────────────────────

echo "Launching Moruk OS..."
echo ""

exec "$VENV_PYTHON" "$MAIN" "$@"
