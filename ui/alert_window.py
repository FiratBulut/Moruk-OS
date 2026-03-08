"""
Moruk OS – Alert Window
Separates Popup-Fenster für System-Warnungen und Crash-Reports.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal


class AlertWindow(QDialog):
    """Popup-Fenster für System-Alerts mit OK / Reparieren Optionen."""

    repair_requested = pyqtSignal(str)  # Signal: Reparatur angefordert (problem_id)

    def __init__(self, title: str, message: str, problem_id: str = "",
                 can_repair: bool = True, parent=None):
        super().__init__(parent)
        self.problem_id = problem_id
        self.can_repair = can_repair
        self._build_ui(title, message)

    def _build_ui(self, title: str, message: str):
        self.setWindowTitle("Moruk OS – System Alert")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog
        )
        self.setMinimumWidth(420)
        self.setMaximumWidth(560)

        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a2e;
                border: 2px solid #e94560;
                border-radius: 12px;
            }
            QLabel#header {
                color: #e94560;
                font-size: 15px;
                font-weight: bold;
                padding: 4px;
            }
            QLabel#icon {
                font-size: 28px;
                padding: 4px;
            }
            QTextEdit {
                background-color: #16213e;
                color: #c8d6e5;
                border: 1px solid #2a2a4a;
                border-radius: 6px;
                font-size: 13px;
                padding: 8px;
            }
            QPushButton#btn_ok {
                background-color: #2a2a4a;
                color: #c8d6e5;
                border: 1px solid #3a3a6a;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
            }
            QPushButton#btn_ok:hover { background-color: #3a3a6a; }
            QPushButton#btn_repair {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#btn_repair:hover { background-color: #ff6b6b; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header: Icon + Titel
        header_row = QHBoxLayout()
        icon_label = QLabel("⚠️")
        icon_label.setObjectName("icon")
        header_label = QLabel(title)
        header_label.setObjectName("header")
        header_label.setWordWrap(True)
        header_row.addWidget(icon_label)
        header_row.addWidget(header_label, 1)
        layout.addLayout(header_row)

        # Nachricht
        msg_box = QTextEdit()
        msg_box.setPlainText(message)
        msg_box.setReadOnly(True)
        msg_box.setMaximumHeight(120)
        layout.addWidget(msg_box)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("btn_ok")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)

        if self.can_repair:
            btn_repair = QPushButton("🔧 Reparieren")
            btn_repair.setObjectName("btn_repair")
            btn_repair.clicked.connect(self._on_repair)
            btn_row.addWidget(btn_repair)

        layout.addLayout(btn_row)

    def _on_repair(self):
        """Reparatur angefordert – Signal senden."""
        self.repair_requested.emit(self.problem_id)
        self.accept()

    @staticmethod
    def show_alert(title: str, message: str, problem_id: str = "",
                   can_repair: bool = True, parent=None) -> 'AlertWindow':
        """Convenience: Erstellt und zeigt Alert-Fenster."""
        win = AlertWindow(title, message, problem_id, can_repair, parent)
        win.show()
        win.raise_()
        win.activateWindow()
        return win
