"""
Moruk AI OS - Autonomy Loop v4
Background Thread mit Goal Generation + Task Execution + Project Mode.
Idle → scannt nach Signalen → generiert Goals → arbeitet sie ab.
Project Mode: DeepThink zerlegt → Small Model arbeitet Subtasks ab → DeepThink reviewed.
"""

import time
import json
import threading

from PyQt6.QtCore import QThread, pyqtSignal
from core.logger import get_logger

log = get_logger("autonomy")


class AutonomyLoop(QThread):
    """Background Thread: Goal Detection + Task Execution + Project Mode."""

    thought_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    tool_start_signal = pyqtSignal(str, str)
    tool_result_signal = pyqtSignal(str, str, bool)
    project_progress_signal = pyqtSignal(dict)  # NEU: Project progress updates

    def __init__(
        self, brain, state_manager, task_manager, reflector, memory, parent=None
    ):
        super().__init__(parent)
        self.brain = brain
        self.state = state_manager
        self.tasks = task_manager
        self.reflector = reflector
        self.memory = memory
        self.goal_engine = None
        self.health_monitor = None
        self.project_manager = None  # NEU: Wird von MainWindow gesetzt
        self.running = False
        self.paused = True
        self.interval = 20
        self.idle_interval = 60
        self.goal_scan_interval = 5
        self.health_check_interval = 30
        self.cycle_count = 0
        self.cycles_without_task = 0
        self.max_idle_cycles = 3

        # Project Mode State
        self._project_queue = []  # Queue von Projekt-Prompts
        self._project_lock = threading.Lock()

        # Event zum sofortigen Aufwecken aus sleep
        self._wake_event = threading.Event()

        # Warmup: Goals aus alter Session nicht sofort aktivieren
        # Erst nach WARMUP_CYCLES Zyklen dürfen auto-Goals laufen
        self._warmup_cycles = 3  # 3 Zyklen × 20s = ~1 Minute Warmup
        self._user_triggered = False  # True wenn User explizit Task/Projekt queued
        self._user_active_until = 0.0  # Timestamp bis wann User als aktiv gilt

    def run(self):
        self.running = True
        while self.running:
            if not self.paused and self.brain.is_configured():
                try:
                    self.cycle_count += 1
                    self._think_cycle()
                except Exception as e:
                    log.error(f"Autonomy error: {e}", exc_info=True)
                    self.status_signal.emit(f"Autonomy error: {str(e)[:100]}")
                    self._wake_event.wait(timeout=30)
                    self._wake_event.clear()
                    continue

            sleep_time = (
                self.idle_interval
                if self.cycles_without_task >= self.max_idle_cycles
                else self.interval
            )
            # Kein Sleep wenn noch Tasks oder Projekte warten
            if self.tasks.get_next_task() is not None or self._has_pending_projects():
                time.sleep(0.1)
                continue
            self._wake_event.wait(timeout=sleep_time)
            self._wake_event.clear()

    def _think_cycle(self):
        """Ein Zyklus: Check Projects → Check Tasks → Check Goals → Idle Scan."""

        # User gerade aktiv? → Autonomy pausieren
        import time as _time

        if _time.time() < self._user_active_until:
            remaining = int(self._user_active_until - _time.time())
            self.status_signal.emit(f"Autonomy: wartet auf User ({remaining}s)")
            return

        # 0. NEU: Pending Projects haben höchste Priorität
        if self._has_pending_projects():
            self.cycles_without_task = 0
            self._execute_project()
            return

        # 1. User-erstellte Tasks haben Priorität
        next_task = self.tasks.get_next_task()
        if next_task:
            # Prüfe ob es ein Projekt-Task ist (hat Subtasks)
            if self.tasks.is_project_task(next_task["id"]):
                # Projekt-Tasks werden vom ProjectManager verwaltet, nicht direkt
                # Falls der PM aktiv ist, skip — sonst als normalen Task behandeln
                if self.project_manager and self.project_manager.is_running:
                    return
                # Ansonsten als normalen Task ausführen (z.B. manuell erstellte Projekte)

            self.cycles_without_task = 0
            self._user_triggered = True  # User-Task → Warmup überspringen
            self._execute_task(next_task)
            return

        # 2. Goal-generierte Tasks prüfen
        # Warmup: Erst nach N Zyklen oder wenn User explizit was getriggert hat
        if self.goal_engine:
            in_warmup = (
                self.cycle_count <= self._warmup_cycles and not self._user_triggered
            )
            if in_warmup:
                self.status_signal.emit(
                    f"Autonomy: warming up ({self.cycle_count}/{self._warmup_cycles})..."
                )
            else:
                goal = self.goal_engine.get_next_goal()
                if goal:
                    self.goal_engine.activate_goal(goal["id"])
                    self.thought_signal.emit(f"🎯 New goal: {goal['title']}")
                    self.status_signal.emit(f"Goal: {goal['title'][:40]}")
                    return

        # 3. Periodischer Health Check
        if (
            self.health_monitor
            and self.cycle_count % self.health_check_interval == 0
            and self.cycle_count > 0
        ):
            try:
                report = self.health_monitor.full_check(auto_repair=True)
                if report.get("repairs"):
                    self.thought_signal.emit(
                        f"🔧 Auto-repaired {len(report['repairs'])} system issues"
                    )
                issues = report.get("issues", 0)
                if issues > 0 and not report.get("repairs"):
                    self.thought_signal.emit(f"⚠ {issues} system issues need attention")
            except Exception as e:
                log.error(f"Health check failed: {e}")

        # 4. Idle: Periodisch nach neuen Goals scannen
        self.cycles_without_task += 1

        if self.goal_engine and self.cycle_count % self.goal_scan_interval == 0:
            new_goals = self.goal_engine.run_cycle()
            if new_goals:
                for goal in new_goals:
                    self.thought_signal.emit(f"🔍 Detected: {goal['title']}")
                self.status_signal.emit(f"Found {len(new_goals)} improvement(s)")
            else:
                if self.cycles_without_task == 1:
                    self.status_signal.emit("Autonomy: idle")

    # ── Project Mode ─────────────────────────────────────────

    def queue_project(self, user_prompt: str, codebase_context: str = ""):
        """Fügt ein Projekt in die Queue ein. Wird im nächsten Zyklus gestartet."""
        with self._project_lock:
            self._project_queue.append(
                {"prompt": user_prompt, "context": codebase_context}
            )
        log.info(f"Project queued: {user_prompt[:80]}")
        self.thought_signal.emit(f"📋 Projekt in Queue: {user_prompt[:60]}...")
        self._user_triggered = True  # User hat explizit was gestartet
        self._wake_event.set()  # Sofort aufwecken

    def _has_pending_projects(self) -> bool:
        with self._project_lock:
            return len(self._project_queue) > 0

    def _execute_project(self):
        """Führt das nächste Projekt aus der Queue aus."""
        with self._project_lock:
            if not self._project_queue:
                return
            project_request = self._project_queue.pop(0)

        if not self.project_manager:
            log.error("ProjectManager nicht gesetzt!")
            self.thought_signal.emit("❌ ProjectManager nicht konfiguriert")
            return

        prompt = project_request["prompt"]
        context = project_request["context"]

        self.state.set_mode("project")
        self.status_signal.emit(f"🏗 Project: {prompt[:50]}...")
        self.thought_signal.emit(f"🏗 Starte Projekt: {prompt[:80]}")

        # Callbacks für UI verbinden
        self.project_manager.on_status = lambda msg: self.status_signal.emit(msg)
        self.project_manager.on_thought = lambda msg: self.thought_signal.emit(msg)
        self.project_manager.on_subtask_start = self._on_subtask_start
        self.project_manager.on_subtask_done = self._on_subtask_done
        self.project_manager.on_project_done = self._on_project_done

        def on_tool_start(name, params):
            self.tool_start_signal.emit(
                name, json.dumps(params, ensure_ascii=False)[:200]
            )

        def on_tool_result(name, result):
            self.tool_result_signal.emit(
                name, str(result.get("result", ""))[:500], result.get("success", False)
            )

        # Parent-Task ID für Delete-Check merken
        parent_task_id = getattr(self.project_manager, "_current_task_id", None)

        try:
            result = self.project_manager.run_project(
                prompt,
                context,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
            )

            # Prüfe ob Projekt während Ausführung gelöscht wurde
            if parent_task_id and not self.tasks.get_task_by_id(parent_task_id):
                log.warning(
                    f"Projekt-Task [{parent_task_id}] wurde gelöscht — Ergebnis verwerfen"
                )
                self.state.set_mode("idle")
                return

            if result.get("success"):
                self.thought_signal.emit("🎉 Projekt erfolgreich abgeschlossen!")
            else:
                error = result.get("error", "Unknown")
                final = result.get("final_review", {})
                verdict = final.get("final_verdict", error)
                self.thought_signal.emit(f"⚠ Projekt: {verdict}")

        except Exception as e:
            log.error(f"Project execution error: {e}", exc_info=True)
            self.thought_signal.emit(f"❌ Projekt-Fehler: {str(e)[:100]}")

        self.state.set_mode("idle")

    def _on_subtask_start(self, index: int, subtask: dict):
        """Callback wenn ein Subtask startet."""
        self.project_progress_signal.emit(self.project_manager.get_project_status())

    def _on_subtask_done(self, index: int, status: str, review: dict):
        """Callback wenn ein Subtask fertig ist."""
        self.project_progress_signal.emit(self.project_manager.get_project_status())

    def _on_project_done(self, final_review: dict):
        """Callback wenn das Projekt fertig ist."""
        self.project_progress_signal.emit(self.project_manager.get_project_status())

    # ── Normal Task Execution ────────────────────────────────

    def _execute_task(self, task: dict):
        """Führt einen Task aus. Setzt Status auf 'failed' bei Fehler."""
        task_id = task["id"]
        self.tasks.update_status(task_id, "active")
        self.state.set("active_task", task["title"])
        self.state.set_mode("working")
        self.status_signal.emit(f"Working: {task['title'][:40]}")

        relevant_memory = self.memory.get_memory_context(query=task["title"])
        reflection_ctx = self.reflector.get_reflection_context()
        goal_ctx = self.goal_engine.get_goal_context() if self.goal_engine else ""

        # Codebase-Kontext: relevante Dateien aus Vector-Index laden
        codebase_ctx = ""
        CODE_KEYWORDS = (
            ".py",
            "fix",
            "bug",
            "implement",
            "refactor",
            "add",
            "update",
            "fehler",
            "funktion",
            "klasse",
            "modul",
            "datei",
            "code",
        )
        task_lower = (task["title"] + " " + task.get("description", "")).lower()
        is_code_task = any(kw in task_lower for kw in CODE_KEYWORDS)
        if is_code_task and hasattr(self.memory, "search_codebase"):
            hits = self.memory.search_codebase(task["title"], max_results=3)
            if hits:
                codebase_ctx = "RELEVANT CODEBASE FILES:\n"
                for hit in hits:
                    snippet = hit["content"][:800]
                    codebase_ctx += f"\n--- {snippet} ---\n"

        context = f"""AUTONOMOUS MODE - Working on task.

Current Task: [{task_id}] {task['title']}
Description: {task.get('description', 'No description')}
Priority: {task['priority']}

{self.state.get_context_summary()}
{relevant_memory}
{reflection_ctx}
{goal_ctx}
{codebase_ctx}
INSTRUCTIONS:
- Work on this task FULLY AUTONOMOUSLY using tools. Do NOT ask the user for input.
- Use terminal, read_file, write_file and other tools to complete the work.
- When the task is done, call task_complete with the task_id.
- If the task is impossible or blocked by a hard constraint, call task_complete anyway and explain why in the result.
- Do NOT wait. Do NOT ask questions. Just work and complete.
"""

        def on_tool_start(name, params):
            self.tool_start_signal.emit(
                name, json.dumps(params, ensure_ascii=False)[:200]
            )

        def on_tool_result(name, result):
            self.tool_result_signal.emit(
                name, str(result.get("result", ""))[:500], result.get("success", False)
            )

        try:
            response = self.brain.think(
                f"[AUTONOMOUS] Work on: {task['title']}",
                extra_context=context,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
                max_iterations=10,
                depth=4,
                isolated=True,
            )

            # Prüfe ob Task während Ausführung gelöscht wurde
            current = next((t for t in self.tasks.tasks if t["id"] == task_id), None)
            if not current:
                log.warning(
                    f"Task [{task_id}] wurde während Ausführung gelöscht — Ergebnis verwerfen"
                )
                self.state.set_mode("idle")
                return

            self.thought_signal.emit(f"🤖 {response}")
            self.state.set("last_thought", response[:200])

            # Falls Agent task_complete nicht aufgerufen hat → Auto-Complete
            if current.get("status") == "active":
                log.warning(
                    f"Task [{task_id}] still active after think() — auto-completing"
                )
                self.tasks.complete_task(task_id)
                self.thought_signal.emit(f"✅ Task auto-completed: {task['title']}")
        except Exception as e:
            log.error(f"Task execution failed [{task_id}]: {e}", exc_info=True)
            # Nur fail setzen wenn Task noch existiert
            if any(t["id"] == task_id for t in self.tasks.tasks):
                self.tasks.fail_task(task_id)
            self.thought_signal.emit(
                f"❌ Task failed: {task['title']} — {str(e)[:100]}"
            )
            self.state.set_mode("idle")
            return

        self.state.set_mode("idle")
        self._check_goal_completion(task)

    def _check_goal_completion(self, task: dict):
        """Prüft ob das Goal hinter einem Task abgeschlossen werden kann."""
        if not self.goal_engine:
            return

        task_id = task["id"]
        current_task = next((t for t in self.tasks.tasks if t["id"] == task_id), None)
        if not current_task or current_task.get("status") != "completed":
            return

        if hasattr(self.goal_engine, "complete_goals_for_task"):
            completed = self.goal_engine.complete_goals_for_task(task_id)
            for goal in completed:
                self.thought_signal.emit(f"✅ Goal completed: {goal['title']}")
        else:
            for goal in self.goal_engine.goals:
                if task_id in goal.get("task_ids", []) and goal["status"] == "active":
                    self.goal_engine.complete_goal(goal["id"])
                    self.thought_signal.emit(f"✅ Goal completed: {goal['title']}")

    # ── Controls ─────────────────────────────────────────────

    def start_autonomy(self):
        self.paused = False
        self.cycles_without_task = 0
        self.cycle_count = 0
        self._user_triggered = False  # Warmup zurücksetzen
        self.status_signal.emit("Autonomy: ACTIVE")
        self._wake_event.set()

    def pause_autonomy(self):
        self.paused = True
        self.state.set_mode("idle")
        self.status_signal.emit("Autonomy: PAUSED")
        self._wake_event.set()

    def stop(self):
        self.running = False
        self.paused = True
        # Laufendes Projekt stoppen
        if self.project_manager and self.project_manager.is_running:
            self.project_manager.stop()
        self._wake_event.set()

    def set_interval(self, seconds: int):
        self.interval = max(5, seconds)
