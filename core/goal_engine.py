"""
Moruk AI OS - Goal Generation Engine
Proaktive Zielerkennung: Signal Detection → Opportunity Analysis → Goal Generation.
Verwandelt Moruk von reaktiv zu proaktiv.
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter
from core.logger import get_logger

log = get_logger("goals")
DATA_DIR = Path(__file__).parent.parent / "data"


# ═══════════════════════════════════════════════
# 1. SIGNAL DETECTOR
# ═══════════════════════════════════════════════


class SignalDetector:
    """Scannt interne Daten nach Signalen die Ziele auslösen könnten."""

    def __init__(self):
        self.cooldowns = {}
        self.cooldown_durations = {
            "repeated_failure": timedelta(minutes=10),
            "low_tool_efficiency": timedelta(minutes=30),
            "user_pattern": timedelta(hours=1),
            "optimization": timedelta(minutes=30),
            "maintenance": timedelta(hours=2),
            "learning": timedelta(minutes=15),
            "system_health": timedelta(hours=1),
            # Neue proaktive Signal-Typen
            "daily_morning": timedelta(hours=20),  # max 1x pro Tag
            "daily_evening": timedelta(hours=20),
            "idle_suggestion": timedelta(minutes=30),  # alle 30min wenn idle
            "new_file": timedelta(minutes=10),  # neue Datei im Projekt
            "long_idle": timedelta(hours=2),  # sehr lang idle
        }

    def scan(
        self, reflector=None, tasks=None, memory=None, state=None, health_monitor=None
    ) -> list:
        """Scannt alle Quellen und gibt gefundene Signale zurück."""
        signals = []

        if reflector:
            signals.extend(self._scan_reflections(reflector))
        if tasks:
            signals.extend(self._scan_tasks(tasks))
        if memory:
            signals.extend(self._scan_memory(memory))
        if state:
            signals.extend(self._scan_state(state))
        if health_monitor:
            signals.extend(self._scan_system_health(health_monitor))

        # Proaktive Zeit- und Event-basierte Signale (immer scannen)
        signals.extend(self._scan_time_based())
        signals.extend(self._scan_idle(state))
        signals.extend(self._scan_file_events())

        # Cooldown Filter
        active_signals = []
        now = datetime.now()
        for signal in signals:
            sig_type = signal["type"]
            last_fired = self.cooldowns.get(sig_type)
            cooldown = self.cooldown_durations.get(sig_type, timedelta(minutes=15))

            if last_fired is None or (now - last_fired) > cooldown:
                active_signals.append(signal)
                self.cooldowns[sig_type] = now

        if active_signals:
            log.info(f"Signals detected: {[s['type'] for s in active_signals]}")

        return active_signals

    def _scan_reflections(self, reflector) -> list:
        signals = []
        stats = reflector.get_full_stats()

        # Wiederholte Fehler (3+ gleicher Typ)
        errors = stats.get("error_patterns", [])
        if errors:
            error_types = Counter(e.get("error_type", "unknown") for e in errors[-20:])
            for error_type, count in error_types.items():
                if count >= 3 and error_type != "unknown":
                    signals.append(
                        {
                            "type": "repeated_failure",
                            "detail": f"Error '{error_type}' occurred {count}x recently",
                            "data": {"error_type": error_type, "count": count},
                            "impact": min(1.0, count * 0.15),
                            "confidence": 0.8,
                        }
                    )

        # Niedrige Erfolgsrate
        rate = stats.get("success_rate", 100)
        if rate < 60 and stats.get("total_actions", 0) > 10:
            signals.append(
                {
                    "type": "low_tool_efficiency",
                    "detail": f"Overall success rate dropped to {rate:.0f}%",
                    "data": {"success_rate": rate},
                    "impact": 0.7,
                    "confidence": 0.7,
                }
            )

        # Tool mit schlechter Performance
        tool_usage = stats.get("tool_usage", {})
        for tool, count in tool_usage.items():
            if count >= 5:
                tool_errors = len([e for e in errors if e.get("tool") == tool])
                if count > 0 and tool_errors / count > 0.5:
                    signals.append(
                        {
                            "type": "low_tool_efficiency",
                            "detail": f"Tool '{tool}' fails >50% ({tool_errors}/{count})",
                            "data": {"tool": tool, "fail_rate": tool_errors / count},
                            "impact": 0.6,
                            "confidence": 0.75,
                        }
                    )

        return signals

    def _scan_tasks(self, tasks) -> list:
        signals = []

        all_tasks = tasks.tasks
        recent = [
            t
            for t in all_tasks
            if t.get("updated_at", "")
            > (datetime.now() - timedelta(hours=24)).isoformat()
        ]
        failed = [t for t in recent if t.get("status") == "failed"]

        if len(failed) >= 3:
            signals.append(
                {
                    "type": "repeated_failure",
                    "detail": f"{len(failed)} tasks failed in last 24h",
                    "data": {"failed_tasks": len(failed)},
                    "impact": 0.6,
                    "confidence": 0.7,
                }
            )

        # Langlebige pending Tasks (>2h alt)
        old_pending = [
            t
            for t in tasks.get_active_tasks()
            if t.get("created_at", "")
            < (datetime.now() - timedelta(hours=2)).isoformat()
        ]
        if old_pending:
            signals.append(
                {
                    "type": "optimization",
                    "detail": f"{len(old_pending)} tasks pending for >2 hours",
                    "data": {"stale_tasks": len(old_pending)},
                    "impact": 0.4,
                    "confidence": 0.6,
                }
            )

        return signals

    def _scan_memory(self, memory) -> list:
        signals = []
        stats = memory.get_stats()

        total = stats.get("long_term_count", 0)
        if total > 400:
            signals.append(
                {
                    "type": "maintenance",
                    "detail": f"Memory has {total} entries, cleanup recommended",
                    "data": {"memory_count": total},
                    "impact": 0.3,
                    "confidence": 0.9,
                }
            )

        return signals

    def _scan_state(self, state) -> list:
        signals = []

        interactions = state.get("total_interactions", 0)
        sessions = state.get("session_count", 1)
        avg_per_session = interactions / max(sessions, 1)

        if avg_per_session > 50:
            signals.append(
                {
                    "type": "learning",
                    "detail": f"High interaction rate ({avg_per_session:.0f}/session), consider learning patterns",
                    "data": {"avg_interactions": avg_per_session},
                    "impact": 0.3,
                    "confidence": 0.5,
                }
            )

        return signals

    def _scan_system_health(self, health_monitor) -> list:
        """Prüft System Health und generiert Signale bei Problemen."""
        signals = []
        try:
            signal = health_monitor.get_signal_for_goal_engine()
            if signal:
                signals.append(signal)
        except Exception as e:
            log.warning(f"Health monitor scan failed: {e}")
        return signals

    def _scan_time_based(self) -> list:
        """Tageszeit-basierte Goals: Morgen-Check, Abend-Summary."""
        signals = []
        hour = datetime.now().hour

        # Morgen-Routine: 7-10 Uhr
        if 7 <= hour < 10:
            signals.append(
                {
                    "type": "daily_morning",
                    "detail": "Morning routine: system health check + task review",
                    "data": {"hour": hour},
                    "impact": 0.6,
                    "confidence": 0.95,
                }
            )

        # Abend-Summary: 19-22 Uhr
        elif 19 <= hour < 22:
            signals.append(
                {
                    "type": "daily_evening",
                    "detail": "Evening summary: reflect on completed tasks and lessons learned",
                    "data": {"hour": hour},
                    "impact": 0.5,
                    "confidence": 0.9,
                }
            )

        return signals

    def _scan_idle(self, state=None) -> list:
        """Schlägt proaktiv etwas vor wenn das System lange idle ist."""
        signals = []
        if state is None:
            return signals

        last_interaction = state.get("last_active", "") or state.get(
            "last_interaction_at", ""
        )
        if not last_interaction:
            return signals

        try:
            last_dt = datetime.fromisoformat(last_interaction)
            idle_minutes = (datetime.now() - last_dt).total_seconds() / 60

            # 30+ Minuten idle → leichte Aufgabe vorschlagen
            if idle_minutes >= 30:
                signals.append(
                    {
                        "type": "idle_suggestion",
                        "detail": f"System idle for {idle_minutes:.0f} minutes — good time for background optimization",
                        "data": {"idle_minutes": idle_minutes},
                        "impact": 0.4,
                        "confidence": 0.7,
                    }
                )

            # 2+ Stunden idle → Memory-Cleanup oder Reflection
            if idle_minutes >= 120:
                signals.append(
                    {
                        "type": "long_idle",
                        "detail": f"System idle for {idle_minutes:.0f} minutes — run deep reflection and memory cleanup",
                        "data": {"idle_minutes": idle_minutes},
                        "impact": 0.55,
                        "confidence": 0.85,
                    }
                )

        except Exception:
            pass

        return signals

    def _scan_file_events(self) -> list:
        """Erkennt neue oder kürzlich geänderte Dateien im Projekt-Ordner."""
        signals = []
        project_root = Path(__file__).parent.parent
        watch_dirs = [
            project_root / "plugins",
            project_root / "core",
            project_root / "data",
        ]

        now = datetime.now()
        cutoff = now - timedelta(minutes=5)

        new_files = []
        for watch_dir in watch_dirs:
            if not watch_dir.exists():
                continue
            try:
                for f in watch_dir.glob("*.py"):
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if mtime > cutoff:
                        new_files.append(str(f.relative_to(project_root)))
            except Exception:
                continue

        if new_files:
            signals.append(
                {
                    "type": "new_file",
                    "detail": f"New/modified files detected: {', '.join(new_files[:3])}",
                    "data": {"files": new_files},
                    "impact": 0.5,
                    "confidence": 0.8,
                }
            )

        return signals


# ═══════════════════════════════════════════════
# 2. OPPORTUNITY ANALYZER
# ═══════════════════════════════════════════════


class OpportunityAnalyzer:
    """Bewertet ob ein Signal ein Ziel wert ist."""

    THRESHOLD = 0.35  # Minimum score für Goal-Erzeugung

    def evaluate(self, signal: dict, existing_goals: list) -> dict | None:
        """
        Bewertet ein Signal. Returns Goal-Proposal oder None.
        Score = impact * 0.4 + confidence * 0.3 + novelty * 0.2 - effort * 0.3
        """
        impact = signal.get("impact", 0.5)
        confidence = signal.get("confidence", 0.5)
        novelty = self._calc_novelty(signal, existing_goals)
        effort = self._estimate_effort(signal)

        score = impact * 0.4 + confidence * 0.3 + novelty * 0.2 - effort * 0.3

        if score < self.THRESHOLD:
            log.debug(f"Signal '{signal['type']}' below threshold: score={score:.2f}")
            return None

        # Redundanz-Check
        if self._is_redundant(signal, existing_goals):
            log.debug(f"Signal '{signal['type']}' redundant with existing goal")
            return None

        return {
            "signal": signal,
            "score": score,
            "impact": impact,
            "confidence": confidence,
            "novelty": novelty,
            "effort": effort,
        }

    def _calc_novelty(self, signal: dict, existing_goals: list) -> float:
        """Wie neu ist dieses Signal? 1.0 = komplett neu."""
        sig_type = signal["type"]
        similar = [
            g
            for g in existing_goals
            if g.get("source_signal") == sig_type and g.get("status") != "discarded"
        ]
        if not similar:
            return 1.0
        elif len(similar) == 1:
            return 0.5
        else:
            return 0.2

    def _estimate_effort(self, signal: dict) -> float:
        """Geschätzter Aufwand 0-1."""
        effort_map = {
            "repeated_failure": 0.4,
            "low_tool_efficiency": 0.5,
            "user_pattern": 0.6,
            "optimization": 0.5,
            "maintenance": 0.2,
            "learning": 0.3,
            "system_health": 0.3,
        }
        return effort_map.get(signal["type"], 0.5)

    def _is_redundant(self, signal: dict, existing_goals: list) -> bool:
        """Prüft ob ein ähnliches Ziel schon aktiv ist."""
        for goal in existing_goals:
            if goal.get("status") in ("pending", "active"):
                if goal.get("source_signal") == signal["type"]:
                    return True
        return False


# ═══════════════════════════════════════════════
# 3. GOAL QUEUE MANAGER
# ═══════════════════════════════════════════════


class GoalEngine:
    """Zentrale Goal Generation + Management Engine."""

    MAX_ACTIVE_GOALS = 5
    MAX_STORED_GOALS = 50

    def __init__(
        self, reflector=None, tasks=None, memory=None, state=None, health_monitor=None
    ):
        self.reflector = reflector
        self.tasks = tasks
        self.memory = memory
        self.state = state
        self.health_monitor = health_monitor

        self.goals_path = DATA_DIR / "goals.json"
        self.goals = self._load_goals()

        self.detector = SignalDetector()
        self.analyzer = OpportunityAnalyzer()

    def _load_goals(self) -> list:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self.goals_path.exists():
            try:
                with open(self.goals_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save_goals(self):
        """Speichert Goals atomar via Temp-Datei (konsistent mit TaskManager)."""
        self.goals = self.goals[-self.MAX_STORED_GOALS :]
        tmp_path = self.goals_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.goals, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.goals_path)
        except Exception as e:
            log.error(f"Fehler beim Speichern der Goals: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    # ── Core: Scan → Analyze → Generate ──────────────────────

    def run_cycle(self) -> list:
        """
        Ein Goal-Generation-Zyklus:
        1. Signale scannen
        2. Bewerten
        3. Goals generieren
        4. In Queue einfügen
        Returns: Neu generierte Goals
        """
        active = [g for g in self.goals if g["status"] in ("pending", "active")]
        if len(active) >= self.MAX_ACTIVE_GOALS:
            return []

        signals = self.detector.scan(
            reflector=self.reflector,
            tasks=self.tasks,
            memory=self.memory,
            state=self.state,
            health_monitor=self.health_monitor,
        )

        if not signals:
            return []

        new_goals = []
        for signal in signals:
            proposal = self.analyzer.evaluate(signal, self.goals)
            if proposal:
                goal = self._create_goal(proposal)
                if goal:
                    new_goals.append(goal)

        if new_goals:
            self._sort_queue()
            self._save_goals()
            log.info(
                f"Generated {len(new_goals)} new goals: "
                f"{[g['title'][:40] for g in new_goals]}"
            )

        return new_goals

    def _create_goal(self, proposal: dict) -> dict:
        """Erstellt ein strukturiertes Goal-Objekt."""
        signal = proposal["signal"]

        if not self._safety_check(signal):
            log.warning(f"Goal rejected by safety check: {signal['type']}")
            return None

        title_map = {
            "repeated_failure": f"Fix recurring {signal.get('data', {}).get('error_type', 'error')} errors",
            "low_tool_efficiency": f"Improve reliability of {signal.get('data', {}).get('tool', 'tools')}",
            "optimization": "Optimize pending task processing",
            "maintenance": "Run system maintenance and cleanup",
            "learning": "Analyze interaction patterns for improvements",
            "user_pattern": "Automate detected user workflow",
            "system_health": "Run system health repair",
            "daily_morning": "Morning routine: system check + task review",
            "daily_evening": "Evening reflection: summarize today's work",
            "idle_suggestion": "Background optimization while idle",
            "long_idle": "Deep reflection and memory cleanup",
            "new_file": "Analyze and integrate newly detected files",
        }

        goal = {
            "id": f"goal_{str(uuid.uuid4())[:6]}",
            "title": title_map.get(signal["type"], f"Address: {signal['detail'][:60]}"),
            "reason": signal["detail"],
            "source_signal": signal["type"],
            "priority": proposal["score"],
            "estimated_effort": proposal["effort"],
            "status": "pending",  # pending, active, completed, failed, discarded
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "completed_at": None,
            "task_ids": [],  # Verknüpfte Task-IDs
        }

        self.goals.append(goal)
        log.info(
            f"Goal created: [{goal['id']}] {goal['title']} (priority={goal['priority']:.2f})"
        )
        return goal

    def _safety_check(self, signal: dict) -> bool:
        """Sicherheitsprüfung: Nur sichere, lokale, reversible Ziele."""
        safe_types = {
            "repeated_failure",
            "low_tool_efficiency",
            "optimization",
            "maintenance",
            "learning",
            "user_pattern",
            "system_health",
            # Proaktive Typen
            "daily_morning",
            "daily_evening",
            "idle_suggestion",
            "long_idle",
            "new_file",
        }
        return signal.get("type") in safe_types

    def _sort_queue(self):
        """Sortiert Goals nach Priorität (höchste zuerst)."""
        pending = [g for g in self.goals if g["status"] == "pending"]
        rest = [g for g in self.goals if g["status"] != "pending"]
        pending.sort(key=lambda g: g.get("priority", 0), reverse=True)
        self.goals = pending + rest

    # ── Goal Lifecycle ────────────────────────────────────────

    def get_next_goal(self) -> dict | None:
        """Gibt das nächste zu bearbeitende Goal zurück."""
        for goal in self.goals:
            if goal["status"] == "pending":
                return goal
        return None

    def activate_goal(self, goal_id: str) -> bool:
        """Aktiviert ein Goal und erstellt einen Task dafür."""
        for goal in self.goals:
            if goal["id"] == goal_id:
                goal["status"] = "active"
                goal["updated_at"] = datetime.now().isoformat()

                if self.tasks:
                    task = self.tasks.add_task(
                        title=f"🎯 {goal['title']}",
                        description=f"Auto-generated goal: {goal['reason']}",
                        priority="normal",
                    )
                    goal["task_ids"].append(task["id"])

                self._save_goals()
                log.info(f"Goal activated: {goal_id}")
                return True
        return False

    def complete_goal(self, goal_id: str):
        """Markiert ein einzelnes Goal als abgeschlossen."""
        for goal in self.goals:
            if goal["id"] == goal_id:
                goal["status"] = "completed"
                goal["completed_at"] = datetime.now().isoformat()
                goal["updated_at"] = datetime.now().isoformat()
                self._save_goals()

                if self.memory:
                    self.memory.remember_long(
                        f"Completed self-generated goal: {goal['title']}",
                        category="reflection",
                        tags=["goal", "self-improvement"],
                    )
                log.info(f"Goal completed: {goal_id}")
                return

    def complete_goals_for_task(self, task_id: str) -> list:
        """
        Schließt alle aktiven Goals ab die mit task_id verknüpft sind.
        Wird von autonomy_loop._check_goal_completion() aufgerufen.
        Gibt Liste der abgeschlossenen Goals zurück.
        """
        completed = []
        for goal in self.goals:
            if task_id in goal.get("task_ids", []) and goal["status"] == "active":
                goal["status"] = "completed"
                goal["completed_at"] = datetime.now().isoformat()
                goal["updated_at"] = datetime.now().isoformat()
                completed.append(goal)
                log.info(
                    f"Goal completed via task [{task_id}]: {goal['id']} — {goal['title']}"
                )

                if self.memory:
                    self.memory.remember_long(
                        f"Completed self-generated goal: {goal['title']}",
                        category="reflection",
                        tags=["goal", "self-improvement"],
                    )

        if completed:
            self._save_goals()

        return completed

    def discard_goal(self, goal_id: str):
        for goal in self.goals:
            if goal["id"] == goal_id:
                goal["status"] = "discarded"
                goal["updated_at"] = datetime.now().isoformat()
                self._save_goals()
                return

    # ── Context / Stats ───────────────────────────────────────

    def get_active_goals(self) -> list:
        return [g for g in self.goals if g["status"] in ("pending", "active")]

    def get_goal_context(self) -> str:
        """Kontext für System Prompt."""
        active = self.get_active_goals()
        if not active:
            return ""

        parts = [f"Self-Generated Goals ({len(active)}):"]
        for goal in active[:5]:
            parts.append(
                f"  🎯 [{goal['status']}] {goal['title']} (priority: {goal['priority']:.2f})"
            )
            parts.append(f"     Reason: {goal['reason'][:80]}")
        return "\n".join(parts)

    def get_stats(self) -> dict:
        statuses = Counter(g["status"] for g in self.goals)
        return {
            "total_goals": len(self.goals),
            "pending": statuses.get("pending", 0),
            "active": statuses.get("active", 0),
            "completed": statuses.get("completed", 0),
            "failed": statuses.get("failed", 0),
            "discarded": statuses.get("discarded", 0),
        }
