"""
Live Activity Window — Moruk OS
Zeigt in Echtzeit was Moruk gerade tut:
  • Aktuell geschriebene Datei mit Live-Code
  • Tool-Call Stream (terminal, read_file, web_search etc.)
  • 🧠 DeepThink Review Button
  • 🔧 Patch Button
"""

import json
import os
import re
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QSplitter,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter

# ── Syntax Highlighter ────────────────────────────────────────────────────────


class PythonHighlighter(QSyntaxHighlighter):
    KEYWORDS = [
        "def",
        "class",
        "import",
        "from",
        "return",
        "if",
        "else",
        "elif",
        "for",
        "while",
        "try",
        "except",
        "with",
        "as",
        "in",
        "not",
        "and",
        "or",
        "True",
        "False",
        "None",
        "lambda",
        "pass",
        "break",
        "continue",
        "global",
        "yield",
        "async",
        "await",
        "raise",
        "del",
        "assert",
    ]

    def __init__(self, document):
        super().__init__(document)
        self._rules = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#c792ea"))
        kw_fmt.setFontWeight(700)
        for kw in self.KEYWORDS:
            self._rules.append((re.compile(rf"\b{kw}\b"), kw_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#c3e88d"))
        self._rules.append((re.compile(r"(\".*?\"|\'.*?\')"), str_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#546e7a"))
        comment_fmt.setFontItalic(True)
        self._rules.append((re.compile(r"#[^\n]*"), comment_fmt))

        func_fmt = QTextCharFormat()
        func_fmt.setForeground(QColor("#82aaff"))
        self._rules.append((re.compile(r"\b([a-zA-Z_]\w*)\s*(?=\()"), func_fmt))

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#f78c6c"))
        self._rules.append((re.compile(r"\b\d+\.?\d*\b"), num_fmt))

        plugin_fmt = QTextCharFormat()
        plugin_fmt.setForeground(QColor("#ffcb6b"))
        plugin_fmt.setFontWeight(700)
        self._rules.append((re.compile(r"PLUGIN_\w+"), plugin_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── DeepThink Review Worker ───────────────────────────────────────────────────


class DeepThinkWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, brain, code: str, filename: str):
        super().__init__()
        self.brain = brain
        self.code = code
        self.filename = filename

    def run(self):
        try:
            prompt = (
                f"Du bist ein Code-Reviewer. Analysiere diesen Code aus `{self.filename}` "
                f"und gib:\n1. Kritische Bugs (falls vorhanden)\n2. Verbesserungsvorschläge\n"
                f"3. Security-Issues\nSei präzise, max 300 Wörter.\n\n```python\n{self.code}\n```"
            )
            if hasattr(self.brain, "deepthink") and self.brain.deepthink:
                result = self.brain.deepthink.think(prompt)
            else:
                result = self.brain.think(prompt, max_iterations=1)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ── Tool Event Item ───────────────────────────────────────────────────────────

TOOL_ICONS = {
    "write_file": ("📝", "#c3e88d"),
    "read_file": ("📖", "#82aaff"),
    "terminal": ("⚡", "#ffcb6b"),
    "web_search": ("🌐", "#89ddff"),
    "web_scraper": ("🌐", "#89ddff"),
    "memory_store": ("🧠", "#c792ea"),
    "memory_search": ("🧠", "#c792ea"),
    "image_generator": ("🎨", "#f78c6c"),
    "task_create": ("✅", "#c3e88d"),
    "task_complete": ("✅", "#c3e88d"),
    "list_tools": ("🔍", "#546e7a"),
    "vision": ("👁", "#89ddff"),
    "voice": ("🔊", "#c792ea"),
    "browser": ("🌍", "#89ddff"),
    "file_manager": ("📁", "#ffcb6b"),
    "self_edit": ("✏️", "#f78c6c"),
}
DEFAULT_ICON = ("🔧", "#89ddff")


class ToolEventWidget(QFrame):
    def __init__(self, tool_name: str, params_str: str, parent=None):
        super().__init__(parent)
        icon, color = TOOL_ICONS.get(tool_name, DEFAULT_ICON)
        timestamp = datetime.now().strftime("%H:%M:%S")

        self.setStyleSheet(f"""
            QFrame {{
                background: #1a1a2e;
                border-left: 2px solid {color};
                border-radius: 4px;
                margin: 1px 0;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(tool_name)
        name_lbl.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 11px; border: none; background: transparent;"
        )
        name_lbl.setFixedWidth(110)
        layout.addWidget(name_lbl)

        try:
            p = json.loads(params_str)
            short = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(p.items())[:2])
        except Exception:
            short = params_str[:60]

        param_lbl = QLabel(short)
        param_lbl.setStyleSheet(
            "color: #546e7a; font-size: 10px; border: none; background: transparent;"
        )
        param_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        param_lbl.setWordWrap(False)
        layout.addWidget(param_lbl, 1)

        time_lbl = QLabel(timestamp)
        time_lbl.setStyleSheet(
            "color: #3a3a5c; font-size: 9px; border: none; background: transparent;"
        )
        layout.addWidget(time_lbl)

    def mark_done(self, success: bool):
        border = "#c3e88d" if success else "#f07178"
        self.setStyleSheet(
            self.styleSheet().replace(
                "border-left:", f"border-right: 2px solid {border}; border-left:"
            )
        )


# ── LiveActivityWindow ────────────────────────────────────────────────────────


class LiveActivityWindow(QWidget):
    """
    Floating Live Activity Monitor.
    Verbindung zu ChatWorker:
        window.connect_worker(worker)  → auf jeden neuen Worker aufrufen
    """

    sig_tool_start = pyqtSignal(str, str)
    sig_tool_result = pyqtSignal(str, str, bool)
    sig_token = pyqtSignal(str)
    sig_clear = pyqtSignal()

    def __init__(self, brain=None, parent=None):
        super().__init__(parent)
        self.brain = brain
        self._current_file = None
        self._current_code = ""
        self._tool_widgets = {}
        self._dt_thread = None
        self._patch_code = ""

        self._build_ui()
        self._connect_internal()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(720, 580)
        self.setWindowTitle("⚡ Live Activity — Moruk OS")

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget {
                background: #0d0d1a;
                color: #cdd3de;
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
            }
            QScrollBar:vertical { background: #0d0d1a; width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #2a2a4a; border-radius: 3px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(46)
        header.setStyleSheet("background: #0a0a18; border-bottom: 1px solid #1e1e3a;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 0, 14, 0)
        h_layout.setSpacing(10)

        pulse = QLabel("⚡")
        pulse.setStyleSheet("font-size: 16px; color: #ffcb6b;")
        h_layout.addWidget(pulse)

        title = QLabel("Live Activity")
        title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #e0e0ff; letter-spacing: 1px;"
        )
        h_layout.addWidget(title)
        h_layout.addStretch()

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #3a3a5c; font-size: 12px;")
        h_layout.addWidget(self._status_dot)

        self._status_lbl = QLabel("Bereit")
        self._status_lbl.setStyleSheet("color: #546e7a; font-size: 11px;")
        h_layout.addWidget(self._status_lbl)

        clear_btn = QPushButton("✕ Leeren")
        clear_btn.setFixedHeight(26)
        clear_btn.setStyleSheet("""
            QPushButton { background: #1a1a2e; color: #546e7a; border: 1px solid #2a2a4a;
                          border-radius: 4px; padding: 0 10px; font-size: 10px; }
            QPushButton:hover { background: #2a2a4a; color: #cdd3de; }
        """)
        clear_btn.clicked.connect(self._clear_all)
        h_layout.addWidget(clear_btn)
        root.addWidget(header)

        # Splitter: Code oben / Tool-Log unten
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setStyleSheet(
            "QSplitter::handle { background: #1e1e3a; height: 3px; }"
        )

        # Code Panel
        code_panel = QWidget()
        code_panel.setStyleSheet("background: #0d0d1a;")
        cp_layout = QVBoxLayout(code_panel)
        cp_layout.setContentsMargins(0, 0, 0, 0)
        cp_layout.setSpacing(0)

        self._file_bar = QFrame()
        self._file_bar.setFixedHeight(30)
        self._file_bar.setStyleSheet(
            "background: #0a0a18; border-bottom: 1px solid #1e1e3a;"
        )
        fb_layout = QHBoxLayout(self._file_bar)
        fb_layout.setContentsMargins(12, 0, 12, 0)
        self._file_lbl = QLabel("— keine Datei —")
        self._file_lbl.setStyleSheet("color: #3a3a5c; font-size: 11px;")
        fb_layout.addWidget(self._file_lbl)
        fb_layout.addStretch()
        self._lang_lbl = QLabel("")
        self._lang_lbl.setStyleSheet("color: #2a2a4a; font-size: 10px;")
        fb_layout.addWidget(self._lang_lbl)
        cp_layout.addWidget(self._file_bar)

        self._code_edit = QTextEdit()
        self._code_edit.setReadOnly(True)
        self._code_edit.setFont(QFont("JetBrains Mono", 10))
        self._code_edit.setStyleSheet("""
            QTextEdit { background: #0d0d1a; color: #cdd3de; border: none;
                        padding: 10px; selection-background-color: #2a2a5a; }
        """)
        self._code_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._highlighter = PythonHighlighter(self._code_edit.document())
        cp_layout.addWidget(self._code_edit)
        splitter.addWidget(code_panel)

        # Tool Log Panel
        log_panel = QWidget()
        log_panel.setStyleSheet("background: #0a0a18;")
        lp_layout = QVBoxLayout(log_panel)
        lp_layout.setContentsMargins(0, 0, 0, 0)
        lp_layout.setSpacing(0)

        log_header = QFrame()
        log_header.setFixedHeight(28)
        log_header.setStyleSheet(
            "background: #080810; border-bottom: 1px solid #1e1e3a;"
        )
        lh_layout = QHBoxLayout(log_header)
        lh_layout.setContentsMargins(12, 0, 12, 0)
        lh_label = QLabel("🔧 Tool Calls")
        lh_label.setStyleSheet("color: #546e7a; font-size: 10px; letter-spacing: 1px;")
        lh_layout.addWidget(lh_label)
        lp_layout.addWidget(log_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0a0a18; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tool_scroll = scroll

        self._tool_container = QWidget()
        self._tool_container.setStyleSheet("background: #0a0a18;")
        self._tool_layout = QVBoxLayout(self._tool_container)
        self._tool_layout.setContentsMargins(8, 6, 8, 6)
        self._tool_layout.setSpacing(3)
        self._tool_layout.addStretch()
        scroll.setWidget(self._tool_container)
        lp_layout.addWidget(scroll)

        splitter.addWidget(log_panel)
        splitter.setSizes([320, 180])
        root.addWidget(splitter, 1)

        # Footer Buttons
        footer = QFrame()
        footer.setFixedHeight(52)
        footer.setStyleSheet("background: #0a0a18; border-top: 1px solid #1e1e3a;")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(14, 8, 14, 8)
        f_layout.setSpacing(10)

        self._dt_btn = QPushButton("🧠  DeepThink Review")
        self._dt_btn.setFixedHeight(34)
        self._dt_btn.setEnabled(False)
        self._dt_btn.setStyleSheet("""
            QPushButton { background: #1a0a2e; color: #c792ea; border: 1px solid #4a1a7a;
                          border-radius: 6px; padding: 0 16px; font-size: 12px; font-weight: bold; }
            QPushButton:hover { background: #2a0a4e; border-color: #c792ea; }
            QPushButton:disabled { color: #3a2a5a; border-color: #2a1a4a; }
        """)
        self._dt_btn.clicked.connect(self._run_deepthink)
        f_layout.addWidget(self._dt_btn)

        self._patch_btn = QPushButton("🔧  Patchen")
        self._patch_btn.setFixedHeight(34)
        self._patch_btn.setEnabled(False)
        self._patch_btn.setStyleSheet("""
            QPushButton { background: #0a1a2e; color: #82aaff; border: 1px solid #1a4a7a;
                          border-radius: 6px; padding: 0 16px; font-size: 12px; font-weight: bold; }
            QPushButton:hover { background: #0a2a4e; border-color: #82aaff; }
            QPushButton:disabled { color: #2a3a5a; border-color: #1a2a4a; }
        """)
        self._patch_btn.clicked.connect(self._run_patch)
        f_layout.addWidget(self._patch_btn)

        f_layout.addStretch()

        copy_btn = QPushButton("📋 Code kopieren")
        copy_btn.setFixedHeight(34)
        copy_btn.setStyleSheet("""
            QPushButton { background: #111120; color: #546e7a; border: 1px solid #2a2a4a;
                          border-radius: 6px; padding: 0 14px; font-size: 11px; }
            QPushButton:hover { color: #cdd3de; border-color: #546e7a; }
        """)
        copy_btn.clicked.connect(self._copy_code)
        f_layout.addWidget(copy_btn)

        root.addWidget(footer)

    def _connect_internal(self):
        self.sig_tool_start.connect(self._on_tool_start)
        self.sig_tool_result.connect(self._on_tool_result)
        self.sig_token.connect(self._on_token)
        self.sig_clear.connect(self._clear_all)

    def connect_worker(self, worker):
        """Verbindet ChatWorker Signals mit dem Live-Fenster."""
        try:
            worker.tool_start.connect(lambda n, p: self.sig_tool_start.emit(n, p))
            worker.tool_result.connect(
                lambda n, r, s: self.sig_tool_result.emit(n, r, s)
            )
            worker.token_received.connect(lambda t: self.sig_token.emit(t))
        except Exception:
            pass

    def _on_tool_start(self, tool_name: str, params_str: str):
        self._set_status(f"{tool_name}…", active=True)

        if tool_name == "write_file":
            try:
                p = json.loads(params_str)
                filepath = p.get("path", p.get("filename", "unknown"))
                content = p.get("content", "")
                self._show_file(filepath, content)
            except Exception:
                pass
        elif tool_name == "read_file":
            try:
                p = json.loads(params_str)
                fp = p.get("path", p.get("filename", ""))
                if fp:
                    self._file_lbl.setText(f"📖 {os.path.basename(fp)}")
                    self._file_lbl.setStyleSheet("color: #82aaff; font-size: 11px;")
            except Exception:
                pass

        w = ToolEventWidget(tool_name, params_str)
        count = self._tool_layout.count()
        self._tool_layout.insertWidget(count - 1, w)
        self._tool_widgets[tool_name] = w

        QTimer.singleShot(
            50,
            lambda: self._tool_scroll.verticalScrollBar().setValue(
                self._tool_scroll.verticalScrollBar().maximum()
            ),
        )

    def _on_tool_result(self, tool_name: str, result: str, success: bool):
        w = self._tool_widgets.get(tool_name)
        if w:
            w.mark_done(success)
        self._set_status("Bereit", active=False)

    def _on_token(self, token: str):
        pass  # Optional: streaming tokens anzeigen

    def _show_file(self, filepath: str, content: str):
        self._current_file = filepath
        self._current_code = content
        name = os.path.basename(filepath)
        ext = os.path.splitext(filepath)[1].lower()
        lang = {
            ".py": "Python",
            ".json": "JSON",
            ".md": "Markdown",
            ".js": "JavaScript",
            ".html": "HTML",
            ".sh": "Shell",
        }.get(ext, "Text")

        self._file_lbl.setText(f"📝 {name}")
        self._file_lbl.setStyleSheet("color: #c3e88d; font-size: 11px;")
        self._lang_lbl.setText(lang)
        self._code_edit.setPlainText(content)

        QTimer.singleShot(
            30,
            lambda: self._code_edit.verticalScrollBar().setValue(
                self._code_edit.verticalScrollBar().maximum()
            ),
        )

        self._dt_btn.setEnabled(True)
        self._patch_btn.setEnabled(True)
        self._patch_code = content

    def _set_status(self, text: str, active: bool = False):
        self._status_lbl.setText(text)
        color = "#c3e88d" if active else "#3a3a5c"
        self._status_dot.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _run_deepthink(self):
        if not self._current_code or not self.brain:
            return
        self._dt_btn.setEnabled(False)
        self._dt_btn.setText("🧠  Analysiere…")
        self._set_status("DeepThink läuft…", active=True)

        worker = DeepThinkWorker(
            self.brain, self._current_code, self._current_file or "code.py"
        )
        self._dt_thread = QThread()
        worker.moveToThread(self._dt_thread)
        self._dt_thread.started.connect(worker.run)
        worker.finished.connect(self._on_deepthink_done)
        worker.error.connect(self._on_deepthink_error)
        worker.finished.connect(self._dt_thread.quit)
        worker.error.connect(self._dt_thread.quit)
        self._dt_thread.start()

    def _on_deepthink_done(self, review: str):
        self._dt_btn.setEnabled(True)
        self._dt_btn.setText("🧠  DeepThink Review")
        self._set_status("Review fertig", active=False)
        separator = "\n\n" + "─" * 60 + "\n🧠 DeepThink Review:\n" + "─" * 60 + "\n"
        self._code_edit.setPlainText(self._current_code + separator + review)
        self._patch_btn.setEnabled(True)
        self._patch_btn.setText("🔧  Review anwenden")

    def _on_deepthink_error(self, error: str):
        self._dt_btn.setEnabled(True)
        self._dt_btn.setText("🧠  DeepThink Review")
        self._set_status(f"Fehler: {error[:40]}", active=False)

    def _run_patch(self):
        if not self.brain or not self._current_file:
            return
        patch_prompt = (
            f"Patch die Datei `{self._current_file}` basierend auf dem DeepThink Review. "
            f"Schreibe die verbesserte Version direkt mit write_file.\n\n"
            f"Aktueller Code:\n```python\n{self._current_code}\n```"
        )
        self._patch_btn.setEnabled(False)
        self._patch_btn.setText("🔧  Wird gepatcht…")
        self._set_status("Patching…", active=True)

        import threading

        threading.Thread(
            target=self._do_patch, args=(patch_prompt,), daemon=True
        ).start()

    def _do_patch(self, prompt: str):
        try:
            self.brain.think(prompt, max_iterations=5)
            QTimer.singleShot(0, lambda: self._patch_btn.setText("✅  Gepatcht!"))
            QTimer.singleShot(
                2000,
                lambda: (
                    self._patch_btn.setEnabled(True),
                    self._patch_btn.setText("🔧  Patchen"),
                ),
            )
        except Exception as e:
            QTimer.singleShot(0, lambda: self._patch_btn.setText(f"❌ {str(e)[:30]}"))
            QTimer.singleShot(
                2000,
                lambda: (
                    self._patch_btn.setEnabled(True),
                    self._patch_btn.setText("🔧  Patchen"),
                ),
            )

    def _copy_code(self):
        QApplication.clipboard().setText(self._current_code)
        self._set_status("Code kopiert!", active=False)
        QTimer.singleShot(2000, lambda: self._set_status("Bereit"))

    def _clear_all(self):
        while self._tool_layout.count() > 1:
            item = self._tool_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tool_widgets.clear()
        self._code_edit.clear()
        self._file_lbl.setText("— keine Datei —")
        self._file_lbl.setStyleSheet("color: #3a3a5c; font-size: 11px;")
        self._lang_lbl.setText("")
        self._current_file = None
        self._current_code = ""
        self._dt_btn.setEnabled(False)
        self._patch_btn.setEnabled(False)
        self._patch_btn.setText("🔧  Patchen")
        self._dt_btn.setText("🧠  DeepThink Review")
        self._set_status("Bereit")
