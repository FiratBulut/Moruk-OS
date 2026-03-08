"""
Moruk AI OS - Settings Dialog v3
5 Model Slots: Small Model, DeepThink, Vision, Voice, Video.
Jeder Slot = Button → Pop-up mit API Key, Base URL, Model Name.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QSlider, QMessageBox, QTextEdit,
    QScrollArea, QWidget, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import copy

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# ═══════════════════════════════════════════════
# SLOT CONFIG DIALOG (Pop-up für jeden Slot)
# ═══════════════════════════════════════════════

class SlotConfigDialog(QDialog):
    """Pop-up Dialog für einen einzelnen Model-Slot."""

    def __init__(self, slot_name: str, slot_icon: str, slot_data: dict, parent=None):
        super().__init__(parent)
        self.slot_name = slot_name
        self.slot_data = copy.deepcopy(slot_data)
        self.setWindowTitle(f"{slot_icon} {slot_name} — Configuration")
        self.setMinimumWidth(520)
        self.setMinimumHeight(380)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel(f"Configure {self.slot_name}")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #e94560;")
        layout.addWidget(title)

        desc = QLabel(self._get_description())
        desc.setStyleSheet("color: #888; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # API Key
        layout.addWidget(QLabel("API Key:"))
        key_row = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-... or key...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(self.api_key_input)
        show_btn = QPushButton("👁")
        show_btn.setFixedWidth(36)
        show_btn.setStyleSheet("background-color: #2a2a4a; padding: 6px;")
        show_btn.clicked.connect(lambda: self.api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        ))
        key_row.addWidget(show_btn)
        layout.addLayout(key_row)

        # Base URL
        layout.addWidget(QLabel("Base URL (optional):"))
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.openai.com/v1 (leer = Standard)")
        layout.addWidget(self.base_url_input)

        # Model Name
        layout.addWidget(QLabel("Model Name:"))
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText(self._get_placeholder())
        layout.addWidget(self.model_input)

        # Extra Felder für Voice Slot
        if self.slot_name == "Voice":
            # Provider Dropdown
            layout.addWidget(QLabel("TTS Provider:"))
            from PyQt6.QtWidgets import QComboBox
            self.provider_combo = QComboBox()
            self.provider_combo.addItems(["auto", "piper", "google", "elevenlabs", "openai"])
            self.provider_combo.setToolTip("auto = wird aus Model/Key erkannt")
            layout.addWidget(self.provider_combo)

            # Language
            layout.addWidget(QLabel("Language (z.B. de-DE, en-US):"))
            self.language_input = QLineEdit()
            self.language_input.setPlaceholderText("de-DE")
            layout.addWidget(self.language_input)

            # Voice Name
            layout.addWidget(QLabel("Voice Name (optional):"))
            self.voice_name_input = QLineEdit()
            self.voice_name_input.setPlaceholderText("de-DE-Wavenet-B, onyx, Adam...")
            layout.addWidget(self.voice_name_input)
        else:
            self.provider_combo = None
            self.language_input = None
            self.voice_name_input = None

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()

        clear_btn = QPushButton("🗑 Clear")
        clear_btn.setStyleSheet("background-color: #661020; padding: 8px 16px;")
        clear_btn.clicked.connect(self._clear)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: #333; padding: 8px 16px;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet("background-color: #0f3460; padding: 8px 16px; font-weight: bold;")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _get_description(self) -> str:
        descs = {
            "Small Model": "Haupt-Brain für alltägliche Tasks. Schnell und günstig.",
            "DeepThink": "Supervisor-Model für Validierung und komplexes Denken.",
            "Vision": "Bild-Erkennung und -Analyse (z.B. GPT-4V, Claude Vision).",
            "Voice": "Sprach-zu-Text und Text-zu-Sprache API.",
            "Video": "Video-Generierung und -Analyse (z.B. Sora, Runway).",
        }
        return descs.get(self.slot_name, "")

    def _get_placeholder(self) -> str:
        placeholders = {
            "Small Model": "claude-3-5-haiku-20241022, gpt-4o-mini, llama3...",
            "DeepThink": "claude-sonnet-4-20250514, gpt-4, o1-preview...",
            "Vision": "claude-sonnet-4-20250514, gpt-4o...",
            "Voice": "whisper-1, tts-1, eleven_multilingual_v2... (optional bei Google)",
            "Video": "sora, runway-gen3...",
        }
        return placeholders.get(self.slot_name, "model-name")

    def _populate(self):
        self.api_key_input.setText(self.slot_data.get("api_key", ""))
        self.base_url_input.setText(self.slot_data.get("base_url", ""))
        self.model_input.setText(self.slot_data.get("model", ""))
        if self.slot_name == "Voice":
            provider = self.slot_data.get("tts_provider", "auto")
            idx = self.provider_combo.findText(provider)
            self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.language_input.setText(self.slot_data.get("language", "de-DE"))
            self.voice_name_input.setText(self.slot_data.get("voice_name", ""))

    def _clear(self):
        self.api_key_input.clear()
        self.base_url_input.clear()
        self.model_input.clear()
        if self.slot_name == "Voice":
            self.provider_combo.setCurrentIndex(0)
            self.language_input.clear()
            self.voice_name_input.clear()

    def _save(self):
        self.slot_data = {
            "api_key": self.api_key_input.text().strip(),
            "base_url": self.base_url_input.text().strip(),
            "model": self.model_input.text().strip(),
        }
        if self.slot_name == "Voice":
            self.slot_data["tts_provider"] = self.provider_combo.currentText()
            self.slot_data["language"] = self.language_input.text().strip() or "de-DE"
            self.slot_data["voice_name"] = self.voice_name_input.text().strip()
        self.accept()

    def get_data(self) -> dict:
        return self.slot_data




# ═══════════════════════════════════════════════
# USER PROFILE DIALOG
# ═══════════════════════════════════════════════

class UserProfileDialog(QDialog):
    """Zeigt und bearbeitet was Moruk über den User gelernt hat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("👤 User Profile — What Moruk knows about you")
        self.setMinimumSize(560, 620)
        self.setModal(True)

        try:
            from core.user_profile import UserProfileEngine
            self.engine = UserProfileEngine()
        except Exception as e:
            self.engine = None

        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        # Header
        header = QLabel("👤 User Profile")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;")
        layout.addWidget(header)

        sub = QLabel("What Moruk has learned about you — and what you can tell him directly.")
        sub.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # ── Direkte Eingabe ──────────────────────────────────
        input_group = QGroupBox("✏️  Tell Moruk about yourself")
        input_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; color: #e94560;
                border: 1px solid rgba(233,69,96,0.3);
                border-radius: 6px; margin-top: 8px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        """)
        input_layout = QVBoxLayout(input_group)

        hint = QLabel(
            "Write anything: name, job, preferences, language, topics you care about…\n"
            "Example: Ich heiße Firat. Ich spreche Deutsch. Ich arbeite als Software-Entwickler."
        )
        hint.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px; font-style: italic;")
        hint.setWordWrap(True)
        input_layout.addWidget(hint)

        self.user_input = QTextEdit()
        self.user_input.setPlaceholderText(
            "Ich heiße … / My name is …\n"
            "Ich arbeite als … / I work as …\n"
            "Ich bevorzuge … / I prefer …\n"
            "Antworte immer auf Deutsch / Always respond in English\n"
            "Ich mag kurze Antworten / I like detailed explanations"
        )
        self.user_input.setMaximumHeight(130)
        self.user_input.setStyleSheet("""
            QTextEdit {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px;
                padding: 8px;
                color: white;
                font-size: 13px;
            }
            QTextEdit:focus { border-color: #e94560; }
        """)
        input_layout.addWidget(self.user_input)

        save_input_btn = QPushButton("💾  Save & Apply to Profile")
        save_input_btn.setStyleSheet("""
            QPushButton {
                background-color: #e94560; color: white;
                border: none; border-radius: 6px;
                padding: 8px 16px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #ff6080; }
        """)
        save_input_btn.clicked.connect(self._save_user_input)
        input_layout.addWidget(save_input_btn)

        layout.addWidget(input_group)

        # ── Gelernte Daten ───────────────────────────────────
        learned_group = QGroupBox("🧠  What Moruk learned automatically")
        learned_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; color: rgba(255,255,255,0.7);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px; margin-top: 8px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        """)
        learned_layout = QVBoxLayout(learned_group)

        self.profile_display = QTextEdit()
        self.profile_display.setReadOnly(True)
        self.profile_display.setMinimumHeight(180)
        self.profile_display.setStyleSheet("""
            QTextEdit {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.07);
                border-radius: 6px; padding: 8px;
                color: rgba(255,255,255,0.75);
                font-family: 'JetBrains Mono', monospace;
                font-size: 11px;
            }
        """)
        learned_layout.addWidget(self.profile_display)
        layout.addWidget(learned_group)

        # ── Buttons ──────────────────────────────────────────
        btn_row = QHBoxLayout()

        reset_btn = QPushButton("🗑  Reset Profile")
        reset_btn.setStyleSheet("""
            QPushButton {
                background: rgba(233,69,96,0.12); color: #e94560;
                border: 1px solid rgba(233,69,96,0.3); border-radius: 6px; padding: 7px 14px;
            }
            QPushButton:hover { background: rgba(233,69,96,0.25); }
        """)
        reset_btn.clicked.connect(self._reset_profile)
        btn_row.addWidget(reset_btn)

        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08); color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px; padding: 7px 20px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.15); }
        """)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _load(self):
        """Lädt Profil-Daten in die Anzeige."""
        if not self.engine:
            self.profile_display.setPlainText("UserProfileEngine not available.")
            return

        p = self.engine.profile
        sessions = p.get("sessions_analyzed", 0)

        # Gelernte Preferences ins Input-Feld laden (als Referenz)
        # Preferences aus user_profile.json lesen
        import json
        from pathlib import Path
        profile_path = Path(__file__).parent.parent / "data" / "user_profile.json"
        try:
            with open(profile_path) as f:
                up = json.load(f)
            prefs_from_profile = up.get("preferences", [])
        except Exception:
            prefs_from_profile = []
        prefs = p.get("explicit_preferences", []) + prefs_from_profile
        manual = p.get("manual_notes", "")
        if manual:
            self.user_input.setPlainText(manual)

        if sessions == 0 and not prefs:
            self.profile_display.setPlainText(
                "No learned data yet.\n\n"
                "Moruk learns automatically after each conversation.\n"
                "You can also write above to tell him directly."
            )
            return
        if prefs and sessions == 0:
            self.profile_display.setPlainText("\n".join(f"• {x}" for x in prefs))
            return

        lines = []
        lines.append(f"Sessions: {sessions}  |  Messages: {p.get('total_messages', 0)}")
        lines.append(f"Last updated: {p.get('updated_at', '')[:16]}")
        lines.append("")

        lang = p.get("language", {})
        lines.append(f"Language: {lang.get('primary','?')}  |  "
                     f"Style: {lang.get('formality','neutral')}  |  "
                     f"Length: {lang.get('response_length','medium')}")
        lines.append("")

        domains = p.get("domains", [])
        if domains:
            lines.append(f"Domains:  {', '.join(domains)}")

        dist = p.get("task_distribution", {})
        if dist:
            lines.append("")
            lines.append("Task distribution:")
            for task, count in sorted(dist.items(), key=lambda x: x[1], reverse=True)[:6]:
                bar = "█" * min(count, 20)
                lines.append(f"  {task:<14} {bar} ({count})")

        wf = p.get("workflow", {})
        wf_active = [k.replace("prefers_","") for k, v in wf.items() if v]
        if wf_active:
            lines.append("")
            lines.append(f"Workflow:  {', '.join(wf_active)}")

        if prefs:
            lines.append("")
            lines.append("Learned preferences:")
            for pref in prefs[:10]:
                lines.append(f"  • {pref}")

        topics = p.get("frequent_topics", {})
        if topics:
            top = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:12]
            lines.append("")
            lines.append("Frequent topics:  " + ", ".join(w for w, _ in top))

        hours = p.get("activity_hours", {})
        if hours:
            peak = sorted(hours.items(), key=lambda x: x[1], reverse=True)[:3]
            lines.append("")
            lines.append("Active hours:  " + ", ".join(f"{h}:00" for h, _ in peak))

        self.profile_display.setPlainText("\n".join(lines))

    def _save_user_input(self):
        """Speichert manuelle Eingabe ins Profil."""
        if not self.engine:
            return

        text = self.user_input.toPlainText().strip()
        if not text:
            return

        # Manuellen Text als Notiz speichern
        self.engine.profile["manual_notes"] = text

        # Text als synthetische Session analysieren
        # → einfach in explicit_preferences einfügen
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        existing = self.engine.profile.get("explicit_preferences", [])
        for line in lines:
            if line not in existing:
                existing.append(line)
        self.engine.profile["explicit_preferences"] = existing[-20:]

        # Name erkennen
        import re
        name_match = re.search(
            r"(?:ich hei[sße]e|my name is|ich bin)\s+([A-ZÄÖÜa-zäöü]+)",
            text, re.IGNORECASE
        )
        if name_match:
            name = name_match.group(1).capitalize()
            self.engine.profile.setdefault("user_name", name)

        # Sprache aus manuellem Text erkennen
        de_words = ["ich", "heiße", "heisse", "bin", "arbeite", "spreche", "mag"]
        en_words = ["my", "name", "i am", "i work", "i like", "i prefer"]
        text_lower = text.lower()
        if any(w in text_lower for w in de_words):
            self.engine.profile["language"]["primary"] = "de"
        elif any(w in text_lower for w in en_words):
            self.engine.profile["language"]["primary"] = "en"

        self.engine.save()
        self._load()

        QMessageBox.information(self, "✅ Saved",
            "Profile updated! Moruk will use this in future conversations.")

    def _reset_profile(self):
        reply = QMessageBox.question(
            self, "Reset Profile",
            "Delete everything Moruk learned about you?\nYour manual notes will also be cleared.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from pathlib import Path
                p = Path.home() / "moruk-os" / "data" / "user_profile.json"
                if p.exists():
                    p.unlink()
                if self.engine:
                    from core.user_profile import UserProfileEngine
                    self.engine = UserProfileEngine()
                self.user_input.clear()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))


# ═══════════════════════════════════════════════
# MAIN SETTINGS DIALOG
# ═══════════════════════════════════════════════

class SettingsDialog(QDialog):
    """Settings Dialog v3 mit 5 Model-Slots."""

    SLOTS = [
        ("Small Model", "🤖", "small"),
        ("DeepThink", "🧠", "deepthink"),
        ("Vision", "👁", "vision"),
        ("Voice", "🎤", "voice"),
        ("Video", "🎬", "video"),
    ]

    def __init__(self, settings: dict, parent=None, save_fn=None):
        super().__init__(parent)
        self.settings = copy.deepcopy(settings)
        self._save_fn = save_fn  # optional immediate-save callback
        self.setWindowTitle("⚙ Moruk OS — Brain Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(520)
        self.slot_buttons = {}
        self.slot_status = {}
        self._build_ui()
        self._update_slot_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel("⚙ Brain Configuration")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #e94560;")
        layout.addWidget(title)

        subtitle = QLabel("Klicke auf einen Slot um ihn zu konfigurieren.")
        subtitle.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(subtitle)

        # ═══ Model Slots ═══
        slots_group = QGroupBox("Model Slots")
        slots_layout = QVBoxLayout()
        slots_layout.setSpacing(8)

        for display_name, icon, key in self.SLOTS:
            row = QHBoxLayout()

            # Slot Button
            btn = QPushButton(f"  {icon}  {display_name}")
            btn.setFixedHeight(48)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a1a3e;
                    border: 1px solid #333;
                    border-radius: 8px;
                    text-align: left;
                    padding-left: 16px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #e0e0e0;
                }
                QPushButton:hover {
                    background-color: #2a2a5e;
                    border-color: #e94560;
                }
            """)
            btn.clicked.connect(lambda checked, k=key, n=display_name, i=icon: self._open_slot(k, n, i))
            row.addWidget(btn, stretch=3)

            # Status Label
            status = QLabel("⚫ Not configured")
            status.setFixedWidth(160)
            status.setStyleSheet("color: #666; font-size: 11px;")
            row.addWidget(status, stretch=1)

            self.slot_buttons[key] = btn
            self.slot_status[key] = status

            slots_layout.addLayout(row)

        slots_group.setLayout(slots_layout)
        layout.addWidget(slots_group)

        # ═══ Advanced ═══
        adv_group = QGroupBox("Advanced")
        ag_layout = QVBoxLayout()

        # Provider (für Kompatibilität)
        prov_row = QHBoxLayout()
        prov_row.addWidget(QLabel("Provider Format:"))
        self.provider_label = QLabel("auto-detect")
        self.provider_label.setStyleSheet("color: #e94560; font-weight: bold;")
        prov_row.addWidget(self.provider_label)
        prov_row.addStretch()
        ag_layout.addLayout(prov_row)

        # Temperature
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(QLabel("Temperature:"))
        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_slider.setValue(70)
        self.temp_value_label = QLabel("0.70")
        self.temp_value_label.setStyleSheet("color: #e94560; font-weight: bold;")
        self.temp_slider.valueChanged.connect(
            lambda v: self.temp_value_label.setText(f"{v / 100:.2f}")
        )
        temp_layout.addWidget(self.temp_slider)
        temp_layout.addWidget(self.temp_value_label)
        ag_layout.addLayout(temp_layout)

        # Max Tokens
        tokens_layout = QHBoxLayout()
        tokens_layout.addWidget(QLabel("Max Tokens:"))
        self.tokens_input = QLineEdit("4096")
        self.tokens_input.setFixedWidth(100)
        tokens_layout.addWidget(self.tokens_input)
        tokens_layout.addStretch()
        ag_layout.addLayout(tokens_layout)

        adv_group.setLayout(ag_layout)
        layout.addWidget(adv_group)

        layout.addStretch()

        # ═══ Buttons ═══
        btn_layout = QHBoxLayout()

        test_btn = QPushButton("🧪 Test Connection")
        test_btn.setStyleSheet("background-color: #0f3460; padding: 8px 16px;")
        test_btn.clicked.connect(self._test_connection)
        btn_layout.addWidget(test_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: #333; padding: 8px 16px;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        reset_btn = QPushButton("🗑 Factory Reset")
        reset_btn.setToolTip("Löscht Memory, Goals, Tasks, Reflection, Sessions — API Keys bleiben")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a0a0a;
                color: #e94560;
                border: 1px solid #4a1a1a;
                padding: 8px 14px;
                font-size: 11px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #4a1a1a; border-color: #e94560; }
        """)
        reset_btn.clicked.connect(self._factory_reset)
        btn_layout.addWidget(reset_btn)

        profile_btn = QPushButton("👤 User Profile")
        profile_btn.setToolTip("Was Moruk über dich weiß — und direkt bearbeiten")
        profile_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.07); color: rgba(255,255,255,0.8);
                border: 1px solid rgba(255,255,255,0.15); border-radius: 4px; padding: 8px 14px;
                font-size: 11px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.14); }
        """)
        profile_btn.clicked.connect(self._open_profile_dialog)
        btn_layout.addWidget(profile_btn)

        save_btn = QPushButton("💾 Save All")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #e94560;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _open_profile_dialog(self):
        dlg = UserProfileDialog(parent=self)
        dlg.exec()

    # ── Factory Reset ─────────────────────────────────────────

    def _factory_reset(self):
        """Löscht alle gelernten Daten — frischer Start wie nach Neuinstallation."""
        from PyQt6.QtWidgets import QMessageBox
        from pathlib import Path
        import shutil

        msg = "\n".join([
            "FACTORY RESET",
            "",
            "Folgendes wird GELOESCHT:",
            "  - Vector Memory (memory.db)",
            "  - Conversation History",
            "  - Short-Term Memory",
            "  - Goals, Tasks",
            "  - Reflection Log + Strategy Rules",
            "  - Self-Profile",
            "  - Sessions",
            "  - Codebase Index",
            "",
            "Folgendes bleibt ERHALTEN:",
            "  - API Keys und Settings",
            "  - Alle .py Dateien",
            "  - Plugins",
            "  - Recovery Snapshots",
            "",
            "Moruk OS muss danach neu gestartet werden.",
            "Wirklich fortfahren?",
        ])

        reply = QMessageBox.warning(self, "Factory Reset",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Zweite Bestätigung
        confirm = QMessageBox.question(self, "Sicher?",
            "Letzter Check: Alle gelernten Daten unwiderruflich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if confirm != QMessageBox.StandardButton.Yes:
            return

        project_root = Path(__file__).parent.parent
        data_dir = project_root / "data"
        deleted = []
        errors = []

        # Dateien löschen
        delete_files = [
            data_dir / "memory.db",
            data_dir / "memory_short.json",
            data_dir / "conversation.json",
            data_dir / "goals.json",
            data_dir / "tasks.json",
            data_dir / "tasks.json.bak",
            data_dir / "reflection_log.json",
            data_dir / "reflection_stats.json",
            data_dir / "strategy_rules.json",
            data_dir / "self_profile.json",
            data_dir / "codebase_index.json",
            data_dir / "history.json",
        ]

        for f in delete_files:
            if f.exists():
                try:
                    f.unlink()
                    deleted.append(f.name)
                except Exception as e:
                    errors.append(f"{f.name}: {e}")

        # Sessions Ordner leeren
        sessions_dir = data_dir / "sessions"
        if sessions_dir.exists():
            try:
                shutil.rmtree(str(sessions_dir))
                sessions_dir.mkdir(exist_ok=True)
                deleted.append("sessions/")
            except Exception as e:
                errors.append(f"sessions/: {e}")

        lines_out = [f"Factory Reset abgeschlossen!", f"", f"Geloescht ({len(deleted)}):"]
        lines_out += [f"  - {f}" for f in deleted]
        if errors:
            lines_out += ["", "Fehler:"] + [f"  - {e}" for e in errors]
        lines_out += ["", "Bitte Moruk OS neu starten!"]
        result = "\n".join(lines_out)

        QMessageBox.information(self, "✅ Factory Reset", result)

    # ── Slot Management ───────────────────────────────────────

    def _get_slot_data(self, key: str) -> dict:
        """Holt Slot-Daten aus Settings."""
        if key == "small":
            return {
                "api_key": self.settings.get("api_key", ""),
                "base_url": self.settings.get("active_model_config", {}).get("base_url", ""),
                "model": self.settings.get("model", ""),
            }
        elif key == "voice":
            return {
                "api_key":     self.settings.get("tts_api_key", "") or self.settings.get("voice_api_key", ""),
                "base_url":    self.settings.get("voice_base_url", ""),
                "model":       self.settings.get("tts_model", "") or self.settings.get("voice_model", ""),
                "tts_provider": self.settings.get("tts_provider", "auto"),
                "language":    self.settings.get("tts_language", "de-DE"),
                "voice_name":  self.settings.get("tts_voice", ""),
            }
        elif key == "video":
            return {
                "api_key": self.settings.get("video_api_key", ""),
                "base_url": self.settings.get("video_base_url", ""),
                "model":    self.settings.get("video_model", ""),
                "video_provider": self.settings.get("video_provider", "fal"),
            }
        else:
            prefix = f"{key}_"
            return {
                "api_key": self.settings.get(f"{prefix}api_key", ""),
                "base_url": self.settings.get(f"{prefix}base_url", ""),
                "model": self.settings.get(f"{prefix}model", ""),
            }

    def _set_slot_data(self, key: str, data: dict):
        """Speichert Slot-Daten in Settings."""
        if key == "small":
            self.settings["api_key"] = data.get("api_key", "")
            self.settings["model"] = data.get("model", "")
            # Provider auto-detect
            api_key = data.get("api_key", "")
            base_url = data.get("base_url", "")
            if base_url:
                if "localhost" in base_url or "11434" in base_url:
                    self.settings["provider"] = "ollama"
                else:
                    self.settings["provider"] = "custom"
            elif api_key.startswith("sk-ant-"):
                self.settings["provider"] = "anthropic"
            elif api_key.startswith("sk-"):
                self.settings["provider"] = "openai"
            else:
                self.settings["provider"] = "custom"

            # Model config updaten
            if "active_model_config" not in self.settings:
                self.settings["active_model_config"] = {}
            self.settings["active_model_config"]["name"] = data.get("model", "")
            self.settings["active_model_config"]["base_url"] = data.get("base_url", "")
            self.settings["active_model_config"]["api_key"] = data.get("api_key", "")

            # Providers dict updaten für Kompatibilität
            provider = self.settings["provider"]
            if "providers" not in self.settings:
                self.settings["providers"] = {}
            if provider not in self.settings["providers"]:
                self.settings["providers"][provider] = {"name": provider.title()}
            self.settings["providers"][provider]["api_key"] = data.get("api_key", "")
            self.settings["providers"][provider]["base_url"] = data.get("base_url", "")

        elif key == "voice":
            api_key  = data.get("api_key", "")
            model    = data.get("model", "")
            base_url = data.get("base_url", "")
            provider = data.get("tts_provider", "auto")

            # Auto-detect wenn "auto" gewählt
            if provider == "auto":
                if not api_key:
                    provider = "piper"
                elif "generativelanguage" in base_url or "AIza" in api_key:
                    provider = "google"
                elif "elevenlabs" in base_url or "elevenlabs" in model.lower():
                    provider = "elevenlabs"
                elif model in ("tts-1", "tts-1-hd") or "openai" in base_url:
                    provider = "openai"
                elif api_key.startswith("sk-"):
                    provider = "openai"
                else:
                    provider = "google"  # Google API Keys haben kein Standard-Prefix

            # tts_* Felder schreiben — das liest voice.py
            self.settings["tts_provider"] = provider
            self.settings["tts_api_key"]  = api_key
            self.settings["tts_model"]    = model
            self.settings["tts_language"] = data.get("language", "de-DE")
            self.settings["tts_voice"]    = data.get("voice_name", "")
            # Auch alte voice_* Felder schreiben für Kompatibilität
            self.settings["voice_api_key"]  = api_key
            self.settings["voice_base_url"] = base_url
            self.settings["voice_model"]    = model

        elif key == "video":
            api_key = data.get("api_key", "")
            model   = data.get("model", "")
            # Auto-detect provider
            provider = data.get("video_provider", "fal")
            if provider == "auto" or not provider:
                if "veo" in model.lower():
                    provider = "fal"   # Veo via fal.ai
                elif "sora" in model.lower() or api_key.startswith("sk-"):
                    provider = "openai"
                else:
                    provider = "fal"   # Default
            self.settings["video_provider"] = provider
            self.settings["video_api_key"]  = api_key
            self.settings["video_model"]    = model
            self.settings["video_base_url"] = data.get("base_url", "")

        else:
            prefix = f"{key}_"
            self.settings[f"{prefix}api_key"] = data.get("api_key", "")
            self.settings[f"{prefix}base_url"] = data.get("base_url", "")
            self.settings[f"{prefix}model"] = data.get("model", "")

            # Provider auto-detect für DeepThink
            if key == "deepthink":
                api_key = data.get("api_key", "")
                base_url = data.get("base_url", "")
                if base_url and ("localhost" in base_url or "11434" in base_url):
                    self.settings["deepthink_provider"] = "ollama"
                elif api_key.startswith("sk-ant-"):
                    self.settings["deepthink_provider"] = "anthropic"
                elif api_key.startswith("sk-"):
                    self.settings["deepthink_provider"] = "openai"
                elif base_url:
                    self.settings["deepthink_provider"] = "custom"

    def _open_slot(self, key: str, display_name: str, icon: str):
        """Öffnet den Slot-Config Dialog."""
        data = self._get_slot_data(key)
        dialog = SlotConfigDialog(display_name, icon, data, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data()
            self._set_slot_data(key, new_data)
            self._update_slot_status()
            # Auto-save immediately so key takes effect without needing "Save All"
            if self._save_fn:
                self._save_fn(self.settings)

    def _update_slot_status(self):
        """Aktualisiert die Status-Labels aller Slots."""
        for display_name, icon, key in self.SLOTS:
            data = self._get_slot_data(key)
            status_label = self.slot_status[key]
            btn = self.slot_buttons[key]

            has_key = bool(data.get("api_key"))
            has_model = bool(data.get("model"))
            provider = data.get("tts_provider", "auto") if key == "voice" else None

            # Voice: kein Model nötig bei Google/piper
            voice_ok = (key == "voice" and (
                not has_key  # piper — kein Key nötig
                or has_key   # API Key reicht für Google/ElevenLabs
            ))

            if (has_key and has_model) or voice_ok:
                label_txt = data.get("model") or data.get("voice_name") or provider or "piper"
                model_short = label_txt[:25]
                status_label.setText(f"🟢 {model_short}")
                status_label.setStyleSheet("color: #4ecca3; font-size: 11px;")
                btn.setProperty("configured", True)
            elif has_key or has_model:
                status_label.setText("🟡 Incomplete")
                status_label.setStyleSheet("color: #f0a500; font-size: 11px;")
                btn.setProperty("configured", False)
            else:
                status_label.setText("⚫ Not configured")
                status_label.setStyleSheet("color: #666; font-size: 11px;")
                btn.setProperty("configured", False)

            # Style neu anwenden damit Qt das Property erkennt
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # Provider label updaten
        provider = self.settings.get("provider", "auto")
        self.provider_label.setText(provider)

        # Temperature + Tokens
        temp = self.settings.get("temperature", 0.7)
        self.temp_slider.setValue(int(temp * 100))
        self.tokens_input.setText(str(self.settings.get("max_tokens", 4096)))

    # ── Test Connection ───────────────────────────────────────

    def _test_connection(self):
        """Testet alle konfigurierten Slots."""
        results = []

        for display_name, icon, key in self.SLOTS:
            data = self._get_slot_data(key)

            # Voice: eigener Test — nicht über OpenAI Client
            if key == "voice":
                provider = data.get("tts_provider", "auto")
                api_key = data.get("api_key", "")
                if not api_key and provider in ("auto", "piper"):
                    results.append(f"  {icon} {display_name}: ✅ Piper (lokal)")
                elif api_key:
                    results.append(f"  {icon} {display_name}: ✅ {provider} — Key gesetzt")
                else:
                    results.append(f"  {icon} {display_name}: ⚫ Nicht konfiguriert")
                continue

            if not data.get("api_key") or not data.get("model"):
                continue

            api_key = data["api_key"]
            base_url = data.get("base_url", "")
            model = data["model"]

            try:
                # Vision mit Google API Key → nativen Gemini Endpunkt testen
                if key == "vision" and (api_key.startswith("AIza") or "generativelanguage" in base_url):
                    import requests as _req
                    needs_alpha = any(x in model.lower() for x in ["gemini-3-pro-image", "gemini-3.1-flash-image", "gemini-3-flash-image"])
                    api_ver = "v1alpha" if needs_alpha else "v1beta"
                    test_url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model}:generateContent?key={api_key}"
                    resp = _req.post(test_url, json={
                        "contents": [{"parts": [{"text": "Hi"}]}]
                    }, timeout=30)
                    if resp.status_code in (200, 400):  # 400 kann OK sein (Modell existiert aber kein Image-Prompt)
                        data = resp.json()
                        # 400 mit INVALID_ARGUMENT = Key ok aber falscher Request → Key ist gültig!
                        if resp.status_code == 200 or (resp.status_code == 400 and "INVALID_ARGUMENT" in str(data)):
                            results.append(f"  {icon} {display_name}: ✅ {model} (Gemini API)")
                        else:
                            err = data.get("error", {}).get("message", str(data))[:80]
                            results.append(f"  {icon} {display_name}: ❌ Error code: {resp.status_code} - {err}")
                    else:
                        err = resp.json().get("error", {}).get("message", "Unknown")[:80]
                        results.append(f"  {icon} {display_name}: ❌ Error code: {resp.status_code} - {err}")

                elif api_key.startswith("sk-ant-"):
                    if Anthropic is None:
                        results.append(f"  {icon} {display_name}: ❌ anthropic package not installed")
                        continue
                    client = Anthropic(api_key=api_key)
                    client.messages.create(
                        model=model, max_tokens=10,
                        messages=[{"role": "user", "content": "Hi"}]
                    )
                    results.append(f"  {icon} {display_name}: ✅ {model}")
                else:
                    if OpenAI is None:
                        results.append(f"  {icon} {display_name}: ❌ openai package not installed")
                        continue
                    if base_url:
                        client = OpenAI(base_url=base_url, api_key=api_key)
                    else:
                        client = OpenAI(api_key=api_key)
                    client.chat.completions.create(
                        model=model, max_tokens=10,
                        messages=[{"role": "user", "content": "Hi"}]
                    )
                    results.append(f"  {icon} {display_name}: ✅ {model}")

            except Exception as e:
                err = str(e)[:80]
                results.append(f"  {icon} {display_name}: ❌ {err}")

        if not results:
            QMessageBox.warning(self, "Test", "Kein Slot konfiguriert.\nKlicke auf einen Slot und gib API Key + Model ein.")
            return

        QMessageBox.information(self, "🧪 Connection Test",
            "Test Results:\n\n" + "\n".join(results))

    # ── Save ──────────────────────────────────────────────────

    def _apply_advanced(self, settings: dict):
        """Advanced Settings anwenden."""
        settings["temperature"] = self.temp_slider.value() / 100
        try:
            settings["max_tokens"] = int(self.tokens_input.text())
        except ValueError:
            settings["max_tokens"] = 4096

    def _save(self):
        """Speichert alle Settings."""
        # Small Model muss konfiguriert sein
        small_data = self._get_slot_data("small")
        if not small_data.get("api_key") and not small_data.get("model"):
            reply = QMessageBox.question(self, "Warnung",
                "Small Model ist nicht konfiguriert.\nMoruk kann ohne Model nicht funktionieren.\n\nTrotzdem speichern?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return

        self._apply_advanced(self.settings)
        self.accept()

    def get_settings(self) -> dict:
        return self.settings
