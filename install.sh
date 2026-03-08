#!/bin/bash
# ============================================================
#  Moruk OS — Installer
#  https://github.com/FiratBulut/Moruk-OS
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${CYAN}${BOLD}"
echo "███╗   ███╗ ██████╗ ██████╗ ██╗   ██╗██╗  ██╗     ██████╗ ███████╗"
echo "████╗ ████║██╔═══██╗██╔══██╗██║   ██║██║ ██╔╝    ██╔═══██╗██╔════╝"
echo "██╔████╔██║██║   ██║██████╔╝██║   ██║█████╔╝     ██║   ██║███████╗"
echo "██║╚██╔╝██║██║   ██║██╔══██╗██║   ██║██╔═██╗     ██║   ██║╚════██║"
echo "██║ ╚═╝ ██║╚██████╔╝██║  ██║╚██████╔╝██║  ██╗    ╚██████╔╝███████║"
echo "╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝     ╚═════╝ ╚══════╝"
echo -e "${NC}"
echo -e "${BOLD}  Autonomous AI Operating System — Installer${NC}"
echo ""

# ── Helpers ─────────────────────────────────────────────────
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
err()  { echo -e "  ${RED}✗${NC} $1"; exit 1; }
step() { echo -e "\n${CYAN}${BOLD}▶ $1${NC}"; }

# ── Check OS ────────────────────────────────────────────────
step "Checking system"

if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    warn "Moruk OS is designed for Linux. Other platforms may work but are untested."
fi

# ── Check Python ─────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    err "Python 3 not found. Install with: sudo apt install python3"
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10 ]]; then
    err "Python 3.10+ required. Found: $PYTHON_VERSION"
fi
ok "Python $PYTHON_VERSION"

# ── Check system dependencies ────────────────────────────────
step "Checking system dependencies"

MISSING_PKGS=()

check_pkg() {
    if ! dpkg -l "$1" &>/dev/null && ! command -v "$2" &>/dev/null; then
        MISSING_PKGS+=("$1")
        warn "Missing: $1"
    else
        ok "$1"
    fi
}

check_pkg "python3-pip"       "pip3"
check_pkg "python3-venv"      "pyvenv"
check_pkg "libxcb-xinerama0"  "false"
check_pkg "libxcb-cursor0"    "false"
check_pkg "portaudio19-dev"   "false"
check_pkg "espeak-ng"         "espeak-ng"
check_pkg "xdotool"           "xdotool"

if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
    echo ""
    echo -e "  ${YELLOW}Installing missing packages...${NC}"
    sudo apt-get install -y "${MISSING_PKGS[@]}" || warn "Some packages failed to install — continuing anyway"
fi

# ── Create venv ──────────────────────────────────────────────
step "Setting up Python environment"

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
    ok "venv created"
else
    ok "venv already exists"
fi

VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
VENV_PIP="$SCRIPT_DIR/venv/bin/pip"

# ── Install Python packages ──────────────────────────────────
step "Installing Python packages"

"$VENV_PIP" install --upgrade pip --quiet
ok "pip upgraded"

"$VENV_PIP" install -r "$SCRIPT_DIR/requirements.txt" --quiet
ok "All packages installed"

# ── Create data directories ──────────────────────────────────
step "Creating data directories"

DIRS=(
    "$SCRIPT_DIR/data/logs"
    "$SCRIPT_DIR/data/sessions"
    "$SCRIPT_DIR/data/attachments"
    "$SCRIPT_DIR/data/images"
    "$SCRIPT_DIR/data/vision_snapshots"
    "$SCRIPT_DIR/config"
)

for dir in "${DIRS[@]}"; do
    mkdir -p "$dir"
    ok "$dir"
done

# ── Create default config if missing ────────────────────────
if [ ! -f "$SCRIPT_DIR/config/settings.json" ]; then
    cat > "$SCRIPT_DIR/config/settings.json" << 'EOF'
{
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "api_keys": {},
  "autonomy": false,
  "deepthink_enabled": false,
  "voice_enabled": false,
  "theme": "dark"
}
EOF
    ok "Default config created"
fi

# ── Make scripts executable ──────────────────────────────────
chmod +x "$SCRIPT_DIR/run.sh"
ok "run.sh is executable"

# ── X11 permissions for GUI tools ────────────────────────────
step "Configuring X11 access"

if [ -f ~/.xprofile ]; then
    if ! grep -q "xhost +local:" ~/.xprofile; then
        echo "xhost +local:" >> ~/.xprofile
        ok "Added xhost to ~/.xprofile"
    else
        ok "xhost already configured"
    fi
else
    echo "xhost +local:" > ~/.xprofile
    ok "Created ~/.xprofile with xhost"
fi
xhost +local: &>/dev/null && ok "X11 local access granted" || warn "xhost failed (normal if no display)"

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   Moruk OS installed successfully! 🚀    ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Start with:  ${CYAN}${BOLD}./run.sh${NC}"
echo ""
echo -e "  First time? Open ${BOLD}Settings ⚙${NC} and add your API key."
echo -e "  Supported: Anthropic, OpenAI, Google Gemini, Groq, DeepSeek"
echo ""
