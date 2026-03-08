"""
Moruk AI OS - System Tray Icon
Zeigt ein Icon im System Tray (neben Uhr) mit Menü.
"""

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt


def create_tray_icon_pixmap() -> QPixmap:
    """Erstellt ein 64x64 Moruk OS Icon programmatisch."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # Transparent

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Hintergrund-Kreis (dunkelblau)
    painter.setBrush(QColor(12, 14, 26))
    painter.setPen(QColor(233, 69, 96))
    painter.drawEllipse(2, 2, size - 4, size - 4)

    # "M" Buchstabe
    painter.setPen(QColor(233, 69, 96))
    font = QFont("Segoe UI", 28, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M")

    painter.end()
    return pixmap


class MorukTrayIcon(QSystemTrayIcon):
    """System Tray Icon für Moruk OS."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        # Icon setzen
        pixmap = create_tray_icon_pixmap()
        self.setIcon(QIcon(pixmap))
        self.setToolTip("Moruk AI OS")

        # Menü erstellen
        menu = QMenu()

        show_action = menu.addAction("🖥 Show Moruk OS")
        show_action.triggered.connect(self._show_window)

        menu.addSeparator()

        status_action = menu.addAction("● Ready")
        status_action.setEnabled(False)
        self._status_action = status_action

        menu.addSeparator()

        quit_action = menu.addAction("✕ Quit")
        quit_action.triggered.connect(self._quit)

        self.setContextMenu(menu)

        # Doppelklick auf Tray Icon → Fenster anzeigen
        self.activated.connect(self._on_activated)

    def _show_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _quit(self):
        self.main_window.close()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def update_status(self, text: str):
        """Aktualisiert den Status im Tray-Menü."""
        self._status_action.setText(text)
        self.setToolTip(f"Moruk AI OS — {text}")

    def show_notification(self, title: str, message: str):
        """Zeigt eine System-Notification."""
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
