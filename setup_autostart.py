#!/usr/bin/env python3
"""
Moruk AI OS - Autostart Setup
Erstellt einen .desktop Eintrag für automatischen Start beim Login.

Usage:
    python setup_autostart.py install    → Autostart aktivieren
    python setup_autostart.py remove     → Autostart deaktivieren
    python setup_autostart.py status     → Status prüfen
"""

import os
import sys
import stat
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
AUTOSTART_DIR = Path.home() / ".config" / "autostart"
DESKTOP_FILE = AUTOSTART_DIR / "moruk-os.desktop"
APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
APP_DESKTOP_FILE = APPLICATIONS_DIR / "moruk-os.desktop"


def get_desktop_content() -> str:
    """Erstellt den .desktop Datei-Inhalt."""
    venv_python = PROJECT_DIR / "venv" / "bin" / "python"
    main_py = PROJECT_DIR / "main.py"

    # Falls venv existiert, nutze venv Python
    if venv_python.exists():
        exec_cmd = f"{venv_python} {main_py}"
    else:
        exec_cmd = f"python3 {main_py}"

    return f"""[Desktop Entry]
Type=Application
Name=Moruk AI OS
Comment=Persistent Autonomous AI Operating System
Exec={exec_cmd}
Path={PROJECT_DIR}
Icon={PROJECT_DIR}/icon.png
Terminal=false
Categories=Utility;Development;
StartupNotify=true
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
"""


def create_icon():
    """Erstellt ein einfaches PNG Icon falls keines existiert."""
    icon_path = PROJECT_DIR / "icon.png"
    if icon_path.exists():
        return

    try:
        # Versuche mit PyQt6 ein Icon zu erstellen
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
        from PyQt6.QtCore import Qt

        # Brauche App-Instanz für QPixmap
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        size = 128
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Hintergrund
        painter.setBrush(QColor(12, 14, 26))
        painter.setPen(QColor(233, 69, 96, 200))
        painter.drawRoundedRect(4, 4, size - 8, size - 8, 24, 24)

        # "M" Buchstabe
        painter.setPen(QColor(233, 69, 96))
        font = QFont("Segoe UI", 56, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M")

        painter.end()
        pixmap.save(str(icon_path), "PNG")
        print(f"✓ Icon created: {icon_path}")

    except Exception as e:
        print(f"⚠ Could not create icon: {e}")


def install():
    """Installiert Autostart + Application Entry."""
    # Icon erstellen
    create_icon()

    content = get_desktop_content()

    # Autostart
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    DESKTOP_FILE.write_text(content)
    os.chmod(DESKTOP_FILE, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    print(f"✓ Autostart installed: {DESKTOP_FILE}")

    # Application Menu Entry
    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    APP_DESKTOP_FILE.write_text(content)
    os.chmod(APP_DESKTOP_FILE, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    print(f"✓ Application entry installed: {APP_DESKTOP_FILE}")

    print("\n🟢 Moruk OS will start automatically on next login.")
    print("   You can also find it in your application menu.")


def remove():
    """Entfernt Autostart."""
    removed = False
    if DESKTOP_FILE.exists():
        DESKTOP_FILE.unlink()
        print(f"✓ Autostart removed: {DESKTOP_FILE}")
        removed = True
    if APP_DESKTOP_FILE.exists():
        APP_DESKTOP_FILE.unlink()
        print(f"✓ Application entry removed: {APP_DESKTOP_FILE}")
        removed = True

    if not removed:
        print("ℹ No autostart entries found.")
    else:
        print("\n🔴 Moruk OS will no longer start automatically.")


def status():
    """Zeigt Status."""
    if DESKTOP_FILE.exists():
        print("🟢 Autostart: ACTIVE")
        print(f"   File: {DESKTOP_FILE}")
    else:
        print("🔴 Autostart: NOT ACTIVE")

    if APP_DESKTOP_FILE.exists():
        print("🟢 App Menu: INSTALLED")
    else:
        print("⚪ App Menu: NOT INSTALLED")

    icon_path = PROJECT_DIR / "icon.png"
    if icon_path.exists():
        print("🟢 Icon: EXISTS")
    else:
        print("⚪ Icon: NOT CREATED (run install to create)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python setup_autostart.py [install|remove|status]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "install":
        install()
    elif cmd == "remove":
        remove()
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python setup_autostart.py [install|remove|status]")
