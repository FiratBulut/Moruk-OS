"""
Moruk AI OS - Startup Checks
Prüft Abhängigkeiten, API-Keys, Datenintegrität beim Start.
"""

import json
import importlib
import sqlite3
import subprocess
from pathlib import Path
from core.logger import get_logger

log = get_logger("startup")

CONFIG_DIR = Path(__file__).parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent / "data"


class StartupCheck:
    """Führt alle Startup-Prüfungen durch."""

    def __init__(self):
        self.issues = []
        self.warnings = []
        self.info = []

    def run_all(self) -> dict:
        """Führt alle Checks durch und gibt Ergebnis zurück."""
        self._check_directories()
        self._check_dependencies()
        self._check_api_config()
        self._check_data_integrity()
        self._check_system_prompt()
        self._check_disk_ram()
        self._check_watchdog()

        result = {
            "ok": len(self.issues) == 0,
            "issues": self.issues,
            "warnings": self.warnings,
            "info": self.info,
        }

        for issue in self.issues:
            log.error(f"Startup Issue: {issue}")
        for warning in self.warnings:
            log.warning(f"Startup Warning: {warning}")
        for info in self.info:
            log.info(f"Startup: {info}")

        return result

    def _check_directories(self):
        """Prüft ob alle Verzeichnisse existieren."""
        dirs = [CONFIG_DIR, DATA_DIR]
        for d in dirs:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                self.info.append(f"Created directory: {d.name}")
        log_dir = DATA_DIR / "logs"
        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)

    def _check_dependencies(self):
        """Prüft ob alle Python-Dependencies installiert sind."""
        required = {"PyQt6": "PyQt6"}
        optional = {"anthropic": "anthropic", "openai": "openai"}

        for name, module in required.items():
            try:
                importlib.import_module(module)
                self.info.append(f"✓ {name}")
            except ImportError:
                self.issues.append(f"Missing required: {name} (pip install {name})")

        for name, module in optional.items():
            try:
                importlib.import_module(module)
                self.info.append(f"✓ {name}")
            except ImportError:
                self.warnings.append(f"Optional missing: {name}")

    def _check_api_config(self):
        """Prüft ob API-Key konfiguriert ist."""
        user_path = CONFIG_DIR / "user_settings.json"
        settings_path = CONFIG_DIR / "settings.json"
        api_key = ""

        if user_path.exists():
            try:
                with open(user_path, "r") as f:
                    data = json.load(f)
                    api_key = data.get("api_key", "")
                    if api_key:
                        provider = data.get("provider", "unknown")
                        self.info.append(f"✓ API Key konfiguriert ({provider})")
            except Exception:
                pass

        if not api_key and settings_path.exists():
            try:
                with open(settings_path, "r") as f:
                    data = json.load(f)
                    api_key = data.get("api_key", "")
                    if api_key:
                        provider = data.get("provider", "unknown")
                        self.info.append(f"✓ API Key konfiguriert ({provider})")
            except Exception:
                pass

        if not api_key:
            self.warnings.append("Kein API Key konfiguriert — click ⚙ to setup")

    def _check_data_integrity(self):
        """Prüft DB-Integrität."""
        db_path = DATA_DIR / "moruk.db"
        if not db_path.exists():
            self.info.append("DB wird neu erstellt")
            return
        try:
            conn = sqlite3.connect(str(db_path))
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if result and result[0] == "ok":
                self.info.append("✓ DB Integrität OK")
            else:
                self.warnings.append(f"DB Integrität: {result}")
        except Exception as e:
            self.issues.append(f"DB Fehler: {e}")

    def _check_system_prompt(self):
        """Prüft ob System-Prompt existiert."""
        prompt_path = CONFIG_DIR / "system_prompt.txt"
        if not prompt_path.exists():
            self.issues.append("system_prompt.txt fehlt!")
        else:
            size = prompt_path.stat().st_size
            self.info.append(f"✓ System Prompt ({size} bytes)")

    def _check_disk_ram(self):
        """Prüft Disk-Speicher und RAM beim Start."""
        try:
            import shutil

            total, used, free = shutil.disk_usage("/")
            free_gb = free / (1024**3)
            used_pct = (used / total) * 100
            if used_pct > 90:
                self.warnings.append(
                    f"Disk fast voll: {used_pct:.0f}% genutzt ({free_gb:.1f}GB frei)"
                )
            else:
                self.info.append(
                    f"✓ Disk: {free_gb:.0f}GB frei ({used_pct:.0f}% genutzt)"
                )
        except Exception as e:
            log.warning(f"Disk check failed: {e}")

        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            mem = {}
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(":")] = int(parts[1])
            total_mb = mem.get("MemTotal", 0) // 1024
            avail_mb = mem.get("MemAvailable", 0) // 1024
            used_pct = ((total_mb - avail_mb) / total_mb * 100) if total_mb > 0 else 0
            if used_pct > 85:
                self.warnings.append(
                    f"RAM: {used_pct:.0f}% genutzt ({avail_mb}MB verfügbar)"
                )
            else:
                self.info.append(
                    f"✓ RAM: {avail_mb}MB verfügbar ({used_pct:.0f}% genutzt)"
                )
        except Exception as e:
            log.warning(f"RAM check failed: {e}")

    def _check_watchdog(self):
        """Prüft ob es recent Crashes gab und loggt Watchdog-Status."""
        # Crash-Log prüfen
        crash_log = DATA_DIR / "logs" / "crash.log"
        if crash_log.exists():
            try:
                size = crash_log.stat().st_size
                if size > 0:
                    with open(crash_log, "r") as f:
                        lines = [l.strip() for l in f.readlines() if l.strip()]
                    if lines:
                        last = lines[-1][:120]
                        self.warnings.append(f"Letzter Crash: {last}")
                else:
                    self.info.append("✓ Watchdog: Keine Crashes")
            except Exception as e:
                log.warning(f"Crash log read failed: {e}")
                self.info.append("✓ Watchdog: OK")
        else:
            self.info.append("✓ Watchdog: Keine Crashes")

        try:
            result = subprocess.run(
                ["pgrep", "-fc", "python3 main.py"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
            if count > 1:
                self.warnings.append(f"Mehrere Moruk-Instanzen laufen ({count})")
        except Exception as e:
            log.debug(f"Process check failed: {e}")
