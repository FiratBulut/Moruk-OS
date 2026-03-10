"""
Moruk AI OS - Recovery System
Schützt gegen Self-Edit-Katastrophen.
- Automatische Snapshots vor jedem self_edit
- Rollback zu letztem funktionierenden Zustand
- Standalone recovery.py als Notfall-Tool
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from core.logger import get_logger

log = get_logger("recovery")

PROJECT_ROOT = Path(__file__).parent.parent
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"


# Kritische Dateien die gesnapshot werden
def _generate_architecture_md() -> str:
    """Generiert architecture.md automatisch aus dem aktuellen Dateisystem."""
    lines = [
        "# Moruk OS — Architecture",
        f"*Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    for folder in ["core", "ui", "plugins"]:
        d = PROJECT_ROOT / folder
        if not d.exists():
            continue
        lines.append(f"## {folder}/")
        for f in sorted(d.glob("*.py")):
            # Ersten Docstring oder PLUGIN_DESCRIPTION lesen
            desc = ""
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                # PLUGIN_DESCRIPTION
                for line in text.splitlines():
                    if line.startswith("PLUGIN_DESCRIPTION"):
                        raw = line.split("=", 1)[-1].strip()
                        desc = raw.strip('"').strip("'").strip("()").strip()[:80]
                        break
                # Modul-Docstring
                if not desc:
                    import ast as _ast

                    try:
                        tree = _ast.parse(text)
                        ds = _ast.get_docstring(tree)
                        if ds:
                            desc = ds.splitlines()[0][:80]
                    except Exception:
                        pass
            except Exception:
                pass
            lines.append(f"- **{f.name}** — {desc}" if desc else f"- **{f.name}**")
        lines.append("")

    # Config
    lines.append("## config/")
    for cfg in ["system_prompt.txt", "architecture.md", "user_settings.json"]:
        if (PROJECT_ROOT / "config" / cfg).exists():
            lines.append(f"- **{cfg}**")

    return "\n".join(lines)


def _get_critical_files() -> list:
    """
    Dynamisch alle .py Dateien aus core/, ui/, plugins/ sammeln
    + fixe Config-Dateien. Neue Plugins/Module werden automatisch erkannt.
    """
    files = []
    scan_dirs = ["core", "ui", "plugins"]
    for folder in scan_dirs:
        d = PROJECT_ROOT / folder
        if d.exists():
            for f in sorted(d.glob("*.py")):
                files.append(f"{folder}/{f.name}")
    # Root-Level
    if (PROJECT_ROOT / "main.py").exists():
        files.append("main.py")
    # Config-Dateien
    for cfg in ["config/system_prompt.txt", "config/architecture.md"]:
        if (PROJECT_ROOT / cfg).exists():
            files.append(cfg)
    return files


# Wird bei jedem Snapshot-Call frisch berechnet — nie veraltet
CRITICAL_FILES = _get_critical_files()

# Dateien die Moruk lernt/erstellt — IMMER behalten bei Recovery!
LEARNED_FILES = [
    "data/memory.db",
    "data/self_profile.json",
    "data/reflection_log.json",
    "data/reflection_stats.json",
    "data/strategy_rules.json",
    "data/memory_short.json",
    "data/user_settings.json",
    "data/goals.json",
    "data/tasks.json",
    "data/state.json",
]

MAX_SNAPSHOTS = 10  # Maximal gespeicherte Snapshots


class RecoveryManager:
    """Verwaltet Snapshots und Recovery."""

    def __init__(self):
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        self.manifest_path = SNAPSHOT_DIR / "manifest.json"
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> list:
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save_manifest(self):
        with open(self.manifest_path, "w") as f:
            json.dump(self.manifest, f, indent=2)

    # ── Snapshot erstellen ────────────────────────────────────

    def create_snapshot(self, reason: str = "manual") -> dict | None:
        """Erstellt einen Snapshot aller kritischen Dateien + Plugins + Learned Data."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_dir = SNAPSHOT_DIR / timestamp

        try:
            snap_dir.mkdir(parents=True, exist_ok=True)
            files_saved = []

            # architecture.md vor Snapshot aktualisieren
            try:
                arch_path = PROJECT_ROOT / "config" / "architecture.md"
                arch_path.parent.mkdir(parents=True, exist_ok=True)
                arch_path.write_text(_generate_architecture_md(), encoding="utf-8")
                log.info("architecture.md auto-updated")
            except Exception as e:
                log.warning(f"architecture.md update failed: {e}")

            # Dynamisch alle aktuellen Dateien scannen (inkl. neue Plugins)
            current_files = _get_critical_files()
            for rel_path in current_files:
                src = PROJECT_ROOT / rel_path
                if src.exists():
                    dst = snap_dir / rel_path
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    files_saved.append(rel_path)

            # Learned Data (Memories, Self-Profile, etc.)
            for rel_path in LEARNED_FILES:
                src = PROJECT_ROOT / rel_path
                if src.exists():
                    dst = snap_dir / rel_path
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    files_saved.append(rel_path)

            entry = {
                "id": timestamp,
                "reason": reason,
                "created_at": datetime.now().isoformat(),
                "files": files_saved,
                "file_count": len(files_saved),
            }

            self.manifest.append(entry)

            # Alte Snapshots aufräumen
            while len(self.manifest) > MAX_SNAPSHOTS:
                old = self.manifest.pop(0)
                old_dir = SNAPSHOT_DIR / old["id"]
                if old_dir.exists():
                    shutil.rmtree(str(old_dir), ignore_errors=True)

            self._save_manifest()
            log.info(
                f"Snapshot created: {timestamp} ({len(files_saved)} files, reason: {reason})"
            )
            return entry

        except Exception as e:
            log.error(f"Snapshot creation failed: {e}")
            return None

    # ── Recovery ──────────────────────────────────────────────

    def get_snapshots(self) -> list:
        """Gibt alle verfügbaren Snapshots zurück."""
        return list(reversed(self.manifest))  # Neueste zuerst

    def restore_snapshot(
        self, snapshot_id: str = None, preserve_learned: bool = True
    ) -> dict:
        """
        Stellt einen Snapshot wieder her.
        preserve_learned=True: Memories, Self-Profile, Tasks, Settings bleiben erhalten.
        Plugins werden aus Snapshot HINZUGEFÜGT (nicht überschrieben).
        """
        if not self.manifest:
            return {"success": False, "error": "No snapshots available"}

        if snapshot_id:
            entry = next((s for s in self.manifest if s["id"] == snapshot_id), None)
        else:
            entry = self.manifest[-1]

        if not entry:
            return {"success": False, "error": f"Snapshot {snapshot_id} not found"}

        snap_dir = SNAPSHOT_DIR / entry["id"]
        if not snap_dir.exists():
            return {
                "success": False,
                "error": f"Snapshot directory missing: {snap_dir}",
            }

        restored = []
        skipped = []
        errors = []

        # Learned Data Pfade die wir NICHT überschreiben
        learned_prefixes = set()
        if preserve_learned:
            learned_prefixes = {f for f in LEARNED_FILES}

        for rel_path in entry.get("files", []):
            src = snap_dir / rel_path
            dst = PROJECT_ROOT / rel_path

            # Learned Data: NICHT überschreiben (Memories/Profile behalten!)
            if preserve_learned and rel_path in learned_prefixes:
                skipped.append(rel_path)
                continue

            # Plugins: Aus Snapshot wiederherstellen (Skills behalten!)
            # Wenn Plugin in Snapshot UND nicht mehr auf Disk → wiederherstellen
            # Wenn Plugin auf Disk existiert UND im Snapshot → NICHT überschreiben (neuere Version behalten)
            if rel_path.startswith("plugins/") and dst.exists():
                # Plugin existiert schon — aktuelle Version behalten
                skipped.append(rel_path)
                continue

            if src.exists():
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    restored.append(rel_path)
                except Exception as e:
                    errors.append(f"{rel_path}: {e}")
            else:
                errors.append(f"{rel_path}: not in snapshot")

        # Plugins die NUR im Snapshot sind (gelöschte Skills wiederherstellen)
        plugin_snap_dir = snap_dir / "plugins"
        if plugin_snap_dir.exists():
            for plugin_file in plugin_snap_dir.glob("*.py"):
                rel = f"plugins/{plugin_file.name}"
                dst = PROJECT_ROOT / rel
                if not dst.exists():
                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(plugin_file), str(dst))
                        restored.append(f"{rel} (recovered skill)")
                    except Exception as e:
                        errors.append(f"{rel}: {e}")

        result = {
            "success": len(errors) == 0,
            "snapshot_id": entry["id"],
            "restored": len(restored),
            "skipped": len(skipped),
            "errors": errors,
            "message": f"Restored {len(restored)} files, preserved {len(skipped)} learned files",
        }

        log.info(
            f"Recovery: restored {len(restored)} files from {entry['id']}, errors: {len(errors)}"
        )
        return result

    def restore_single_file(self, rel_path: str, snapshot_id: str = None) -> dict:
        """Stellt eine einzelne Datei aus dem neuesten Snapshot wieder her."""
        if not self.manifest:
            return {"success": False, "error": "No snapshots"}

        entry = (
            self.manifest[-1]
            if not snapshot_id
            else next((s for s in self.manifest if s["id"] == snapshot_id), None)
        )

        if not entry:
            return {"success": False, "error": "Snapshot not found"}

        snap_dir = SNAPSHOT_DIR / entry["id"]
        src = snap_dir / rel_path
        dst = PROJECT_ROOT / rel_path

        if not src.exists():
            return {"success": False, "error": f"{rel_path} not in snapshot"}

        try:
            shutil.copy2(str(src), str(dst))
            return {
                "success": True,
                "message": f"Restored {rel_path} from {entry['id']}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Health Check ──────────────────────────────────────────

    def health_check(self) -> dict:
        """Prüft ob alle kritischen Dateien syntaktisch korrekt sind."""
        import ast

        issues = []
        for rel_path in _get_critical_files():
            filepath = PROJECT_ROOT / rel_path
            if not filepath.exists():
                issues.append({"file": rel_path, "error": "MISSING"})
                continue

            if rel_path.endswith(".py"):
                try:
                    with open(filepath, "r") as f:
                        ast.parse(f.read())
                except SyntaxError as e:
                    issues.append({"file": rel_path, "error": f"SyntaxError: {e}"})

        return {
            "healthy": len(issues) == 0,
            "checked": len(CRITICAL_FILES),
            "issues": issues,
        }
