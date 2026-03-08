#!/bin/bash
# ============================================================
#  Moruk OS — Release Cleanup Script
#  Bereinigt einen kopierten moruk-os Ordner für den Release.
#  Führe dieses Script im KOPIERTEN Ordner aus, nie im Original!
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
echo -e "${CYAN}${BOLD}Moruk OS — Release Cleanup${NC}"
echo -e "${YELLOW}Ordner: $SCRIPT_DIR${NC}"
echo ""

# Sicherheitscheck — nicht im Original-Ordner ausführen
if [[ "$SCRIPT_DIR" == *"moruk-os" ]] && [[ ! "$SCRIPT_DIR" == *"release"* ]] && [[ ! "$SCRIPT_DIR" == *"clone"* ]] && [[ ! "$SCRIPT_DIR" == *"dist"* ]]; then
    echo -e "${RED}${BOLD}⚠ WARNUNG: Du scheinst im Original-Ordner zu sein!${NC}"
    echo -e "   Dieser Script sollte nur in einer KOPIE ausgeführt werden."
    echo ""
    read -p "   Trotzdem fortfahren? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Abgebrochen."
        exit 0
    fi
fi

echo -e "${CYAN}▶ Entferne persönliche Daten...${NC}"

# ── API Keys & Einstellungen ──────────────────────────────────
rm -f "$SCRIPT_DIR/config/settings.json"
rm -f "$SCRIPT_DIR/config/user_settings.json"
rm -f "$SCRIPT_DIR/config/history.json"
echo -e "  ${GREEN}✓${NC} API Keys & Settings entfernt"

# Standard-Config anlegen (ohne Keys)
mkdir -p "$SCRIPT_DIR/config"
cat > "$SCRIPT_DIR/config/settings.json" << 'EOF'
{
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "api_keys": {},
  "onboarding_done": false
}
EOF
echo -e "  ${GREEN}✓${NC} Leere Standard-Config erstellt"

# system_prompt.txt behalten (ist Teil des Produkts)

# ── Chat Sessions & Verlauf ───────────────────────────────────
rm -rf "$SCRIPT_DIR/data/sessions/"
mkdir -p "$SCRIPT_DIR/data/sessions"
echo -e "  ${GREEN}✓${NC} Chat-Sessions gelöscht"

# ── Memory & persönliche Daten ────────────────────────────────
rm -f "$SCRIPT_DIR/data/memory.db"
rm -f "$SCRIPT_DIR/data/memory.db-shm"
rm -f "$SCRIPT_DIR/data/memory.db-wal"
rm -f "$SCRIPT_DIR/data/memory_short.json"
rm -f "$SCRIPT_DIR/data/conversation.json"
rm -f "$SCRIPT_DIR/data/conversation_summary.json"
rm -f "$SCRIPT_DIR/data/agent_state.json"
rm -f "$SCRIPT_DIR/data/user_profile.json"
rm -f "$SCRIPT_DIR/data/goals.json"
rm -f "$SCRIPT_DIR/data/tasks.json"
rm -f "$SCRIPT_DIR/data/tasks.json.bak"
rm -f "$SCRIPT_DIR/data/reflection_log.json"
rm -f "$SCRIPT_DIR/data/reflection_stats.json"
rm -f "$SCRIPT_DIR/data/deepthink_stats.json"
rm -f "$SCRIPT_DIR/data/benchmark_report.json"
rm -f "$SCRIPT_DIR/data/health_report.json"
rm -f "$SCRIPT_DIR/data/monitors.json"
rm -f "$SCRIPT_DIR/data/scheduled_tasks.json"
rm -f "$SCRIPT_DIR/data/strategy_rules.json"
rm -f "$SCRIPT_DIR/data/token_usage.json"
echo -e "  ${GREEN}✓${NC} Memory & persönliche Daten gelöscht"

# ── Logs ──────────────────────────────────────────────────────
rm -rf "$SCRIPT_DIR/data/logs/"
rm -rf "$SCRIPT_DIR/logs/"
mkdir -p "$SCRIPT_DIR/data/logs"
echo -e "  ${GREEN}✓${NC} Logs gelöscht"

# ── Bilder & Attachments ──────────────────────────────────────
rm -rf "$SCRIPT_DIR/data/attachments/"
rm -rf "$SCRIPT_DIR/data/images/"
rm -rf "$SCRIPT_DIR/data/vision_snapshots/"
mkdir -p "$SCRIPT_DIR/data/attachments"
mkdir -p "$SCRIPT_DIR/data/images"
mkdir -p "$SCRIPT_DIR/data/vision_snapshots"
echo -e "  ${GREEN}✓${NC} Bilder & Attachments gelöscht"

# ── Agent-generierte Dateien im Root ─────────────────────────
rm -f "$SCRIPT_DIR/results.json"
rm -f "$SCRIPT_DIR/headlines.json"
rm -f "$SCRIPT_DIR/hello.py"
rm -f "$SCRIPT_DIR/test.txt"
rm -f "$SCRIPT_DIR/*.bak"
echo -e "  ${GREEN}✓${NC} Agent-generierte Dateien entfernt"

echo ""
echo -e "${CYAN}▶ Entferne venv & Cache...${NC}"

# ── Virtual Environments ──────────────────────────────────────
rm -rf "$SCRIPT_DIR/venv/"
rm -rf "$SCRIPT_DIR/venv_xtts/"
echo -e "  ${GREEN}✓${NC} venv entfernt (wird via install.sh neu erstellt)"

# ── Python Cache ──────────────────────────────────────────────
find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.pyo" -delete 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} Python Cache geleert"

echo ""
echo -e "${CYAN}▶ Erstelle leere Datenstruktur...${NC}"

# Leere Placeholder damit Git die Ordner tracked
for dir in data/sessions data/logs data/attachments data/images data/vision_snapshots; do
    touch "$SCRIPT_DIR/$dir/.gitkeep"
done
echo -e "  ${GREEN}✓${NC} .gitkeep Placeholder erstellt"

echo ""
echo -e "${CYAN}▶ Prüfe finale Struktur...${NC}"

# Checke ob wichtige Dateien noch da sind
REQUIRED=(
    "main.py" "run.sh" "install.sh" "requirements.txt"
    "README.md" ".gitignore"
    "core/brain.py" "core/tool_router.py"
    "ui/main_window.py" "ui/onboarding.py"
    "plugins/web_search.py"
)

all_ok=true
for f in "${REQUIRED[@]}"; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        echo -e "  ${GREEN}✓${NC} $f"
    else
        echo -e "  ${RED}✗${NC} $f — FEHLT!"
        all_ok=false
    fi
done

echo ""
if $all_ok; then
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║   Release-Ordner ist bereit! 🚀              ║${NC}"
    echo -e "${GREEN}${BOLD}║   Kein API Key, keine persönlichen Daten.    ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Nächste Schritte:"
    echo -e "  ${CYAN}1.${NC} git init && git add . && git commit -m 'Initial release'"
    echo -e "  ${CYAN}2.${NC} git remote add origin https://github.com/FiratBulut/Moruk-OS.git"
    echo -e "  ${CYAN}3.${NC} git push -u origin main"
else
    echo -e "${RED}${BOLD}⚠ Einige Pflichtdateien fehlen — prüfe den Ordner!${NC}"
fi
echo ""
