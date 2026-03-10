#!/bin/bash
# ============================================================
# Moruk OS — Auto Installer
# One-command install
# ============================================================

set -e

REPO="https://github.com/FiratBulut/Moruk-OS.git"
INSTALL_DIR="$HOME/Moruk-OS"

echo ""
echo "🚀 Installing Moruk OS..."
echo ""

# ── Check Git ───────────────────────────────────────────────

if ! command -v git &>/dev/null; then
    echo "Git not found. Installing..."

    if command -v apt &>/dev/null; then
        sudo apt update
        sudo apt install -y git
    else
        echo "Please install git manually."
        exit 1
    fi
fi

# ── Clone Repo ──────────────────────────────────────────────

if [ -d "$INSTALL_DIR" ]; then
    echo "Moruk OS already exists in $INSTALL_DIR"
else
    git clone "$REPO" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Run Installer ───────────────────────────────────────────

chmod +x install.sh
./install.sh

# ── Launch Moruk ────────────────────────────────────────────

echo ""
echo "Starting Moruk OS..."
echo ""

chmod +x run.sh
./run.sh
