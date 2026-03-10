"""
Moruk AI OS - Task Manager
Strukturierte Task Engine mit Prioritäten, Status und Subtask-Support.
Moruk-Edition: Atomares Speichern, Backups & Logging.
"""

import json
import uuid
import os
import shutil
from datetime import datetime
from pathlib import Path
from core.logger import get_logger

DATA_DIR = Path(__file__).parent.parent / "data"
logger = get_logger("task_manager")


class TaskManager:
    """Verwaltet strukturierte Tasks für Moruk OS."""

    def __init__(self):
        self.tasks_path = DATA_DIR / "tasks.json"
        self.backup_path = DATA_DIR / "tasks.json.bak"
        self.tasks = self._load_tasks()

    def _load_tasks(self) -> list:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Versuche Hauptdatei zu laden
        if self.tasks_path.exists():
            try:
                with open(self.tasks_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.debug(f"Tasks erfolgreich geladen ({len(data)} Einträge).")
                    return data
            except (json.JSONDecodeError, IOError) as e:
                logger.error(
                    f"Fehler beim Laden von tasks.json: {e}. Suche nach Backup..."
                )

        # Backup-Versuch, falls Hauptdatei Schrott ist
        if self.backup_path.exists():
            try:
                with open(self.backup_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.warning("Backup-Datei geladen, da Hauptdatei korrupt war.")
                    return data
            except Exception as e:
                logger.critical(
                    f"Backup-Datei ebenfalls korrupt oder nicht lesbar: {e}"
                )

        return []

    def _save_tasks(self):
        """Speichert Tasks atomar und erstellt ein Backup."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = self.tasks_path.with_suffix(".tmp")

        try:
            # 1. In Temp-Datei schreiben
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, indent=2, ensure_ascii=False)

            # 2. Backup der alten Version erstellen (falls vorhanden)
            if self.tasks_path.exists():
                shutil.copy2(self.tasks_path, self.backup_path)

            # 3. Temp-Datei zu Hauptdatei umbenennen (atomarer Swap)
            os.replace(tmp_path, self.tasks_path)
            logger.debug("Tasks erfolgreich gespeichert (atomar).")
        except Exception as e:
            logger.error(f"Kritischer Fehler beim Speichern der Tasks: {e}")
            if tmp_path.exists():
                os.remove(tmp_path)

    def add_task(
        self,
        title: str,
        description: str = "",
        priority: str = "normal",
        parent_id: str = None,
    ) -> dict:
        """Erstellt einen neuen Task."""
        # Duplikat-Check nur für Top-Level Tasks (nicht Subtasks)
        if not parent_id:
            normalized_title = title.strip().lower()
            for existing in self.get_active_tasks():
                if (
                    not existing.get("parent_id")
                    and existing["title"].strip().lower() == normalized_title
                ):
                    logger.info(
                        f"Task '{title}' existiert bereits. Überspringe Neuanlage."
                    )
                    return existing

        task = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "description": description,
            "status": "pending",  # pending, active, completed, failed
            "priority": priority,  # low, normal, high, critical
            "parent_id": parent_id,
            "subtasks": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "completed_at": None,
        }
        self.tasks.append(task)
        self._save_tasks()
        logger.info(
            f"Neuer Task erstellt: [{task['id']}] {title}"
            + (f" (parent: {parent_id})" if parent_id else "")
        )
        return task

    def add_subtask_id(self, parent_id: str, subtask_id: str) -> bool:
        """Fügt eine Subtask-ID zur subtasks-Liste des Parent-Tasks hinzu."""
        for task in self.tasks:
            if task["id"] == parent_id:
                if subtask_id not in task["subtasks"]:
                    task["subtasks"].append(subtask_id)
                    task["updated_at"] = datetime.now().isoformat()
                    self._save_tasks()
                    logger.debug(
                        f"Subtask {subtask_id} zu Parent {parent_id} hinzugefügt"
                    )
                return True
        logger.warning(
            f"Parent Task [{parent_id}] nicht gefunden für Subtask-Zuordnung."
        )
        return False

    def get_subtasks(self, parent_id: str) -> list:
        """Gibt alle Subtasks eines Parent-Tasks zurück, in Erstellungsreihenfolge."""
        subtasks = [t for t in self.tasks if t.get("parent_id") == parent_id]
        # Sortierung nach Erstellungszeit
        subtasks.sort(key=lambda t: t.get("created_at", ""))
        return subtasks

    def get_parent_task(self, task_id: str) -> dict | None:
        """Gibt den Parent-Task eines Subtasks zurück."""
        task = self.get_task_by_id(task_id)
        if task and task.get("parent_id"):
            return self.get_task_by_id(task["parent_id"])
        return None

    def get_task_by_id(self, task_id: str) -> dict | None:
        """Gibt einen Task anhand seiner ID zurück."""
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return None

    def is_project_task(self, task_id: str) -> bool:
        """Prüft ob ein Task ein Projekt (hat Subtasks) ist."""
        task = self.get_task_by_id(task_id)
        return task is not None and len(task.get("subtasks", [])) > 0

    def is_subtask(self, task_id: str) -> bool:
        """Prüft ob ein Task ein Subtask ist."""
        task = self.get_task_by_id(task_id)
        return task is not None and task.get("parent_id") is not None

    def get_project_progress(self, parent_id: str) -> dict:
        """Gibt den Fortschritt eines Projekts zurück."""
        subtasks = self.get_subtasks(parent_id)
        total = len(subtasks)
        if total == 0:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "active": 0,
                "pending": 0,
                "progress": 0.0,
            }

        completed = sum(1 for t in subtasks if t["status"] == "completed")
        failed = sum(1 for t in subtasks if t["status"] == "failed")
        active = sum(1 for t in subtasks if t["status"] == "active")
        pending = sum(1 for t in subtasks if t["status"] == "pending")

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "active": active,
            "pending": pending,
            "progress": completed / total,
        }

    def update_status(self, task_id: str, status: str) -> bool:
        """Aktualisiert den Status eines Tasks."""
        for task in self.tasks:
            if task["id"] == task_id:
                old_status = task["status"]
                task["status"] = status
                task["updated_at"] = datetime.now().isoformat()
                if status == "completed":
                    task["completed_at"] = datetime.now().isoformat()
                self._save_tasks()
                logger.info(
                    f"Task [{task_id}] Status geändert: {old_status} -> {status}"
                )
                return True
        logger.warning(f"Update fehlgeschlagen: Task [{task_id}] nicht gefunden.")
        return False

    def complete_task(self, task_id: str) -> bool:
        """Markiert einen Task als erledigt."""
        return self.update_status(task_id, "completed")

    def fail_task(self, task_id: str) -> bool:
        """Markiert einen Task als fehlgeschlagen."""
        return self.update_status(task_id, "failed")

    def get_active_tasks(self) -> list:
        """Gibt alle noch nicht erledigten Tasks zurück."""
        return [t for t in self.tasks if t["status"] in ("pending", "active")]

    def get_next_task(self) -> dict | None:
        """Gibt den nächsten zu bearbeitenden Task zurück.
        Subtasks werden NICHT direkt zurückgegeben — die managed der ProjectManager.
        """
        priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        active = [t for t in self.get_active_tasks() if not t.get("parent_id")]
        if not active:
            return None
        active.sort(key=lambda t: priority_order.get(t["priority"], 2))
        return active[0]

    def get_task_context(self) -> str:
        """Gibt Task-Kontext für den System Prompt."""
        active = self.get_active_tasks()
        if not active:
            return "No active tasks."

        priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        active.sort(key=lambda t: priority_order.get(t["priority"], 2))

        lines = ["Active Tasks:"]
        for t in active[:5]:
            prefix = "  └─" if t.get("parent_id") else "-"
            lines.append(f"{prefix} [{t['id']}] {t['title']} ({t['priority']})")
        return "\n".join(lines)

    def delete_task(self, task_id: str) -> bool:
        """Löscht einen Task komplett aus der Liste. Bei Projekten auch alle Subtasks."""
        task = self.get_task_by_id(task_id)
        if not task:
            logger.warning(f"Löschen fehlgeschlagen: Task [{task_id}] nicht gefunden.")
            return False

        # Wenn es ein Projekt ist, auch alle Subtasks löschen
        subtask_ids = task.get("subtasks", [])
        ids_to_remove = {task_id} | set(subtask_ids)

        initial_count = len(self.tasks)
        self.tasks = [t for t in self.tasks if t["id"] not in ids_to_remove]

        if len(self.tasks) < initial_count:
            self._save_tasks()
            logger.info(
                f"Task [{task_id}] gelöscht"
                + (f" (inkl. {len(subtask_ids)} Subtasks)" if subtask_ids else "")
            )
            return True
        return False

    def clear_all(self):
        """Löscht alle Tasks komplett."""
        self.tasks = []
        self._save_tasks()
        logger.info("Alle Tasks wurden gelöscht.")

    def clear_completed(self):
        """Löscht alle abgeschlossenen Tasks (status=completed)."""
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if t["status"] != "completed"]
        removed = before - len(self.tasks)
        if removed > 0:
            self._save_tasks()
            logger.info(f"{removed} abgeschlossene Tasks gelöscht.")

    def reload(self):
        """Lädt die Tasks neu von der Festplatte."""
        self.tasks = self._load_tasks()
        logger.debug("Tasks manuell neu geladen.")
