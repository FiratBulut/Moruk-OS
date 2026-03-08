#!/usr/bin/env python3
"""
MORUK AI OS
Ein persistentes, autonomes AI-Betriebssystem.

Usage:
    ./run.sh               (recommended - always uses venv)
    venv/bin/python3 main.py
    python main.py         (venv site-packages auto-injected as fallback)
"""

import sys
import os
import logging

# === VENV SITE-PACKAGES FALLBACK ===
# If launched with system python instead of venv/bin/python3,
# inject venv site-packages so all dependencies (anthropic, torch, etc.) are available.
# Uses sys.version_info to avoid hardcoding the Python version.
_base_dir = os.path.dirname(os.path.abspath(__file__))
_venv_site = os.path.join(
    _base_dir, "venv", "lib",
    "python{}.{}".format(*sys.version_info[:2]),
    "site-packages"
)
if os.path.isdir(_venv_site):
    if _venv_site not in sys.path:
        sys.path.insert(1, _venv_site)
else:
    logging.warning(
        f"[startup] venv site-packages not found at {_venv_site}. "
        "Dependencies like anthropic/torch may be missing. "
        "Run: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    )
# === END VENV FALLBACK ===

# Ensure moruk-os root is on path
sys.path.insert(0, _base_dir)

from core.logger import log, install_crash_handler


def main():
    log.info("=" * 50)
    log.info("MORUK OS starting...")
    log.info(f"Python: {sys.executable} ({sys.version_info.major}.{sys.version_info.minor})")
    log.info(f"venv site-packages: {'injected' if _venv_site in sys.path else 'not needed (already in venv)'}")
    log.info("=" * 50)

    # Install crash handler
    install_crash_handler(log)

    # Ensure data directories exist
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(base_dir, "data", "logs"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "data", "sessions"), exist_ok=True)

    # Startup Checks
    from core.startup_checks import StartupCheck
    checker = StartupCheck()
    result = checker.run_all()

    if result["issues"]:
        log.error(f"Startup issues found: {result['issues']}")
        log.warning("Startup Issues:")
        for issue in result["issues"]:
            log.warning(f"  ✗ {issue}")

    # Start PyQt6 App
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont, QFontDatabase
    app = QApplication(sys.argv)
    app.setApplicationName("Moruk AI OS")
    app.setStyle("Fusion")

    # Set emoji-capable font
    available = QFontDatabase.families()
    if "Noto Sans" in available:
        base_font = "Noto Sans"
    elif "DejaVu Sans" in available:
        base_font = "DejaVu Sans"
    else:
        base_font = "Sans Serif"

    app_font = QFont(base_font, 10)
    app.setFont(app_font)
    log.info(f"App font set to: {base_font}")

    # ── Onboarding (erster Start) ────────────────────────────
    from ui.onboarding import should_show_onboarding, OnboardingDialog
    if should_show_onboarding():
        log.info("First run — showing onboarding wizard")
        onboarding = OnboardingDialog()
        onboarding.exec()
        log.info("Onboarding completed")
        # Startup result neu laden damit Brain die API Keys kennt
        result = checker.run_all()

    # ── Main Window ───────────────────────────────────────────
    from ui.main_window import MainWindow
    window = MainWindow(startup_result=result)
    window.show()

    log.info("MORUK OS UI ready")

    exit_code = app.exec()
    log.info(f"MORUK OS shutdown (exit code: {exit_code})")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
