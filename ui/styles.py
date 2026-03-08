"""
Moruk AI OS - Premium Dark Glass Theme
Frameless, glasig, Chat-Bubbles, Copy-Buttons.
"""

DARK_THEME = """
/* ══════════════════════════════════════════════
   GLOBAL
   ══════════════════════════════════════════════ */

QMainWindow {
    background-color: transparent;
}

QWidget {
    color: #e0e0e0;
    font-family: 'Segoe UI', 'Ubuntu', 'Noto Sans', sans-serif;
    font-size: 14px;
}

QWidget#centralWidget {
    background-color: rgba(12, 14, 26, 240);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 16px;
}

/* ══════════════════════════════════════════════
   TITLE BAR (custom frameless)
   ══════════════════════════════════════════════ */

QWidget#titleBar {
    background-color: rgba(10, 12, 24, 250);
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

QLabel#titleLabel {
    color: #e94560;
    font-size: 16px;
    font-weight: bold;
    padding: 0px 8px;
    background: transparent;
}

QLabel#titleSubLabel {
    color: rgba(255, 255, 255, 0.25);
    font-size: 11px;
    background: transparent;
}

QPushButton#winBtn {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: rgba(255, 255, 255, 0.4);
    font-size: 14px;
    padding: 4px 10px;
    min-width: 30px;
    max-width: 30px;
    min-height: 24px;
}

QPushButton#winBtn:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: #e0e0e0;
}

QPushButton#closeBtn {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: rgba(255, 255, 255, 0.4);
    font-size: 14px;
    padding: 4px 10px;
    min-width: 30px;
    max-width: 30px;
    min-height: 24px;
}

QPushButton#closeBtn:hover {
    background-color: #e94560;
    color: white;
}

/* ══════════════════════════════════════════════
   TOP CONTROLS
   ══════════════════════════════════════════════ */

QWidget#controlBar {
    background: transparent;
}

QLabel#statusLabel {
    color: rgba(255, 255, 255, 0.3);
    font-size: 11px;
    padding: 4px 8px;
    background: transparent;
}

QPushButton#autonomyBtn {
    background-color: rgba(15, 52, 96, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 11px;
    padding: 5px 12px;
    border-radius: 6px;
    color: #888;
}

QPushButton#autonomyBtn:hover {
    background-color: rgba(15, 52, 96, 0.9);
    color: #e0e0e0;
}

QPushButton#iconBtn {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: rgba(255, 255, 255, 0.3);
    font-size: 18px;
    padding: 4px 8px;
}

QPushButton#iconBtn:hover {
    background-color: rgba(255, 255, 255, 0.06);
    color: #e94560;
}

/* ══════════════════════════════════════════════
   CHAT AREA
   ══════════════════════════════════════════════ */

QScrollArea#chatScroll {
    background: transparent;
    border: none;
}

QWidget#chatContainer {
    background: transparent;
}

/* ══════════════════════════════════════════════
   CHAT BUBBLES
   ══════════════════════════════════════════════ */

QFrame#userBubble {
    background-color: rgba(15, 52, 96, 0.5);
    border: 1px solid rgba(233, 69, 96, 0.15);
    border-radius: 16px;
    border-top-right-radius: 4px;
}

QFrame#assistantBubble {
    background-color: rgba(22, 33, 62, 0.6);
    border: 1px solid rgba(0, 210, 255, 0.08);
    border-radius: 16px;
    border-top-left-radius: 4px;
}

QFrame#toolBubble {
    background-color: rgba(10, 22, 40, 0.7);
    border-left: 2px solid rgba(233, 69, 96, 0.4);
    border-radius: 4px;
}

QFrame#toolResultBubble {
    background-color: rgba(10, 22, 40, 0.5);
    border-left: 2px solid rgba(0, 210, 255, 0.3);
    border-radius: 4px;
}

QFrame#systemBubble {
    background: transparent;
    border: none;
}

QFrame#reflectionBubble {
    background-color: rgba(20, 15, 10, 0.5);
    border-left: 2px solid rgba(255, 165, 0, 0.4);
    border-radius: 4px;
}

QLabel#bubbleSender {
    font-size: 11px;
    font-weight: bold;
    background: transparent;
    padding: 0;
}

QLabel#bubbleText {
    font-size: 13px;
    background: transparent;
    padding: 0;
    line-height: 1.5;
}

QPushButton#copyBtn {
    background: transparent;
    border: none;
    border-radius: 4px;
    color: rgba(255, 255, 255, 0.15);
    font-size: 12px;
    padding: 2px 6px;
}

QPushButton#copyBtn:hover {
    background-color: rgba(255, 255, 255, 0.06);
    color: rgba(255, 255, 255, 0.5);
}

/* ══════════════════════════════════════════════
   INPUT AREA
   ══════════════════════════════════════════════ */

QWidget#inputArea {
    background-color: rgba(18, 22, 38, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 14px;
}

QTextEdit#inputField {
    background: transparent;
    color: #e0e0e0;
    border: none;
    padding: 8px 12px;
    font-size: 14px;
    selection-background-color: rgba(233, 69, 96, 0.3);
}

QPushButton#sendBtn {
    background-color: #e94560;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 8px 18px;
    font-weight: bold;
    font-size: 13px;
}

QPushButton#sendBtn:hover {
    background-color: #ff6b81;
}

QPushButton#sendBtn:pressed {
    background-color: #c23152;
}

/* ══════════════════════════════════════════════
   SIDEBAR
   ══════════════════════════════════════════════ */

QWidget#sidebar {
    background-color: rgba(10, 12, 22, 0.95);
    border-left: 1px solid rgba(255, 255, 255, 0.04);
}

QTabWidget#sidebarTabs {
    background: transparent;
}

QTabWidget#sidebarTabs::pane {
    background: transparent;
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.04);
}

QTabBar::tab {
    background: transparent;
    color: rgba(255, 255, 255, 0.35);
    border: none;
    padding: 8px 10px;
    font-size: 11px;
    font-weight: bold;
    min-width: 50px;
}

QTabBar::tab:selected {
    color: #e94560;
    border-bottom: 2px solid #e94560;
}

QTabBar::tab:hover {
    color: rgba(255, 255, 255, 0.7);
}

QListWidget {
    background: transparent;
    border: none;
    outline: none;
    font-size: 12px;
}

QListWidget::item {
    background-color: rgba(22, 33, 62, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.03);
    border-radius: 6px;
    padding: 8px 10px;
    margin: 2px 4px;
    color: #e0e0e0;
}

QListWidget::item:selected {
    background-color: rgba(15, 52, 96, 0.7);
    border-color: rgba(233, 69, 96, 0.3);
}

QListWidget::item:hover {
    background-color: rgba(22, 33, 62, 0.7);
}

QLabel#sidebarTitle {
    color: #e94560;
    font-size: 13px;
    font-weight: bold;
    padding: 6px 10px;
    background: transparent;
}

QLabel#sidebarStat {
    color: rgba(255, 255, 255, 0.3);
    font-size: 11px;
    padding: 2px 10px;
    background: transparent;
}

QLabel#reflectionLabel {
    color: #ffa500;
    font-size: 11px;
    padding: 2px 10px;
    background: transparent;
}

QPushButton#sidebarBtn {
    background-color: rgba(31, 41, 64, 0.5);
    color: rgba(255, 255, 255, 0.4);
    font-size: 11px;
    padding: 5px 10px;
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 4px;
    font-weight: normal;
}

QPushButton#sidebarBtn:hover {
    background-color: rgba(31, 41, 64, 0.8);
    color: #e94560;
}

QProgressBar {
    background-color: rgba(31, 41, 64, 0.5);
    border: none;
    border-radius: 4px;
    height: 6px;
    color: transparent;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #e94560, stop:1 #ff6b81);
    border-radius: 3px;
}

QSplitter::handle {
    background: transparent;
    width: 0px;
    height: 0px;
    image: none;
}
QSplitter::handle:hover { background: transparent; }
QSplitter::handle:horizontal { image: none; width: 0px; }
QSplitter::handle:vertical   { image: none; height: 0px; }
QSplitter > QAbstractScrollArea { border: none; }

/* ══════════════════════════════════════════════
   SETTINGS DIALOG
   ══════════════════════════════════════════════ */

QDialog {
    background-color: rgba(14, 16, 30, 250);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
}

QComboBox {
    background-color: rgba(31, 41, 64, 0.6);
    color: #e0e0e0;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 20px;
}

QComboBox:hover {
    border-color: rgba(233, 69, 96, 0.4);
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #e94560;
    margin-right: 10px;
}

QComboBox QAbstractItemView {
    background-color: rgba(20, 24, 42, 250);
    color: #e0e0e0;
    border: 1px solid rgba(255, 255, 255, 0.06);
    selection-background-color: rgba(233, 69, 96, 0.4);
}

QLineEdit {
    background-color: rgba(31, 41, 64, 0.6);
    color: #e0e0e0;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}

QLineEdit:focus {
    border-color: rgba(233, 69, 96, 0.5);
}

QLabel {
    color: rgba(255, 255, 255, 0.6);
    font-size: 13px;
    background: transparent;
}

QGroupBox {
    color: #e94560;
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    background: transparent;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QSlider::groove:horizontal {
    background: rgba(42, 42, 74, 0.5);
    height: 4px;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #e94560;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QScrollBar:vertical {
    background: transparent;
    width: 6px;
    border-radius: 3px;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.08);
    border-radius: 3px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(233, 69, 96, 0.4);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    height: 0;
}

/* Stats display in sidebar */
QTextEdit#statsDisplay {
    background-color: rgba(10, 16, 28, 0.8);
    color: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.03);
    border-radius: 6px;
    padding: 10px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 11px;
}
"""
