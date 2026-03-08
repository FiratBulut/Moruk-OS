"""
Moruk OS — First-Run Onboarding Wizard
3 Schritte: Willkommen → Profil → API Keys → Systemcheck
"""

import json
import os
import subprocess
import platform
import psutil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QStackedWidget, QWidget, QProgressBar,
    QComboBox, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
USER_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "user_profile.json")


# ── System Check Worker ───────────────────────────────────────────────────────

class SystemCheckWorker(QThread):
    result = pyqtSignal(str, bool)  # message, success
    done   = pyqtSignal(dict)

    def run(self):
        info = {}

        checks = [
            ("Python Version", self._check_python),
            ("PyQt6", self._check_pyqt),
            ("Internet Connection", self._check_internet),
            ("RAM", self._check_ram),
            ("Disk Space", self._check_disk),
            ("Display (X11/Wayland)", self._check_display),
            ("espeak-ng (TTS)", self._check_espeak),
            ("GPU / Grafik", self._check_gpu),
        ]

        for name, fn in checks:
            try:
                ok, detail = fn()
                info[name] = {"ok": ok, "detail": detail}
                self.result.emit(f"{name}: {detail}", ok)
            except Exception as e:
                info[name] = {"ok": False, "detail": str(e)}
                self.result.emit(f"{name}: Fehler — {e}", False)

        self.done.emit(info)

    def _check_python(self):
        v = platform.python_version()
        major, minor = int(v.split(".")[0]), int(v.split(".")[1])
        ok = major >= 3 and minor >= 10
        return ok, f"Python {v}"

    def _check_pyqt(self):
        try:
            from PyQt6.QtCore import QT_VERSION_STR
            return True, f"PyQt6 (Qt {QT_VERSION_STR})"
        except Exception:
            return False, "Nicht installiert"

    def _check_internet(self):
        try:
            import urllib.request
            urllib.request.urlopen("https://www.google.com", timeout=5)
            return True, "Online ✓"
        except Exception:
            return False, "Kein Internetzugang"

    def _check_ram(self):
        ram = psutil.virtual_memory()
        total_gb = ram.total / (1024**3)
        avail_gb = ram.available / (1024**3)
        ok = avail_gb >= 1.0
        return ok, f"{avail_gb:.1f} GB verfügbar / {total_gb:.1f} GB total"

    def _check_disk(self):
        disk = psutil.disk_usage(os.path.expanduser("~"))
        free_gb = disk.free / (1024**3)
        ok = free_gb >= 2.0
        return ok, f"{free_gb:.1f} GB frei"

    def _check_display(self):
        display = os.environ.get("DISPLAY", "") or os.environ.get("WAYLAND_DISPLAY", "")
        if display:
            return True, display
        return False, "Kein Display gefunden"

    def _check_espeak(self):
        try:
            result = subprocess.run(["espeak-ng", "--version"],
                                    capture_output=True, text=True, timeout=5)
            return result.returncode == 0, "Installiert ✓" if result.returncode == 0 else "Nicht gefunden"
        except Exception:
            return False, "Nicht installiert (optional)"

    def _check_gpu(self):
        # Versuche GPU Info zu lesen
        try:
            result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
            lines = [l for l in result.stdout.split("\n") if "VGA" in l or "3D" in l or "Display" in l]
            if lines:
                gpu = lines[0].split(":")[-1].strip()[:60]
                return True, gpu
        except Exception:
            pass
        return True, "Keine dedizierte GPU (CPU-Rendering)"


# ── Onboarding Dialog ─────────────────────────────────────────────────────────

class OnboardingDialog(QDialog):
    finished_signal = pyqtSignal(dict)  # settings dict wenn fertig

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Moruk OS — Setup")
        self.setFixedSize(660, 580)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.settings = {}
        self.system_info = {}
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Header
        self.header = QLabel()
        self.header.setFixedHeight(80)
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(self.header)

        # Stack
        self.stack = QStackedWidget()
        main.addWidget(self.stack)

        self.stack.addWidget(self._page_welcome())    # 0
        self.stack.addWidget(self._page_profile())    # 1
        self.stack.addWidget(self._page_syscheck())   # 2

        # Footer nav
        footer = QWidget()
        footer.setFixedHeight(64)
        footer.setObjectName("footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(24, 0, 24, 0)

        self.btn_back = QPushButton("← Zurück")
        self.btn_back.setObjectName("btnBack")
        self.btn_back.clicked.connect(self._go_back)
        self.btn_back.hide()

        self.step_label = QLabel("Schritt 1 von 3")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_label.setObjectName("stepLabel")

        self.btn_next = QPushButton("Weiter →")
        self.btn_next.setObjectName("btnNext")
        self.btn_next.clicked.connect(self._go_next)

        fl.addWidget(self.btn_back)
        fl.addStretch()
        fl.addWidget(self.step_label)
        fl.addStretch()
        fl.addWidget(self.btn_next)
        main.addWidget(footer)

        self._update_header(0)

    # ── Pages ─────────────────────────────────────────────────

    def _page_welcome(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.setSpacing(20)
        l.setContentsMargins(60, 40, 60, 40)

        logo = QLabel("🤖")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size: 72px;")

        title = QLabel("Willkommen bei Moruk OS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "Dein autonomes KI-Betriebssystem.\n\n"
            "Moruk OS denkt selbstständig, lernt aus Erfahrungen\n"
            "und erledigt komplexe Aufgaben — auf deinem Rechner.\n\n"
            "Das Setup dauert ca. 2 Minuten."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)

        l.addWidget(logo)
        l.addWidget(title)
        l.addWidget(subtitle)
        return w

    def _page_profile(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(50, 30, 50, 30)
        l.setSpacing(14)

        title = QLabel("Erzähl mir von dir")
        title.setObjectName("pageTitle")
        l.addWidget(title)

        subtitle = QLabel("Moruk OS lernt deinen Stil und passt sich an. Je mehr du schreibst, desto besser.")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        l.addWidget(subtitle)

        # Name
        l.addWidget(self._label("Dein Name (optional)"))
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("z.B. Firat")
        self.profile_name.setObjectName("inputField")
        l.addWidget(self.profile_name)

        # Beruf
        l.addWidget(self._label("Was machst du beruflich?"))
        self.profile_job = QLineEdit()
        self.profile_job.setPlaceholderText("z.B. Software Engineer, Designer, Forscher...")
        self.profile_job.setObjectName("inputField")
        l.addWidget(self.profile_job)

        # Sprache
        l.addWidget(self._label("Bevorzugte Sprache"))
        self.profile_lang = QComboBox()
        self.profile_lang.setObjectName("inputField")
        self.profile_lang.addItems(["Deutsch", "English", "Türkçe", "Français", "Español", "中文"])
        l.addWidget(self.profile_lang)

        # Bio
        l.addWidget(self._label("Was soll Moruk OS über dich wissen? (optional)"))
        self.profile_bio = QTextEdit()
        self.profile_bio.setPlaceholderText(
            "z.B. Ich arbeite viel mit Python, interessiere mich für KI-Projekte, "
            "mag direkte Antworten ohne Smalltalk..."
        )
        self.profile_bio.setObjectName("inputField")
        self.profile_bio.setFixedHeight(90)
        l.addWidget(self.profile_bio)

        return w

    def _page_apikeys(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(50, 30, 50, 30)
        l.setSpacing(14)

        title = QLabel("API Keys")
        title.setObjectName("pageTitle")
        l.addWidget(title)

        subtitle = QLabel(
            "Mindestens ein API Key wird benötigt. "
            "Weitere können später in den Einstellungen hinzugefügt werden."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        l.addWidget(subtitle)

        providers = [
            ("Anthropic (Claude)", "anthropic", "https://console.anthropic.com"),
            ("OpenAI (GPT-4)", "openai", "https://platform.openai.com"),
            ("Google (Gemini)", "gemini", "https://aistudio.google.com"),
            ("Groq (Llama/Mixtral)", "groq", "https://console.groq.com"),
        ]

        self.api_fields = {}
        for label, key, url in providers:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}")
            lbl.setFixedWidth(180)
            lbl.setObjectName("fieldLabel")

            field = QLineEdit()
            field.setPlaceholderText(f"sk-... oder API Key")
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setObjectName("inputField")
            self.api_fields[key] = field

            link = QPushButton("🔗")
            link.setFixedSize(30, 30)
            link.setToolTip(f"Öffne {url}")
            link.setObjectName("btnLink")
            link.clicked.connect(lambda _, u=url: subprocess.Popen(["xdg-open", u]))

            row.addWidget(lbl)
            row.addWidget(field)
            row.addWidget(link)
            l.addLayout(row)

        note = QLabel("🔒 Keys werden lokal in config/settings.json gespeichert — nie übertragen.")
        note.setObjectName("noteLabel")
        note.setWordWrap(True)
        l.addStretch()
        l.addWidget(note)

        return w

    def _page_syscheck(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(50, 30, 50, 30)
        l.setSpacing(12)

        title = QLabel("Systemcheck")
        title.setObjectName("pageTitle")
        l.addWidget(title)

        subtitle = QLabel("Moruk OS prüft deine Umgebung...")
        subtitle.setObjectName("pageSubtitle")
        self.syscheck_subtitle = subtitle
        l.addWidget(subtitle)

        self.syscheck_progress = QProgressBar()
        self.syscheck_progress.setRange(0, 8)
        self.syscheck_progress.setValue(0)
        self.syscheck_progress.setObjectName("progressBar")
        l.addWidget(self.syscheck_progress)

        # Scroll area für Ergebnisse
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scrollArea")
        inner = QWidget()
        self.syscheck_layout = QVBoxLayout(inner)
        self.syscheck_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.syscheck_layout.setSpacing(4)
        scroll.setWidget(inner)
        l.addWidget(scroll)

        return w

    # ── Navigation ────────────────────────────────────────────

    def _go_next(self):
        current = self.stack.currentIndex()

        if current >= 2:  # Letzte Seite — fertig
            self._finish()
            return

        if current == 1:  # Profil → Systemcheck
            self._save_profile()
            self.stack.setCurrentIndex(2)
            self._update_header(2)
            self._run_syscheck()
            self.btn_next.setText("Los geht's! 🚀")
            self.btn_next.setEnabled(False)
        else:
            self.stack.setCurrentIndex(current + 1)
            self._update_header(current + 1)

        self.btn_back.show() if self.stack.currentIndex() > 0 else self.btn_back.hide()
        self.step_label.setText(f"Schritt {self.stack.currentIndex() + 1} von 3")

    def _go_back(self):
        current = self.stack.currentIndex()
        if current > 0:
            self.stack.setCurrentIndex(current - 1)
            self._update_header(current - 1)
        self.btn_back.hide() if self.stack.currentIndex() == 0 else self.btn_back.show()
        self.btn_next.setText("Weiter →")
        self.step_label.setText(f"Schritt {self.stack.currentIndex() + 1} von 3")

    def _update_header(self, idx):
        titles = ["Willkommen", "Dein Profil", "Systemcheck"]
        icons  = ["🌟", "👤", "🔍"]
        idx = min(idx, len(titles) - 1)
        self.header.setText(f'<span style="font-size:24px">{icons[idx]}</span>  '
                            f'<span style="font-size:18px; font-weight:bold">{titles[idx]}</span>')

    # ── Validation ────────────────────────────────────────────

    def _validate_apikeys(self):
        has_any = any(f.text().strip() for f in self.api_fields.values())
        if not has_any:
            for f in self.api_fields.values():
                f.setStyleSheet("border: 1px solid #ff4444;")
            return False
        return True

    # ── System Check ─────────────────────────────────────────

    def _run_syscheck(self):
        self._check_count = 0
        self.worker = SystemCheckWorker()
        self.worker.result.connect(self._on_check_result)
        self.worker.done.connect(self._on_check_done)
        self.worker.start()

    def _on_check_result(self, message: str, success: bool):
        self._check_count += 1
        self.syscheck_progress.setValue(self._check_count)

        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(4, 2, 4, 2)

        icon = QLabel("✅" if success else "⚠️")
        icon.setFixedWidth(24)
        text = QLabel(message)
        text.setWordWrap(True)
        text.setStyleSheet("color: #e0e0e0; font-size: 13px;")

        rl.addWidget(icon)
        rl.addWidget(text)
        rl.addStretch()
        self.syscheck_layout.addWidget(row)

    def _on_check_done(self, info: dict):
        self.system_info = info
        failures = sum(1 for v in info.values() if not v["ok"])

        if failures == 0:
            self.syscheck_subtitle.setText(
                "✅ Alles gut! Öffne nach dem Start Settings ⚙ und trage deinen API Key ein."
            )
        else:
            msg = f"⚠️  {failures} Warnung(en) — Moruk OS startet trotzdem. Öffne Settings ⚙ und trage deinen API Key ein."
            self.syscheck_subtitle.setText(msg)

        self.btn_next.setEnabled(True)
        self.btn_next.setText("Los geht's! 🚀")

    # ── Save & Finish ─────────────────────────────────────────

    def _save_all(self):
        # Profil speichern
        profile = {
            "name": self.profile_name.text().strip(),
            "job": self.profile_job.text().strip(),
            "language": self.profile_lang.currentText(),
            "bio": self.profile_bio.toPlainText().strip(),
            "onboarding_done": True
        }
        os.makedirs(os.path.dirname(USER_PROFILE_PATH), exist_ok=True)
        with open(USER_PROFILE_PATH, "w") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)

        # API Keys speichern
        settings = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                settings = json.load(f)

        api_keys = {}
        for key, field in self.api_fields.items():
            val = field.text().strip()
            if val:
                api_keys[key] = val

        settings["api_keys"] = api_keys
        settings["onboarding_done"] = True

        # Ersten Provider als Default setzen
        if api_keys:
            first = list(api_keys.keys())[0]
            settings.setdefault("provider", first)

        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(settings, f, indent=2)

        self.settings = settings

    def _finish(self):
        self._save_profile()
        self.finished_signal.emit(self.settings)
        self.accept()

    def _save_profile(self):
        """Nur Profil speichern — API Keys kommen über Settings."""
        import json, os
        profile = {
            "name": self.profile_name.text().strip(),
            "job": self.profile_job.text().strip(),
            "language": self.profile_lang.currentText(),
            "bio": self.profile_bio.toPlainText().strip(),
            "onboarding_done": True
        }
        os.makedirs(os.path.dirname(USER_PROFILE_PATH), exist_ok=True)
        with open(USER_PROFILE_PATH, "w") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)

        # onboarding_done in settings setzen
        settings = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    settings = json.load(f)
            except Exception:
                pass
        settings["onboarding_done"] = True
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(settings, f, indent=2)
        self.settings = settings

    # ── Helpers ──────────────────────────────────────────────

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("fieldLabel")
        return lbl

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0d0d0d;
                color: #e0e0e0;
            }
            QLabel#pageTitle {
                font-size: 22px;
                font-weight: bold;
                color: #ffffff;
                margin-bottom: 4px;
            }
            QLabel#pageSubtitle {
                font-size: 13px;
                color: #aaaaaa;
                line-height: 1.5;
            }
            QLabel#fieldLabel {
                font-size: 13px;
                color: #cccccc;
                font-weight: bold;
            }
            QLabel#noteLabel {
                font-size: 12px;
                color: #888888;
                font-style: italic;
            }
            QLineEdit#inputField, QTextEdit#inputField, QComboBox#inputField {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #e0e0e0;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit#inputField:focus, QTextEdit#inputField:focus {
                border: 1px solid #00d4ff;
            }
            QWidget#footer {
                background-color: #111111;
                border-top: 1px solid #222222;
            }
            QPushButton#btnNext {
                background-color: #00d4ff;
                color: #000000;
                border: none;
                border-radius: 8px;
                padding: 10px 28px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#btnNext:hover {
                background-color: #00eeff;
            }
            QPushButton#btnNext:disabled {
                background-color: #333333;
                color: #666666;
            }
            QPushButton#btnBack {
                background-color: transparent;
                color: #888888;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
            }
            QPushButton#btnBack:hover {
                color: #cccccc;
                border-color: #555555;
            }
            QPushButton#btnLink {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 4px;
                color: #888888;
            }
            QPushButton#btnLink:hover {
                background-color: #252525;
            }
            QLabel#stepLabel {
                color: #555555;
                font-size: 12px;
            }
            QProgressBar#progressBar {
                background-color: #1a1a1a;
                border: none;
                border-radius: 4px;
                height: 6px;
                text-visible: false;
            }
            QProgressBar#progressBar::chunk {
                background-color: #00d4ff;
                border-radius: 4px;
            }
            QScrollArea#scrollArea {
                background-color: #111111;
                border: 1px solid #222222;
                border-radius: 6px;
            }
        """)
        # Header style
        self.header.setStyleSheet("""
            background-color: #111111;
            border-bottom: 1px solid #222222;
            color: #ffffff;
            padding: 0 24px;
        """)


# ── Entry Point ───────────────────────────────────────────────────────────────

def should_show_onboarding() -> bool:
    """True wenn Onboarding noch nicht abgeschlossen wurde."""
    if not os.path.exists(CONFIG_PATH):
        return True
    try:
        with open(CONFIG_PATH) as f:
            settings = json.load(f)
        return not settings.get("onboarding_done", False)
    except Exception:
        return True


def run_onboarding(parent=None) -> dict:
    """Zeigt Onboarding-Dialog und gibt settings zurück."""
    dialog = OnboardingDialog(parent)
    result = {}
    dialog.finished_signal.connect(lambda s: result.update(s))
    dialog.exec()
    return result
