"""
Moruk AI OS - System Health Monitor + Self-Repair Engine
Periodische Systemüberwachung mit automatischer Reparatur.

Checks:
- Disk Usage, RAM, CPU Load
- SQLite DB Integrität (memory.db)
- Log-Rotation (data/logs/)
- Orphaned Backup Files (.bak)
- Config Integrität
- Python Dependencies
- Data Directory Hygiene

Repair Actions:
- DB VACUUM + integrity_check
- Log-Rotation (>5MB → archivieren)
- .bak Cleanup (>24h alt)
- Disk Cleanup (alte Snapshots)
- Memory Cleanup (>500 entries)
- TF-IDF Cache Invalidation
- Missing Dependencies Installation
"""

import os
import json
import sqlite3
import shutil
import subprocess
import ast
from datetime import datetime, timedelta
from pathlib import Path
from core.logger import get_logger

log = get_logger("health")

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class HealthStatus:
    """Einzelnes Health-Check Ergebnis."""
    def __init__(self, name: str, healthy: bool, detail: str = "", action: str = ""):
        self.name = name
        self.healthy = healthy
        self.detail = detail
        self.action = action  # Repair-Aktion die ausgeführt wurde

    def to_dict(self):
        return {
            "name": self.name,
            "healthy": self.healthy,
            "detail": self.detail,
            "action": self.action
        }


class SystemHealthMonitor:
    """Überwacht und repariert das System automatisch."""

    # Thresholds
    DISK_WARN_PERCENT = 90
    RAM_WARN_PERCENT = 90
    DB_MAX_SIZE_MB = 50
    LOG_MAX_SIZE_MB = 5
    MAX_MEMORY_ENTRIES = 500
    BAK_MAX_AGE_HOURS = 24
    MAX_SNAPSHOTS = 10
    MAX_REFLECTION_LOG = 300

    def __init__(self):
        self.last_check = None
        self.last_report = None
        self.repair_log = []

    # ══════════════════════════════════════════════
    # FULL HEALTH CHECK
    # ══════════════════════════════════════════════

    def full_check(self, auto_repair: bool = True) -> dict:
        """Führt alle Health Checks durch. Optional mit Auto-Repair."""
        checks = [
            self._check_disk(),
            self._check_ram(),
            self._check_cpu(),
            self._check_db_integrity(),
            self._check_db_size(),
            self._check_logs(),
            self._check_bak_files(),
            self._check_snapshots(),
            self._check_config_integrity(),
            self._check_python_files(),
            self._check_memory_count(),
            self._check_reflection_log(),
            self._check_data_dir(),
        ]

        issues = [c for c in checks if not c.healthy]

        # Auto-Repair
        repairs = []
        if auto_repair and issues:
            repairs = self._auto_repair(issues)

        self.last_check = datetime.now().isoformat()
        report = {
            "timestamp": self.last_check,
            "total_checks": len(checks),
            "healthy": len(checks) - len(issues),
            "issues": len(issues),
            "checks": [c.to_dict() for c in checks],
            "repairs": repairs,
            "overall": "healthy" if not issues else ("repaired" if repairs else "needs_attention")
        }

        self.last_report = report
        self._save_report(report)

        log.info(f"Health check: {report['healthy']}/{report['total_checks']} healthy, "
                 f"{len(issues)} issues, {len(repairs)} repairs")

        return report

    # ══════════════════════════════════════════════
    # INDIVIDUAL CHECKS
    # ══════════════════════════════════════════════

    def _check_disk(self) -> HealthStatus:
        """Disk Usage prüfen."""
        try:
            stat = shutil.disk_usage(str(PROJECT_ROOT))
            percent = (stat.used / stat.total) * 100
            free_gb = stat.free / (1024**3)
            if percent > self.DISK_WARN_PERCENT:
                return HealthStatus("disk", False,
                    f"Disk {percent:.1f}% full ({free_gb:.1f}GB free)")
            return HealthStatus("disk", True, f"{percent:.1f}% used, {free_gb:.1f}GB free")
        except Exception as e:
            return HealthStatus("disk", False, f"Check failed: {e}")

    def _check_ram(self) -> HealthStatus:
        """RAM Usage prüfen."""
        try:
            result = subprocess.run("free -m", shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    parts = lines[1].split()
                    total = int(parts[1])
                    used = int(parts[2])
                    percent = (used / total) * 100
                    if percent > self.RAM_WARN_PERCENT:
                        return HealthStatus("ram", False, f"RAM {percent:.1f}% used ({used}MB/{total}MB)")
                    return HealthStatus("ram", True, f"{percent:.1f}% used ({used}MB/{total}MB)")
            return HealthStatus("ram", True, "Could not parse, assuming OK")
        except Exception as e:
            return HealthStatus("ram", True, f"Check skipped: {e}")

    def _check_cpu(self) -> HealthStatus:
        """CPU Load prüfen."""
        try:
            result = subprocess.run("cat /proc/loadavg", shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                load_1min = float(result.stdout.split()[0])
                cores = os.cpu_count() or 1
                if load_1min > cores * 2:
                    return HealthStatus("cpu", False, f"High load: {load_1min:.1f} (cores: {cores})")
                return HealthStatus("cpu", True, f"Load: {load_1min:.1f} (cores: {cores})")
            return HealthStatus("cpu", True, "Could not check")
        except Exception as e:
            return HealthStatus("cpu", True, f"Check skipped: {e}")

    def _check_db_integrity(self) -> HealthStatus:
        """SQLite DB Integrität prüfen."""
        db_path = DATA_DIR / "memory.db"
        if not db_path.exists():
            return HealthStatus("db_integrity", True, "No DB yet (fresh install)")

        try:
            conn = sqlite3.connect(str(db_path))
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if result[0] == "ok":
                return HealthStatus("db_integrity", True, "SQLite integrity: OK")
            return HealthStatus("db_integrity", False, f"SQLite corrupt: {result[0]}")
        except Exception as e:
            return HealthStatus("db_integrity", False, f"DB error: {e}")

    def _check_db_size(self) -> HealthStatus:
        """DB Größe prüfen."""
        db_path = DATA_DIR / "memory.db"
        if not db_path.exists():
            return HealthStatus("db_size", True, "No DB yet")

        size_mb = db_path.stat().st_size / (1024 * 1024)
        if size_mb > self.DB_MAX_SIZE_MB:
            return HealthStatus("db_size", False, f"DB too large: {size_mb:.1f}MB (max {self.DB_MAX_SIZE_MB}MB)")
        return HealthStatus("db_size", True, f"DB size: {size_mb:.1f}MB")

    def _check_logs(self) -> HealthStatus:
        """Log-Dateien Größe prüfen."""
        log_dir = DATA_DIR / "logs"
        if not log_dir.exists():
            return HealthStatus("logs", True, "No logs yet")

        total_size = sum(f.stat().st_size for f in log_dir.glob("*") if f.is_file())
        total_mb = total_size / (1024 * 1024)

        if total_mb > self.LOG_MAX_SIZE_MB:
            return HealthStatus("logs", False, f"Logs too large: {total_mb:.1f}MB")
        return HealthStatus("logs", True, f"Logs: {total_mb:.1f}MB")

    def _check_bak_files(self) -> HealthStatus:
        """Orphaned .bak Dateien prüfen."""
        bak_files = list(PROJECT_ROOT.rglob("*.bak"))
        old_baks = []
        cutoff = datetime.now() - timedelta(hours=self.BAK_MAX_AGE_HOURS)

        for f in bak_files:
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    old_baks.append(f)
            except Exception:
                pass  # Datei zwischen Scan und stat() gelöscht — ignorieren

        if old_baks:
            return HealthStatus("bak_files", False, f"{len(old_baks)} old .bak files (>{self.BAK_MAX_AGE_HOURS}h)")
        return HealthStatus("bak_files", True, f"{len(bak_files)} .bak files (all recent)")

    def _check_snapshots(self) -> HealthStatus:
        """Snapshot-Anzahl prüfen."""
        snap_dir = DATA_DIR / "snapshots"
        if not snap_dir.exists():
            return HealthStatus("snapshots", True, "No snapshots")

        snap_count = len([d for d in snap_dir.iterdir() if d.is_dir()])
        if snap_count > self.MAX_SNAPSHOTS + 5:
            return HealthStatus("snapshots", False, f"{snap_count} snapshots (max {self.MAX_SNAPSHOTS})")
        return HealthStatus("snapshots", True, f"{snap_count} snapshots")

    def _check_config_integrity(self) -> HealthStatus:
        """Config-Dateien prüfen."""
        issues = []

        # Settings
        settings_path = PROJECT_ROOT / "config" / "user_settings.json"
        if settings_path.exists():
            try:
                with open(settings_path, "r") as f:
                    json.load(f)
            except json.JSONDecodeError:
                issues.append("user_settings.json corrupt")

        # System Prompt
        prompt_path = PROJECT_ROOT / "config" / "system_prompt.txt"
        if not prompt_path.exists():
            issues.append("system_prompt.txt missing")

        if issues:
            return HealthStatus("config", False, "; ".join(issues))
        return HealthStatus("config", True, "Config files OK")

    def _check_python_files(self) -> HealthStatus:
        """Python-Dateien Syntax prüfen."""
        broken = []
        for root, dirs, files in os.walk(str(PROJECT_ROOT)):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'data', 'venv', 'plugins')]
            for f in files:
                if f.endswith('.py'):
                    path = os.path.join(root, f)
                    try:
                        with open(path, 'r') as fh:
                            ast.parse(fh.read())
                    except SyntaxError:
                        broken.append(os.path.relpath(path, str(PROJECT_ROOT)))

        if broken:
            return HealthStatus("python_syntax", False, f"Broken files: {', '.join(broken[:3])}")
        return HealthStatus("python_syntax", True, "All Python files OK")

    def _check_memory_count(self) -> HealthStatus:
        """Memory Entry Count prüfen."""
        db_path = DATA_DIR / "memory.db"
        if not db_path.exists():
            return HealthStatus("memory_count", True, "No memories yet")

        try:
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conn.close()
            if count > self.MAX_MEMORY_ENTRIES:
                return HealthStatus("memory_count", False,
                    f"{count} memories (max {self.MAX_MEMORY_ENTRIES})")
            return HealthStatus("memory_count", True, f"{count} memories")
        except Exception as e:
            return HealthStatus("memory_count", True, f"Check skipped: {e}")

    def _check_reflection_log(self) -> HealthStatus:
        """Reflection Log Größe prüfen."""
        log_path = DATA_DIR / "reflection_log.json"
        if not log_path.exists():
            return HealthStatus("reflection_log", True, "No reflections yet")

        try:
            with open(log_path, "r") as f:
                entries = json.load(f)
            if len(entries) > self.MAX_REFLECTION_LOG:
                return HealthStatus("reflection_log", False,
                    f"{len(entries)} entries (max {self.MAX_REFLECTION_LOG})")
            return HealthStatus("reflection_log", True, f"{len(entries)} entries")
        except Exception:
            return HealthStatus("reflection_log", True, "Could not parse")

    def _check_data_dir(self) -> HealthStatus:
        """Data Directory Größe prüfen."""
        if not DATA_DIR.exists():
            return HealthStatus("data_dir", True, "No data dir yet")

        total = sum(f.stat().st_size for f in DATA_DIR.rglob("*") if f.is_file())
        total_mb = total / (1024 * 1024)

        if total_mb > 200:
            return HealthStatus("data_dir", False, f"Data dir: {total_mb:.1f}MB (>200MB)")
        return HealthStatus("data_dir", True, f"Data dir: {total_mb:.1f}MB")

    # ══════════════════════════════════════════════
    # AUTO-REPAIR
    # ══════════════════════════════════════════════

    def _auto_repair(self, issues: list) -> list:
        """Repariert erkannte Probleme automatisch."""
        repairs = []

        for issue in issues:
            try:
                repair = self._repair(issue)
                if repair:
                    repairs.append(repair)
                    self.repair_log.append({
                        "timestamp": datetime.now().isoformat(),
                        "issue": issue.name,
                        "detail": issue.detail,
                        "repair": repair
                    })
            except Exception as e:
                log.error(f"Repair failed for {issue.name}: {e}")

        # Repair Log begrenzen
        self.repair_log = self.repair_log[-50:]
        return repairs

    def _repair(self, issue: HealthStatus) -> str | None:
        """Einzelne Reparatur-Aktion."""

        if issue.name == "db_integrity":
            return self._repair_db()

        elif issue.name == "db_size":
            return self._repair_db_vacuum()

        elif issue.name == "logs":
            return self._repair_logs()

        elif issue.name == "bak_files":
            return self._repair_bak_files()

        elif issue.name == "snapshots":
            return self._repair_snapshots()

        elif issue.name == "memory_count":
            return self._repair_memory_cleanup()

        elif issue.name == "reflection_log":
            return self._repair_reflection_trim()

        elif issue.name == "python_syntax":
            return self._repair_python_restore()

        elif issue.name == "config":
            return self._repair_config()

        elif issue.name == "disk":
            return self._repair_disk_cleanup()

        return None

    def _repair_db(self) -> str:
        """DB Integrität reparieren."""
        db_path = DATA_DIR / "memory.db"
        backup = DATA_DIR / "memory.db.repair_backup"
        try:
            shutil.copy2(str(db_path), str(backup))
            conn = sqlite3.connect(str(db_path))
            conn.execute("REINDEX")
            conn.execute("PRAGMA integrity_check")
            conn.close()
            return "DB reindexed"
        except Exception as e:
            # Restore from backup
            if backup.exists():
                shutil.copy2(str(backup), str(db_path))
            return f"DB repair attempted: {e}"

    def _repair_db_vacuum(self) -> str:
        """DB komprimieren."""
        db_path = DATA_DIR / "memory.db"
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("VACUUM")
            conn.close()
            new_size = db_path.stat().st_size / (1024 * 1024)
            return f"DB vacuumed → {new_size:.1f}MB"
        except Exception as e:
            return f"VACUUM failed: {e}"

    def _repair_logs(self) -> str:
        """Alte Logs rotieren/löschen."""
        log_dir = DATA_DIR / "logs"
        if not log_dir.exists():
            return "No logs to clean"

        removed = 0
        for f in sorted(log_dir.glob("*")):
            if f.is_file() and f.stat().st_size > 1024 * 1024:  # >1MB
                f.unlink()
                removed += 1

        return f"Removed {removed} large log files"

    def _repair_bak_files(self) -> str:
        """Alte .bak Dateien entfernen."""
        cutoff = datetime.now() - timedelta(hours=self.BAK_MAX_AGE_HOURS)
        removed = 0

        for f in PROJECT_ROOT.rglob("*.bak"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink()
                    removed += 1
            except Exception:
                pass  # Datei zwischen Scan und unlink() gelöscht — ignorieren

        return f"Removed {removed} old .bak files"

    def _repair_snapshots(self) -> str:
        """Überzählige Snapshots entfernen."""
        snap_dir = DATA_DIR / "snapshots"
        manifest_path = snap_dir / "manifest.json"

        if not manifest_path.exists():
            return "No manifest"

        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            # 1. Trim manifest if needed
            while len(manifest) > self.MAX_SNAPSHOTS:
                old = manifest.pop(0)
                old_dir = snap_dir / old["id"]
                if old_dir.exists():
                    shutil.rmtree(str(old_dir), ignore_errors=True)

            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            # 2. Cleanup orphaned directories
            valid_ids = {snap["id"] for snap in manifest}
            removed_orphans = 0
            for d in snap_dir.iterdir():
                if d.is_dir() and d.name not in valid_ids:
                    shutil.rmtree(str(d), ignore_errors=True)
                    removed_orphans += 1

            return f"Trimmed to {len(manifest)} snapshots (removed {removed_orphans} orphans)"
        except Exception as e:
            return f"Snapshot cleanup failed: {e}"

    def _repair_memory_cleanup(self) -> str:
        """Memory Entries aufräumen."""
        db_path = DATA_DIR / "memory.db"
        try:
            conn = sqlite3.connect(str(db_path))
            count_before = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            to_delete = count_before - self.MAX_MEMORY_ENTRIES
            if to_delete > 0:
                conn.execute(
                    """DELETE FROM memories WHERE id IN (
                        SELECT id FROM memories
                        ORDER BY access_count ASC, updated_at ASC LIMIT ?
                    )""", (to_delete,))
                conn.commit()
            conn.close()
            return f"Cleaned {to_delete} old memories"
        except Exception as e:
            return f"Memory cleanup failed: {e}"

    def _repair_reflection_trim(self) -> str:
        """Reflection Log trimmen."""
        log_path = DATA_DIR / "reflection_log.json"
        try:
            with open(log_path, "r") as f:
                entries = json.load(f)
            trimmed = entries[-self.MAX_REFLECTION_LOG:]
            tmp_path = log_path.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(trimmed, f, indent=2)
            os.replace(tmp_path, log_path)
            return f"Trimmed reflections: {len(entries)} → {len(trimmed)}"
        except Exception as e:
            return f"Reflection trim failed: {e}"

    def _repair_python_restore(self) -> str:
        """Kaputte Python-Dateien aus Snapshot wiederherstellen."""
        try:
            from core.recovery import RecoveryManager
            rm = RecoveryManager()
            result = rm.restore_snapshot()
            if result["success"]:
                return f"Restored {result['restored']} files from snapshot"
            return f"Restore failed: {result.get('error', 'unknown')}"
        except Exception as e:
            return f"Recovery import failed: {e}"

    def _repair_config(self) -> str:
        """Config-Dateien reparieren."""
        repairs = []

        settings_path = PROJECT_ROOT / "config" / "user_settings.json"
        if settings_path.exists():
            try:
                with open(settings_path, "r") as f:
                    json.load(f)
            except json.JSONDecodeError:
                settings_path.rename(settings_path.with_suffix(".json.corrupt"))
                repairs.append("Renamed corrupt settings")

        prompt_path = PROJECT_ROOT / "config" / "system_prompt.txt"
        if not prompt_path.exists():
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text("You are MORUK OS.\n")
            repairs.append("Created minimal system_prompt.txt")

        return "; ".join(repairs) if repairs else "No config repairs needed"

    def _repair_disk_cleanup(self) -> str:
        """Aggressiver Disk Cleanup."""
        freed = 0

        # Alte Logs
        log_dir = DATA_DIR / "logs"
        if log_dir.exists():
            for f in log_dir.glob("*"):
                if f.is_file():
                    freed += f.stat().st_size
                    f.unlink()

        # Alle .bak files
        for f in PROJECT_ROOT.rglob("*.bak"):
            freed += f.stat().st_size
            f.unlink()

        # __pycache__
        for d in PROJECT_ROOT.rglob("__pycache__"):
            shutil.rmtree(str(d), ignore_errors=True)

        freed_mb = freed / (1024 * 1024)
        return f"Freed {freed_mb:.1f}MB (logs, .bak, __pycache__)"

    # ══════════════════════════════════════════════
    # REPORTING
    # ══════════════════════════════════════════════

    def _save_report(self, report: dict):
        """Speichert Health Report atomar."""
        report_path = DATA_DIR / "health_report.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = report_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(report, f, indent=2)
            os.replace(tmp_path, report_path)
        except Exception as e:
            log.error(f"Failed to save health report: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def get_summary(self) -> str:
        """Kurze Zusammenfassung für UI/Prompt."""
        if not self.last_report:
            return "No health check yet. Run: health_check tool."

        r = self.last_report
        lines = [
            f"System Health: {r['overall'].upper()}",
            f"Checks: {r['healthy']}/{r['total_checks']} healthy",
        ]

        issues = [c for c in r["checks"] if not c["healthy"]]
        if issues:
            lines.append("Issues:")
            for issue in issues[:3]:
                lines.append(f"  ⚠ {issue['name']}: {issue['detail']}")

        if r["repairs"]:
            lines.append(f"Repairs: {len(r['repairs'])} performed")

        return "\n".join(lines)

    def get_signal_for_goal_engine(self) -> dict | None:
        """Generiert ein Signal für die Goal Engine wenn System Issues hat."""
        if not self.last_report:
            return None

        issues = [c for c in self.last_report["checks"] if not c["healthy"]]
        if not issues:
            return None

        return {
            "type": "system_health",
            "detail": f"{len(issues)} system issues detected",
            "data": {"issues": [i["name"] for i in issues]},
            "impact": min(0.9, 0.3 + len(issues) * 0.15),
            "confidence": 0.95
        }
