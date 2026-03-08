"""
Moruk AI OS - Sidebar
Tabs: Tasks, Memory, Reflections, Goals, Stats
Live-Aktualisierung der Daten.
Subtask-Anzeige mit Einrückung + Projekt-Fortschrittsbalken.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QListWidget, QListWidgetItem, QLabel, QPushButton,
    QProgressBar, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

from core.task_manager import TaskManager
from core.memory import Memory
from core.reflector import Reflector
from core.state_manager import StateManager
from core.logger import get_logger

log = get_logger("sidebar")


class Sidebar(QWidget):
    """Sidebar mit Tabs für Tasks, Memory, Reflections, Goals, Stats."""

    def __init__(self, tasks: TaskManager, memory: Memory,
                 reflector: Reflector, state: StateManager, goal_engine=None, self_model=None, main_window=None, parent=None):
        super().__init__(parent)
        self._main_window = main_window
        self.tasks = tasks
        self.memory = memory
        self.reflector = reflector
        self.state = state
        self.goal_engine = goal_engine
        self.self_model = self_model

        self.setObjectName("sidebar")
        self.setMinimumWidth(280)
        self.setMaximumWidth(400)

        self._build_ui()

        # Auto-Refresh alle 5 Sekunden
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_all)
        self.refresh_timer.start(5000)

        # Initial laden
        self.refresh_all()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setObjectName("sidebarTabs")

        # Tab 1: Tasks
        self.tasks_tab = self._build_tasks_tab()
        self.tabs.addTab(self.tasks_tab, "📋 Tasks")

        # Tab 2: Memory
        self.memory_tab = self._build_memory_tab()
        self.tabs.addTab(self.memory_tab, "🧠 Memory")

        # Tab 3: Reflections
        self.reflection_tab = self._build_reflection_tab()
        self.tabs.addTab(self.reflection_tab, "🪞 Reflect")

        # Tab 4: Goals
        self.goals_tab = self._build_goals_tab()
        self.tabs.addTab(self.goals_tab, "🎯 Goals")

        # Tab 5: Stats
        self.stats_tab = self._build_stats_tab()
        self.tabs.addTab(self.stats_tab, "📊 Stats")

        layout.addWidget(self.tabs)

    # ── Tasks Tab ─────────────────────────────────────────────

    def _build_tasks_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        title = QLabel("Active Tasks")
        title.setObjectName("sidebarTitle")
        header.addWidget(title)

        self.task_count_label = QLabel("0")
        self.task_count_label.setObjectName("sidebarStat")
        header.addWidget(self.task_count_label)
        header.addStretch()

        layout.addLayout(header)

        # NEU: Projekt-Fortschrittsbalken (initial hidden)
        self.project_progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.project_progress_widget)
        progress_layout.setContentsMargins(4, 2, 4, 2)
        progress_layout.setSpacing(2)

        self.project_title_label = QLabel("")
        self.project_title_label.setObjectName("sidebarStat")
        self.project_title_label.setStyleSheet("color: #ffa500; font-weight: bold; font-size: 11px;")
        progress_layout.addWidget(self.project_title_label)

        progress_bar_layout = QHBoxLayout()
        self.project_progress_bar = QProgressBar()
        self.project_progress_bar.setMaximum(100)
        self.project_progress_bar.setFixedHeight(10)
        self.project_progress_bar.setStyleSheet("""
            QProgressBar { background: #1a1a2e; border: 1px solid #333; border-radius: 4px; }
            QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #00d2ff, stop:1 #44ff44); border-radius: 3px; }
        """)
        progress_bar_layout.addWidget(self.project_progress_bar)

        self.project_progress_label = QLabel("0/0")
        self.project_progress_label.setStyleSheet("color: #888; font-size: 10px;")
        progress_bar_layout.addWidget(self.project_progress_label)

        progress_layout.addLayout(progress_bar_layout)
        self.project_progress_widget.setVisible(False)
        layout.addWidget(self.project_progress_widget)

        # Task Liste
        self.task_list = QListWidget()
        layout.addWidget(self.task_list, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()

        show_all_btn = QPushButton("Show All")
        show_all_btn.setObjectName("sidebarBtn")
        show_all_btn.clicked.connect(self._toggle_all_tasks)
        btn_layout.addWidget(show_all_btn)

        clear_done_btn = QPushButton("Clear Done")
        clear_done_btn.setObjectName("sidebarBtn")
        clear_done_btn.clicked.connect(self._clear_completed_tasks)
        btn_layout.addWidget(clear_done_btn)

        layout.addLayout(btn_layout)

        self._show_all_tasks = False
        return widget

    def _make_task_widget(self, text: str, task_id: str, color: str,
                           bold: bool = False, small: bool = False) -> QWidget:
        """Erstellt ein Task-Widget mit Text + X-Button."""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 2, 2)
        layout.setSpacing(4)

        label = QLabel(text)
        label.setStyleSheet(f"color: {color}; background: transparent;")
        label.setWordWrap(True)
        if bold:
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        if small:
            font = label.font()
            font.setPointSize(max(font.pointSize() - 1, 8))
            label.setFont(font)
        layout.addWidget(label, stretch=1)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(18, 18)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #555;
                border: none;
                font-size: 11px;
                padding: 0;
            }
            QPushButton:hover { color: #e94560; }
        """)
        del_btn.setToolTip("Task löschen")
        del_btn.clicked.connect(lambda: self._delete_task(task_id))
        layout.addWidget(del_btn)

        return widget

    def _delete_task(self, task_id: str):
        """Löscht einen Task und aktualisiert die Sidebar."""
        self.tasks.delete_task(task_id)
        self._refresh_tasks()

    def _refresh_tasks(self):
        self.task_list.clear()
        if self._show_all_tasks:
            all_tasks = self.tasks.tasks
        else:
            all_tasks = self.tasks.get_active_tasks()

        self.task_count_label.setText(f"{len(self.tasks.get_active_tasks())} active")

        priority_colors = {
            "critical": "#ff4444",
            "high": "#e94560",
            "normal": "#00d2ff",
            "low": "#666"
        }

        status_icons = {
            "pending": "⏳",
            "active": "🔄",
            "completed": "✅",
            "failed": "❌"
        }

        for task in all_tasks:
            if task.get("parent_id"):
                continue

            icon = status_icons.get(task["status"], "❓")
            priority_color = priority_colors.get(task["priority"], "#888")
            priority = str(task.get("priority", "normal")).upper()
            is_project = len(task.get("subtasks", [])) > 0

            if is_project:
                progress = self.tasks.get_project_progress(task["id"])
                total = progress["total"]
                done = progress["completed"]
                failed = progress["failed"]
                text = f"🏗 {task['title']}"
                text += f"\n   📊 {done}/{total} done"
                if failed > 0:
                    text += f" | {failed} failed"
            else:
                text = f"{icon} [{priority}] {task['title']}"
                if task.get("description"):
                    text += f"\n   {task['description'][:60]}"

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, task["id"])
            self.task_list.addItem(item)
            widget = self._make_task_widget(text, task["id"], priority_color, bold=is_project)
            item.setSizeHint(widget.sizeHint())
            self.task_list.setItemWidget(item, widget)

            if is_project:
                subtasks = self.tasks.get_subtasks(task["id"])
                for sub in subtasks:
                    if not self._show_all_tasks and sub["status"] not in ("pending", "active"):
                        continue

                    sub_icon = status_icons.get(sub["status"], "❓")
                    sub_text = f"  └─ {sub_icon} {sub['title']}"
                    if sub.get("description"):
                        sub_text += f"\n       {sub['description'][:50]}"

                    if sub["status"] == "completed":
                        sub_color = "#44ff44"
                    elif sub["status"] == "failed":
                        sub_color = "#ff4444"
                    elif sub["status"] == "active":
                        sub_color = "#ffa500"
                    else:
                        sub_color = "#666"

                    sub_item = QListWidgetItem()
                    sub_item.setData(Qt.ItemDataRole.UserRole, sub["id"])
                    self.task_list.addItem(sub_item)
                    sub_widget = self._make_task_widget(sub_text, sub["id"], sub_color, small=True)
                    sub_item.setSizeHint(sub_widget.sizeHint())
                    self.task_list.setItemWidget(sub_item, sub_widget)

        self._update_project_progress()

    def _update_project_progress(self):
        """Aktualisiert den Projekt-Fortschrittsbalken in der Sidebar."""
        # Finde aktives Projekt (Parent-Task mit Subtasks, Status active/pending)
        active_project = None
        for task in self.tasks.tasks:
            if (len(task.get("subtasks", [])) > 0 and
                    task["status"] in ("pending", "active")):
                active_project = task
                break

        if active_project:
            progress = self.tasks.get_project_progress(active_project["id"])
            total = progress["total"]
            done = progress["completed"] + progress["failed"]
            pct = int((done / total) * 100) if total > 0 else 0

            self.project_title_label.setText(f"🏗 {active_project['title'][:40]}")
            self.project_progress_bar.setValue(pct)
            self.project_progress_label.setText(f"{progress['completed']}/{total}")
            self.project_progress_widget.setVisible(True)
        else:
            self.project_progress_widget.setVisible(False)

    def update_project_progress(self, status: dict):
        """Externer Aufruf von AutonomyLoop via Signal."""
        if not status.get("active"):
            self.project_progress_widget.setVisible(False)
            return

        total = status.get("total_subtasks", 0)
        done = status.get("completed", 0)
        pct = int(status.get("progress", 0) * 100)

        self.project_title_label.setText(f"🏗 {status.get('title', '?')[:40]}")
        self.project_progress_bar.setValue(pct)
        self.project_progress_label.setText(
            f"{status.get('approved', 0)}✅ {status.get('failed', 0)}❌ / {total}"
        )
        self.project_progress_widget.setVisible(True)

    def _toggle_all_tasks(self):
        self._show_all_tasks = not self._show_all_tasks
        self._refresh_tasks()

    def _clear_completed_tasks(self):
        self.tasks.clear_completed()
        self._refresh_tasks()

    # ── Memory Tab ────────────────────────────────────────────

    def _build_memory_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        title = QLabel("Long-Term Memory")
        title.setObjectName("sidebarTitle")
        header.addWidget(title)

        self.memory_count_label = QLabel("0")
        self.memory_count_label.setObjectName("sidebarStat")
        header.addWidget(self.memory_count_label)
        header.addStretch()

        layout.addLayout(header)

        # Memory Liste
        self.memory_list = QListWidget()
        layout.addWidget(self.memory_list, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()

        clear_short_btn = QPushButton("Clear Short-Term")
        clear_short_btn.setObjectName("sidebarBtn")
        clear_short_btn.clicked.connect(self._clear_short_memory)
        btn_layout.addWidget(clear_short_btn)

        layout.addLayout(btn_layout)

        return widget

    def _refresh_memory(self):
        self.memory_list.clear()
        stats = self.memory.get_stats()
        db_size = stats.get("db_size_kb", 0)
        self.memory_count_label.setText(
            f"{stats['long_term_count']} memories ({db_size}KB)"
        )

        category_colors = {
            "learned": "#00d2ff",
            "user_preference": "#e94560",
            "project": "#ffa500",
            "discovery": "#44ff44",
            "reflection": "#ffa500",
            "general": "#888"
        }

        # Letzte 30 Long-Term Memories
        entries = self.memory.get_long_term(30)
        for entry in entries:
            cat = entry.get("category", "general")
            color = category_colors.get(cat, "#888")
            tags = ", ".join(entry.get("tags", []))
            text = f"[{cat}] {entry['content'][:80]}"
            if tags:
                text += f"\n  🏷 {tags}"

            item = QListWidgetItem(text)
            item.setForeground(QColor(color))
            self.memory_list.addItem(item)

    def _clear_short_memory(self):
        self.memory.clear_short_term()
        self._refresh_memory()

    # ── Reflection Tab ────────────────────────────────────────

    def _build_reflection_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(4)

        title = QLabel("Reflection Log")
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)

        # Success Rate Bar
        rate_layout = QHBoxLayout()
        rate_label = QLabel("Success Rate:")
        rate_label.setObjectName("sidebarStat")
        rate_layout.addWidget(rate_label)

        self.success_bar = QProgressBar()
        self.success_bar.setMaximum(100)
        self.success_bar.setFixedHeight(12)
        rate_layout.addWidget(self.success_bar)

        self.success_label = QLabel("0%")
        self.success_label.setObjectName("sidebarStat")
        rate_layout.addWidget(self.success_label)

        layout.addLayout(rate_layout)

        # Streak
        self.streak_label = QLabel("Streak: 0 | Best: 0")
        self.streak_label.setObjectName("reflectionLabel")
        layout.addWidget(self.streak_label)

        # Reflection Liste
        self.reflection_list = QListWidget()
        layout.addWidget(self.reflection_list, stretch=1)

        return widget

    def _refresh_reflections(self):
        self.reflection_list.clear()

        # Stats
        stats = self.reflector.get_full_stats()
        rate = stats.get("success_rate", 0)
        self.success_bar.setValue(int(rate))
        self.success_label.setText(f"{rate:.0f}%")

        streak = stats.get("streak", {})
        self.streak_label.setText(
            f"🔥 Streak: {streak.get('current', 0)} | Best: {streak.get('best', 0)} | "
            f"Total: {stats.get('total_actions', 0)}"
        )

        # Letzte 30 Reflections (neueste zuerst)
        entries = list(reversed(self.reflector.log[-30:]))
        for entry in entries:
            success = entry.get("success", False)
            icon = "✅" if success else "❌"
            color = "#44ff44" if success else "#ff4444"
            text = f"{icon} {entry['action'][:70]}"
            if entry.get("lesson"):
                text += f"\n  💡 {entry['lesson'][:60]}"

            item = QListWidgetItem(text)
            item.setForeground(QColor(color))
            self.reflection_list.addItem(item)

    # ── Goals Tab ───────────────────────────────────────────

    def _build_goals_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Self-Generated Goals")
        title.setObjectName("sidebarTitle")
        header.addWidget(title)
        header.addStretch()
        self.goal_count_label = QLabel("0 goals")
        self.goal_count_label.setStyleSheet("color: #888; font-size: 11px;")
        header.addWidget(self.goal_count_label)
        layout.addLayout(header)

        self.goal_list = QListWidget()
        layout.addWidget(self.goal_list, stretch=1)

        return widget

    def _refresh_goals(self):
        self.goal_list.clear()
        if not self.goal_engine:
            self.goal_count_label.setText("no engine")
            return

        goals = self.goal_engine.goals
        active = [g for g in goals if g["status"] in ("pending", "active")]
        self.goal_count_label.setText(f"{len(active)} active / {len(goals)} total")

        status_icons = {
            "pending": "⏳",
            "active": "🔄",
            "completed": "✅",
            "failed": "❌",
            "discarded": "🗑"
        }

        status_colors = {
            "pending": "#00d2ff",
            "active": "#44ff44",
            "completed": "#666",
            "failed": "#e94560",
            "discarded": "#444"
        }

        for goal in goals[-20:]:
            icon = status_icons.get(goal["status"], "❓")
            pri = goal.get("priority", 0)
            text = f"{icon} {goal['title'][:50]}"
            text += f"\n   Priority: {pri:.2f} | {goal['reason'][:40]}"

            item = QListWidgetItem(text)
            color = status_colors.get(goal["status"], "#888")
            item.setForeground(QColor(color))
            self.goal_list.addItem(item)

    # ── Stats Tab ─────────────────────────────────────────────

    def _build_stats_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(6)

        title = QLabel("System Statistics")
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)

        self.stats_display = QTextEdit()
        self.stats_display.setObjectName("statsDisplay")
        self.stats_display.setReadOnly(True)
        layout.addWidget(self.stats_display, stretch=1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("sidebarBtn")
        refresh_btn.clicked.connect(self.refresh_all)
        layout.addWidget(refresh_btn)

        return widget

    def _refresh_stats(self):
        lines = []

        # State
        lines.append("═══ SYSTEM STATE ═══")
        lines.append(f"  Mode: {self.state.get('mode', 'unknown')}")
        lines.append(f"  Session: #{self.state.get('session_count', 0)}")
        lines.append(f"  Interactions: {self.state.get('total_interactions', 0)}")
        goal = self.state.get("current_goal")
        if goal:
            lines.append(f"  Current Goal: {goal}")
        lines.append("")

        # Memory
        mem_stats = self.memory.get_stats()
        lines.append("═══ MEMORY ═══")
        lines.append(f"  Short-term: {mem_stats['short_term_count']} entries")
        lines.append(f"  Long-term: {mem_stats['long_term_count']} entries")
        if mem_stats["categories"]:
            lines.append(f"  Categories: {', '.join(mem_stats['categories'])}")
        if mem_stats["all_tags"]:
            lines.append(f"  Tags: {', '.join(mem_stats['all_tags'][:15])}")
        lines.append("")

        # Tasks (erweitert mit Projekt-Info)
        active = self.tasks.get_active_tasks()
        all_tasks = self.tasks.tasks
        completed = len([t for t in all_tasks if t["status"] == "completed"])
        failed = len([t for t in all_tasks if t["status"] == "failed"])
        projects = len([t for t in all_tasks if len(t.get("subtasks", [])) > 0])
        subtasks = len([t for t in all_tasks if t.get("parent_id")])

        lines.append("═══ TASKS ═══")
        lines.append(f"  Active: {len(active)}")
        lines.append(f"  Completed: {completed}")
        lines.append(f"  Failed: {failed}")
        lines.append(f"  Total: {len(all_tasks)}")
        if projects > 0:
            lines.append(f"  Projects: {projects} ({subtasks} subtasks)")
        lines.append("")

        # Reflection
        ref_stats = self.reflector.get_full_stats()
        lines.append("═══ REFLECTION ═══")
        lines.append(f"  Total Actions: {ref_stats.get('total_actions', 0)}")
        lines.append(f"  Success Rate: {ref_stats.get('success_rate', 0):.1f}%")
        streak = ref_stats.get("streak", {})
        lines.append(f"  Current Streak: {streak.get('current', 0)}")
        lines.append(f"  Best Streak: {streak.get('best', 0)}")
        lines.append(f"  Lessons Learned: {ref_stats.get('lessons_learned', 0)}")

        top_tools = ref_stats.get("most_used_tools", [])
        if top_tools:
            lines.append("")
            lines.append("═══ TOP TOOLS ═══")
            for tool, count in top_tools:
                bar = "█" * min(count, 20)
                lines.append(f"  {tool:15s} {bar} ({count})")

        common_errors = ref_stats.get("common_errors", [])
        if common_errors:
            lines.append("")
            lines.append("═══ COMMON ERRORS ═══")
            for error, count in common_errors:
                lines.append(f"  ({count}x) {error[:50]}")

        # Self-Model
        if self.self_model:
            lines.append("")
            lines.append("═══ SELF-MODEL ═══")
            lines.append(self.self_model.get_profile_summary())

        self.stats_display.setPlainText("\n".join(lines))

    # ── Refresh ───────────────────────────────────────────────

    def refresh_all(self):
        """Aktualisiert alle Tabs."""
        try:
            self._refresh_tasks()
            self._refresh_memory()
            self._refresh_reflections()
            self._refresh_goals()
            self._refresh_stats()
        except Exception as e:
            log.error(f"Sidebar refresh error: {e}")
