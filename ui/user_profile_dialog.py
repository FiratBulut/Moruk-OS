"""
Moruk OS — User Profile Dialog
Zeigt was Moruk OS über den User weiß: Profil + Preferences aus Memory.
"""
import json
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGroupBox, QLineEdit, QTextEdit,
    QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

PROFILE_PATH = Path(__file__).parent.parent / "data" / "user_profile.json"


class UserProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("👤 User Profile")
        self.setMinimumSize(520, 600)
        self.setStyleSheet("""
            QDialog { background-color: #0d0d1a; color: #e0e0e0; }
            QGroupBox {
                border: 1px solid #333;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px;
                font-size: 13px;
                color: #00d4ff;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
            QLineEdit, QTextEdit {
                background: #1a1a2e;
                border: 1px solid #333;
                border-radius: 6px;
                color: #e0e0e0;
                padding: 6px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus { border-color: #00d4ff; }
            QPushButton {
                background-color: #1a1a3e;
                border: 1px solid #333;
                border-radius: 6px;
                color: #e0e0e0;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #2a2a5e; border-color: #00d4ff; }
            QPushButton#save_btn {
                background-color: #00d4ff;
                color: #0d0d1a;
                font-weight: bold;
            }
            QPushButton#save_btn:hover { background-color: #00b8d9; }
            QPushButton#delete_btn { border-color: #e94560; color: #e94560; }
            QPushButton#delete_btn:hover { background-color: #2a0a1a; }
            QLabel { color: #e0e0e0; font-size: 13px; }
            QScrollArea { border: none; background: transparent; }
        """)
        self.profile = self._load_profile()
        self._build_ui()

    def _load_profile(self) -> dict:
        if PROFILE_PATH.exists():
            try:
                with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_profile(self):
        self.profile["name"] = self.name_edit.text().strip()
        self.profile["job"] = self.job_edit.text().strip()
        self.profile["bio"] = self.bio_edit.toPlainText().strip()
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PROFILE_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.profile, f, indent=2, ensure_ascii=False)
        os.replace(tmp, PROFILE_PATH)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("👤 Was Moruk OS über dich weiß")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #00d4ff;")
        layout.addWidget(title)

        subtitle = QLabel("Diese Informationen helfen Moruk OS dir besser zu helfen.")
        subtitle.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(subtitle)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        inner = QVBoxLayout(container)
        inner.setSpacing(12)

        # ── Basis Profil ──
        profile_group = QGroupBox("📋 Basis Profil")
        pg_layout = QVBoxLayout(profile_group)

        pg_layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit(self.profile.get("name", ""))
        self.name_edit.setPlaceholderText("Dein Name...")
        pg_layout.addWidget(self.name_edit)

        pg_layout.addWidget(QLabel("Job / Beruf:"))
        self.job_edit = QLineEdit(self.profile.get("job", ""))
        self.job_edit.setPlaceholderText("Dein Beruf...")
        pg_layout.addWidget(self.job_edit)

        pg_layout.addWidget(QLabel("Über mich:"))
        self.bio_edit = QTextEdit()
        self.bio_edit.setPlainText(self.profile.get("bio", ""))
        self.bio_edit.setPlaceholderText("Kurze Beschreibung...")
        self.bio_edit.setMaximumHeight(80)
        pg_layout.addWidget(self.bio_edit)

        inner.addWidget(profile_group)

        # ── Preferences (was Moruk sich gemerkt hat) ──
        prefs = self.profile.get("preferences", [])
        pref_group = QGroupBox(f"🧠 Was Moruk sich gemerkt hat ({len(prefs)} Einträge)")
        pref_layout = QVBoxLayout(pref_group)

        if not prefs:
            empty = QLabel("Noch nichts gespeichert.\nSag z.B.: 'Merke dir: Mein Lieblingsessen ist Pizza'")
            empty.setStyleSheet("color: #666; font-size: 12px;")
            empty.setWordWrap(True)
            pref_layout.addWidget(empty)
        else:
            for i, pref in enumerate(prefs):
                row = QHBoxLayout()
                label = QLabel(f"• {pref}")
                label.setWordWrap(True)
                label.setStyleSheet("color: #c0c0c0; font-size: 12px;")
                row.addWidget(label, stretch=1)

                del_btn = QPushButton("✕")
                del_btn.setObjectName("delete_btn")
                del_btn.setFixedSize(28, 28)
                del_btn.clicked.connect(lambda checked, idx=i: self._delete_pref(idx))
                row.addWidget(del_btn)

                pref_layout.addLayout(row)

                if i < len(prefs) - 1:
                    line = QFrame()
                    line.setFrameShape(QFrame.Shape.HLine)
                    line.setStyleSheet("color: #222;")
                    pref_layout.addWidget(line)

        inner.addWidget(pref_group)
        inner.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Buttons
        btn_row = QHBoxLayout()

        clear_btn = QPushButton("🗑 Alle Preferences löschen")
        clear_btn.setObjectName("delete_btn")
        clear_btn.clicked.connect(self._clear_all_prefs)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Speichern")
        save_btn.setObjectName("save_btn")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _delete_pref(self, idx: int):
        prefs = self.profile.get("preferences", [])
        if 0 <= idx < len(prefs):
            prefs.pop(idx)
            self.profile["preferences"] = prefs
            self._save_profile()
            self._refresh()

    def _clear_all_prefs(self):
        reply = QMessageBox.question(self, "Bestätigen",
            "Alle gemerkten Preferences löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.profile["preferences"] = []
            self._save_profile()
            self._refresh()

    def _on_save(self):
        self._save_profile()
        self.accept()

    def _refresh(self):
        """Dialog neu aufbauen nach Änderungen."""
        for i in reversed(range(self.layout().count())):
            item = self.layout().itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self._build_ui()
