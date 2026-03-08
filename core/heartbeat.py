"""
Moruk AI OS - Heartbeat Monitor
Überwacht ob Brain, AutonomyLoop und TaskManager noch leben.
Wenn eine Komponente hängt oder tot ist → Signal an MainWindow.
"""

import time
import threading
from datetime import datetime
from core.logger import get_logger

log = get_logger("heartbeat")


class Heartbeat:
    """
    Überwacht alle registrierten Komponenten in einem Background-Thread.
    MainWindow registriert Komponenten via register().
    Bei Problem → on_failure(name, reason) Callback.
    """

    CHECK_INTERVAL = 10  # Sekunden zwischen Checks

    def __init__(self, on_failure=None):
        self._components = {}   # name → {"obj": ..., "check_fn": ..., "last_ok": ...}
        self._running = False
        self._thread = None
        self.on_failure = on_failure  # Callback: fn(name: str, reason: str)
        self._lock = threading.Lock()

    def register(self, name: str, obj, check_fn=None):
        """
        Registriert eine Komponente für Überwachung.
        check_fn(obj) → True wenn OK, False wenn tot/hängend.
        Wenn kein check_fn → default checks werden verwendet.
        """
        with self._lock:
            self._components[name] = {
                "obj": obj,
                "check_fn": check_fn or self._default_check(name),
                "last_ok": datetime.now().isoformat(),
                "failures": 0,
            }
        log.info(f"Heartbeat: registered '{name}'")

    def _default_check(self, name: str):
        """Gibt default Check-Funktion für bekannte Komponenten zurück."""
        def check_brain(obj):
            # Brain lebt wenn client gesetzt und is_configured()
            return obj is not None and obj.is_configured()

        def check_autonomy(obj):
            # AutonomyLoop lebt wenn QThread isRunning()
            return obj is not None and obj.isRunning()

        def check_task_manager(obj):
            # TaskManager lebt wenn tasks Attribut vorhanden und lesbar
            return obj is not None and isinstance(obj.tasks, list)

        def check_generic(obj):
            return obj is not None

        checks = {
            "brain":          check_brain,
            "autonomy":       check_autonomy,
            "autonomy_loop":  check_autonomy,
            "task_manager":   check_task_manager,
            "tasks":          check_task_manager,
        }
        return checks.get(name, check_generic)

    def start(self):
        """Startet den Heartbeat-Thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="heartbeat")
        self._thread.start()
        log.info("Heartbeat started")

    def stop(self):
        """Stoppt den Heartbeat-Thread."""
        self._running = False
        log.info("Heartbeat stopped")

    def _run(self):
        while self._running:
            time.sleep(self.CHECK_INTERVAL)
            if not self._running:
                break
            self._check_all()

    def _check_all(self):
        with self._lock:
            components = dict(self._components)

        for name, info in components.items():
            obj = info["obj"]
            check_fn = info["check_fn"]
            try:
                alive = check_fn(obj)
            except Exception as e:
                alive = False
                log.warning(f"Heartbeat check exception for '{name}': {e}")

            if alive:
                with self._lock:
                    if name in self._components:
                        self._components[name]["last_ok"] = datetime.now().isoformat()
                        self._components[name]["failures"] = 0
            else:
                with self._lock:
                    if name in self._components:
                        self._components[name]["failures"] += 1
                        failures = self._components[name]["failures"]

                reason = self._diagnose(name, obj)
                log.warning(f"Heartbeat FAIL [{name}] (#{failures}): {reason}")

                if self.on_failure:
                    try:
                        self.on_failure(name, reason)
                    except Exception as e:
                        log.error(f"on_failure callback error: {e}")

    def _diagnose(self, name: str, obj) -> str:
        """Gibt eine lesbare Fehlerursache zurück."""
        if obj is None:
            return "Object is None — not initialized"

        if name in ("autonomy", "autonomy_loop"):
            try:
                if not obj.isRunning():
                    return "QThread not running — crashed or never started"
                if obj.paused:
                    return "Thread running but paused"
            except Exception as e:
                return f"Cannot inspect thread: {e}"

        if name == "brain":
            try:
                if obj.client is None:
                    return "No API client — missing API key or provider not configured"
                if not obj.is_configured():
                    return "Brain not configured — check API key in Settings"
            except Exception as e:
                return f"Cannot inspect brain: {e}"

        if name in ("task_manager", "tasks"):
            try:
                _ = obj.tasks
            except Exception as e:
                return f"TaskManager.tasks not accessible: {e}"

        return "Component check returned False"

    def get_status(self) -> dict:
        """Gibt aktuellen Status aller Komponenten zurück (für UI/Stats)."""
        with self._lock:
            return {
                name: {
                    "alive": info["failures"] == 0,
                    "last_ok": info["last_ok"],
                    "failures": info["failures"],
                }
                for name, info in self._components.items()
            }

    def check_pulse(self) -> str:
        """Kompatibilität mit altem Stub. Gibt Status-String zurück."""
        status = self.get_status()
        if not status:
            return "No components registered."

        dead = [n for n, s in status.items() if not s["alive"]]
        if dead:
            return f"⚠ Dead components: {', '.join(dead)}"
        return f"✅ All {len(status)} components alive."
