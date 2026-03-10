"""
Moruk AI OS - Main Window v5.1
Frameless Glass Design, Chat Bubbles mit Copy-Button, Custom Titlebar.

v5.1 Fixes:
- tool_router.set_brain() wird jetzt aufgerufen (Plugins bekommen Brain-Referenz)
- tool_router.set_autonomy_loop() statt direktem _autonomy_loop Attribut
- _toggle_deepthink: brain.deepthink statt tool_router.deepthink
- _show_monitor_notification/_show_routing_hint: chat_display → _append_message
- closeEvent: _load_chat_history() entfernt (existierte nicht → Crash)
- _tool_group_count wird jetzt inkrementiert (war immer 0)
- ThinkWorker: unnötiger inspect.signature Call entfernt
"""

import base64
import mimetypes
import os
import threading
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QSplitter,
    QScrollArea,
    QFrame,
    QApplication,
    QSizeGrip,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QGroupBox,
    QLineEdit,
)
from PyQt6.QtCore import (
    Qt,
    QThread,
    pyqtSignal,
    QObject,
    QTimer,
    QBuffer,
    QIODevice,
    QByteArray,
    pyqtSlot,
    QMetaObject,
    Q_ARG,
)
from PyQt6.QtGui import QFont, QKeyEvent, QPixmap, QImage

from ui.settings_dialog import SettingsDialog
from core.model_router import ModelRouter
from ui.sidebar import Sidebar
from ui.live_activity_window import LiveActivityWindow
from ui.tray_icon import MorukTrayIcon
from ui.markdown_renderer import markdown_to_html
from ui.styles import DARK_THEME
from core.brain import Brain
from core.state_manager import StateManager
from core.memory import Memory
from core.task_manager import TaskManager
from core.reflector import Reflector
from core.executor import Executor
from core.tool_router import ToolRouter
from core.autonomy_loop import AutonomyLoop
from core.context_router import ContextRouter, HistoryCompressor
from core.goal_engine import GoalEngine
from core.project_manager import ProjectManager
from ui.alert_window import AlertWindow
import plugins.system_watchdog as watchdog
from core.heartbeat import Heartbeat


class ThinkWorker(QObject):
    """Worker für async LLM Calls mit Tool-Loop + Streaming."""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    tool_start = pyqtSignal(str, str)
    tool_result = pyqtSignal(str, str, bool)
    token_received = pyqtSignal(str)

    def __init__(
        self, brain, message, context, max_iterations=10, depth=3, force_deepthink=False
    ):
        super().__init__()
        self.brain = brain
        self.message = message
        self.context = context
        self.max_iterations = max_iterations
        self.depth = depth
        self.force_deepthink = force_deepthink

    def run(self):
        try:
            import json

            def on_tool_start(name, params):
                if name == "write_file":
                    self.tool_start.emit(name, json.dumps(params, ensure_ascii=False))
                else:
                    self.tool_start.emit(
                        name, json.dumps(params, ensure_ascii=False)[:300]
                    )

            def on_tool_result(name, result):
                self.tool_result.emit(
                    name,
                    str(result.get("result", ""))[:500],
                    result.get("success", False),
                )

            def on_token(token):
                self.token_received.emit(token)

            response = self.brain.think(
                self.message,
                extra_context=self.context,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
                max_iterations=self.max_iterations,
                depth=self.depth,
                on_token=on_token,
                force_deepthink=self.force_deepthink,
            )

            self.finished.emit(response)
        except Exception as e:
            self.error.emit(str(e))


class ChatInput(QTextEdit):
    """Custom Input mit Enter=Send, Shift+Enter=Newline, Drag&Drop, Paste."""

    send_signal = pyqtSignal()
    file_attached = pyqtSignal(str, str, object)  # path, mime_type, thumbnail_pixmap

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.attached_files = []  # [(path, mime_type, base64_data)]

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_signal.emit()
        elif (
            event.key() == Qt.Key.Key_V
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            # Ctrl+V: Check for image in clipboard
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData()
            if mime.hasImage():
                self._handle_clipboard_image(clipboard)
            elif mime.hasUrls():
                for url in mime.urls():
                    if url.isLocalFile():
                        self._attach_file(url.toLocalFile())
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self._attach_file(url.toLocalFile())
        elif mime.hasImage():
            self._handle_dropped_image(mime)
        event.acceptProposedAction()

    def _attach_file(self, filepath: str):
        """Hängt eine Datei an."""
        if not os.path.exists(filepath):
            return

        mime_type, _ = mimetypes.guess_type(filepath)
        mime_type = mime_type or "application/octet-stream"

        # Thumbnail erstellen
        thumb = None
        if mime_type.startswith("image/"):
            thumb = QPixmap(filepath)
            if not thumb.isNull():
                thumb = thumb.scaled(
                    80,
                    80,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

            # Base64 für LLM
            try:
                with open(filepath, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                self.attached_files.append((filepath, mime_type, b64))
            except Exception:
                self.attached_files.append((filepath, mime_type, None))
        else:
            # Nicht-Bild-Dateien: Pfad merken
            self.attached_files.append((filepath, mime_type, None))

        self.file_attached.emit(filepath, mime_type, thumb)

    def _handle_clipboard_image(self, clipboard):
        """Screenshot/Bild aus Clipboard einfügen."""
        image = clipboard.image()
        if image.isNull():
            return

        # Als PNG in temp speichern
        temp_dir = os.path.join(
            os.path.expanduser("~"), "moruk-os", "data", "attachments"
        )
        os.makedirs(temp_dir, exist_ok=True)

        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(temp_dir, filename)

        pixmap = QPixmap.fromImage(image)
        pixmap.save(filepath, "PNG")

        # Base64
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        b64 = base64.b64encode(buffer.data().data()).decode()
        buffer.close()

        # Thumbnail
        thumb = pixmap.scaled(
            80,
            80,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.attached_files.append((filepath, "image/png", b64))
        self.file_attached.emit(filepath, "image/png", thumb)

    def _handle_dropped_image(self, mime):
        """Bild direkt aus Drag&Drop."""
        image = mime.imageData()
        if image is None:
            return

        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return

        temp_dir = os.path.join(
            os.path.expanduser("~"), "moruk-os", "data", "attachments"
        )
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"dropped_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(temp_dir, filename)
        pixmap.save(filepath, "PNG")

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        b64 = base64.b64encode(buffer.data().data()).decode()
        buffer.close()

        thumb = pixmap.scaled(
            80,
            80,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.attached_files.append((filepath, "image/png", b64))
        self.file_attached.emit(filepath, "image/png", thumb)

    def clear_attachments(self):
        self.attached_files = []

    def get_attachments(self) -> list:
        return self.attached_files.copy()


class ChatBubble(QFrame):
    """Chat-Blase mit Copy-Button und optionalen Bild-Attachments."""

    def __init__(self, role: str, text: str, attachments: list = None, parent=None):
        super().__init__(parent)
        self.raw_text = text
        self.role = role

        bubble_ids = {
            "user": "userBubble",
            "assistant": "assistantBubble",
            "tool_exec": "toolBubble",
            "tool_result": "toolResultBubble",
            "system": "systemBubble",
            "reflection": "reflectionBubble",
            "token_info": "tokenInfoBubble",
        }
        self.setObjectName(bubble_ids.get(role, "systemBubble"))

        sender_colors = {
            "user": "#e94560",
            "assistant": "#00d2ff",
            "tool_exec": "#e94560",
            "tool_result": "#00d2ff",
            "system": "rgba(255,255,255,0.3)",
            "reflection": "#ffa500",
            "token_info": "rgba(255,255,255,0.25)",
        }

        sender_names = {
            "user": "Du",
            "assistant": "Moruk",
            "tool_exec": "⚡ Tool",
            "tool_result": "→ Result",
            "system": "System",
            "reflection": "🧠 Reflect",
            "token_info": "",
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.setSpacing(6)

        sender = QLabel(sender_names.get(role, ""))
        sender.setObjectName("bubbleSender")
        sender.setStyleSheet(f"color: {sender_colors.get(role, '#888')};")
        header.addWidget(sender)
        header.addStretch()

        if role in ("user", "assistant"):
            copy_btn = QPushButton("📋")
            copy_btn.setObjectName("copyBtn")
            copy_btn.setToolTip("Copy")
            copy_btn.setFixedSize(28, 22)
            copy_btn.clicked.connect(self._copy_text)
            header.addWidget(copy_btn)

        layout.addLayout(header)

        # Attachments (Thumbnails)
        if attachments:
            attach_layout = QHBoxLayout()
            attach_layout.setSpacing(6)
            attach_layout.setContentsMargins(0, 4, 0, 4)

            for filepath, mime_type, thumb_or_b64 in attachments:
                fname = os.path.basename(filepath)

                attach_frame = QFrame()
                attach_frame.setStyleSheet("""
                    QFrame {
                        background-color: rgba(255,255,255,0.04);
                        border: 1px solid rgba(255,255,255,0.08);
                        border-radius: 8px;
                        padding: 4px;
                    }
                """)
                af_layout = QVBoxLayout(attach_frame)
                af_layout.setContentsMargins(6, 6, 6, 6)
                af_layout.setSpacing(2)

                if mime_type and mime_type.startswith("image/"):
                    # Bild-Vorschau
                    img_label = QLabel()
                    if isinstance(thumb_or_b64, QPixmap) and not thumb_or_b64.isNull():
                        img_label.setPixmap(thumb_or_b64)
                    elif isinstance(thumb_or_b64, str):
                        # Es ist base64, lade als Pixmap
                        try:
                            data = base64.b64decode(thumb_or_b64)
                            img = QImage()
                            img.loadFromData(QByteArray(data))
                            pix = QPixmap.fromImage(img)
                            pix = pix.scaled(
                                90,
                                90,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                            img_label.setPixmap(pix)
                        except Exception:
                            img_label.setText("🖼")
                    elif os.path.exists(filepath):
                        pix = QPixmap(filepath)
                        if not pix.isNull():
                            pix = pix.scaled(
                                90,
                                90,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                            img_label.setPixmap(pix)
                        else:
                            img_label.setText("🖼")
                    else:
                        img_label.setText("🖼")

                    img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    img_label.setStyleSheet("background: transparent; border: none;")
                    af_layout.addWidget(img_label)
                else:
                    # Datei-Icon
                    icon_map = {
                        "application/pdf": "📄",
                        "text/plain": "📝",
                        "text/csv": "📊",
                    }
                    icon = "📎"
                    for prefix, emoji in icon_map.items():
                        if mime_type and mime_type.startswith(prefix):
                            icon = emoji
                            break

                    icon_label = QLabel(icon)
                    icon_label.setStyleSheet(
                        "font-size: 32px; background: transparent; border: none;"
                    )
                    icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    af_layout.addWidget(icon_label)

                # Dateiname
                name_label = QLabel(fname[:25])
                name_label.setStyleSheet(
                    "color: rgba(255,255,255,0.5); font-size: 10px; background: transparent; border: none;"
                )
                name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                af_layout.addWidget(name_label)

                attach_layout.addWidget(attach_frame)

            attach_layout.addStretch()
            layout.addLayout(attach_layout)

        # Text Content
        if text:
            text_label = QLabel()
            text_label.setObjectName("bubbleText")
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            text_label.setOpenExternalLinks(True)

            # Markdown Rendering für Assistant-Bubbles
            if role == "assistant":
                text_label.setTextFormat(Qt.TextFormat.RichText)
                text_label.setText(markdown_to_html(text))
            elif role == "system":
                text_label.setText(text)
                text_label.setStyleSheet(
                    "color: rgba(255,255,255,0.35); font-style: italic; font-size: 12px;"
                )
            elif role in ("tool_exec", "tool_result"):
                text_label.setText(text)
                text_label.setStyleSheet(
                    "font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 12px; color: rgba(255,255,255,0.5);"
                )
            elif role == "reflection":
                text_label.setText(text)
                text_label.setStyleSheet("color: #ffa500; font-size: 12px;")
            else:
                text_label.setText(text)

            layout.addWidget(text_label)

    def _copy_text(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.raw_text)
        sender = self.sender()
        if sender:
            sender.setText("✓")
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(1500, lambda: sender.setText("📋"))


class CollapsibleToolBlock(QWidget):
    """Zusammenklappbarer Tool-Ausführungs-Block im Chat."""

    def __init__(self, tool_name: str, params: str, parent=None):
        super().__init__(parent)
        self.tool_name = tool_name
        self._expanded = False
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (immer sichtbar)
        self.header_btn = QPushButton(f"⚡ {tool_name}  ▶")
        self.header_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px;
                color: #a0cfff;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
            }
        """)
        self.header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_btn.clicked.connect(self._toggle)
        layout.addWidget(self.header_btn)

        # Detail-Container (eingeklappt)
        self.detail_widget = QWidget()
        self.detail_widget.setStyleSheet("""
            background: rgba(0,0,0,0.25);
            border: 1px solid rgba(255,255,255,0.08);
            border-top: none;
            border-radius: 0 0 8px 8px;
        """)
        detail_layout = QVBoxLayout(self.detail_widget)
        detail_layout.setContentsMargins(10, 8, 10, 8)
        detail_layout.setSpacing(4)

        # Params
        self.params_label = QLabel(f"<b>Params:</b> {params[:200]}")
        self.params_label.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px;"
        )
        self.params_label.setWordWrap(True)
        detail_layout.addWidget(self.params_label)

        # Result
        self.result_label = QLabel("⏳ Running...")
        self.result_label.setStyleSheet(
            "color: rgba(255,255,255,0.75); font-size: 11px;"
        )
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.result_label)

        self.detail_widget.setVisible(False)
        layout.addWidget(self.detail_widget)

    def _toggle(self):
        self._expanded = not self._expanded
        self.detail_widget.setVisible(self._expanded)
        arrow = "▼" if self._expanded else "▶"
        status = self._current_status
        self.header_btn.setText(f"{status}  {arrow}")

    def set_result(self, result: str, success: bool):
        icon = "✅" if success else "❌"
        short_result = result[:120] + "..." if len(result) > 120 else result
        self._current_status = f"{icon} {self.tool_name}"
        self.header_btn.setText(f"{icon} {self.tool_name}  ▶")
        self.header_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
                color: %s;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
                text-align: left;
            }
            QPushButton:hover { background: rgba(255,255,255,0.10); }
        """ % ("#7dff9e" if success else "#ff7d7d"))
        self.result_label.setText(f"{icon} {short_result}")
        self.result_label.setStyleSheet(
            "color: %s; font-size: 11px;" % ("#7dff9e" if success else "#ff7d7d")
        )

    @property
    def _current_status(self):
        return getattr(self, "__status", f"⚡ {self.tool_name}")

    @_current_status.setter
    def _current_status(self, v):
        self.__status = v


class ToolGroupBlock(QWidget):
    """Gruppiert alle Tool-Calls einer Antwort unter einem klappbaren Header."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tool_blocks = []
        self._expanded = False
        self._success_count = 0
        self._fail_count = 0
        self.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(0)
        self.header_btn = QPushButton("⚡ Tools werden ausgeführt...  ▶")
        self.header_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
                color: #a0cfff;
                font-size: 12px;
                font-weight: 600;
                padding: 5px 12px;
                text-align: left;
            }
            QPushButton:hover { background: rgba(255,255,255,0.10); }
        """)
        self.header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_btn.clicked.connect(self._toggle)
        self._layout.addWidget(self.header_btn)
        self._inner = QWidget()
        self._inner.setStyleSheet("""
            background: rgba(0,0,0,0.20);
            border: 1px solid rgba(255,255,255,0.07);
            border-top: none;
            border-radius: 0 0 8px 8px;
        """)
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(8, 4, 8, 4)
        self._inner_layout.setSpacing(2)
        self._inner.setVisible(False)
        self._layout.addWidget(self._inner)

    def add_tool(self, block):
        self._tool_blocks.append(block)
        self._inner_layout.addWidget(block)
        n = len(self._tool_blocks)
        plural = "s" if n > 1 else ""
        self.header_btn.setText(f"⚡ {n} Tool{plural} läuft...  ▶")

    def set_result(self, tool_name, result, success):
        for block in self._tool_blocks:
            if block.tool_name == tool_name:
                block.set_result(result, success)
                if success:
                    self._success_count += 1
                else:
                    self._fail_count += 1
                break

    def finalize(self):
        n = len(self._tool_blocks)
        arrow = "▼" if self._expanded else "▶"
        plural = "s" if n > 1 else ""
        if self._fail_count == 0:
            self.header_btn.setText(f"✅ {n} Tool{plural} ausgeführt  {arrow}")
            self.header_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid rgba(255,255,255,0.10);
                    border-radius: 8px;
                    color: #7dff9e;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 5px 12px;
                    text-align: left;
                }
                QPushButton:hover { background: rgba(255,255,255,0.10); }
            """)
        else:
            self.header_btn.setText(f"⚠ {n} Tools ({self._fail_count} Fehler)  {arrow}")
            self.header_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid rgba(255,255,255,0.10);
                    border-radius: 8px;
                    color: #ffb347;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 5px 12px;
                    text-align: left;
                }
                QPushButton:hover { background: rgba(255,255,255,0.10); }
            """)

    def _toggle(self):
        self._expanded = not self._expanded
        self._inner.setVisible(self._expanded)
        text = self.header_btn.text()
        if text.endswith("▶"):
            self.header_btn.setText(text[:-1] + "▼")
        elif text.endswith("▼"):
            self.header_btn.setText(text[:-1] + "▶")


# ═══════════════════════════════════════════════
# MONITOR WINDOW
# ═══════════════════════════════════════════════


class MonitorWindow(QWidget):
    """Floating window — zeigt alle Web-Monitors und deren Status."""

    def __init__(self, monitor_engine=None, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.monitor_engine = monitor_engine
        self.setWindowTitle("🛰 Web Monitors")
        self.setMinimumSize(520, 580)
        self.setStyleSheet("""
            QWidget { background: #0e101e; color: white; font-family: 'Inter', 'Segoe UI', sans-serif; }
            QLabel#title { font-size: 18px; font-weight: bold; color: #e94560; }
            QLabel#sub { color: rgba(255,255,255,0.45); font-size: 12px; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: rgba(255,255,255,0.04); width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,0.2); border-radius: 3px; }
            QPushButton { background: rgba(255,255,255,0.07); color: rgba(255,255,255,0.85);
                border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; padding: 6px 14px; font-size: 12px; }
            QPushButton:hover { background: rgba(255,255,255,0.14); }
            QPushButton#addBtn { background: rgba(233,69,96,0.15); color: #e94560; border: 1px solid rgba(233,69,96,0.3); }
            QPushButton#addBtn:hover { background: rgba(233,69,96,0.28); }
            QLineEdit, QComboBox { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px; padding: 6px 10px; color: white; font-size: 12px; }
            QLineEdit:focus, QComboBox:focus { border-color: #e94560; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #1a1d2e; color: white; selection-background-color: #e94560; }
        """)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(12)

        title = QLabel("🛰 Web Monitors")
        title.setObjectName("title")
        outer.addWidget(title)

        sub = QLabel(
            "Moruk beobachtet diese Quellen automatisch und meldet Änderungen."
        )
        sub.setObjectName("sub")
        sub.setWordWrap(True)
        outer.addWidget(sub)

        form_box = QGroupBox("➕  Neuen Monitor hinzufügen")
        form_box.setStyleSheet("""
            QGroupBox { color: rgba(255,255,255,0.6); font-size: 12px;
                border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
                margin-top: 6px; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        form_layout = QVBoxLayout(form_box)
        form_layout.setSpacing(6)

        row1 = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name  (z.B. 'EUR/USD Kurs')")
        row1.addWidget(self.name_input, stretch=2)
        self.type_combo = QComboBox()
        for t in ["search", "news", "url", "github", "price"]:
            self.type_combo.addItem(t)
        row1.addWidget(self.type_combo, stretch=1)
        form_layout.addLayout(row1)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Query / URL / github-repo")
        form_layout.addWidget(self.query_input)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Interval (min):"))
        self.interval_input = QLineEdit("60")
        self.interval_input.setMaximumWidth(80)
        row3.addWidget(self.interval_input)
        row3.addStretch()
        row3.addWidget(QLabel("On change:"))
        self.onchange_combo = QComboBox()
        for oc in ["notify", "log", "act"]:
            self.onchange_combo.addItem(oc)
        row3.addWidget(self.onchange_combo)
        add_btn = QPushButton("➕ Add")
        add_btn.setObjectName("addBtn")
        add_btn.clicked.connect(self._add_monitor)
        row3.addWidget(add_btn)
        form_layout.addLayout(row3)
        outer.addWidget(form_box)

        list_label = QLabel("Aktive Monitors")
        list_label.setStyleSheet(
            "font-weight:bold;color:rgba(255,255,255,0.5);font-size:11px;"
        )
        outer.addWidget(list_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setSpacing(6)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.addStretch()
        scroll.setWidget(self.list_widget)
        outer.addWidget(scroll, stretch=1)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(refresh_btn)
        check_btn = QPushButton("⚡ Check All Now")
        check_btn.clicked.connect(self._check_all)
        btn_row.addWidget(check_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

    def refresh(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.monitor_engine:
            lbl = QLabel("MonitorEngine nicht verfügbar.")
            lbl.setStyleSheet("color:rgba(255,255,255,0.4);padding:20px;")
            self.list_layout.insertWidget(0, lbl)
            return

        monitors = self.monitor_engine.list_monitors()
        if not monitors:
            lbl = QLabel(
                "Noch keine Monitors.\n\nFüge oben einen Monitor hinzu oder sag Moruk:\n'Beobachte täglich den EUR/USD Kurs'"
            )
            lbl.setStyleSheet(
                "color:rgba(255,255,255,0.4);padding:20px;font-size:12px;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_layout.insertWidget(0, lbl)
            return

        from core.monitor_engine import MonitorEngine as ME
        from datetime import datetime

        for i, m in enumerate(monitors):
            self.list_layout.insertWidget(i, self._make_card(m))

    def _make_card(self, m):
        from core.monitor_engine import MonitorEngine as ME
        from datetime import datetime

        card = QWidget()
        card.setStyleSheet(
            "QWidget{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;}"
        )
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 10, 10, 10)
        icon = ME.TYPE_ICONS.get(m.get("type", "custom"), "📡")
        status_color = "#aaaaaa" if m["status"] == "paused" else "#00cc88"
        last = m.get("last_checked")
        last_str = datetime.fromisoformat(last).strftime("%d.%m %H:%M") if last else "–"
        chg = m.get("change_count", 0)
        chg_str = f"  ⚡{chg}" if chg > 0 else ""
        info = QLabel(
            f"<b style='color:white;font-size:13px;'>{icon} {m['name']}</b>"
            f"<br><span style='color:rgba(255,255,255,0.45);font-size:11px;'>"
            f"{m['type']} · every {m['interval_minutes']}min · {last_str}{chg_str}</span>"
            f"<br><span style='color:rgba(255,255,255,0.3);font-size:10px;'>{m['query'][:60]}</span>"
        )
        info.setStyleSheet("background:transparent;border:none;")
        info.setTextFormat(Qt.TextFormat.RichText)
        cl.addWidget(info, stretch=1)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color:{status_color};font-size:10px;background:transparent;border:none;"
        )
        cl.addWidget(dot)
        rm = QPushButton("✕")
        rm.setFixedSize(26, 26)
        rm.setStyleSheet(
            "QPushButton{background:rgba(233,69,96,0.1);color:#e94560;border:1px solid rgba(233,69,96,0.2);border-radius:4px;font-size:11px;}QPushButton:hover{background:rgba(233,69,96,0.3);}"
        )
        rm.clicked.connect(lambda _, i=m["id"]: self._remove_monitor(i))
        cl.addWidget(rm)
        return card

    def _add_monitor(self):
        if not self.monitor_engine:
            return
        name = self.name_input.text().strip()
        query = self.query_input.text().strip()
        if not name or not query:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Missing", "Name and Query required.")
            return
        try:
            interval = int(self.interval_input.text().strip() or "60")
        except ValueError:
            interval = 60
        self.monitor_engine.add_monitor(
            name,
            self.type_combo.currentText(),
            query,
            interval,
            self.onchange_combo.currentText(),
        )
        self.name_input.clear()
        self.query_input.clear()
        self.refresh()

    def _remove_monitor(self, mid):
        if self.monitor_engine:
            self.monitor_engine.remove_monitor(mid)
            self.refresh()

    def _check_all(self):
        if self.monitor_engine:
            self.monitor_engine.force_check_all()


class MainWindow(QMainWindow):
    """Moruk OS v5 – Frameless Glass Design."""

    MAX_BUBBLES = 200  # Chat-Bubbles Limit für Memory-Cleanup
    # Signal für thread-sicheren Heartbeat-Callback (Background → Main Thread)
    heartbeat_failure_signal = pyqtSignal(str, str)  # name, reason

    def __init__(self, startup_result=None):
        super().__init__()

        from core.logger import get_logger

        self.log = get_logger("ui")

        self.startup_result = startup_result or {
            "ok": True,
            "issues": [],
            "warnings": [],
            "info": [],
        }
        self.bubble_count = 0
        self._tool_blocks = {}  # tool_name -> CollapsibleToolBlock
        self._current_tool_group = None  # Aktive ToolGroupBlock während Antwort
        self._tool_group_count = 0
        self._deepthink_mode = False  # DeepThink toggle

        # ── Core Systems ──
        self.state = StateManager()
        self.memory = Memory()
        self.tasks = TaskManager()
        self.brain = Brain()
        self.executor = Executor()
        self.reflector = Reflector(memory=self.memory)

        self.tool_router = ToolRouter(self.executor, self.tasks, self.memory)
        self.tool_router.reflector = self.reflector
        self.tool_router.set_brain(self.brain)  # FIX: Plugins bekommen Brain-Referenz
        self.brain.tool_router = self.tool_router

        # ── Token-Saving Engine ──
        self.context_router = ContextRouter()
        self.model_router = ModelRouter()
        self.history_compressor = HistoryCompressor()

        # ── Goal Generation Engine ──
        self.goal_engine = GoalEngine(
            reflector=self.reflector,
            tasks=self.tasks,
            memory=self.memory,
            state=self.state,
        )

        # System Health Monitor
        from core.system_health import SystemHealthMonitor

        self.health_monitor = SystemHealthMonitor()

        self.autonomy = AutonomyLoop(
            self.brain, self.state, self.tasks, self.reflector, self.memory
        )
        self.autonomy.goal_engine = self.goal_engine
        self.autonomy.health_monitor = self.health_monitor
        self.goal_engine.health_monitor = (
            self.health_monitor
        )  # Wire health signals to goal engine
        self.autonomy.thought_signal.connect(self._on_autonomy_thought)
        self.autonomy.status_signal.connect(self._update_status)
        self.autonomy.tool_start_signal.connect(self._on_tool_start)
        self.autonomy.tool_result_signal.connect(self._on_tool_result)
        # Live Activity: Autonomy/Project Tool-Calls weiterleiten
        self.autonomy.tool_start_signal.connect(
            lambda name, params: (
                self.live_activity.sig_tool_start.emit(name, params)
                if hasattr(self, "live_activity")
                else None
            )
        )
        self.autonomy.tool_result_signal.connect(
            lambda name, result, success: (
                self.live_activity.sig_tool_result.emit(name, result, success)
                if hasattr(self, "live_activity")
                else None
            )
        )
        self.autonomy_active = False

        # ── Project Manager ──
        self.project_manager = ProjectManager(
            brain=self.brain,
            deepthink=self.brain.deepthink,
            task_manager=self.tasks,
            reflector=self.reflector,
        )
        self.autonomy.project_manager = self.project_manager

        # ── Live Activity Window ──
        self.live_activity = LiveActivityWindow(brain=self.brain, parent=self)

        # ── Monitor Engine ──
        try:
            from core.monitor_engine import MonitorEngine

            self.monitor_engine = MonitorEngine()
            self.monitor_engine.start(
                brain=self.brain, notify_fn=self._show_monitor_notification
            )
            self.autonomy.monitor_engine = self.monitor_engine
            try:
                import plugins.web_monitor as wm

                wm._engine = self.monitor_engine
            except Exception:
                pass
            self.log.info(
                f"MonitorEngine started ({len(self.monitor_engine.monitors)} monitors)"
            )
        except Exception as e:
            self.monitor_engine = None
            self.log.warning(f"MonitorEngine not available: {e}")
        self.tool_router.set_autonomy_loop(self.autonomy)  # FIX: saubere Referenz

        # ── Heartbeat Monitor ──
        self.heartbeat = Heartbeat(on_failure=self._on_heartbeat_failure)
        self.heartbeat.register("brain", self.brain)
        self.heartbeat.register("autonomy_loop", self.autonomy)
        self.heartbeat.register("task_manager", self.tasks)
        self.heartbeat.start()
        self.heartbeat_failure_signal.connect(self._handle_heartbeat_failure)

        # AutonomyLoop Thread starten (paused) — muss laufen damit Heartbeat ihn überwacht
        self.autonomy.start()

        # ── Frameless Window ──
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1100, 700)
        self.resize(1300, 820)

        # Drag state
        self._drag_pos = None

        # ── Build UI ──
        self._build_ui()
        self.setStyleSheet(DARK_THEME)
        self._show_startup_message()

        # ── System Tray Icon ──
        self.tray_icon = MorukTrayIcon(self)
        self.tray_icon.show()

        self.worker_thread = None
        self.worker = None

        # ── Voice State ──
        self.tts_enabled = False  # Speaker toggle
        self.mic_recording = False  # Mic recording state
        self._mic_thread = None  # STT worker thread

        # ── System Watchdog ──
        self._active_alerts = []
        watchdog.set_alert_callback(self._on_watchdog_alert)
        watchdog.start_watchdog(interval=30)
        self.log.info("System Watchdog gestartet")

    def _build_ui(self):
        # Central widget with rounded corners
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ═══ Custom Title Bar ═══
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(44)
        title_bar.mousePressEvent = self._title_mouse_press
        title_bar.mouseMoveEvent = self._title_mouse_move
        title_bar.mouseDoubleClickEvent = self._title_double_click

        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(16, 0, 8, 0)
        tb_layout.setSpacing(8)

        # Logo/Title
        title_label = QLabel("MORUK")
        title_label.setObjectName("titleLabel")
        tb_layout.addWidget(title_label)

        sub_label = QLabel("AI OS")
        sub_label.setObjectName("titleSubLabel")
        tb_layout.addWidget(sub_label)

        tb_layout.addStretch()

        # Window controls
        min_btn = QPushButton("─")
        min_btn.setObjectName("winBtn")
        min_btn.clicked.connect(self.showMinimized)
        tb_layout.addWidget(min_btn)

        max_btn = QPushButton("□")
        max_btn.setObjectName("winBtn")
        max_btn.clicked.connect(self._toggle_maximize)
        tb_layout.addWidget(max_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.close)
        tb_layout.addWidget(close_btn)

        outer.addWidget(title_bar)

        # ═══ Control Bar ═══
        control_bar = QWidget()
        control_bar.setObjectName("controlBar")
        cb_layout = QHBoxLayout(control_bar)
        cb_layout.setContentsMargins(16, 4, 16, 4)
        cb_layout.setSpacing(8)

        self.status_label = QLabel("● Ready")
        self.status_label.setObjectName("statusLabel")
        cb_layout.addWidget(self.status_label)

        cb_layout.addStretch()

        self.autonomy_btn = QPushButton("⟳ Autonomy: OFF")
        self.autonomy_btn.setObjectName("autonomyBtn")
        self.autonomy_btn.clicked.connect(self._toggle_autonomy)
        cb_layout.addWidget(self.autonomy_btn)

        recovery_btn = QPushButton("🔧")
        recovery_btn.setObjectName("iconBtn")
        recovery_btn.setToolTip("Recovery: Restore last working state")
        recovery_btn.clicked.connect(self._emergency_recovery)
        cb_layout.addWidget(recovery_btn)

        history_btn = QPushButton("🕐")
        history_btn.setObjectName("iconBtn")
        history_btn.setToolTip("Chat History")
        history_btn.clicked.connect(self._toggle_history_panel)
        cb_layout.addWidget(history_btn)

        live_btn = QPushButton("⚡")
        live_btn.setObjectName("iconBtn")
        live_btn.setToolTip("Live Activity — Zeige Code & Tool-Calls in Echtzeit")
        live_btn.clicked.connect(self._toggle_live_activity)
        cb_layout.addWidget(live_btn)

        monitor_btn = QPushButton("🛰")
        monitor_btn.setObjectName("iconBtn")
        monitor_btn.setToolTip("Web Monitors")
        monitor_btn.clicked.connect(self._open_monitor_window)
        cb_layout.addWidget(monitor_btn)

        sidebar_btn = QPushButton("☰")
        sidebar_btn.setObjectName("iconBtn")
        sidebar_btn.setToolTip("Toggle Sidebar")
        sidebar_btn.clicked.connect(self._toggle_sidebar)
        cb_layout.addWidget(sidebar_btn)

        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("iconBtn")
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self._open_settings)
        cb_layout.addWidget(settings_btn)

        outer.addWidget(control_bar)

        # ═══ Main Content: Chat | Sidebar ═══
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(0)
        self.splitter.setChildrenCollapsible(False)

        # ── History Panel (links, standardmäßig versteckt) ──
        self.history_panel = QWidget()
        self.history_panel.setObjectName("historyPanel")
        self.history_panel.setStyleSheet("""
            #historyPanel {
                background: #0d0f1c;
                border-right: 1px solid rgba(255,255,255,0.08);
            }
        """)
        self.history_panel.setMinimumWidth(0)
        self.history_panel.setMaximumWidth(260)
        hp_layout = QVBoxLayout(self.history_panel)
        hp_layout.setContentsMargins(8, 12, 8, 8)
        hp_layout.setSpacing(6)

        hp_title = QLabel("💬 Chat History")
        hp_title.setStyleSheet(
            "color:rgba(255,255,255,0.5);font-size:11px;font-weight:bold;padding:4px 0;"
        )
        hp_layout.addWidget(hp_title)

        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                background: transparent; border: none;
                color: rgba(255,255,255,0.8); font-size: 12px;
            }
            QListWidget::item {
                padding: 8px 6px; border-radius: 6px;
                border-bottom: 1px solid rgba(255,255,255,0.05);
            }
            QListWidget::item:hover { background: rgba(255,255,255,0.07); }
            QListWidget::item:selected { background: rgba(233,69,96,0.2); color: white; }
        """)
        self.history_list.itemClicked.connect(self._load_history_session)
        hp_layout.addWidget(self.history_list)

        new_chat_btn = QPushButton("＋ New Chat")
        new_chat_btn.setStyleSheet("""
            QPushButton {
                background: rgba(233,69,96,0.15); color: #e94560;
                border: 1px solid rgba(233,69,96,0.3); border-radius: 6px;
                padding: 7px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(233,69,96,0.28); }
        """)
        new_chat_btn.clicked.connect(self._new_chat_session)
        hp_layout.addWidget(new_chat_btn)

        self.splitter.addWidget(self.history_panel)
        self.splitter.setChildrenCollapsible(True)
        self.splitter.setHandleWidth(1)

        # ── Chat Area ──
        chat_widget = QWidget()
        chat_widget.setStyleSheet("background: transparent;")
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(12, 4, 6, 12)
        chat_layout.setSpacing(8)

        # Scrollable Chat
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setObjectName("chatScroll")
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.chat_scroll.setAcceptDrops(True)

        self.chat_container = QWidget()
        self.chat_container.setObjectName("chatContainer")
        self.chat_container.setAcceptDrops(True)
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()

        # Forward drops from chat area to input field
        def chat_drag_enter(event):
            if event.mimeData().hasUrls() or event.mimeData().hasImage():
                event.acceptProposedAction()

        def chat_drop(event):
            self.input_field.dropEvent(event)

        self.chat_scroll.dragEnterEvent = chat_drag_enter
        self.chat_scroll.dropEvent = chat_drop
        self.chat_container.dragEnterEvent = chat_drag_enter
        self.chat_container.dropEvent = chat_drop

        self.chat_scroll.setWidget(self.chat_container)
        chat_layout.addWidget(self.chat_scroll, stretch=1)

        # ── Attachment Preview Bar ──
        self.attachment_bar = QWidget()
        self.attachment_bar.setStyleSheet("""
            QWidget { background: transparent; }
        """)
        self.attachment_bar.hide()
        self.attachment_bar_layout = QHBoxLayout(self.attachment_bar)
        self.attachment_bar_layout.setContentsMargins(8, 4, 8, 0)
        self.attachment_bar_layout.setSpacing(6)
        self.attachment_bar_layout.addStretch()
        chat_layout.addWidget(self.attachment_bar)

        # ── Input Area ──
        # Outer row: [🧠 Button] [Input Wrapper]
        input_outer = QWidget()
        input_outer_layout = QHBoxLayout(input_outer)
        input_outer_layout.setContentsMargins(0, 0, 0, 0)
        input_outer_layout.setSpacing(6)

        # Linke Button-Spalte: 🧠 oben, 🏗 unten
        left_btns = QWidget()
        left_btns_layout = QVBoxLayout(left_btns)
        left_btns_layout.setContentsMargins(0, 0, 0, 0)
        left_btns_layout.setSpacing(3)

        BTN_STYLE = """
            QPushButton {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 17px;
                font-size: 15px;
                padding: 0;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
            QPushButton:checked {{
                background: rgba(233, 69, 96, 0.3);
                border: 1px solid #e94560;
            }}
        """

        # 🧠 DeepThink Toggle
        self.deepthink_btn = QPushButton("🧠")
        self.deepthink_btn.setObjectName("deepthinkBtn")
        self.deepthink_btn.setFixedSize(36, 36)
        self.deepthink_btn.setToolTip("DeepThink Modus: Stärkeres Supervisor-Modell")
        self.deepthink_btn.setCheckable(True)
        self.deepthink_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.deepthink_btn.setStyleSheet(BTN_STYLE)
        self.deepthink_btn.clicked.connect(self._toggle_deepthink)
        left_btns_layout.addWidget(self.deepthink_btn)

        # 🏗 Project Button
        self.project_btn = QPushButton("🏗")
        self.project_btn.setObjectName("projectBtn")
        self.project_btn.setFixedSize(36, 36)
        self.project_btn.setToolTip("Projekt starten — DeepThink zerlegt in Subtasks")
        self.project_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.project_btn.setStyleSheet(BTN_STYLE)
        self.project_btn.clicked.connect(self._on_project_btn_clicked)
        left_btns_layout.addWidget(self.project_btn)

        # Spinner Timer für Project Button
        self._project_spinner_frames = ["◐", "◓", "◑", "◒"]
        self._project_spinner_idx = 0
        self._project_spinner_timer = QTimer()
        self._project_spinner_timer.timeout.connect(self._spin_project_btn)

        input_outer_layout.addWidget(left_btns)

        input_wrapper = QWidget()
        input_wrapper.setObjectName("inputArea")
        input_inner = QHBoxLayout(input_wrapper)
        input_inner.setContentsMargins(4, 4, 4, 4)
        input_inner.setSpacing(6)
        input_outer_layout.addWidget(input_wrapper)

        self.input_field = ChatInput()
        self.input_field.setObjectName("inputField")
        self.input_field.setPlaceholderText("Message Moruk OS...")
        self.input_field.setMaximumHeight(80)
        self.input_field.setFont(QFont("Segoe UI", 13))
        self.input_field.send_signal.connect(self._send_message)
        self.input_field.file_attached.connect(self._on_file_attached)
        input_inner.addWidget(self.input_field)

        # 🎤 Mic Button (Push-to-Talk)
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setObjectName("micBtn")
        self.mic_btn.setFixedSize(38, 38)
        self.mic_btn.setToolTip("Push-to-Talk: Klick zum Aufnehmen, nochmal zum Senden")
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 19px;
                font-size: 16px;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
            }
        """)
        self.mic_btn.clicked.connect(self._toggle_mic)
        input_inner.addWidget(self.mic_btn)

        send_btn = QPushButton("→")
        send_btn.setObjectName("sendBtn")
        send_btn.setFixedSize(44, 38)
        send_btn.setFont(QFont("Segoe UI", 16))
        send_btn.clicked.connect(self._send_message)
        input_inner.addWidget(send_btn)

        # 🔊 Speaker Toggle (Moruk's Voice)
        self.speaker_btn = QPushButton("🔇")
        self.speaker_btn.setObjectName("speakerBtn")
        self.speaker_btn.setFixedSize(38, 38)
        self.speaker_btn.setToolTip("Moruk's Stimme: An/Aus")
        self.speaker_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.speaker_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 19px;
                font-size: 16px;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
            }
        """)
        self.speaker_btn.clicked.connect(self._toggle_speaker)
        input_inner.addWidget(self.speaker_btn)

        chat_layout.addWidget(input_outer)

        self.splitter.addWidget(chat_widget)
        self.splitter.setSizes([0, 1060])
        self.history_panel.hide()

        # ── Sidebar außerhalb Splitter → keine Pfeile ──
        self.sidebar = Sidebar(
            self.tasks,
            self.memory,
            self.reflector,
            self.state,
            goal_engine=self.goal_engine,
            self_model=self.tool_router.self_model,
            main_window=self,
        )
        self.sidebar.setFixedWidth(360)
        self.sidebar.hide()

        # Project Progress Signal → Sidebar
        self.autonomy.project_progress_signal.connect(
            self.sidebar.update_project_progress
        )

        content_row = QHBoxLayout()
        content_row.setSpacing(0)
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.addWidget(self.splitter, stretch=1)
        content_row.addWidget(self.sidebar)

        outer.addLayout(content_row, stretch=1)

        # ── Resize Grip ──
        grip = QSizeGrip(self)
        grip.setStyleSheet("background: transparent;")

    # ══ Frameless Window Dragging ══════════════════════════════

    def _title_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def _title_mouse_move(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _title_double_click(self, event):
        self._toggle_maximize()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ══ Chat Bubbles ══════════════════════════════════════════

    def _append_message(self, role: str, text: str, attachments: list = None):
        """Erstellt eine Chat-Blase und fügt sie zum Chat hinzu."""
        bubble = ChatBubble(role, text, attachments=attachments)

        # Alignment: User rechts, Rest links
        wrapper = QHBoxLayout()
        wrapper.setContentsMargins(0, 0, 0, 0)

        if role == "user":
            wrapper.addStretch()
            bubble.setMaximumWidth(600)
            wrapper.addWidget(bubble)
        elif role in ("tool_exec", "tool_result", "reflection"):
            bubble.setMaximumWidth(700)
            wrapper.addWidget(bubble)
            wrapper.addStretch()
        else:
            bubble.setMaximumWidth(650)
            wrapper.addWidget(bubble)
            wrapper.addStretch()

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(wrapper)

        # Vor dem Stretch einfügen
        count = self.chat_layout.count()
        self.chat_layout.insertWidget(count - 1, container)
        self.bubble_count += 1

        # Memory Cleanup: Alte Bubbles entfernen wenn Limit erreicht
        while self.bubble_count > self.MAX_BUBBLES:
            # Item 0 ist die älteste Bubble (Stretch ist am Ende)
            item = self.chat_layout.itemAt(0)
            if item and item.widget():
                widget = item.widget()
                self.chat_layout.removeWidget(widget)
                widget.deleteLater()
                self.bubble_count -= 1
            else:
                break

        # Auto-scroll nach unten
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.chat_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ══ Startup ═══════════════════════════════════════════════

    def _show_startup_message(self):
        if self.state.is_first_session():
            self._append_message(
                "system",
                "🟢 MORUK OS initialized. First session.\n"
                "Configure your brain: click ⚙ to set Provider + API Key.",
            )
        else:
            session = self.state.get("session_count")
            interactions = self.state.get("total_interactions")
            self._append_message(
                "system",
                f"🔄 Session #{session} | {interactions} interactions | State restored.",
            )

            stats = self.reflector.get_full_stats()
            if stats.get("total_actions", 0) > 0:
                self._append_message(
                    "reflection",
                    f"{stats['total_actions']} actions | "
                    f"{stats['success_rate']:.0f}% success | "
                    f"streak: {stats.get('streak', {}).get('current', 0)}",
                )

        # Startup Check Ergebnisse — Health Summary
        info = self.startup_result.get("info", [])
        health_parts = [
            i for i in info if any(k in i for k in ["Disk", "RAM", "Watchdog", "DB"])
        ]
        if health_parts and not self.state.is_first_session():
            self._append_message("reflection", "System: " + " | ".join(health_parts))

        if self.startup_result.get("warnings"):
            for w in self.startup_result["warnings"]:
                self._append_message("system", f"⚠ {w}")

        if self.startup_result.get("issues"):
            for issue in self.startup_result["issues"]:
                self._append_message("system", f"❌ {issue}")

        active = self.tasks.get_active_tasks()
        if active:
            task_info = ", ".join([t["title"] for t in active[:3]])
            self._append_message("system", f"📋 {task_info}")

        if not self.brain.is_configured():
            self._append_message(
                "system", "⚠ Click ⚙ to configure your brain provider."
            )

    # ══ Message Handling ══════════════════════════════════════

    def _send_message(self):
        text = self.input_field.toPlainText().strip()
        attachments = self.input_field.get_attachments()

        if not text and not attachments:
            return

        self.input_field.clear()
        self.input_field.clear_attachments()
        self._clear_attachment_bar()

        # Bubble mit Attachments anzeigen
        self._append_message("user", text, attachments=attachments)
        self.state.record_interaction()
        self.memory.remember_short(text or "[file attachment]", category="user_input")

        # Auto-detect "merke dir" → direkt in long-term memory + user profile speichern
        if text:
            txt_lower = text.lower().strip()
            merke_prefixes = [
                "merke dir:",
                "merke dir ",
                "remember:",
                "remember ",
                "save:",
                "speichere:",
            ]
            for prefix in merke_prefixes:
                if txt_lower.startswith(prefix):
                    info = text[len(prefix) :].strip()
                    if info:
                        personal_keywords = [
                            "liebling",
                            "favorite",
                            "mag ",
                            "liebe ",
                            "hasse ",
                            "mein name",
                            "ich bin",
                            "ich arbeite",
                            "mein job",
                            "mein hobby",
                            "ich wohne",
                            "meine familie",
                            "ich heiße",
                            "mein alter",
                            "ich esse",
                            "ich trinke",
                            "ich spiele",
                            "ich lese",
                            "mein beruf",
                            "ich mag",
                            "my name",
                            "i am",
                            "my hobby",
                            "my job",
                            "i live",
                            "i eat",
                            "i drink",
                        ]
                        category = (
                            "personal"
                            if any(kw in txt_lower for kw in personal_keywords)
                            else "learned"
                        )
                        self.memory.remember_long(info, category=category)
                    break

        # ── Project Command ──
        if text.startswith(("/project ", "!project ")):
            prompt = text.split(" ", 1)[1]
            self.autonomy.queue_project(prompt)
            self._append_message(
                "system",
                f"🏗 Projekt gestartet: {prompt[:80]}...\n"
                "DeepThink zerlegt die Aufgabe in Subtasks.",
            )
            self.input_field.setEnabled(True)
            return

        self._update_status("⟳ Thinking...")
        self.input_field.setEnabled(False)

        # Message für LLM bauen (mit Datei-Info)
        llm_message = text or ""
        file_context = ""
        for filepath, mime_type, b64_data in attachments:
            fname = os.path.basename(filepath)
            if mime_type and mime_type.startswith("image/"):
                file_context += f"\n[Attached image: {fname} ({mime_type})]"
                file_context += f"\n[Image saved at: {filepath}]"
                # Hinweis: Echte Vision-API braucht base64 im Message-Format
                # Das wird von brain.py unterstützt wenn Provider es kann
            else:
                file_context += (
                    f"\n[Attached file: {fname} ({mime_type}) at {filepath}]"
                )

        if file_context:
            llm_message += f"\n\n--- ATTACHED FILES ---{file_context}"

        # ── Intelligent Context Routing ──
        classification = self.context_router.classify(
            text or "", has_attachments=bool(attachments)
        )
        intent = classification["intent"]
        depth = classification["depth"]

        # Context nur laden was nötig ist
        context = self.context_router.build_context(
            classification,
            state=self.state,
            memory=self.memory,
            tasks=self.tasks,
            reflector=self.reflector,
            query=text or "",
        )

        # History Compression
        if self.history_compressor.should_compress(self.brain.conversation_history):
            self.brain.conversation_history = self.history_compressor.compress(
                self.brain.conversation_history
            )

        # Max iterations basierend auf Depth
        max_iter = {1: 1, 2: 3, 3: 10, 4: 10, 5: 10}.get(depth, 10)

        self.log.info(
            f"Router: intent={intent}, depth={depth}, max_iter={max_iter}, "
            f"context_len={len(context.split())} words"
        )

        self.worker_thread = QThread()
        if self._deepthink_mode:
            self.log.info("DeepThink Modus aktiv — force_deepthink=True")
        self.worker = ThinkWorker(
            self.brain,
            llm_message,
            context,
            max_iterations=max_iter,
            depth=depth,
            force_deepthink=self._deepthink_mode,
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_response)
        self.worker.error.connect(self._on_error)
        self.worker.tool_start.connect(self._on_tool_start)
        self.worker.tool_result.connect(self._on_tool_result)
        self.worker.token_received.connect(self._on_token)
        # Live Activity Window immer verbinden (auch wenn versteckt)
        if hasattr(self, "live_activity"):
            self.live_activity.connect_worker(self.worker)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)

        # Streaming-Bubble vorbereiten
        self._streaming_bubble = None
        self._streaming_text = ""

        self.worker_thread.start()

        # Autonomy Loop für 120s pausieren damit er nicht gleich wiederholt
        if hasattr(self, "autonomy") and self.autonomy:
            self.autonomy._user_active_until = __import__("time").time() + 120

    # ══ Attachment Preview ══════════════════════════════════

    def _on_file_attached(self, filepath: str, mime_type: str, thumb):
        """Zeigt Attachment-Vorschau über dem Input."""
        self.attachment_bar.show()

        # Preview-Widget
        preview = QFrame()
        preview.setStyleSheet("""
            QFrame {
                background-color: rgba(22, 33, 62, 0.7);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px;
                padding: 4px;
            }
        """)
        p_layout = QVBoxLayout(preview)
        p_layout.setContentsMargins(6, 4, 6, 4)
        p_layout.setSpacing(2)

        # Thumbnail oder Icon
        if isinstance(thumb, QPixmap) and not thumb.isNull():
            img_label = QLabel()
            img_label.setPixmap(
                thumb.scaled(
                    80,
                    80,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_label.setStyleSheet("background: transparent; border: none;")
            p_layout.addWidget(img_label)
        else:
            icon = "📄" if "pdf" in (mime_type or "") else "📎"
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(
                "font-size: 28px; background: transparent; border: none;"
            )
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            p_layout.addWidget(icon_label)

        # Filename
        fname = os.path.basename(filepath)
        name_label = QLabel(fname[:20])
        name_label.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 10px; background: transparent; border: none;"
        )
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p_layout.addWidget(name_label)

        # Remove Button
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: rgba(233,69,96,0.3);
                color: white;
                border: none;
                border-radius: 9px;
                font-size: 10px;
                padding: 0;
            }
            QPushButton:hover { background: rgba(233,69,96,0.7); }
        """)
        remove_btn.clicked.connect(
            lambda checked, p=preview, fp=filepath: self._remove_attachment(p, fp)
        )
        p_layout.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Vor dem Stretch einfügen
        count = self.attachment_bar_layout.count()
        self.attachment_bar_layout.insertWidget(count - 1, preview)

    def _remove_attachment(self, preview_widget, filepath):
        """Entfernt ein Attachment."""
        preview_widget.deleteLater()
        # Aus input_field entfernen
        self.input_field.attached_files = [
            (p, m, d) for p, m, d in self.input_field.attached_files if p != filepath
        ]
        if not self.input_field.attached_files:
            self.attachment_bar.hide()

    def _clear_attachment_bar(self):
        """Leert die Attachment-Vorschau."""
        while self.attachment_bar_layout.count() > 1:  # Stretch bleibt
            item = self.attachment_bar_layout.itemAt(0)
            if item and item.widget():
                item.widget().deleteLater()
                self.attachment_bar_layout.removeItem(item)
            else:
                break
        self.attachment_bar.hide()

    def _on_token(self, token: str):
        """Streaming: Token für Token in eine Live-Bubble schreiben."""
        if self._streaming_bubble is None:
            self._streaming_text = token
            self._streaming_bubble = ChatBubble("assistant", token)
            self._streaming_bubble.setMaximumWidth(650)

            wrapper = QHBoxLayout()
            wrapper.setContentsMargins(0, 0, 0, 0)
            wrapper.addWidget(self._streaming_bubble)
            wrapper.addStretch()

            self._streaming_container = QWidget()
            self._streaming_container.setStyleSheet("background: transparent;")
            self._streaming_container.setLayout(wrapper)

            count = self.chat_layout.count()
            self.chat_layout.insertWidget(count - 1, self._streaming_container)
            self.bubble_count += 1
        else:
            self._streaming_text += token
            label = self._streaming_bubble.findChild(QLabel, "bubbleText")
            if label:
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setText(self._streaming_text)

        scrollbar = self.chat_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_response(self, response: str):
        if self._current_tool_group is not None:
            self._current_tool_group.finalize()
            self._current_tool_group = None

        # Wenn Antwort leer → Agent hat nur Tools genutzt ohne Text
        # Zeige eine kurze Zusammenfassung statt leerer Blase
        if not response or not response.strip():
            tool_count = self._tool_group_count
            if tool_count > 0:
                response = (
                    f"✅ {tool_count} Tool{'s' if tool_count > 1 else ''} ausgeführt."
                )
            else:
                response = "✅ Erledigt."

        if self._streaming_bubble is not None and self._streaming_container is not None:
            # Final: Markdown rendern
            label = self._streaming_bubble.findChild(QLabel, "bubbleText")
            if label:
                label.setTextFormat(Qt.TextFormat.RichText)
                label.setText(markdown_to_html(response))
            self._streaming_bubble.raw_text = response
            self._streaming_bubble = None
            self._streaming_container = None
            self._streaming_text = ""
        else:
            self._append_message("assistant", response)

        self._tool_group_count = 0  # Reset für nächste Antwort
        self._update_status("● Ready")
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        self.memory.remember_short(response[:200], category="assistant_response")
        self.sidebar.refresh_all()
        self._show_token_usage()

        # TTS: Moruk spricht die Antwort wenn Speaker aktiviert
        if self.tts_enabled and response.strip():
            self._speak_response(response)

    def _show_token_usage(self):
        """Zeigt Token-Nutzung als kleine Info-Zeile im Chat."""
        try:
            usage = self.brain.last_token_usage
            if not usage or not usage.get("total"):
                return
            inp = usage.get("input", 0)
            out = usage.get("output", 0)
            total = usage.get("total", 0)
            # Kosten schaetzen (Anthropic claude-3.5-sonnet: $3/$15 per 1M)
            model = self.brain.settings.get("model", "")
            if "claude-3-5" in model or "claude-3.5" in model:
                cost = (inp * 3.0 + out * 15.0) / 1_000_000
            elif "claude-3-opus" in model:
                cost = (inp * 15.0 + out * 75.0) / 1_000_000
            elif "claude-3" in model:
                cost = (inp * 0.25 + out * 1.25) / 1_000_000
            elif "gpt-4o" in model:
                cost = (inp * 2.5 + out * 10.0) / 1_000_000
            elif "gpt-4" in model:
                cost = (inp * 30.0 + out * 60.0) / 1_000_000
            elif "gpt-3.5" in model:
                cost = (inp * 0.5 + out * 1.5) / 1_000_000
            else:
                cost = None
            if cost is not None:
                info = f"📊 {inp:,} in | {out:,} out | ${cost:.4f}"
            else:
                info = f"📊 {inp:,} in | {out:,} out | {total:,} total"
            self._append_message("token_info", info)
        except Exception as e:
            self.log.warning(f"Token usage display failed: {e}")

    def _on_error(self, error: str):
        if self._current_tool_group is not None:
            self._current_tool_group.finalize()
            self._current_tool_group = None
        self._append_message("system", f"❌ {error}")
        self._update_status("● Error")
        self.input_field.setEnabled(True)
        self.input_field.setFocus()

    def _on_tool_start(self, tool_name: str, params: str):
        self._update_status(f"⚡ {tool_name}...")
        self._tool_group_count += 1  # FIX: Counter war nie inkrementiert
        # Neuen CollapsibleToolBlock erstellen
        block = CollapsibleToolBlock(tool_name, params)
        self._tool_blocks[tool_name] = block
        # Zur aktuellen Group hinzufügen oder neue Group erstellen
        if self._current_tool_group is None:
            self._current_tool_group = ToolGroupBlock()
            wrapper = QHBoxLayout()
            wrapper.setContentsMargins(0, 0, 0, 0)
            self._current_tool_group.setMaximumWidth(700)
            wrapper.addWidget(self._current_tool_group)
            wrapper.addStretch()
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container.setLayout(wrapper)
            count = self.chat_layout.count()
            self.chat_layout.insertWidget(count - 1, container)
            self.bubble_count += 1
        self._current_tool_group.add_tool(block)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _on_tool_result(self, tool_name: str, result: str, success: bool):
        # Block mit Result füllen (über Group)
        if self._current_tool_group:
            self._current_tool_group.set_result(tool_name, result, success)
        else:
            block = self._tool_blocks.get(tool_name)
            if block:
                block.set_result(result, success)
        if tool_name in self._tool_blocks:
            del self._tool_blocks[tool_name]
        self.sidebar.refresh_all()

    # ══ Autonomy ══════════════════════════════════════════════

    def _toggle_autonomy(self):
        if self.autonomy_active:
            self.autonomy.pause_autonomy()
            self.autonomy_active = False
            self.autonomy_btn.setText("⟳ Autonomy: OFF")
            self.sidebar.refresh_timer.setInterval(5000)  # Normal refresh
        else:
            if not self.brain.is_configured():
                self._append_message("system", "⚠ Configure brain first.")
                return
            if not self.autonomy.isRunning():
                self.autonomy.start()
            self.autonomy.start_autonomy()
            self.autonomy_active = True
            self.autonomy_btn.setText("⟳ Autonomy: ON")
            self.sidebar.refresh_timer.setInterval(
                2000
            )  # Schnellerer Refresh während Autonomy

    def _emergency_recovery(self):
        """Notfall-Recovery: Stellt letzten Snapshot wieder her."""
        from PyQt6.QtWidgets import QMessageBox

        try:
            from core.recovery import RecoveryManager

            recovery = RecoveryManager()

            # Health Check
            health = recovery.health_check()
            snapshots = recovery.get_snapshots()

            if health["healthy"] and not snapshots:
                QMessageBox.information(
                    self,
                    "🔧 Recovery",
                    "✓ System is healthy!\n\n"
                    f"Checked {health['checked']} files — no issues detected.\n\n"
                    "Recovery is not needed.",
                )
                return

            if not snapshots:
                QMessageBox.warning(
                    self,
                    "🔧 Recovery",
                    "No snapshots available yet.\n\n"
                    "Snapshots are created automatically before each self_edit.\n"
                    "Once Moruk modifies his own code, snapshots will appear here.\n\n"
                    "For manual recovery, run in terminal:\n"
                    "  cd <moruk-os-dir> && python recovery.py",
                )
                return

            # ── STEP 1: Info-Dialog ──
            info_msg = "🔧 RECOVERY SYSTEM\n\n"

            if health["issues"]:
                info_msg += f"⚠ {len(health['issues'])} broken files detected:\n"
                for issue in health["issues"][:5]:
                    info_msg += f"  • {issue['file']}: {issue['error']}\n"
                info_msg += "\n"
            else:
                info_msg += "✓ All files currently healthy.\n\n"

            info_msg += f"📸 {len(snapshots)} snapshot(s) available.\n"
            info_msg += f"Latest: {snapshots[0]['id']}\n"
            info_msg += f"Reason: {snapshots[0].get('reason', 'unknown')}\n\n"
            info_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            info_msg += "What Recovery RESTORES:\n"
            info_msg += "  → Source code (core/*.py, ui/*.py)\n"
            info_msg += "  → Config files\n\n"
            info_msg += "What Recovery PRESERVES (not touched!):\n"
            info_msg += "  ✓ Memories & learned knowledge\n"
            info_msg += "  ✓ Self-Profile & confidence scores\n"
            info_msg += "  ✓ Tasks, goals & reflections\n"
            info_msg += "  ✓ API keys & settings\n"
            info_msg += "  ✓ Learned plugins & skills\n"
            info_msg += "  ✓ Deleted plugins recovered from snapshot\n"
            info_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            info_msg += "Do you want to proceed?"

            reply = QMessageBox.warning(
                self,
                "🔧 Recovery — Confirmation",
                info_msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )  # Default = No

            if reply != QMessageBox.StandardButton.Yes:
                return

            # ── STEP 2: Zweite Bestätigung ──
            confirm = QMessageBox.question(
                self,
                "🔧 Final Confirmation",
                f"Are you sure?\n\n"
                f"This will restore {snapshots[0].get('file_count', '?')} source files "
                f"to the state from:\n{snapshots[0].get('created_at', 'unknown')}\n\n"
                f"Moruk OS needs to restart after recovery.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if confirm != QMessageBox.StandardButton.Yes:
                return

            # ── STEP 3: Recovery ausführen ──
            result = recovery.restore_snapshot()
            if result["success"]:
                QMessageBox.information(
                    self,
                    "✓ Recovery Complete",
                    f"Successfully restored {result['restored']} files!\n\n"
                    f"Snapshot: {result['snapshot_id']}\n\n"
                    "⚠ Please restart Moruk OS now\n"
                    "for changes to take effect.",
                )
                if hasattr(self, "tray_icon"):
                    self.tray_icon.show_notification(
                        "✓ Recovery Complete",
                        f"Restored {result['restored']} files. Please restart.",
                    )
            else:
                QMessageBox.warning(
                    self,
                    "Recovery Error",
                    f"Recovery had errors:\n"
                    f"{result.get('error', str(result.get('errors', 'Unknown')))}\n\n"
                    "Try manual recovery:\n"
                    "  cd <moruk-os-dir> && python recovery.py",
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Recovery Error",
                f"Recovery system failed: {str(e)}\n\n"
                "Try manual recovery in terminal:\n"
                "  cd <moruk-os-dir> && python recovery.py",
            )

    def _on_autonomy_thought(self, thought: str):
        self._append_message("assistant", thought)
        self.sidebar.refresh_all()
        # Tray-Notification wenn Fenster minimiert
        if self.isMinimized() or not self.isActiveWindow():
            if hasattr(self, "tray_icon"):
                self.tray_icon.show_notification("🤖 Moruk", thought[:100])

    # ══ Voice Controls ═══════════════════════════════════════

    def _toggle_speaker(self):
        """Toggle Moruk's TTS Stimme an/aus."""
        self.tts_enabled = not self.tts_enabled
        if self.tts_enabled:
            self.speaker_btn.setText("🔊")
            self.speaker_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(0, 210, 255, 0.15);
                    border: 1px solid rgba(0, 210, 255, 0.4);
                    border-radius: 19px;
                    font-size: 16px;
                    padding: 0;
                }
                QPushButton:hover { background: rgba(0, 210, 255, 0.25); }
            """)
            self._append_message("system", "🔊 Moruk's Stimme aktiviert")
        else:
            self.speaker_btn.setText("🔇")
            self.speaker_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.06);
                    border: 1px solid rgba(255,255,255,0.12);
                    border-radius: 19px;
                    font-size: 16px;
                    padding: 0;
                }
                QPushButton:hover { background: rgba(255,255,255,0.12); }
            """)
            self._append_message("system", "🔇 Moruk's Stimme deaktiviert")

    def _speak_response(self, text: str):
        """Sendet Text an das Voice Plugin (TTS) in einem eigenen Thread."""
        import threading

        # Markdown/HTML Tags und Tool-Blöcke rausfiltern
        import re

        clean = re.sub(r"<[^>]+>", "", text)  # HTML Tags
        clean = re.sub(r"```[\s\S]*?```", "", clean)  # Code Blocks
        clean = re.sub(r"`[^`]+`", "", clean)  # Inline Code
        clean = re.sub(r"\[.*?\]\(.*?\)", "", clean)  # Links
        clean = re.sub(r"[*_#>~|]", "", clean)  # Markdown Formatierung
        clean = re.sub(r"📊.*$", "", clean, flags=re.MULTILINE)  # Token Info
        clean = re.sub(r"✅ \d+ Tools? ausgeführt\.", "", clean)  # Tool Summary
        clean = clean.strip()

        if not clean or len(clean) < 3:
            return

        # Max Länge begrenzen (zu lange Texte nerven)
        if len(clean) > 800:
            clean = clean[:800] + "..."

        def _speak():
            try:
                import plugins.voice as voice_plugin

                voice_plugin.execute({"text": clean})
            except Exception as e:
                self.log.error(f"TTS error: {e}")

        t = threading.Thread(target=_speak, daemon=True)
        t.start()

    def _on_project_btn_clicked(self):
        """Projekt starten oder laufendes Projekt abbrechen."""
        if self._project_spinner_timer.isActive():
            # Projekt läuft → abbrechen
            self._stop_project()
        else:
            self._start_project()

    def _start_project(self):
        """Startet einen Projekt-Task aus dem aktuellen Input-Text."""
        text = self.input_field.toPlainText().strip()
        if not text:
            self._append_message(
                "system", "🏗 Bitte zuerst einen Projekt-Prompt eingeben."
            )
            return
        if not self.brain.is_configured():
            self._append_message("system", "Bitte zuerst Brain konfigurieren.")
            return
        self.input_field.clear()
        self._append_message("user", text)
        self.autonomy.queue_project(text)
        preview = text[:80]
        self._append_message(
            "system",
            f"🏗 Projekt gestartet: {preview}... — DeepThink zerlegt in Subtasks.",
        )
        if not self.autonomy.isRunning():
            self.autonomy.start()
        if not self.autonomy_active:
            self.autonomy.start_autonomy()
            self.autonomy_active = True
            self.autonomy_btn.setText("⟳ Autonomy: ON")
            self.sidebar.refresh_timer.setInterval(2000)

        # Spinner starten + Input deaktivieren
        self._project_spinner_timer.start(200)
        self.input_field.setEnabled(False)
        self.input_field.setPlaceholderText(
            "🏗 Projekt läuft... (🏗 klicken zum Abbrechen)"
        )
        self.project_btn.setToolTip("Projekt abbrechen")

    def _stop_project(self):
        """Bricht laufendes Projekt ab."""
        if hasattr(self, "project_manager") and self.project_manager:
            self.project_manager.stop()
        self._project_running_done()
        self._append_message("system", "⏹ Projekt abgebrochen.")

    def _project_running_done(self):
        """Spinner stoppen + Input wieder aktivieren."""
        self._project_spinner_timer.stop()
        self.project_btn.setText("🏗")
        self.project_btn.setToolTip("Projekt starten — DeepThink zerlegt in Subtasks")
        self.input_field.setEnabled(True)
        self.input_field.setPlaceholderText("Message Moruk OS...")

    def _spin_project_btn(self):
        """Dreht den Spinner im Project Button — stoppt wenn Projekt fertig."""
        # Prüfen ob Projekt noch läuft
        if hasattr(self, "project_manager") and not self.project_manager.is_running:
            self._project_running_done()
            return
        self._project_spinner_idx = (self._project_spinner_idx + 1) % 4
        self.project_btn.setText(
            self._project_spinner_frames[self._project_spinner_idx]
        )

    def _toggle_deepthink(self):
        """Schaltet DeepThink-Modus ein/aus."""
        self._deepthink_mode = self.deepthink_btn.isChecked()
        if self._deepthink_mode:
            # Modellname aus Brain's DeepThink-Objekt lesen
            dt = self.brain.deepthink  # FIX: brain hat deepthink, nicht tool_router
            model = self.brain.settings.get("deepthink_model", "DeepThink") if dt else "DeepThink"
            self._update_status(f"🧠 DeepThink aktiv: {str(model)[:30]}")
            self.input_field.setPlaceholderText("🧠 DeepThink Modus aktiv...")
        else:
            self._update_status("● Ready")
            self.input_field.setPlaceholderText("Message Moruk OS...")

    def _toggle_mic(self):
        """Push-to-Talk: Startet/Stoppt Mikrofon-Aufnahme."""
        if self.mic_recording:
            self._stop_mic()
        else:
            self._start_mic()

    def _start_mic(self):
        """Startet Mikrofon-Aufnahme."""
        self.mic_recording = True
        self.mic_btn.setText("⏹")
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(233, 69, 96, 0.3);
                border: 2px solid rgba(233, 69, 96, 0.7);
                border-radius: 19px;
                font-size: 16px;
                padding: 0;
            }
            QPushButton:hover { background: rgba(233, 69, 96, 0.5); }
        """)
        self.mic_btn.setToolTip("Aufnahme läuft... Klick zum Stoppen")
        self.input_field.setPlaceholderText("🎤 Aufnahme läuft...")
        self._update_status("🎤 Listening...")

        import threading

        self._mic_thread = threading.Thread(target=self._mic_record_worker, daemon=True)
        self._mic_thread.start()

    def _stop_mic(self):
        """Stoppt Mikrofon-Aufnahme (Signal an Worker)."""
        self.mic_recording = False
        self.mic_btn.setText("🎤")
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 19px;
                font-size: 16px;
                padding: 0;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); }
        """)
        self.mic_btn.setToolTip("Push-to-Talk: Klick zum Aufnehmen")
        self.input_field.setPlaceholderText("Message Moruk OS...")

    def _mic_record_worker(self):
        """Background Thread: Nimmt Audio auf und transkribiert via STT."""
        try:
            import speech_recognition as sr
        except ImportError:
            self.log.error(
                "speech_recognition nicht installiert: pip install SpeechRecognition"
            )
            from PyQt6.QtCore import QMetaObject, Q_ARG

            QMetaObject.invokeMethod(
                self,
                "_mic_error",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, "❌ Bitte installieren: pip install SpeechRecognition"),
            )
            self.mic_recording = False
            return

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = 300

        try:
            with sr.Microphone() as source:
                self.log.info("Mic: Adjusting for ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.log.info("Mic: Listening...")

                # Aufnahme mit Timeout (max 30 Sek oder bis User stoppt)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=30)

            if not self.mic_recording:
                # User hat schon gestoppt während wir noch aufnahmen — trotzdem transkribieren
                pass

            self.log.info("Mic: Transcribing...")
            # Google STT (kostenlos, kein API Key nötig)
            text = recognizer.recognize_google(audio, language="de-DE")
            self.log.info(f"Mic: Transcribed: '{text}'")

            if text and text.strip():
                # Text im Main Thread ins Input-Feld setzen und senden
                from PyQt6.QtCore import QMetaObject, Q_ARG

                QMetaObject.invokeMethod(
                    self,
                    "_mic_result",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, text),
                )
            else:
                from PyQt6.QtCore import QMetaObject, Q_ARG

                QMetaObject.invokeMethod(
                    self,
                    "_mic_error",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, "🎤 Nichts erkannt — bitte nochmal versuchen"),
                )

        except Exception as e:
            error_msg = str(e)
            self.log.error(f"Mic error: {error_msg}")

            if "Could not understand" in error_msg or "UnknownValueError" in error_msg:
                display = "🎤 Konnte dich nicht verstehen — bitte nochmal versuchen"
            elif (
                "Microphone" in error_msg
                or "ALSA" in error_msg
                or "No Default" in error_msg
            ):
                display = "❌ Kein Mikrofon gefunden. Prüfe deine Audio-Einstellungen."
            elif "timed out" in error_msg.lower():
                display = "🎤 Timeout — kein Sprechen erkannt"
            else:
                display = f"🎤 Fehler: {error_msg[:80]}"

            from PyQt6.QtCore import QMetaObject, Q_ARG

            QMetaObject.invokeMethod(
                self,
                "_mic_error",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, display),
            )

        finally:
            self.mic_recording = False
            # Reset Button im Main Thread
            from PyQt6.QtCore import QMetaObject

            QMetaObject.invokeMethod(
                self, "_stop_mic", Qt.ConnectionType.QueuedConnection
            )

    @pyqtSlot(str)
    def _mic_result(self, text: str):
        """Main Thread: Empfängt transkribierten Text und sendet ihn."""
        self.input_field.setPlainText(text)
        self._send_message()

    @pyqtSlot(str)
    def _mic_error(self, message: str):
        """Main Thread: Zeigt Mic-Fehler im Chat."""
        self._append_message("system", message)
        self._update_status("● Ready")

    # ══ Sidebar ═══════════════════════════════════════════════

    def _show_routing_hint(self, text: str):
        # FIX: chat_display existiert nicht → _append_message verwenden
        self._append_message("system", text)

    def _show_monitor_notification(self, title: str, message: str):
        # FIX: chat_display existiert nicht → _append_message verwenden
        self._append_message("system", f"🛰 {title}: {message[:200]}")
        try:
            if hasattr(self, "tray_icon") and self.tray_icon:
                self.tray_icon.show_notification(title, message[:200])
        except Exception:
            pass

    def _open_monitor_window(self):
        if not hasattr(self, "_monitor_window") or self._monitor_window is None:
            self._monitor_window = MonitorWindow(
                monitor_engine=getattr(self, "monitor_engine", None), parent=self
            )
        self._monitor_window.refresh()
        self._monitor_window.show()
        self._monitor_window.raise_()
        self._monitor_window.activateWindow()

    def _toggle_live_activity(self):
        """Öffnet/schließt das Live Activity Fenster."""
        if self.live_activity.isVisible():
            self.live_activity.hide()
        else:
            self.live_activity.show()
            self.live_activity.raise_()

    def _toggle_history_panel(self):
        """Zeigt/versteckt das linke History-Panel."""
        if self.history_panel.isVisible():
            self.history_panel.hide()
            sizes = self.splitter.sizes()
            self.splitter.setSizes([0, sum(sizes)])
        else:
            self.history_panel.show()
            total = self.splitter.width()
            self.splitter.setSizes([240, max(total - 240, 400)])
            self._refresh_history_list()

    def _refresh_history_list(self):
        """Lädt alle gespeicherten Sessions in die Liste."""
        self.history_list.clear()
        import os
        from datetime import datetime

        sessions_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "sessions",
        )
        os.makedirs(sessions_dir, exist_ok=True)
        files = sorted(
            [f for f in os.listdir(sessions_dir) if f.endswith(".json")], reverse=True
        )
        for fname in files[:50]:
            path = os.path.join(sessions_dir, fname)
            try:
                import json

                with open(path) as f:
                    data = json.load(f)
                title = data.get("title", "")
                ts = data.get("saved_at", "")
                # Wenn Titel wie Dateiname aussieht oder leer, ersten User-Message nehmen
                if not title or title.startswith("session_") or title == "Chat":
                    for msg in data.get("messages", []):
                        if msg.get("role") == "user":
                            c = msg.get("content", "")
                            if isinstance(c, list):
                                c = next(
                                    (
                                        p.get("text", "")
                                        for p in c
                                        if isinstance(p, dict)
                                    ),
                                    "",
                                )
                            if c.strip():
                                title = c.strip()[:55]
                                break
                if not title:
                    title = fname.replace(".json", "")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts)
                        ts = dt.strftime("%d.%m %H:%M")
                    except Exception:
                        pass
                display = f"{title}\n{ts}" if ts else title
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.history_list.addItem(item)
            except Exception:
                pass
        if not files:
            self.history_list.addItem("No saved chats yet.")

    def _load_history_session(self, item):
        """Lädt eine alte Session in den Chat."""
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        try:
            import json

            with open(path) as f:
                data = json.load(f)
            messages = data.get("messages", [])
            if not messages:
                return

            # Chat leeren (alle Widgets außer dem Stretch am Ende)
            while self.chat_layout.count() > 1:
                item_w = self.chat_layout.takeAt(0)
                if item_w.widget():
                    item_w.widget().deleteLater()

            # Nachrichten als Bubbles einfügen
            for msg in messages:
                role = msg.get("role", "")
                content_text = msg.get("content", "")
                if isinstance(content_text, list):
                    content_text = " ".join(
                        p.get("text", "") for p in content_text if isinstance(p, dict)
                    )
                if not content_text.strip():
                    continue
                # System-Nachrichten überspringen (interne Tool-Results etc.)
                if content_text.startswith("[SYSTEM]") or content_text.startswith(
                    "[MORUK"
                ):
                    continue
                if role == "user":
                    self._append_message("user", content_text[:500])
                elif role == "assistant":
                    self._append_message("assistant", content_text[:800])

        except Exception as e:
            self._append_message("system", f"Could not load session: {e}")

    def _new_chat_session(self):
        """Speichert aktuelle Session und startet neuen Chat."""
        self._save_current_session()
        self.brain.clear_conversation()
        # Chat leeren
        while self.chat_layout.count() > 1:
            item_w = self.chat_layout.takeAt(0)
            if item_w.widget():
                item_w.widget().deleteLater()
        self._append_message("system", "New conversation started.")

    def _save_current_session(self):
        """Speichert aktuelle Unterhaltung als Session-Datei."""
        try:
            import json, os
            from datetime import datetime

            history = self.brain.conversation_history
            if len(history) < 2:
                return
            # Titel aus erster User-Nachricht
            title = "Chat"
            for msg in history:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = next(
                            (p.get("text", "") for p in content if isinstance(p, dict)),
                            "",
                        )
                    title = content[:60].strip() or "Chat"
                    break
            sessions_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "sessions",
            )
            os.makedirs(sessions_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = os.path.join(sessions_dir, f"{ts}.json")
            # Nur echte User/Assistant Nachrichten speichern
            clean_messages = []
            for msg in history[-100:]:
                c = msg.get("content", "")
                if isinstance(c, list):
                    c = next((p.get("text", "") for p in c if isinstance(p, dict)), "")
                if str(c).startswith("[SYSTEM]") or str(c).startswith("[MORUK"):
                    continue
                if msg.get("role") not in ("user", "assistant"):
                    continue
                clean_messages.append(msg)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "title": title,
                        "saved_at": datetime.now().isoformat(),
                        "messages": clean_messages,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            self.log.warning(f"Session save failed: {e}")

    def _toggle_sidebar(self):
        if self.sidebar.isVisible():
            self.sidebar.hide()
        else:
            self.sidebar.show()
            self.sidebar.refresh_all()

    # ══ Settings ══════════════════════════════════════════════

    def _open_settings(self):
        dialog = SettingsDialog(self.brain.settings, self)
        if dialog.exec():
            new_settings = dialog.get_settings()
            self.brain.save_settings(new_settings)

            # Status Message
            parts = [
                f"Provider: {new_settings.get('provider', '?')} | Model: {new_settings.get('model', '?')}"
            ]
            if new_settings.get("deepthink_model"):
                parts.append(f"DeepThink: {new_settings['deepthink_model']}")
            if new_settings.get("vision_model"):
                parts.append(f"Vision: {new_settings['vision_model']}")

            self._append_message("system", f"✅ {' | '.join(parts)}")
            if self.brain.is_configured():
                self._update_status("● Ready")

    # ══ Utility ═══════════════════════════════════════════════

    def _update_status(self, text: str):
        self.status_label.setText(text)
        if hasattr(self, "tray_icon"):
            self.tray_icon.update_status(text)

    # ══ Watchdog Alert ════════════════════════════════════════

    def _on_watchdog_alert(self, message):
        """Fängt Watchdog-Warnungen ab und zeigt sie im UI oder Log."""
        self._append_message("system", f"🛡️ WATCHDOG: {message}")

        # Tray-Notification für Watchdog-Alerts
        if hasattr(self, "tray_icon"):
            self.tray_icon.show_notification("⚠ Moruk Watchdog", message[:100])

        try:
            alert = AlertWindow(message)
            alert.show()
            self._active_alerts.append(alert)
        except Exception as e:
            self.log.error(f"Failed to show alert window: {e}")

    def _on_heartbeat_failure(self, name: str, reason: str):
        """Vom Heartbeat-Thread aufgerufen — leitet via Signal in Main-Thread weiter."""
        self.heartbeat_failure_signal.emit(name, reason)

    def _handle_heartbeat_failure(self, name: str, reason: str):
        """Läuft im Main-Thread (via Signal). Sicher für UI-Updates."""
        self.log.warning(f"Heartbeat failure: [{name}] {reason}")
        self._update_status(f"⚠ {name}: {reason[:60]}")

        # AutonomyLoop neu starten wenn gecrasht
        if name in ("autonomy_loop", "autonomy"):
            if not self.autonomy.isRunning():
                self.log.warning("AutonomyLoop crashed — restarting...")
                self.autonomy.start()
                if self.autonomy_active:
                    self.autonomy.start_autonomy()
                self._update_status("🔄 AutonomyLoop restarted")

        # Brain neu initialisieren wenn tot
        elif name == "brain":
            self.log.warning("Brain failure — reinitializing client...")
            self.brain._init_client()

    def closeEvent(self, event):
        self.log.info("Shutdown initiated...")

        # Session speichern beim Schließen
        try:
            self._save_current_session()
        except Exception:
            pass

        # Watchdog stoppen
        try:
            watchdog.stop_watchdog()
        except Exception:
            pass

        # Heartbeat stoppen
        if hasattr(self, "heartbeat"):
            self.heartbeat.stop()

        # Tray Icon entfernen
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()

        # Autonomy stoppen
        self.autonomy.stop()
        if self.autonomy.isRunning():
            self.autonomy.wait(3000)

        # ProjectManager stoppen falls aktiv
        if hasattr(self, "project_manager") and self.project_manager.is_running:
            self.project_manager.stop()

        # Worker Thread sauber beenden
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(2000)

        # State speichern + dirty Stats flushen
        self.state.set_mode("shutdown")
        self.state.flush()
        self.reflector.flush()

        # Conversation auto-save
        try:
            self.brain._save_conversation()
        except Exception as e:
            self.log.error(f"Failed to save conversation: {e}")

        # Vector Memory schließen
        try:
            self.memory.vector.close()
        except Exception:
            pass

        self.log.info("Shutdown complete")
        event.accept()
