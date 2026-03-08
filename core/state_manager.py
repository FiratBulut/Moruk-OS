"""
Moruk AI OS - State Manager
Persistenter Agent-Zustand über Sessions hinweg.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from core.logger import get_logger

log = get_logger("state")
DATA_DIR = Path(__file__).parent.parent / "data"

# Interactions werden alle N Aufrufe auf Disk geschrieben
INTERACTION_SAVE_INTERVAL = 10


class StateManager:
    """Verwaltet den persistenten Zustand von Moruk OS."""

    DEFAULT_STATE = {
        "identity": "Moruk",
        "mode": "idle",           # idle, working, thinking, reflecting
        "current_goal": None,
        "active_task": None,
        "last_action": None,
        "last_thought": None,
        "session_count": 0,
        "total_interactions": 0,
        "created_at": None,
        "last_active": None,
        "uptime_sessions": []
    }

    def __init__(self):
        self.state_path = DATA_DIR / "agent_state.json"
        self.state = self._load_state()
        self._interaction_dirty_count = 0
        self._register_session()

    def _load_state(self) -> dict:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self.state_path.exists():
            try:
                with open(self.state_path, "r") as f:
                    saved = json.load(f)
                return {**self.DEFAULT_STATE, **saved}
            except (json.JSONDecodeError, IOError):
                pass
        state = self.DEFAULT_STATE.copy()
        state["created_at"] = datetime.now().isoformat()
        return state

    def _save_state(self, force: bool = False):
        """Speichert State atomar via Temp-Datei."""
        tmp_path = self.state_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.state_path)
        except Exception as e:
            log.error(f"State speichern fehlgeschlagen: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def flush(self):
        """Erzwingt sofortiges Speichern — z.B. beim Shutdown."""
        self._save_state()
        self._interaction_dirty_count = 0

    def _register_session(self):
        """Registriert einen neuen App-Start."""
        self.state["session_count"] += 1
        self.state["last_active"] = datetime.now().isoformat()
        self.state["uptime_sessions"].append({
            "started": datetime.now().isoformat(),
            "session_number": self.state["session_count"]
        })
        self.state["uptime_sessions"] = self.state["uptime_sessions"][-20:]
        self._save_state()

    # ── Public API ────────────────────────────────────────────

    def get(self, key: str, default=None):
        return self.state.get(key, default)

    def set(self, key: str, value):
        self.state[key] = value
        self.state["last_active"] = datetime.now().isoformat()
        self._save_state()

    def set_mode(self, mode: str):
        self.state["mode"] = mode
        self._save_state()

    def set_goal(self, goal: str):
        self.state["current_goal"] = goal
        self.state["mode"] = "working"
        self._save_state()

    def clear_goal(self):
        self.state["current_goal"] = None
        self.state["active_task"] = None
        self.state["mode"] = "idle"
        self._save_state()

    def record_interaction(self):
        """Zählt Interaktionen — schreibt nur alle N Aufrufe auf Disk."""
        self.state["total_interactions"] += 1
        self.state["last_active"] = datetime.now().isoformat()
        self._interaction_dirty_count += 1
        if self._interaction_dirty_count >= INTERACTION_SAVE_INTERVAL:
            self._save_state()
            self._interaction_dirty_count = 0

    def get_context_summary(self) -> str:
        """Gibt State-Kontext für den System Prompt."""
        parts = [
            f"Mode: {self.state['mode']}",
            f"Session: #{self.state['session_count']}",
            f"Total Interactions: {self.state['total_interactions']}",
        ]
        if self.state["current_goal"]:
            parts.append(f"Current Goal: {self.state['current_goal']}")
        if self.state["active_task"]:
            parts.append(f"Active Task: {self.state['active_task']}")
        if self.state["last_action"]:
            parts.append(f"Last Action: {self.state['last_action']}")
        return "\n".join(parts)

    def is_first_session(self) -> bool:
        return self.state["session_count"] <= 1

    def was_restarted(self) -> bool:
        return self.state["session_count"] > 1
